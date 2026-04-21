import logging
from celery import shared_task
from django.utils import timezone
from .models import ComprobanteElectronico, SRIConfig, PuntoEmision, CertificadoDigital
from .services.xml_generator import XMLGeneratorSRI
from .services.signature import SignatureServiceSRI
from zeep import Client
from zeep.transports import Transport
import requests

import base64
from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

def notificar_monitor(comprobante, mensaje=None):
    """Auxiliar para notificar al WebSocket monitor"""
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
        
    async_to_sync(channel_layer.group_send)(
        "sri_monitor",
        {
            "type": "sri_status_update",
            "comprobante_id": str(comprobante.id),
            "venta_numero": comprobante.venta.numero_factura,
            "estado": comprobante.estado,
            "clave_acceso": comprobante.clave_acceso,
            "numero_autorizacion": comprobante.numero_autorizacion,
            "mensaje": mensaje,
            "mensajes_error": comprobante.mensajes_error,
            "email_enviado": comprobante.email_enviado,
            "email_mensaje": comprobante.email_mensaje,
        }
    )

def to_list(obj):
    if obj is None: return []
    if isinstance(obj, list): return obj
    return [obj]

import zeep.helpers

def extraer_errores_sri_recursivo(data, errores):
    if isinstance(data, dict):
        if 'mensaje' in data and data['mensaje'] and isinstance(data['mensaje'], str):
            ident = data.get('identificador', '?')
            msg = data.get('mensaje', '')
            info = data.get('informacionAdicional', '')
            err = f"[{ident}] {msg}"
            if info: err += f" - Detalles: {info}"
            errores.append(err)
        for val in data.values():
            extraer_errores_sri_recursivo(val, errores)
    elif isinstance(data, list):
        for item in data:
            extraer_errores_sri_recursivo(item, errores)

def extraer_errores_sri(respuesta):
    errores = []
    try:
        dict_resp = zeep.helpers.serialize_object(respuesta)
        extraer_errores_sri_recursivo(dict_resp, errores)
    except Exception as e:
        logger.error(f"Error parseando estructura SRI con serialize: {e}")
        errores.append("Error crudo: " + str(respuesta))
        
    return " | ".join(errores) if errores else ("Rechazado sin detalle (Suele ser por firma electrónica o clave no válida para RUC). " + str(respuesta))

@shared_task
def procesar_factura_electronica(comprobante_id):
    """
    Tarea asíncrona para procesar una factura completa ante el SRI con reintentos asíncronos.
    """
    try:
        comprobante = ComprobanteElectronico.objects.get(pk=comprobante_id)
        venta = comprobante.venta
        config = SRIConfig.objects.first()
        punto_emision = comprobante.punto_emision or PuntoEmision.objects.filter(activo=True).first()
        
        if not config or not punto_emision:
            comprobante.estado = 'ERROR'
            comprobante.mensajes_error = "Configuración SRI o Punto de Emisión no encontrados."
            comprobante.save()
            return

        # 1. GENERAR XML (Solo si no existe clave de acceso aún)
        if not comprobante.clave_acceso or not comprobante.xml_firmado:
            comprobante.estado = 'GENERADO'
            comprobante.save()
            notificar_monitor(comprobante, "Generando XML...")
            
            generator = XMLGeneratorSRI(config, punto_emision)
            xml_bruto, clave_acceso = generator.generar_xml_factura(venta)
            notificar_monitor(comprobante, "XML Generado OK")
            
            # Incrementar secuencial SOLO si es la primera vez que generamos para esta factura
            if not comprobante.clave_acceso:
                from django.db.models import F
                punto_emision.ultimo_secuencial = F('ultimo_secuencial') + 1
                punto_emision.save(update_fields=['ultimo_secuencial'])
                punto_emision.refresh_from_db()

            comprobante.clave_acceso = clave_acceso
            comprobante.xml_generado = xml_bruto.decode('utf-8')
            
            # 2. FIRMAR XML
            notificar_monitor(comprobante, "Firmando XML...")
            certificado = CertificadoDigital.objects.filter(activo=True).first()
            if not certificado:
                raise ValueError("No hay certificado digital (firma) activo.")
                
            signer = SignatureServiceSRI(certificado)
            xml_firmado_bytes = signer.firmar_xml(xml_bruto)
            
            xml_firmado_str = xml_firmado_bytes.decode('utf-8') if isinstance(xml_firmado_bytes, bytes) else xml_firmado_bytes
            
            comprobante.xml_firmado = xml_firmado_str
            comprobante.estado = 'FIRMADO'
            comprobante.save()
            notificar_monitor(comprobante, "XML Firmado Exitosamente")
        else:
            xml_firmado_str = comprobante.xml_firmado
            clave_acceso = comprobante.clave_acceso

        # 3. ENVIAR AL SRI (RECEPCIÓN)
        if comprobante.estado != 'RECIBIDO' and comprobante.estado != 'AUTORIZADO':
            notificar_monitor(comprobante, "Enviando al SRI (Recepción)...")
            ambiente = config.ambiente
            url_recepcion = config.wsdl_recepcion_pruebas if ambiente == 1 else config.wsdl_recepcion_produccion
            client_recepcion = Client(url_recepcion)
            
            xml_raw_bytes = xml_firmado_str.encode('utf-8')
            
            try:
                respuesta_recepcion = client_recepcion.service.validarComprobante(xml_raw_bytes)
                notificar_monitor(comprobante, "Respuesta SRI recibida")
            except Exception as e:
                logger.error(f"Error de conexión con SRI (Recepción): {e}")
                comprobante.estado = 'ERROR'
                comprobante.mensajes_error = f"No hay conexión con SRI: {str(e)}"
                comprobante.save()
                notificar_monitor(comprobante, "Fallo red SRI")
                return False

            if respuesta_recepcion.estado == 'RECIBIDA':
                comprobante.estado = 'RECIBIDO'
                comprobante.save()
                notificar_monitor(comprobante, "Recibido por SRI")
            else:
                comprobante.estado = 'RECHAZADO'
                error_detalles = extraer_errores_sri(respuesta_recepcion)
                comprobante.mensajes_error = f"Recepción SRI ({respuesta_recepcion.estado}): {error_detalles}"
                
                comprobante.save()
                notificar_monitor(comprobante, "Rechazo SRI")
                return False

        # 4. SOLICITAR AUTORIZACIÓN
        if comprobante.estado == 'RECIBIDO':
            ambiente = config.ambiente
            url_autorizacion = config.wsdl_autorizacion_pruebas if ambiente == 1 else config.wsdl_autorizacion_produccion
            client_autorizacion = Client(url_autorizacion)
            import time
            max_intentos = 10
            delay_segundos = 5
            
            for intento_actual in range(1, max_intentos + 1):
                time.sleep(delay_segundos)
                
                try:
                    respuesta_aut = client_autorizacion.service.autorizacionComprobante(clave_acceso)
                    
                    if hasattr(respuesta_aut, 'autorizaciones') and respuesta_aut.autorizaciones and respuesta_aut.autorizaciones.autorizacion:
                        autorizacion = respuesta_aut.autorizaciones.autorizacion[0]
                        estado_sri = autorizacion.estado
                        
                        if estado_sri in ['AUTORIZADA', 'AUTORIZADO']:
                            comprobante.estado = 'AUTORIZADO'
                            comprobante.numero_autorizacion = autorizacion.numeroAutorizacion
                            comprobante.fecha_autorizacion = autorizacion.fechaAutorizacion
                            comprobante.xml_autorizado = autorizacion.comprobante
                            comprobante.mensajes_error = None
                            comprobante.save()
                            
                            # Generar RIDE
                            try:
                                from .services.ride_generator import RIDEGenerator
                                ride_gen = RIDEGenerator(comprobante)
                                pdf_buffer = ride_gen.generar_pdf()
                                filename = f"RIDE_{comprobante.clave_acceso}.pdf"
                                comprobante.pdf_ride.save(filename, ContentFile(pdf_buffer.getvalue()), save=True)
                            except Exception as e:
                                logger.error(f"Error generando RIDE: {e}")

                            # ENVIAR POR EMAIL
                            try:
                                notificar_monitor(comprobante, "Enviando email al cliente...")
                                from .services.resend_service import ResendInvoicingService
                                if ResendInvoicingService.enviar_comprobante(comprobante):
                                    notificar_monitor(comprobante, "Email enviado con éxito")
                                else:
                                    notificar_monitor(comprobante, "Fallo al enviar email (Verificar Resend)")
                            except Exception as e:
                                logger.error(f"Error al disparar envío por Resend: {e}")
                                notificar_monitor(comprobante, "Error técnico en envío de email")

                            notificar_monitor(comprobante, "¡Proceso finalizado!")
                            return True
                        
                        elif estado_sri in ['EN PROCESO', 'PENDIENTE'] or not estado_sri:
                            if intento_actual < max_intentos:
                                notificar_monitor(comprobante, f"SRI procesando ({intento_actual}/{max_intentos})")
                                continue
                            else:
                                comprobante.estado = 'ERROR'
                                comprobante.mensajes_error = "SRI indicó que sigue en proceso y nunca finalizó."
                                comprobante.save()
                                notificar_monitor(comprobante, "SRI colapsado")
                                return False
                        else:
                            error_detalles = extraer_errores_sri(respuesta_aut)
                            comprobante.estado = 'RECHAZADO'
                            comprobante.mensajes_error = f"SRI {estado_sri}: {error_detalles}"
                            comprobante.save()
                            notificar_monitor(comprobante, "SRI Rechazado")
                            return False
                    else:
                        if intento_actual < max_intentos:
                            notificar_monitor(comprobante, f"Esperando SRI ({intento_actual}/{max_intentos})")
                            continue
                        else:
                            comprobante.estado = 'RECHAZADO'
                            comprobante.mensajes_error = "Rechazo Silencioso del SRI."
                            comprobante.save()
                            notificar_monitor(comprobante, "SRI Rechazo Silencioso")
                            return False

                except Exception as e:
                    logger.error(f"Falla red autorización: {e}")
                    if intento_actual < max_intentos:
                        continue
                    else:
                        comprobante.estado = 'ERROR'
                        comprobante.mensajes_error = "Error red SRI."
                        comprobante.save()
                        return False

    except Exception as exc:
        if 'comprobante' in locals():
            comprobante.estado = 'ERROR'
            comprobante.mensajes_error = str(exc)
            comprobante.save()
            notificar_monitor(comprobante, f"Error: {exc}")
        return False

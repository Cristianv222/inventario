# apps/electronic_invoicing/services/resend_service.py

import resend
import os
import logging
import base64
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

class ResendInvoicingService:
    """
    Servicio para el envío de comprobantes electrónicos a través de la API de Resend
    Solución para servidores con puertos SMTP bloqueados.
    """
    
    @staticmethod
    def enviar_comprobante(comprobante):
        """
        Envía el XML y PDF de un comprobante autorizado al correo del cliente.
        """
        # Configurar API Key
        api_key = getattr(settings, 'RESEND_API_KEY', os.getenv('RESEND_API_KEY'))
        if not api_key:
            logger.error("API Key no configurada en settings o env")
            return False
            
        resend.api_key = api_key
        
        venta = comprobante.venta
        cliente = venta.cliente
        
        if not cliente or not cliente.email:
            logger.warning(f"Venta {venta.numero_factura} no tiene un cliente con email válido")
            return False

        attachments = []
        
        # 1. Adjuntar PDF RIDE
        if comprobante.pdf_ride:
            try:
                pdf_path = comprobante.pdf_ride.path
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        # Resend SDK espera el contenido codificado en base64
                        pdf_bytes = f.read()
                        attachments.append({
                            "filename": f"Factura_{venta.numero_factura}.pdf",
                            "content": base64.b64encode(pdf_bytes).decode('utf-8')
                        })
                else:
                    logger.error(f"El archivo PDF no existe físicamente: {pdf_path}")
            except Exception as e:
                logger.error(f"Error al leer PDF para adjunto: {str(e)}")

        # 2. Adjuntar XML Autorizado
        if comprobante.xml_autorizado:
            try:
                # Convertir el string XML a bytes y luego a base64
                xml_bytes = comprobante.xml_autorizado.encode('utf-8')
                attachments.append({
                    "filename": f"Factura_{venta.numero_factura}.xml",
                    "content": base64.b64encode(xml_bytes).decode('utf-8')
                })
            except Exception as e:
                logger.error(f"Error al codificar XML para adjunto: {str(e)}")

        # 3. Preparar y enviar el correo
        try:
            # Usar remitente desde settings
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', "david.vasquez@vp-motos.com")
            
            # Usar API Key desde settings preferiblemente
            resend.api_key = api_key

            # Renderizar HTML interactivo
            public_base_url = getattr(settings, 'PUBLIC_BASE_URL', os.getenv('PUBLIC_BASE_URL', 'http://localhost:8001'))
            context = {
                'public_base_url': public_base_url.rstrip('/'),
                'cliente_nombre': cliente.get_nombre_completo(),
                'numero_factura': venta.numero_factura,
                'fecha_emision': venta.fecha_hora.strftime('%d/%m/%Y %H:%M'),
                'total': venta.total,
                'year': timezone.now().year
            }
            html_content = render_to_string('electronic_invoicing/emails/factura_electronica.html', context)

            params = {
                "from": from_email,
                "to": [cliente.email],
                "subject": f"Tu Factura Electrónica VPMotos - {venta.numero_factura}",
                "html": html_content,
                "attachments": attachments
            }
            
            logger.info(f"Intentando enviar email a {cliente.email}...")
            email_response = resend.Emails.send(params)
            logger.info(f"Email enviado exitosamente: {email_response}")
            
            # Guardar éxito en base de datos
            comprobante.email_enviado = True
            comprobante.email_mensaje = f"Enviado (ID: {email_response.get('id', '?')})"
            comprobante.save()
            
            return True
            
        except Exception as e:
            logger.error(f"Error crítico al enviar correo: {str(e)}")
            
            # Guardar error en base de datos para visibilidad
            comprobante.email_enviado = False
            comprobante.email_mensaje = str(e)
            comprobante.save()
            
            return False

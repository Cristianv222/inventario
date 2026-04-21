from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from .models import ComprobanteElectronico, SRIConfig, PuntoEmision, CertificadoDigital
from .services.ride_generator import RIDEGenerator
from django.core.files.base import ContentFile
import logging
from lxml import etree

logger = logging.getLogger(__name__)

def _prettify_xml(xml_str: str) -> str:
    """Formatea XML con indentación legible."""
    try:
        root = etree.fromstring(xml_str.encode('utf-8'))
        return etree.tostring(root, pretty_print=True, encoding='unicode', xml_declaration=False)
    except Exception:
        return xml_str

@login_required
def descargar_xml_sri(request, pk):
    """Sirve el XML del comprobante como descarga (prioriza autorizado > firmado > generado)"""
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    xml_content = comprobante.xml_autorizado or comprobante.xml_firmado or comprobante.xml_generado
    if not xml_content:
        raise Http404("No hay contenido XML disponible para este comprobante.")
    response = HttpResponse(xml_content, content_type='application/xml')
    filename = f"{comprobante.clave_acceso}.xml" if comprobante.clave_acceso else f"comprobante_{comprobante.venta.numero_venta}.xml"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def ver_xml_sri(request, pk):
    """Muestra el XML del comprobante en el navegador (inline, legible)"""
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    # Prioridad: Autorizado > Firmado > Generado
    xml_label = 'AUTORIZADO'
    xml_content = comprobante.xml_autorizado
    if not xml_content:
        xml_label = 'FIRMADO'
        xml_content = comprobante.xml_firmado
    if not xml_content:
        xml_label = 'GENERADO (sin firma)'
        xml_content = comprobante.xml_generado
    
    if not xml_content:
        return HttpResponse(
            "<h3 style='font-family:sans-serif'>❌ No hay XML disponible aún para este comprobante.</h3>",
            status=404
        )
    
    pretty_xml = _prettify_xml(xml_content)
    
    return render(request, 'electronic_invoicing/visor_xml.html', {
        'comprobante': comprobante,
        'xml_content': pretty_xml,
        'xml_label': xml_label,
    })

@login_required
def api_xml_sri(request, pk):
    """API JSON que retorna el XML y metadata del comprobante para uso AJAX"""
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    xml_label = 'AUTORIZADO'
    xml_content = comprobante.xml_autorizado
    if not xml_content:
        xml_label = 'FIRMADO'
        xml_content = comprobante.xml_firmado
    if not xml_content:
        xml_label = 'GENERADO (sin firma)'
        xml_content = comprobante.xml_generado

    return JsonResponse({
        'tiene_xml': bool(xml_content),
        'xml_label': xml_label,
        'xml_content': _prettify_xml(xml_content) if xml_content else None,
        'estado': comprobante.estado,
        'clave_acceso': comprobante.clave_acceso,
        'mensajes_error': comprobante.mensajes_error,
    })

@login_required
def descargar_pdf_sri(request, pk):
    """Sirve el PDF/RIDE del comprobante (lo genera si no existe)"""
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    if comprobante.pdf_ride:
        try:
            response = HttpResponse(comprobante.pdf_ride.read(), content_type='application/pdf')
            filename = comprobante.pdf_ride.name.split('/')[-1]
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        except Exception as e:
            logger.warning(f"Archivo PDF no encontrado en disco para {comprobante.id}, regenerando... Error: {e}")
    try:
        generator = RIDEGenerator(comprobante)
        pdf_buffer = generator.generar_pdf()
        if comprobante.estado == 'AUTORIZADO' and not comprobante.pdf_ride:
            filename = f"RIDE_{comprobante.clave_acceso or comprobante.venta.numero_venta}.pdf"
            comprobante.pdf_ride.save(filename, ContentFile(pdf_buffer.getvalue()), save=True)
            pdf_buffer.seek(0)
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f"RIDE_{comprobante.clave_acceso or comprobante.venta.numero_venta}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception as e:
        logger.error(f"Error crítico generando PDF para {comprobante.id}: {e}")
        return HttpResponse(f"Error creando el documento RIDE: {str(e)}", status=500)

@login_required
def actualizar_secuencial_sri(request):
    """API endpoint to update the next sequential number for a Punto de Emision"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            punto_id = data.get('id')
            nuevo_valor = int(data.get('ultimo_secuencial'))
            
            from .models import PuntoEmision
            punto = get_object_or_404(PuntoEmision, pk=punto_id)
            
            # El SRI usa 9 dígitos.
            if 0 <= nuevo_valor <= 999999999:
                punto.ultimo_secuencial = nuevo_valor
                punto.save()
                return JsonResponse({'status': 'success', 'message': f'Secuencial actualizado a {nuevo_valor:09d}'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Valor fuera de rango (0-999,999,999)'}, status=400)
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return JsonResponse({'status': 'error', 'message': f'Datos inválidos: {str(e)}'}, status=400)
    
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@login_required
def gestion_facturacion(request):
    """Panel principal de gestión y monitoreo SRI"""
    from django.utils import timezone
    from django.db.models import Count
    from django.db import models
    
    hoy = timezone.now().date()
    config = SRIConfig.objects.first()
    puntos = PuntoEmision.objects.all()
    comprobantes_recientes = ComprobanteElectronico.objects.select_related('venta', 'venta__cliente').order_by('-fecha_registro')[:50]
    certificados = CertificadoDigital.objects.all()
    
    # Estadísticas del día
    stats_dia = ComprobanteElectronico.objects.filter(fecha_registro__date=hoy).aggregate(
        autorizados=Count('id', filter=models.Q(estado='AUTORIZADO')),
        rechazados=Count('id', filter=models.Q(estado='RECHAZADO')),
        errores=Count('id', filter=models.Q(estado='ERROR')),
        recibidos=Count('id', filter=models.Q(estado='RECIBIDO')),
    )
    
    return render(request, 'electronic_invoicing/gestion_facturacion.html', {
        'config': config,
        'puntos': puntos,
        'comprobantes': comprobantes_recientes,
        'certificados': certificados,
        'stats': stats_dia,
    })

@login_required
def guardar_config_sri(request):
    """API para guardar configuración general del SRI"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            config, created = SRIConfig.objects.get_or_create(id=1)
            
            config.razon_social = data.get('razon_social', config.razon_social)
            config.nombre_comercial = data.get('nombre_comercial', config.nombre_comercial)
            config.ruc = data.get('ruc', config.ruc)
            config.direccion_matriz = data.get('direccion_matriz', config.direccion_matriz)
            config.contribuyente_especial = data.get('contribuyente_especial', config.contribuyente_especial)
            config.obligado_contabilidad = data.get('obligado_contabilidad', False)
            config.agente_retencion = data.get('agente_retencion', config.agente_retencion)
            config.regimen_rimpe = data.get('regimen_rimpe', False)
            config.ambiente = int(data.get('ambiente', 1))
            
            config.save()
            return JsonResponse({'status': 'success', 'message': 'Configuración actualizada'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@login_required
def subir_certificado_sri(request):
    """API para subir el certificado digital .p12 y su clave"""
    if request.method == 'POST':
        archivo = request.FILES.get('archivo_p12')
        password = request.POST.get('password')
        
        if not archivo or not password:
            return JsonResponse({'status': 'error', 'message': 'Falta el archivo o la contraseña'}, status=400)
            
        if not archivo.name.endswith('.p12'):
            return JsonResponse({'status': 'error', 'message': 'El certificado debe tener formato .p12'}, status=400)
            
        try:
            # Desactivar todos los certificados actuales
            from .models import CertificadoDigital
            CertificadoDigital.objects.update(activo=False)
            
            # Crear y guardar el nuevo certificado
            from .services.certificate_reader import CertificateReaderSRI
            
            # Leer contenido para extracción de metadata
            p12_content = archivo.read()
            archivo.seek(0)
            
            metadata = CertificateReaderSRI.extraer_metadata(p12_content, password)
            
            cert = CertificadoDigital()
            cert.archivo = archivo
            cert.set_password(password)
            
            # Guardar metadata extraída
            cert.nombre_titular = metadata.get('nombre_titular')
            cert.ruc_titular = metadata.get('ruc_titular')
            cert.emisor = metadata.get('emisor')
            cert.fecha_vencimiento = metadata.get('fecha_vencimiento')
            
            cert.activo = True
            cert.save()
            
            return JsonResponse({
                'status': 'success', 
                'message': f'Certificado de {cert.nombre_titular} subido y activado correctamente. Expira el {cert.fecha_vencimiento}.'
            })
        except Exception as e:
            logger.error(f"Error subiendo certificado: {e}")
            return JsonResponse({'status': 'error', 'message': f'Error al procesar el certificado: {str(e)}'}, status=400)
            
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@login_required
def crear_punto_emision(request):
    """API para crear un nuevo punto de emisión"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            est = str(data.get('establecimiento', '')).zfill(3)
            punto = str(data.get('punto_emision', '')).zfill(3)
            dir_est = data.get('direccion_establecimiento', '')
            seq = int(data.get('ultimo_secuencial', 0))
            
            if not est or not punto or not dir_est:
                return JsonResponse({'status': 'error', 'message': 'Faltan campos obligatorios'}, status=400)
            
            # Verificar si ya existe
            if PuntoEmision.objects.filter(establecimiento=est, punto_emision=punto).exists():
                return JsonResponse({'status': 'error', 'message': f'El punto {est}-{punto} ya existe'}, status=400)

            # Si es el primero, lo ponemos activo
            count = PuntoEmision.objects.count()
            
            p = PuntoEmision.objects.create(
                establecimiento=est,
                punto_emision=punto,
                direccion_establecimiento=dir_est,
                ultimo_secuencial=seq,
                activo=(count == 0)
            )
            
            return JsonResponse({'status': 'success', 'message': f'Punto de emisión {est}-{punto} creado correctamente'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@login_required
def toggle_punto_emision(request):
    """API para activar/desactivar un punto de emisión"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            punto_id = data.get('id')
            p = get_object_or_404(PuntoEmision, pk=punto_id)
            
            if not p.activo:
                # Solo permitimos un punto activo a la vez para evitar confusiones de secuenciales
                PuntoEmision.objects.exclude(id=p.id).update(activo=False)
                p.activo = True
            else:
                p.activo = False
            
            p.save()
            estado_str = "Activado y se usará para facturación" if p.activo else "Desactivado"
            return JsonResponse({'status': 'success', 'message': f'Punto {p.establecimiento}-{p.punto_emision} {estado_str}'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)
@login_required
def reintentar_factura(request, pk):
    """Reinicia el proceso de facturación para un comprobante fallido o estancado."""
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    
    # Solo permitimos reintentar si no está autorizado
    if comprobante.estado == 'AUTORIZADO':
        return JsonResponse({'status': 'error', 'message': 'Este comprobante ya está AUTORIZADO'}, status=400)
    
    try:
        # Resetear estado y errores
        from .tasks import procesar_factura_electronica, notificar_monitor
        
        comprobante.estado = 'GENERADO'
        comprobante.mensajes_error = "Reintento manual iniciado..."
        comprobante.save()
        
        # Notificar al monitor
        notificar_monitor(comprobante, "Reintento iniciado")
        
        # Disparar tarea nuevamente (Usar ID del comprobante, no de la venta)
        procesar_factura_electronica.delay(comprobante.id)
        
        return JsonResponse({'status': 'success', 'message': 'Factura enviada a procesamiento nuevamente'})
    except Exception as e:
        logger.error(f"Error al reintentar factura {pk}: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def editar_punto_emision(request):
    """API para editar un punto de emisión existente"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            punto_id = data.get('id')
            p = get_object_or_404(PuntoEmision, pk=punto_id)
            
            p.establecimiento = str(data.get('establecimiento', p.establecimiento or '')).zfill(3)
            p.punto_emision = str(data.get('punto_emision', p.punto_emision or '')).zfill(3)
            p.direccion_establecimiento = data.get('direccion_establecimiento', p.direccion_establecimiento)
            p.ultimo_secuencial = int(data.get('ultimo_secuencial', p.ultimo_secuencial))
            
            if not p.establecimiento or not p.punto_emision:
                return JsonResponse({'status': 'error', 'message': 'Establecimiento y Punto son obligatorios'}, status=400)
                
            p.save()
            return JsonResponse({'status': 'success', 'message': f'Punto {p.establecimiento}-{p.punto_emision} actualizado correctamente'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

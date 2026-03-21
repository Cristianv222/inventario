from django.template.loader import get_template
from django.http import HttpResponse
# import weasyprint  # ← COMENTADO PARA EVITAR ERROR AL INICIAR
from io import BytesIO
from django.conf import settings
import os
import tempfile
import subprocess
import logging
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)

class FacturaService:
    @staticmethod
    def generar_pdf(venta):
        """Genera un PDF de factura para la venta dada"""
        
        # IMPORT LOCAL - Solo se importa cuando se necesita
        import weasyprint
        
        # Cargar la plantilla
        template = get_template('ventas/facturas/factura_pdf.html')
        
        # Preparar el contexto para la plantilla
        context = {
            'venta': venta,
            'cliente': venta.cliente,
            'detalles': venta.detalleventa_set.all(),
            'fecha': venta.fecha_hora,
            'numero': venta.numero_factura,
            'subtotal': venta.subtotal,
            'iva': venta.iva,
            'descuento': venta.descuento,
            'total': venta.total,
            'es_consumidor_final': venta.cliente is None or venta.cliente.identificacion == '9999999999',
            'empresa': settings.VPMOTOS_SETTINGS,
            'fecha_actual': timezone.now(),
        }
        
        # Renderizar la plantilla HTML
        html = template.render(context)
        
        # Crear archivo PDF
        pdf_file = BytesIO()
        
        try:
            weasyprint.HTML(string=html).write_pdf(
                pdf_file,
                stylesheets=[
                    weasyprint.CSS(filename=os.path.join(settings.BASE_DIR, 'static/css/facturas/factura.css'))
                ]
            )
        except FileNotFoundError:
            # Si no encuentra el CSS, generar sin estilos
            logger.warning("Archivo CSS de factura no encontrado, generando sin estilos")
            weasyprint.HTML(string=html).write_pdf(pdf_file)
        except Exception as e:
            logger.error(f"Error generando PDF: {e}")
            raise
        
        pdf_file.seek(0)
        return pdf_file
    
    @staticmethod
    def imprimir_factura(venta, impresora=None):
        """Imprime una factura en la impresora seleccionada usando hardware_integration"""
        try:
            from hardware_integration.printers.ticket_printer import TicketPrinter
            from hardware_integration.models import Impresora
            
            if not impresora:
                impresora = Impresora.objects.filter(es_principal_tickets=True, estado='ACTIVA').first() or Impresora.objects.filter(tipo_impresora='TICKET', estado='ACTIVA').order_by('-es_principal_tickets').first()
            elif isinstance(impresora, str):
                impresora = Impresora.objects.get(pk=impresora)

            if not impresora:
                return False, "No se encontró una impresora de tickets activa"

            success = TicketPrinter.imprimir_ticket(venta, impresora)
            
            if success:
                return True, "Factura enviada a impresión correctamente"
            else:
                return False, "Error al imprimir la factura con el agente local"
            
        except Exception as e:
            logger.exception("Error al imprimir factura")
            return False, str(e)

    @staticmethod
    def generar_ticket(venta):
        """Genera un ticket en formato PDF (versión simplificada de factura)"""
        
        # IMPORT LOCAL - Solo se importa cuando se necesita
        import weasyprint
        
        # Cargar la plantilla
        template = get_template('ventas/facturas/ticket_pdf.html')
        
        # Preparar el contexto para la plantilla
        context = {
            'venta': venta,
            'cliente': venta.cliente,
            'detalles': venta.detalleventa_set.all(),
            'fecha': venta.fecha_hora,
            'empresa': settings.VPMOTOS_SETTINGS,
        }
        
        # Renderizar la plantilla HTML
        html = template.render(context)
        
        # Crear archivo PDF
        pdf_file = BytesIO()
        
        try:
            weasyprint.HTML(string=html).write_pdf(
                pdf_file,
                stylesheets=[
                    weasyprint.CSS(filename=os.path.join(settings.BASE_DIR, 'static/css/facturas/ticket.css'))
                ]
            )
        except FileNotFoundError:
            # Si no encuentra el CSS, generar sin estilos
            logger.warning("Archivo CSS de ticket no encontrado, generando sin estilos")
            weasyprint.HTML(string=html).write_pdf(pdf_file)
        except Exception as e:
            logger.error(f"Error generando ticket PDF: {e}")
            raise
        
        pdf_file.seek(0)
        return pdf_file
    
    @staticmethod
    def imprimir_ticket(venta, impresora=None):
        """Imprime un ticket en la impresora seleccionada usando hardware_integration"""
        try:
            from hardware_integration.printers.ticket_printer import TicketPrinter
            from hardware_integration.models import Impresora
            
            if not impresora:
                impresora = Impresora.objects.filter(es_principal_tickets=True, estado='ACTIVA').first() or Impresora.objects.filter(tipo_impresora='TICKET', estado='ACTIVA').order_by('-es_principal_tickets').first()
            elif isinstance(impresora, str):
                impresora = Impresora.objects.get(pk=impresora)

            if not impresora:
                return False, "No se encontró una impresora de tickets activa"

            success = TicketPrinter.imprimir_ticket(venta, impresora)
            
            if success:
                return True, "Ticket enviado a impresión correctamente"
            else:
                return False, "Error al imprimir el ticket con el agente local"
            
        except Exception as e:
            logger.exception("Error al imprimir ticket")
            return False, str(e)
    
    @staticmethod
    def test_weasyprint():
        """Método para testear si WeasyPrint funciona correctamente"""
        try:
            import weasyprint
            # Test simple
            html = weasyprint.HTML(string='<html><body><h1>Test WeasyPrint</h1></body></html>')
            pdf_bytes = html.write_pdf()
            return True, "WeasyPrint funciona correctamente"
        except ImportError as e:
            return False, f"Error importando WeasyPrint: {str(e)}"
        except OSError as e:
            return False, f"Error de librerías del sistema: {str(e)}"
        except Exception as e:
            return False, f"Error en WeasyPrint: {str(e)}"
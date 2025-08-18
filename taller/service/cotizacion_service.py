from decimal import Decimal
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class CotizacionService:
    """Servicio para generar cotizaciones del taller"""
    
    @staticmethod
    def generar_cotizacion_pdf(orden):
        """Genera un PDF de cotización para una orden de trabajo"""
        try:
            # Preparar datos para la cotización
            cotizacion_data = orden.generar_cotizacion_data()
            
            # Renderizar template HTML
            html_content = render_to_string('taller/cotizacion_pdf.html', cotizacion_data)
            
            # Generar PDF (necesitarás instalar weasyprint o similar)
            try:
                from weasyprint import HTML, CSS
                from weasyprint.fonts import FontConfiguration
                
                font_config = FontConfiguration()
                
                # CSS para el PDF
                css = CSS(string='''
                    @page {
                        size: A4;
                        margin: 1cm;
                        @top-center {
                            content: "COTIZACIÓN - VPMOTOS";
                            font-size: 12px;
                            color: #666;
                        }
                        @bottom-center {
                            content: "Página " counter(page) " de " counter(pages);
                            font-size: 10px;
                            color: #666;
                        }
                    }
                    
                    body {
                        font-family: Arial, sans-serif;
                        font-size: 12px;
                        line-height: 1.4;
                        color: #333;
                    }
                    
                    .header {
                        text-align: center;
                        margin-bottom: 30px;
                        border-bottom: 2px solid #4361ee;
                        padding-bottom: 20px;
                    }
                    
                    .company-name {
                        font-size: 24px;
                        font-weight: bold;
                        color: #4361ee;
                        margin-bottom: 5px;
                    }
                    
                    .cotizacion-title {
                        font-size: 20px;
                        font-weight: bold;
                        margin: 20px 0;
                        color: #333;
                    }
                    
                    .info-section {
                        margin-bottom: 20px;
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                    }
                    
                    .info-row {
                        display: flex;
                        justify-content: space-between;
                        margin-bottom: 8px;
                    }
                    
                    .info-label {
                        font-weight: bold;
                        color: #666;
                    }
                    
                    .services-table, .parts-table {
                        width: 100%;
                        border-collapse: collapse;
                        margin-bottom: 20px;
                    }
                    
                    .services-table th, .services-table td,
                    .parts-table th, .parts-table td {
                        border: 1px solid #ddd;
                        padding: 8px;
                        text-align: left;
                    }
                    
                    .services-table th, .parts-table th {
                        background-color: #4361ee;
                        color: white;
                        font-weight: bold;
                    }
                    
                    .text-right {
                        text-align: right;
                    }
                    
                    .totals-section {
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                        margin-top: 20px;
                    }
                    
                    .total-row {
                        display: flex;
                        justify-content: space-between;
                        margin-bottom: 5px;
                    }
                    
                    .total-final {
                        font-size: 16px;
                        font-weight: bold;
                        color: #4361ee;
                        border-top: 2px solid #4361ee;
                        padding-top: 10px;
                        margin-top: 10px;
                    }
                    
                    .terms {
                        margin-top: 30px;
                        font-size: 10px;
                        color: #666;
                        border-top: 1px solid #ddd;
                        padding-top: 15px;
                    }
                    
                    .no-iva-notice {
                        background: #fff3cd;
                        border: 1px solid #ffeaa7;
                        padding: 10px;
                        border-radius: 5px;
                        margin: 15px 0;
                        font-size: 11px;
                    }
                ''', font_config=font_config)
                
                # Generar PDF
                html_doc = HTML(string=html_content)
                pdf = html_doc.write_pdf(stylesheets=[css], font_config=font_config)
                
                return pdf
                
            except ImportError:
                # Fallback si no está instalado weasyprint
                logger.warning("WeasyPrint no está instalado. Usando reportlab como fallback.")
                return CotizacionService._generar_pdf_reportlab(cotizacion_data)
            
        except Exception as e:
            logger.error(f"Error generando cotización PDF: {str(e)}")
            raise
    
    @staticmethod
    def _generar_pdf_reportlab(cotizacion_data):
        """Genera PDF usando ReportLab como fallback"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            from io import BytesIO
            
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Título
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=20,
                textColor=colors.HexColor('#4361ee'),
                alignment=1  # Center
            )
            
            story.append(Paragraph("VPMOTOS", title_style))
            story.append(Paragraph("COTIZACIÓN DE SERVICIOS", styles['Heading2']))
            story.append(Spacer(1, 20))
            
            # Información de la orden
            orden = cotizacion_data['orden']
            info_data = [
                ['Cotización No.:', f"COT-{orden.numero_orden}"],
                ['Fecha:', timezone.now().strftime('%d/%m/%Y')],
                ['Válida hasta:', (timezone.now() + timedelta(days=15)).strftime('%d/%m/%Y')],
                ['Cliente:', orden.cliente.get_nombre_completo()],
                ['Motocicleta:', f"{orden.moto.marca} {orden.moto.modelo} - {orden.moto.placa}"],
            ]
            
            info_table = Table(info_data, colWidths=[2*inch, 4*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fa')),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(info_table)
            story.append(Spacer(1, 20))
            
            # Servicios
            if cotizacion_data['servicios']:
                story.append(Paragraph("SERVICIOS A REALIZAR", styles['Heading3']))
                
                servicios_data = [['Servicio', 'Tiempo (h)', 'Precio']]
                for servicio in cotizacion_data['servicios']:
                    servicios_data.append([
                        servicio.tipo_servicio.nombre,
                        str(servicio.tiempo_estimado),
                        f"${servicio.precio_total:.2f}"
                    ])
                
                servicios_table = Table(servicios_data, colWidths=[3*inch, 1*inch, 1.5*inch])
                servicios_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4361ee')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                story.append(servicios_table)
                story.append(Spacer(1, 15))
            
            # Repuestos
            if cotizacion_data['repuestos']:
                story.append(Paragraph("REPUESTOS NECESARIOS", styles['Heading3']))
                
                repuestos_data = [['Repuesto', 'Cantidad', 'Precio Unit.', 'Subtotal']]
                for repuesto in cotizacion_data['repuestos']:
                    repuestos_data.append([
                        repuesto.producto.nombre,
                        str(repuesto.cantidad),
                        f"${repuesto.precio_unitario:.2f}",
                        f"${repuesto.subtotal:.2f}"
                    ])
                
                repuestos_table = Table(repuestos_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1*inch])
                repuestos_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4361ee')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                story.append(repuestos_table)
                story.append(Spacer(1, 15))
            
            # Totales
            totales = cotizacion_data['totales']
            totales_data = [
                ['Mano de Obra (Sin IVA):', f"${totales['mano_obra']:.2f}"],
                ['Repuestos:', f"${totales['repuestos']:.2f}"],
                ['IVA (12% solo repuestos):', f"${totales['iva']:.2f}"],
                ['TOTAL:', f"${totales['total']:.2f}"]
            ]
            
            totales_table = Table(totales_data, colWidths=[3*inch, 2*inch])
            totales_table.setStyle(TableStyle([
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#4361ee')),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTNAME', (0, 0), (0, -2), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(totales_table)
            story.append(Spacer(1, 20))
            
            # Términos y condiciones
            terms_text = """
            TÉRMINOS Y CONDICIONES:
            • Esta cotización es válida por 15 días a partir de la fecha de emisión.
            • Los precios incluyen mano de obra e IVA donde corresponde.
            • Los servicios de mano de obra están exentos de IVA.
            • Los repuestos tienen IVA del 12% incluido.
            • Se requiere autorización del cliente antes de proceder con reparaciones adicionales.
            • El tiempo estimado puede variar según las condiciones encontradas durante el servicio.
            """
            
            story.append(Paragraph(terms_text, styles['Normal']))
            
            # Generar PDF
            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            
            return pdf
            
        except ImportError:
            logger.error("ReportLab no está instalado. No se puede generar PDF.")
            raise Exception("No hay librerías PDF disponibles. Instale weasyprint o reportlab.")
    
    @staticmethod
    def enviar_cotizacion_por_email(orden, email_destino):
        """Envía la cotización por email al cliente"""
        try:
            from django.core.mail import EmailMessage
            from django.conf import settings
            
            # Generar PDF
            pdf = CotizacionService.generar_cotizacion_pdf(orden)
            
            # Preparar email
            subject = f"Cotización de Servicios - {orden.numero_orden}"
            message = f"""
            Estimado/a {orden.cliente.get_nombre_completo()},
            
            Adjunto encontrará la cotización para los servicios de su motocicleta {orden.moto.marca} {orden.moto.modelo}.
            
            Esta cotización es válida por 15 días. Si tiene alguna consulta, no dude en contactarnos.
            
            Saludos cordiales,
            VPMOTOS
            """
            
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email_destino]
            )
            
            # Adjuntar PDF
            email.attach(f"cotizacion_{orden.numero_orden}.pdf", pdf, 'application/pdf')
            
            # Enviar
            email.send()
            
            return True, "Cotización enviada correctamente"
            
        except Exception as e:
            logger.error(f"Error enviando cotización por email: {str(e)}")
            return False, f"Error enviando email: {str(e)}"
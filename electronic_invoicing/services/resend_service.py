# apps/electronic_invoicing/services/resend_service.py

import resend
import os
import logging
from django.conf import settings

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
            logger.warning(f"Venta {venta.numero_venta} no tiene un cliente con email válido")
            return False

        attachments = []
        
        # 1. Adjuntar PDF RIDE
        if comprobante.pdf_ride:
            try:
                pdf_path = comprobante.pdf_ride.path
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        # Resend SDK espera el contenido como una lista de enteros (bytes)
                        pdf_bytes = f.read()
                        attachments.append({
                            "filename": f"Factura_{venta.numero_venta}.pdf",
                            "content": list(pdf_bytes)
                        })
                else:
                    logger.error(f"El archivo PDF no existe físicamente: {pdf_path}")
            except Exception as e:
                logger.error(f"Error al leer PDF para adjunto: {str(e)}")

        # 2. Adjuntar XML Autorizado
        if comprobante.xml_autorizado:
            try:
                # Convertir el string XML a bytes y luego a lista de enteros
                xml_bytes = comprobante.xml_autorizado.encode('utf-8')
                attachments.append({
                    "filename": f"Factura_{venta.numero_venta}.xml",
                    "content": list(xml_bytes)
                })
            except Exception as e:
                logger.error(f"Error al codificar XML para adjunto: {str(e)}")

        # 3. Preparar y enviar el correo
        try:
            # Forzamos onboarding@resend.dev para asegurar compatibilidad con cuenta gratuita/sin dominio
            from_email = "onboarding@resend.dev"
            
            # Usar API Key desde settings preferiblemente
            resend.api_key = getattr(settings, 'RESEND_API_KEY', os.getenv('RESEND_API_KEY'))

            params = {
                "from": from_email,
                "to": [cliente.email],
                "subject": f"Comprobante Electrónico: {venta.numero_venta}",
                "html": f"""
                <div style="font-family: sans-serif; color: #333; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee;">
                    <h2 style="color: #1A237E;">Comprobante Electrónico Autorizado</h2>
                    <p>Estimado/a <strong>{cliente.nombre_completo()}</strong>,</p>
                    <p>Le informamos que se ha generado un nuevo comprobante electrónico por su compra.</p>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    <table style="width: 100%;">
                        <tr><td><strong>Nro. Comprobante:</strong></td><td>{venta.numero_venta}</td></tr>
                        <tr><td><strong>Fecha:</strong></td><td>{venta.fecha_venta.strftime('%d/%m/%Y')}</td></tr>
                        <tr><td><strong>Total:</strong></td><td>${venta.total}</td></tr>
                    </table>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    <p>Adjunto a este correo encontrará el archivo <strong>XML</strong> y la representación impresa <strong>(PDF)</strong> de su factura.</p>
                    <p style="font-size: 12px; color: #888;">Este es un correo automático, por favor no responda.</p>
                </div>
                """,
                "attachments": attachments
            }
            
            logger.info(f"Intentando enviar email a {cliente.email}...")
            email_response = resend.Emails.send(params)
            logger.info(f"Email enviado exitosamente: {email_response}")
            return True
            
        except Exception as e:
            logger.error(f"Error crítico al enviar correo: {str(e)}")
            return False

import logging
import os
import base64
from io import BytesIO
from django.template.loader import render_to_string
from django.conf import settings
from weasyprint import HTML
from barcode import Code128
from barcode.writer import ImageWriter
from core.models import Sucursal
from ..models import SRIConfig

logger = logging.getLogger(__name__)

class RIDEGenerator:
    """
    Servicio para generar el RIDE (Representación Impresa de Documento Electrónico)
    en formato PDF utilizando WeasyPrint y plantillas HTML.
    """

    def __init__(self, comprobante):
        self.comprobante = comprobante
        self.venta = comprobante.venta

    def _get_logo_base64(self):
        """Intenta cargar el logo de la empresa y devolverlo en base64"""
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'logo_vp.png')
        if not os.path.exists(logo_path):
            # Fallback a logo_vpmotos.png si existe
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'logo_vpmotos.png')
            
        if os.path.exists(logo_path):
            try:
                with open(logo_path, "rb") as image_file:
                    return base64.b64encode(image_file.read()).decode('utf-8')
            except Exception as e:
                logger.error(f"Error cargando logo para RIDE: {e}")
        return None

    def _generate_barcode_base64(self, code):
        """Genera un código de barras 128 en base64"""
        if not code:
            return None
        try:
            buffer = BytesIO()
            # Opciones para el código de barras (limpio, sin texto abajo ya que lo ponemos aparte)
            options = {
                'write_text': False,
                'module_height': 15.0,
                'module_width': 0.4,
                'quiet_zone': 3.0,
            }
            Code128(code, writer=ImageWriter()).write(buffer, options=options)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error generando barcode: {e}")
            return None

    def generar_pdf(self):
        """Genera el contenido del PDF y lo devuelve en BytesIO"""
        try:
            # 1. Preparar datos de empresa y configuración
            sucursal = Sucursal.get_sucursal_principal()
            sri_config = SRIConfig.objects.first()
            
            # Datos de la Empresa
            razon_social = sri_config.razon_social if (sri_config and sri_config.razon_social) else (sucursal.nombre if sucursal else "VPMOTOS")
            ruc_emisor = sri_config.ruc if (sri_config and sri_config.ruc) else (sucursal.ruc if sucursal else "0000000000001")
            
            # 2. Preparar detalles de productos
            detalles_pdf = []
            for det in self.venta.detalleventa_set.all():
                if det.producto:
                    codigo = det.producto.codigo_unico or det.producto.codigo
                    nombre = det.producto.nombre
                elif det.tipo_servicio:
                    codigo = det.tipo_servicio.codigo if hasattr(det.tipo_servicio, 'codigo') else "SERV"
                    nombre = det.tipo_servicio.nombre
                else:
                    codigo = "GEN"
                    nombre = det.nombre_personalizado or "ITEM"
                
                detalles_pdf.append({
                    'codigo': codigo,
                    'nombre': nombre,
                    'cantidad': det.cantidad,
                    'precio_unitario': det.precio_unitario,
                    'total': det.total
                })

            # 3. Datos de impuestos
            total_iva_15 = self.venta.get_base_iva_standard()
            total_iva_0 = self.venta.get_base_iva_0()
            valor_iva = self.venta.get_total_iva_standard()

            # 4. Generar elementos visuales
            logo_b64 = self._get_logo_base64()
            barcode_b64 = self._generate_barcode_base64(self.comprobante.clave_acceso)

            # 5. Renderizar contexto
            context = {
                'comprobante': self.comprobante,
                'venta': self.venta,
                'detalles': detalles_pdf,
                'razon_social': razon_social,
                'ruc_emisor': ruc_emisor,
                'direccion_matriz': sri_config.direccion_matriz if sri_config else "N/A",
                'direccion_sucursal': sucursal.get_direccion_completa() if sucursal else "N/A",
                'obligado_contabilidad': sri_config.obligado_contabilidad if sri_config else False,
                'contribuyente_especial': sri_config.contribuyente_especial,
                'agente_retencion': sri_config.agente_retencion,
                'regimen_rimpe': sri_config.regimen_rimpe,
                'logo_base64': logo_b64,
                'barcode_base64': barcode_b64,
                'total_iva_15': total_iva_15,
                'total_iva_0': total_iva_0,
                'subtotal_sin_impuestos': self.venta.subtotal,
                'valor_iva': valor_iva,
            }

            # 6. Generar PDF con WeasyPrint
            html_string = render_to_string('electronic_invoicing/ride_pdf.html', context)
            buffer = BytesIO()
            HTML(string=html_string).write_pdf(target=buffer)
            
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error(f"Error crítico en RIDEGenerator: {e}")
            raise e

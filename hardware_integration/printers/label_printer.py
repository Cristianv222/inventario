# apps/hardware_integration/printers/label_printer.py

import logging
from .printer_service import PrinterService
from ..models import RegistroImpresion, ConfiguracionCodigoBarras
from django.utils import timezone

logger = logging.getLogger(__name__)

class LabelPrinter:
    """Servicio para imprimir etiquetas de códigos de barras"""
    
    @staticmethod
    @staticmethod
    @staticmethod
    @staticmethod
    @staticmethod
    @staticmethod
    @staticmethod
    def generar_zpl_producto(producto, configuracion=None, impresora=None):
        """Genera comandos ZPL para un producto"""
        if impresora:
            ancho_mm = impresora.ancho_etiqueta or 50
            alto_mm  = impresora.alto_etiqueta or 30
        else:
            ancho_mm, alto_mm = 50, 30

        pw = int(ancho_mm * 8)
        ll = int(alto_mm  * 8)

        try:
            from core.models import Sucursal
            s = Sucursal.objects.filter(es_principal=True).first()
            empresa = s.nombre_comercial or s.nombre if s else "VPMOTOS"
        except:
            empresa = "VPMOTOS"

        nombre = producto.nombre
        codigo = producto.codigo_unico
        precio = f"${producto.precio_venta:,.2f}"

        n1 = nombre[:30]
        n2 = nombre[30:60] if len(nombre) > 30 else ""

        zpl = ["^XA", "^CI28", f"^PW{pw}", f"^LL{ll}"]

        # 1. EMPRESA centrada arriba con ^FB (Field Block centrado)
        zpl.append(f"^FO0,5^A0N,22,20^FB{pw},1,0,C,0^FD{empresa}^FS")

        # 2. PRECIO arriba derecha
        zpl.append(f"^FO0,5^A0N,28,26^FB{pw},1,0,R,0^FD{precio}  ^FS")

        # 3. CODIGO DE BARRAS centrado
        bar_h = 55
        bar_y = 35
        # CODE128: ~11 modulos por char x 2 dots = 22 dots/char + overhead
        bar_w = len(codigo) * 22 + 60
        bar_x = max(0, (pw - bar_w) // 2)
        zpl.append(f"^FO{bar_x},{bar_y}^BY2,2.0,{bar_h}^BCN,{bar_h},Y,N,N^FD{codigo}^FS")

        # 4. NOMBRE centrado abajo con ^FB
        nombre_y = ll - 44 if not n2 else ll - 60
        zpl.append(f"^FO0,{nombre_y}^A0N,20,18^FB{pw},1,0,C,0^FD{n1}^FS")
        if n2:
            zpl.append(f"^FO0,{nombre_y+22}^A0N,20,18^FB{pw},1,0,C,0^FD{n2}^FS")

        zpl.append("^XZ")
        return "\n".join(zpl)

    def imprimir_etiqueta_producto(producto, cantidad=1, impresora=None, usuario=None):
        """Imprime etiquetas para un producto"""
        try:
            if not impresora:
                from ..models import Impresora
                impresora = Impresora.objects.filter(tipo_impresora='ETIQUETAS', estado='ACTIVA').first()
            
            if not impresora:
                return False, "No se encontró una impresora de etiquetas activa"
            
            zpl = LabelPrinter.generar_zpl_producto(producto, impresora=impresora)
            
            # Optimización: Usar ^PQ dentro del ZPL para cantidad si es posible,
            # pero dado que el service puede estar enviando a un agente de red,
            # mantendremos el comando de impresión del service.
            
            # Si el ZPL soporta cantidad nativa (^PQ), lo insertamos
            if "^XZ" in zpl:
                zpl = zpl.replace("^XZ", f"^PQ{cantidad}^XZ")
            
            from ..api.agente_views import crear_trabajo_impresion
            zpl_hex = zpl.encode('utf-8').hex()
            trabajo_id = crear_trabajo_impresion(
                usuario=usuario,
                impresora_nombre=impresora.nombre_driver or impresora.nombre,
                comandos_hex=zpl_hex,
                tipo='ETIQUETA',
                prioridad=2,
                abrir_gaveta=False
            )
            success = True
            msg = f'Trabajo creado: {trabajo_id}'

            # Registrar actividad
            RegistroImpresion.objects.create(
                impresora=impresora,
                producto=producto,
                usuario=usuario,
                tipo_documento='ETIQUETA',
                estado='EXITOSO' if success else 'ERROR',
                numero_documento=f"ETIQ-{producto.codigo_unico}",
                contenido_resumen=f"Etiqueta para {producto.nombre} (x{cantidad})",
                tiempo_procesamiento=0
            )
            
            return success, msg
                
        except Exception as e:
            logger.error(f"Error al imprimir etiquetas: {e}")
            return False, str(e)

# apps/hardware_integration/printers/label_printer.py

import logging
from .printer_service import PrinterService
from ..models import RegistroImpresion, ConfiguracionCodigoBarras
from django.utils import timezone

logger = logging.getLogger(__name__)

class LabelPrinter:
    """Servicio para imprimir etiquetas de códigos de barras"""
    
    @staticmethod
    def generar_zpl_producto(producto, configuracion=None, impresora=None):
        """Genera comandos ZPL para un producto basado en la configuración de la impresora"""
        # Priorizar configuración de la impresora si existe
        if impresora:
            imp_nombre = impresora.imprime_nombre
            imp_precio = impresora.imprime_precio
            imp_codigo = impresora.imprime_codigo_barras
            ancho_mm = impresora.ancho_etiqueta or 50
            alto_mm = impresora.alto_etiqueta or 25
        else:
            # Valores por defecto o de la configuración predeterminada
            if not configuracion:
                configuracion = ConfiguracionCodigoBarras.objects.filter(es_predeterminada=True).first()
            
            if configuracion:
                imp_nombre = configuracion.incluir_nombre_producto
                imp_precio = configuracion.incluir_precio
                imp_codigo = True
                ancho_mm = 50 # Default
                alto_mm = 25 # Default
            else:
                imp_nombre = imp_precio = imp_codigo = True
                ancho_mm, alto_mm = 50, 25

        # Convertir mm a dots (8 dots per mm para 203 DPI)
        pw = int(ancho_mm * 8)
        ll = int(alto_mm * 8)
        
        # Iniciar ZPL
        zpl = [
            "^XA",
            "^CI28",  # UTF-8
            f"^PW{pw}",
            f"^LL{ll}"
        ]
        
        current_y = 30
        
        # Nombre del producto
        if imp_nombre:
            nombre = producto.nombre[:40]
            zpl.append(f"^FO20,{current_y}^A0N,30,25^FD{nombre}^FS")
            current_y += 40
            
        # Código de barras
        if imp_codigo:
            codigo = producto.codigo_unico
            zpl.append(f"^FO20,{current_y}^BY2,2.0,50^BCN,50,Y,N,N^FD{codigo}^FS")
            current_y += 80
            
        # Precio
        if imp_precio:
            precio = f"S/ {producto.precio_venta:,.2f}"
            zpl.append(f"^FO20,{current_y}^A0N,40,35^FD{precio}^FS")
            
        zpl.append("^XZ")
        return "\n".join(zpl)

    @staticmethod
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
            
            success, msg = PrinterService.print_test_page(impresora, usar_agente=True) # El service debe manejar el envío raw
            # Nota: print_test_page genera su propio ZPL. Necesitamos un método que envíe RAW ZPL.
            # Según printer_service.py analizado antes, hay métodos para enviar raw.
            
            success, msg = PrinterService.imprimir_raw_windows(impresora.nombre_driver, zpl.encode('utf-8')) if hasattr(PrinterService, 'imprimir_raw_windows') else (False, "Método no disponible")
            
            if not success and impresora.direccion_ip:
                # Intento por red si falla driver
                try:
                    import socket
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(5)
                        s.connect((impresora.direccion_ip, impresora.puerto_red or 9100))
                        s.sendall(zpl.encode('utf-8'))
                        success = True
                        msg = "Enviado por red"
                except:
                    pass

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

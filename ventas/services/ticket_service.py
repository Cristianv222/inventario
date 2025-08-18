# ventas/services/ticket_service.py
import os
import platform
import subprocess
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from datetime import datetime

class TicketThermalService:
    """Servicio para manejo de tickets en impresoras térmicas"""
    
    # Configuración de impresoras térmicas comunes
    THERMAL_PRINTERS = {
        'EPSON_TM_T20': {
            'name': 'Epson TM-T20',
            'width': 42,  # caracteres por línea
            'cut_command': b'\x1D\x56\x00',  # ESC/POS cut command
            'drawer_command': b'\x1B\x70\x00\x19\xFA'  # Abrir cajón
        },
        'EPSON_TM_T88': {
            'name': 'Epson TM-T88',
            'width': 48,
            'cut_command': b'\x1D\x56\x00',
            'drawer_command': b'\x1B\x70\x00\x19\xFA'
        },
        'GENERIC_80MM': {
            'name': 'Genérica 80mm',
            'width': 48,
            'cut_command': b'\x1D\x56\x00',
            'drawer_command': b'\x1B\x70\x00\x19\xFA'
        },
        'GENERIC_58MM': {
            'name': 'Genérica 58mm',
            'width': 32,
            'cut_command': b'\x1D\x56\x00',
            'drawer_command': b'\x1B\x70\x00\x19\xFA'
        }
    }
    
    @classmethod
    def get_available_printers(cls):
        """Obtiene lista de impresoras disponibles en el sistema"""
        printers = []
        
        try:
            if platform.system() == "Windows":
                # Windows - usar wmic para obtener impresoras
                result = subprocess.run(
                    ['wmic', 'printer', 'get', 'name'],
                    capture_output=True, text=True, check=True
                )
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                for line in lines:
                    printer_name = line.strip()
                    if printer_name and printer_name != 'Name':
                        printers.append({
                            'name': printer_name,
                            'type': cls._detect_printer_type(printer_name)
                        })
            
            elif platform.system() == "Linux":
                # Linux - usar lpstat
                result = subprocess.run(
                    ['lpstat', '-p'],
                    capture_output=True, text=True, check=True
                )
                for line in result.stdout.split('\n'):
                    if line.startswith('printer'):
                        printer_name = line.split()[1]
                        printers.append({
                            'name': printer_name,
                            'type': cls._detect_printer_type(printer_name)
                        })
            
            elif platform.system() == "Darwin":  # macOS
                # macOS - usar lpstat
                result = subprocess.run(
                    ['lpstat', '-p'],
                    capture_output=True, text=True, check=True
                )
                for line in result.stdout.split('\n'):
                    if line.startswith('printer'):
                        printer_name = line.split()[1]
                        printers.append({
                            'name': printer_name,
                            'type': cls._detect_printer_type(printer_name)
                        })
        
        except Exception as e:
            print(f"Error obteniendo impresoras: {e}")
            # Agregar impresoras por defecto si no se pueden detectar
            printers = [
                {'name': 'Impresora Térmica', 'type': 'GENERIC_80MM'},
                {'name': 'Ticket Printer', 'type': 'GENERIC_58MM'}
            ]
        
        return printers
    
    @classmethod
    def _detect_printer_type(cls, printer_name):
        """Detecta el tipo de impresora basado en el nombre"""
        name_lower = printer_name.lower()
        
        if 'tm-t88' in name_lower or 'tmt88' in name_lower:
            return 'EPSON_TM_T88'
        elif 'tm-t20' in name_lower or 'tmt20' in name_lower:
            return 'EPSON_TM_T20'
        elif 'epson' in name_lower:
            return 'EPSON_TM_T88'  # Default Epson
        elif '58' in name_lower or '58mm' in name_lower:
            return 'GENERIC_58MM'
        else:
            return 'GENERIC_80MM'  # Default
    
    @classmethod
    def generate_ticket_content(cls, venta, printer_type='GENERIC_80MM'):
        """Genera el contenido del ticket para impresión térmica"""
        config = cls.THERMAL_PRINTERS.get(printer_type, cls.THERMAL_PRINTERS['GENERIC_80MM'])
        width = config['width']
        
        def center_text(text, width):
            """Centra texto en la línea"""
            if len(text) >= width:
                return text[:width]
            spaces = (width - len(text)) // 2
            return ' ' * spaces + text
        
        def left_right_text(left, right, width):
            """Alinea texto a izquierda y derecha"""
            if len(left) + len(right) >= width:
                return (left + right)[:width]
            spaces = width - len(left) - len(right)
            return left + ' ' * spaces + right
        
        def separator_line(width, char='-'):
            """Genera línea separadora"""
            return char * width
        
        # Construir contenido del ticket
        lines = []
        
        # Header con nombre del negocio
        empresa = getattr(settings, 'EMPRESA_NOMBRE', 'VPMOTOS')
        ruc = getattr(settings, 'EMPRESA_RUC', '')
        direccion = getattr(settings, 'EMPRESA_DIRECCION', '')
        telefono = getattr(settings, 'EMPRESA_TELEFONO', '')
        
        lines.append(center_text(empresa, width))
        if ruc:
            lines.append(center_text(f"RUC: {ruc}", width))
        if direccion:
            lines.append(center_text(direccion, width))
        if telefono:
            lines.append(center_text(f"Tel: {telefono}", width))
        
        lines.append(separator_line(width, '='))
        
        # Información de la venta
        lines.append(center_text("TICKET DE VENTA", width))
        lines.append(separator_line(width))
        
        fecha_hora = venta.fecha_hora.strftime("%d/%m/%Y %H:%M:%S")
        lines.append(f"Fecha: {fecha_hora}")
        lines.append(f"Ticket: {venta.numero_factura}")
        lines.append(f"Cliente: {venta.cliente.get_nombre_completo()[:width-9]}")
        if venta.cliente.identificacion != '9999999999':
            lines.append(f"CI/RUC: {venta.cliente.identificacion}")
        lines.append(f"Vendedor: {venta.usuario.get_full_name() or venta.usuario.username}")
        
        lines.append(separator_line(width))
        
        # Encabezado de productos
        lines.append("CANT DESCRIPCION        PRECIO")
        lines.append(separator_line(width))
        
        # Detalles de la venta
        for detalle in venta.detalleventa_set.all():
            # Línea con cantidad y precio
            if detalle.producto:
                descripcion = detalle.producto.nombre
                tipo_item = "PROD"
            elif detalle.tipo_servicio:
                descripcion = detalle.tipo_servicio.nombre
                tipo_item = "SERV"
            else:
                descripcion = "Item"
                tipo_item = ""
            
            # Primera línea: cantidad, descripción corta y precio
            cant_str = f"{int(detalle.cantidad):>3}"
            precio_str = f"${detalle.total:.2f}"
            
            # Calcular espacio disponible para descripción
            desc_space = width - len(cant_str) - len(precio_str) - 2
            desc_short = descripcion[:desc_space] if len(descripcion) > desc_space else descripcion
            
            line = f"{cant_str} {desc_short:<{desc_space}} {precio_str}"
            lines.append(line)
            
            # Si la descripción es muy larga, agregar líneas adicionales
            if len(descripcion) > desc_space:
                remaining = descripcion[desc_space:]
                while remaining:
                    chunk = remaining[:width-4]
                    remaining = remaining[width-4:]
                    lines.append(f"    {chunk}")
            
            # Información adicional si es servicio
            if detalle.tipo_servicio and detalle.tecnico:
                tech_line = f"    Tecnico: {detalle.tecnico.get_nombre_completo()[:width-13]}"
                lines.append(tech_line)
        
        lines.append(separator_line(width))
        
        # Totales
        lines.append(left_right_text("SUBTOTAL:", f"${venta.subtotal:.2f}", width))
        if venta.iva > 0:
            lines.append(left_right_text("IVA (15%):", f"${venta.iva:.2f}", width))
        if venta.descuento > 0:
            lines.append(left_right_text("DESCUENTO:", f"-${venta.descuento:.2f}", width))
        
        lines.append(separator_line(width))
        lines.append(left_right_text("TOTAL:", f"${venta.total:.2f}", width))
        lines.append(separator_line(width, '='))
        
        # Información de pago
        tipo_pago_map = {
            'EFECTIVO': 'EFECTIVO',
            'TARJETA': 'TARJETA',
            'TRANSFERENCIA': 'TRANSFERENCIA',
            'CREDITO': 'CREDITO'
        }
        lines.append(f"Forma de pago: {tipo_pago_map.get(venta.tipo_pago, venta.tipo_pago)}")
        
        lines.append("")
        lines.append(center_text("¡GRACIAS POR SU COMPRA!", width))
        lines.append(center_text("Vuelva pronto", width))
        
        # Si hay información adicional de la empresa
        if hasattr(settings, 'EMPRESA_WEBSITE') and settings.EMPRESA_WEBSITE:
            lines.append(center_text(settings.EMPRESA_WEBSITE, width))
        
        lines.append("")
        lines.append("")
        lines.append("")
        
        return '\n'.join(lines)
    
    @classmethod
    def print_ticket(cls, venta, printer_name=None, printer_type='GENERIC_80MM', open_drawer=False):
        """Imprime ticket en impresora térmica"""
        try:
            # Generar contenido del ticket
            content = cls.generate_ticket_content(venta, printer_type)
            
            # Configuración de la impresora
            config = cls.THERMAL_PRINTERS.get(printer_type, cls.THERMAL_PRINTERS['GENERIC_80MM'])
            
            # Preparar comandos ESC/POS
            commands = []
            
            # Inicializar impresora
            commands.append(b'\x1B\x40')  # ESC @ - Initialize printer
            
            # Configurar tamaño de fuente
            commands.append(b'\x1B\x21\x00')  # ESC ! - Select character font
            
            # Agregar contenido
            commands.append(content.encode('utf-8', errors='ignore'))
            
            # Cortar papel
            commands.append(config['cut_command'])
            
            # Abrir cajón si se solicita
            if open_drawer:
                commands.append(config['drawer_command'])
            
            # Unir todos los comandos
            print_data = b''.join(commands)
            
            # Enviar a impresora
            success = cls._send_to_printer(print_data, printer_name)
            
            if success:
                return True, "Ticket impreso correctamente"
            else:
                return False, "Error al enviar ticket a la impresora"
                
        except Exception as e:
            return False, f"Error al imprimir ticket: {str(e)}"
    
    @classmethod
    def _send_to_printer(cls, data, printer_name=None):
        """Envía datos raw a la impresora"""
        try:
            system = platform.system()
            
            if system == "Windows":
                if printer_name:
                    # Usar impresora específica en Windows
                    import win32print
                    hPrinter = win32print.OpenPrinter(printer_name)
                    try:
                        hJob = win32print.StartDocPrinter(hPrinter, 1, ("Ticket", None, "RAW"))
                        try:
                            win32print.StartPagePrinter(hPrinter)
                            win32print.WritePrinter(hPrinter, data)
                            win32print.EndPagePrinter(hPrinter)
                        finally:
                            win32print.EndDocPrinter(hPrinter)
                    finally:
                        win32print.ClosePrinter(hPrinter)
                    return True
                else:
                    # Usar impresora por defecto
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
                        f.write(data)
                        temp_file = f.name
                    
                    try:
                        subprocess.run(['notepad', '/p', temp_file], check=True)
                        return True
                    finally:
                        os.unlink(temp_file)
            
            elif system in ["Linux", "Darwin"]:
                if printer_name:
                    # Usar lp con impresora específica
                    process = subprocess.Popen(
                        ['lp', '-d', printer_name, '-o', 'raw'],
                        stdin=subprocess.PIPE
                    )
                    process.communicate(input=data)
                    return process.returncode == 0
                else:
                    # Usar impresora por defecto
                    process = subprocess.Popen(['lp', '-o', 'raw'], stdin=subprocess.PIPE)
                    process.communicate(input=data)
                    return process.returncode == 0
            
            return False
            
        except ImportError:
            # Si no está disponible win32print en Windows, usar método alternativo
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.prn') as f:
                    f.write(data)
                    temp_file = f.name
                
                if printer_name:
                    if system == "Windows":
                        subprocess.run(['copy', '/b', temp_file, f'\\\\localhost\\{printer_name}'], 
                                     shell=True, check=True)
                    else:
                        subprocess.run(['lp', '-d', printer_name, '-o', 'raw', temp_file], check=True)
                else:
                    subprocess.run(['lp', '-o', 'raw', temp_file], check=True)
                
                os.unlink(temp_file)
                return True
                
            except Exception:
                return False
        
        except Exception as e:
            print(f"Error enviando a impresora: {e}")
            return False
    
    @classmethod
    def test_printer(cls, printer_name, printer_type='GENERIC_80MM'):
        """Imprime un ticket de prueba"""
        try:
            config = cls.THERMAL_PRINTERS.get(printer_type, cls.THERMAL_PRINTERS['GENERIC_80MM'])
            width = config['width']
            
            lines = []
            lines.append('=' * width)
            lines.append(' ' * ((width - 16) // 2) + 'TICKET DE PRUEBA')
            lines.append('=' * width)
            lines.append('')
            lines.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            lines.append(f"Impresora: {printer_name}")
            lines.append(f"Tipo: {config['name']}")
            lines.append(f"Ancho: {width} caracteres")
            lines.append('')
            lines.append('Caracteres especiales:')
            lines.append('ñáéíóúüÑÁÉÍÓÚÜ')
            lines.append('°!"#$%&\'()*+,-./0123456789:;<=>?')
            lines.append('')
            lines.append('=' * width)
            lines.append(' ' * ((width - 12) // 2) + 'PRUEBA EXITOSA')
            lines.append('=' * width)
            lines.append('')
            lines.append('')
            
            content = '\n'.join(lines)
            
            # Preparar comandos
            commands = []
            commands.append(b'\x1B\x40')  # Initialize
            commands.append(content.encode('utf-8', errors='ignore'))
            commands.append(config['cut_command'])
            
            print_data = b''.join(commands)
            
            success = cls._send_to_printer(print_data, printer_name)
            
            if success:
                return True, "Ticket de prueba impreso correctamente"
            else:
                return False, "Error al imprimir ticket de prueba"
                
        except Exception as e:
            return False, f"Error en prueba de impresión: {str(e)}"
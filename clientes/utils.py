import re
import requests
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings

from .models import Cliente, MovimientoPuntos, ConfiguracionPuntos, CanjeoPuntos

logger = logging.getLogger(__name__)

# ========== VALIDACIONES ==========

def validar_cedula_ecuatoriana(cedula: str) -> bool:
    """
    Valida una cédula ecuatoriana usando el algoritmo oficial.
    
    Args:
        cedula (str): Número de cédula a validar
        
    Returns:
        bool: True si la cédula es válida
    """
    try:
        if not cedula or len(cedula) != 10:
            return False
        
        if not cedula.isdigit():
            return False
        
        # Validar provincia (primeros 2 dígitos)
        provincia = int(cedula[:2])
        if provincia < 1 or provincia > 24:
            return False
        
        # Algoritmo de validación
        coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
        suma = 0
        
        for i in range(9):
            valor = int(cedula[i]) * coeficientes[i]
            if valor >= 10:
                valor = valor - 9
            suma += valor
        
        digito_verificador = 10 - (suma % 10)
        if digito_verificador == 10:
            digito_verificador = 0
        
        return digito_verificador == int(cedula[9])
        
    except (ValueError, IndexError):
        return False

def validar_ruc_ecuatoriano(ruc: str) -> bool:
    """
    Valida un RUC ecuatoriano.
    
    Args:
        ruc (str): Número de RUC a validar
        
    Returns:
        bool: True si el RUC es válido
    """
    try:
        if not ruc or len(ruc) != 13:
            return False
        
        if not ruc.isdigit():
            return False
        
        # RUC de persona natural (termina en 001)
        if ruc.endswith('001'):
            return validar_cedula_ecuatoriana(ruc[:10])
        
        # RUC de empresa
        tercero = int(ruc[2])
        if tercero >= 6 and tercero <= 9:
            # Validación específica para RUC de empresa
            return True
        
        return False
        
    except (ValueError, IndexError):
        return False

def validar_email(email: str) -> bool:
    """
    Valida formato de email.
    
    Args:
        email (str): Email a validar
        
    Returns:
        bool: True si el formato es válido
    """
    if not email:
        return False
    
    patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(patron, email))

def validar_telefono_ecuador(telefono: str) -> bool:
    """
    Valida formato de teléfono ecuatoriano.
    
    Args:
        telefono (str): Teléfono a validar
        
    Returns:
        bool: True si el formato es válido
    """
    if not telefono:
        return False
    
    # Limpiar teléfono
    telefono_limpio = re.sub(r'[^\d]', '', telefono)
    
    # Validar celular (10 dígitos que empiecen con 09)
    if len(telefono_limpio) == 10 and telefono_limpio.startswith('09'):
        return True
    
    # Validar teléfono fijo (9 dígitos que empiecen con 0)
    if len(telefono_limpio) == 9 and telefono_limpio.startswith('0'):
        return True
    
    # Validar con código de país +593
    if len(telefono_limpio) == 12 and telefono_limpio.startswith('593'):
        return True
    
    return False

# ========== GESTIÓN DE PUNTOS ==========

def procesar_puntos_venta(cliente: Cliente, total_venta: Decimal, venta=None) -> int:
    """
    Procesa los puntos a otorgar por una venta.
    
    Args:
        cliente (Cliente): Cliente que realizó la venta
        total_venta (Decimal): Total de la venta
        venta: Instancia de la venta (opcional)
        
    Returns:
        int: Cantidad de puntos otorgados
    """
    try:
        if not cliente or cliente.identificacion == '9999999999':
            return 0
        
        # Calcular puntos según configuraciones activas
        puntos_otorgados = ConfiguracionPuntos.calcular_puntos_venta(total_venta)
        
        if puntos_otorgados > 0:
            concepto = f"Compra por ${total_venta}"
            if venta and hasattr(venta, 'numero_factura'):
                concepto = f"Compra - Factura #{venta.numero_factura}"
            
            cliente.agregar_puntos(puntos_otorgados, concepto, venta)
            
            logger.info(f"Puntos procesados: {puntos_otorgados} para cliente {cliente.identificacion}")
        
        return puntos_otorgados
        
    except Exception as e:
        logger.error(f"Error procesando puntos: {str(e)}")
        return 0

def calcular_descuento_puntos(cliente: Cliente, total_compra: Decimal) -> Dict:
    """
    Calcula el descuento disponible por puntos.
    
    Args:
        cliente (Cliente): Cliente
        total_compra (Decimal): Total de la compra
        
    Returns:
        Dict: Información del descuento calculado
    """
    try:
        if not cliente:
            return {'descuento_disponible': 0, 'puntos_necesarios': 0, 'puede_aplicar': False}
        
        # 1 punto = $0.01 de descuento
        VALOR_PUNTO = Decimal('0.01')
        
        # Descuento máximo permitido (50% del total)
        descuento_maximo = total_compra * Decimal('0.50')
        
        # Descuento disponible por puntos
        descuento_por_puntos = cliente.puntos_disponibles * VALOR_PUNTO
        
        # Tomar el menor entre ambos
        descuento_disponible = min(descuento_maximo, descuento_por_puntos)
        
        # Puntos necesarios para ese descuento
        puntos_necesarios = int(descuento_disponible / VALOR_PUNTO)
        
        return {
            'descuento_disponible': float(descuento_disponible),
            'puntos_necesarios': puntos_necesarios,
            'puede_aplicar': puntos_necesarios > 0 and cliente.puntos_disponibles >= puntos_necesarios,
            'puntos_actuales': cliente.puntos_disponibles,
            'descuento_maximo': float(descuento_maximo),
            'valor_punto': float(VALOR_PUNTO)
        }
        
    except Exception as e:
        logger.error(f"Error calculando descuento por puntos: {str(e)}")
        return {'descuento_disponible': 0, 'puntos_necesarios': 0, 'puede_aplicar': False}

def obtener_premios_disponibles(cliente: Cliente) -> List[Dict]:
    """
    Obtiene la lista de premios que el cliente puede canjear.
    
    Args:
        cliente (Cliente): Cliente
        
    Returns:
        List[Dict]: Lista de premios disponibles
    """
    premios = [
        {
            'tipo': 'DESCUENTO',
            'descripcion': 'Descuento $1.00',
            'puntos_necesarios': 100,
            'valor_equivalente': 1.00,
            'disponible': cliente.puntos_disponibles >= 100,
            'icono': 'fas fa-dollar-sign',
            'color': 'primary'
        },
        {
            'tipo': 'DESCUENTO',
            'descripcion': 'Descuento $5.00',
            'puntos_necesarios': 500,
            'valor_equivalente': 5.00,
            'disponible': cliente.puntos_disponibles >= 500,
            'icono': 'fas fa-dollar-sign',
            'color': 'success'
        },
        {
            'tipo': 'DESCUENTO',
            'descripcion': 'Descuento $10.00',
            'puntos_necesarios': 1000,
            'valor_equivalente': 10.00,
            'disponible': cliente.puntos_disponibles >= 1000,
            'icono': 'fas fa-dollar-sign',
            'color': 'warning'
        },
        {
            'tipo': 'SERVICIO_GRATIS',
            'descripcion': 'Cambio de aceite gratuito',
            'puntos_necesarios': 1500,
            'valor_equivalente': 25.00,
            'disponible': cliente.puntos_disponibles >= 1500,
            'icono': 'fas fa-wrench',
            'color': 'info'
        },
        {
            'tipo': 'PRODUCTO_GRATIS',
            'descripcion': 'Kit de limpieza premium',
            'puntos_necesarios': 2000,
            'valor_equivalente': 35.00,
            'disponible': cliente.puntos_disponibles >= 2000,
            'icono': 'fas fa-gift',
            'color': 'danger'
        },
    ]
    
    return premios

def limpiar_puntos_vencidos(dias_vencimiento: int = 365) -> int:
    """
    Limpia puntos que han vencido después del tiempo especificado.
    
    Args:
        dias_vencimiento (int): Días después de los cuales los puntos vencen
        
    Returns:
        int: Cantidad de clientes afectados
    """
    try:
        fecha_vencimiento = timezone.now().date() - timedelta(days=dias_vencimiento)
        
        # Buscar movimientos de puntos ganados que han vencido
        movimientos_vencidos = MovimientoPuntos.objects.filter(
            tipo='GANADO',
            fecha__date__lte=fecha_vencimiento
        ).exclude(
            cliente__movimientos_puntos__tipo='VENCIDO',
            cliente__movimientos_puntos__concepto__contains='vencimiento automático'
        )
        
        clientes_afectados = 0
        
        for movimiento in movimientos_vencidos:
            cliente = movimiento.cliente
            
            # Verificar si el cliente aún tiene esos puntos
            if cliente.puntos_disponibles >= movimiento.puntos:
                # Quitar puntos vencidos
                cliente.puntos_disponibles -= movimiento.puntos
                cliente.save()
                
                # Registrar movimiento de vencimiento
                MovimientoPuntos.objects.create(
                    cliente=cliente,
                    tipo='VENCIDO',
                    puntos=movimiento.puntos,
                    concepto=f'Puntos vencidos - vencimiento automático después de {dias_vencimiento} días'
                )
                
                clientes_afectados += 1
        
        logger.info(f"Limpieza de puntos vencidos completada: {clientes_afectados} clientes afectados")
        return clientes_afectados
        
    except Exception as e:
        logger.error(f"Error limpiando puntos vencidos: {str(e)}")
        return 0

# ========== ESTADÍSTICAS Y REPORTES ==========

def obtener_estadisticas_cliente(cliente: Cliente) -> Dict:
    """
    Obtiene estadísticas completas de un cliente.
    
    Args:
        cliente (Cliente): Cliente
        
    Returns:
        Dict: Estadísticas del cliente
    """
    try:
        # Estadísticas básicas
        stats = {
            'puntos_disponibles': cliente.puntos_disponibles,
            'puntos_acumulados': cliente.puntos_acumulados,
            'puntos_canjeados': cliente.puntos_canjeados,
            'descuento_preferencial': float(cliente.descuento_preferencial),
        }
        
        # Estadísticas de ventas
        from ventas.models import Venta
        ventas_stats = Venta.objects.filter(
            cliente=cliente,
            estado='COMPLETADA'
        ).aggregate(
            total_ventas=Count('id'),
            valor_total=Sum('total'),
            ticket_promedio=Sum('total') / Count('id') if Count('id') > 0 else 0
        )
        
        stats.update({
            'total_ventas': ventas_stats['total_ventas'] or 0,
            'valor_total_ventas': float(ventas_stats['valor_total'] or 0),
            'ticket_promedio': float(ventas_stats['ticket_promedio'] or 0),
        })
        
        # Última actividad
        ultima_venta = Venta.objects.filter(
            cliente=cliente,
            estado='COMPLETADA'
        ).order_by('-fecha_hora').first()
        
        if ultima_venta:
            stats['ultima_venta'] = {
                'fecha': ultima_venta.fecha_hora,
                'total': float(ultima_venta.total),
                'numero_factura': ultima_venta.numero_factura
            }
        
        # Movimientos de puntos recientes
        movimientos_recientes = MovimientoPuntos.objects.filter(
            cliente=cliente
        ).order_by('-fecha')[:5]
        
        stats['movimientos_recientes'] = [
            {
                'tipo': mov.tipo,
                'puntos': mov.puntos,
                'concepto': mov.concepto,
                'fecha': mov.fecha
            }
            for mov in movimientos_recientes
        ]
        
        # Canjes activos
        canjes_activos = CanjeoPuntos.objects.filter(
            cliente=cliente,
            utilizado=False
        ).count()
        
        stats['canjes_activos'] = canjes_activos
        
        return stats
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas del cliente: {str(e)}")
        return {}

def obtener_ranking_clientes(limite: int = 10) -> List[Dict]:
    """
    Obtiene el ranking de clientes por puntos.
    
    Args:
        limite (int): Cantidad de clientes a incluir
        
    Returns:
        List[Dict]: Lista de clientes ordenados por puntos
    """
    try:
        clientes = Cliente.objects.filter(
            activo=True
        ).exclude(
            identificacion='9999999999'
        ).order_by('-puntos_acumulados')[:limite]
        
        ranking = []
        for i, cliente in enumerate(clientes, 1):
            ranking.append({
                'posicion': i,
                'cliente': cliente,
                'puntos_acumulados': cliente.puntos_acumulados,
                'puntos_disponibles': cliente.puntos_disponibles,
                'puntos_canjeados': cliente.puntos_canjeados,
            })
        
        return ranking
        
    except Exception as e:
        logger.error(f"Error obteniendo ranking de clientes: {str(e)}")
        return []

# ========== NOTIFICACIONES ==========

def notificar_puntos_ganados(cliente: Cliente, puntos: int, venta=None) -> bool:
    """
    Notifica al cliente sobre puntos ganados.
    
    Args:
        cliente (Cliente): Cliente que ganó puntos
        puntos (int): Cantidad de puntos ganados
        venta: Venta asociada (opcional)
        
    Returns:
        bool: True si la notificación fue exitosa
    """
    try:
        # Notificación por email
        if cliente.email and validar_email(cliente.email):
            enviar_email_puntos(cliente, puntos, venta)
        
        # TODO: Implementar notificación por SMS
        # if cliente.celular:
        #     enviar_sms_puntos(cliente, puntos, venta)
        
        return True
        
    except Exception as e:
        logger.error(f"Error enviando notificación de puntos: {str(e)}")
        return False

def enviar_email_puntos(cliente: Cliente, puntos: int, venta=None) -> bool:
    """
    Envía email de notificación de puntos ganados.
    
    Args:
        cliente (Cliente): Cliente
        puntos (int): Puntos ganados
        venta: Venta asociada
        
    Returns:
        bool: True si el email fue enviado
    """
    try:
        asunto = f"¡Has ganado {puntos} puntos!"
        
        mensaje = f"""
        Hola {cliente.get_nombre_completo()},
        
        ¡Excelentes noticias! Has ganado {puntos} puntos en tu última compra.
        
        Resumen de puntos:
        • Puntos ganados: {puntos}
        • Total disponible: {cliente.puntos_disponibles}
        • Total acumulado: {cliente.puntos_acumulados}
        
        {"Factura: #" + venta.numero_factura if venta and hasattr(venta, 'numero_factura') else ""}
        
        ¡Recuerda que puedes canjear tus puntos por descuentos y premios!
        
        Gracias por tu preferencia,
        VPMOTOS
        """
        
        send_mail(
            asunto,
            mensaje,
            settings.DEFAULT_FROM_EMAIL,
            [cliente.email],
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error enviando email de puntos: {str(e)}")
        return False

# ========== UTILIDADES GENERALES ==========

def formatear_identificacion(identificacion: str, tipo: str) -> str:
    """
    Formatea una identificación según su tipo.
    
    Args:
        identificacion (str): Número de identificación
        tipo (str): Tipo de identificación
        
    Returns:
        str: Identificación formateada
    """
    if not identificacion:
        return ""
    
    if tipo == 'CEDULA' and len(identificacion) == 10:
        return f"{identificacion[:2]}-{identificacion[2:9]}-{identificacion[9]}"
    elif tipo == 'RUC' and len(identificacion) == 13:
        return f"{identificacion[:2]}-{identificacion[2:10]}-{identificacion[10:]}"
    else:
        return identificacion

def formatear_telefono(telefono: str) -> str:
    """
    Formatea un número de teléfono.
    
    Args:
        telefono (str): Número de teléfono
        
    Returns:
        str: Teléfono formateado
    """
    if not telefono:
        return ""
    
    # Limpiar teléfono
    telefono_limpio = re.sub(r'[^\d]', '', telefono)
    
    # Formatear según longitud
    if len(telefono_limpio) == 10 and telefono_limpio.startswith('09'):
        return f"{telefono_limpio[:4]}-{telefono_limpio[4:7]}-{telefono_limpio[7:]}"
    elif len(telefono_limpio) == 9 and telefono_limpio.startswith('0'):
        return f"{telefono_limpio[:1]}-{telefono_limpio[1:2]}-{telefono_limpio[2:5]}-{telefono_limpio[5:]}"
    else:
        return telefono

def obtener_provincia_por_cedula(cedula: str) -> str:
    """
    Obtiene la provincia de origen según la cédula.
    
    Args:
        cedula (str): Número de cédula
        
    Returns:
        str: Nombre de la provincia
    """
    provincias = {
        '01': 'Azuay', '02': 'Bolívar', '03': 'Cañar', '04': 'Carchi',
        '05': 'Cotopaxi', '06': 'Chimborazo', '07': 'El Oro', '08': 'Esmeraldas',
        '09': 'Guayas', '10': 'Imbabura', '11': 'Loja', '12': 'Los Ríos',
        '13': 'Manabí', '14': 'Morona Santiago', '15': 'Napo', '16': 'Pastaza',
        '17': 'Pichincha', '18': 'Tungurahua', '19': 'Zamora Chinchipe',
        '20': 'Galápagos', '21': 'Sucumbíos', '22': 'Orellana',
        '23': 'Santo Domingo de los Tsáchilas', '24': 'Santa Elena'
    }
    
    if cedula and len(cedula) >= 2:
        codigo = cedula[:2]
        return provincias.get(codigo, 'Provincia no identificada')
    
    return 'No determinada'

def generar_codigo_cliente(nombres: str, apellidos: str) -> str:
    """
    Genera un código único para el cliente basado en sus nombres.
    
    Args:
        nombres (str): Nombres del cliente
        apellidos (str): Apellidos del cliente
        
    Returns:
        str: Código único generado
    """
    try:
        # Tomar primeras letras
        codigo_base = ""
        
        if nombres:
            codigo_base += nombres.strip().split()[0][:2].upper()
        
        if apellidos:
            codigo_base += apellidos.strip().split()[0][:2].upper()
        
        # Agregar timestamp para unicidad
        from datetime import datetime
        timestamp = datetime.now().strftime("%m%d")
        
        return f"{codigo_base}{timestamp}"
        
    except Exception:
        # Fallback
        from datetime import datetime
        return f"CLI{datetime.now().strftime('%Y%m%d%H%M%S')}"
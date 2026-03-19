# tu_app/tasks.py
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

def limpiar_puntos_vencidos_task():
    """
    Función para limpiar puntos vencidos.
    Versión simplificada sin Celery.
    """
    try:
        from .models import MovimientoPuntos
        
        # Buscar puntos vencidos
        puntos_vencidos = MovimientoPuntos.objects.filter(
            tipo='GANADO',
            fecha_vencimiento__lt=timezone.now().date(),
            activo=True
        )
        
        cantidad = puntos_vencidos.count()
        
        if cantidad > 0:
            # Marcar como inactivos los puntos vencidos
            puntos_vencidos.update(activo=False)
            logger.info(f"Se limpiaron {cantidad} puntos vencidos")
        
        return cantidad
        
    except Exception as e:
        logger.error(f"Error limpiando puntos vencidos: {str(e)}")
        return 0

def procesar_puntos_retroactivos():
    """
    Función para procesar puntos de ventas anteriores al sistema.
    Se puede ejecutar como comando de Django.
    """
    try:
        from .models import ConfiguracionPuntos
        # Importar el modelo Venta desde la app ventas
        from ventas.models import Venta
        
        # Buscar ventas completadas sin puntos procesados
        ventas_sin_puntos = Venta.objects.filter(
            estado='COMPLETADA'
        ).exclude(
            movimientopuntos__tipo='GANADO'
        ).exclude(
            cliente__identificacion='9999999999'
        )
        
        procesadas = 0
        for venta in ventas_sin_puntos:
            if venta.cliente and venta.cliente.activo:
                puntos_ganados = ConfiguracionPuntos.calcular_puntos_venta(venta.total)
                
                if puntos_ganados > 0:
                    venta.cliente.agregar_puntos(
                        puntos_ganados,
                        f"Procesamiento retroactivo - Factura #{venta.numero_factura}",
                        venta
                    )
                    procesadas += 1
        
        logger.info(f"Procesamiento retroactivo completado: {procesadas} ventas procesadas")
        return procesadas
        
    except Exception as e:
        logger.error(f"Error en procesamiento retroactivo: {str(e)}")
        return 0
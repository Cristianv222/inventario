from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
import logging

from .models import Cliente, MovimientoPuntos, ConfiguracionPuntos, HistorialCliente
from .utils import procesar_puntos_venta, notificar_puntos_ganados

logger = logging.getLogger(__name__)

@receiver(post_save, sender='ventas.Venta')
def procesar_puntos_por_venta(sender, instance, created, **kwargs):
    """
    Signal que se ejecuta cuando se guarda una venta.
    Procesa automáticamente los puntos del cliente.
    """
    try:
        # Solo procesar si la venta está completada y no es consumidor final
        if (instance.estado == 'COMPLETADA' and 
            instance.cliente and 
            instance.cliente.identificacion != '9999999999' and
            instance.cliente.activo):
            
            # Verificar si ya se procesaron puntos para esta venta
            puntos_existentes = MovimientoPuntos.objects.filter(
                venta=instance,
                tipo='GANADO'
            ).exists()
            
            if not puntos_existentes:
                # Calcular puntos a otorgar
                puntos_ganados = ConfiguracionPuntos.calcular_puntos_venta(instance.total)
                
                if puntos_ganados > 0:
                    # Agregar puntos al cliente
                    instance.cliente.agregar_puntos(
                        puntos_ganados,
                        f"Compra - Factura #{instance.numero_factura}",
                        instance
                    )
                    
                    # Registrar en historial del cliente
                    HistorialCliente.objects.create(
                        cliente=instance.cliente,
                        tipo='VENTA',
                        descripcion=f"Venta completada - Factura #{instance.numero_factura}. Total: ${instance.total}. Puntos ganados: {puntos_ganados}",
                        venta=instance,
                        importante=instance.total >= 100  # Marcar como importante si es venta grande
                    )
                    
                    logger.info(f"Puntos procesados: Cliente {instance.cliente.identificacion} ganó {puntos_ganados} puntos por venta #{instance.numero_factura}")
                    
                    # Notificar puntos ganados (opcional)
                    try:
                        notificar_puntos_ganados(instance.cliente, puntos_ganados, instance)
                    except Exception as e:
                        logger.warning(f"Error al notificar puntos ganados: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error procesando puntos para venta {instance.id}: {str(e)}")

@receiver(post_save, sender='taller.OrdenTrabajo')
def procesar_historial_orden(sender, instance, created, **kwargs):
    """
    Signal que registra en el historial cuando se completa una orden de trabajo.
    """
    try:
        if (instance.estado == 'COMPLETADO' and 
            instance.cliente and 
            instance.cliente.identificacion != '9999999999'):
            
            # Verificar si ya existe entrada en historial para esta orden
            historial_existente = HistorialCliente.objects.filter(
                cliente=instance.cliente,
                orden_trabajo=instance,
                tipo='SERVICIO'
            ).exists()
            
            if not historial_existente:
                # Crear entrada en historial
                HistorialCliente.objects.create(
                    cliente=instance.cliente,
                    tipo='SERVICIO',
                    descripcion=f"Orden de trabajo completada - #{instance.numero_orden}. {instance.motivo_ingreso[:100]}{'...' if len(instance.motivo_ingreso or '') > 100 else ''}",
                    orden_trabajo=instance,
                    importante=instance.precio_total >= 200  # Marcar como importante si es orden costosa
                )
                
                logger.info(f"Historial registrado: Orden {instance.numero_orden} completada para cliente {instance.cliente.identificacion}")
                
    except Exception as e:
        logger.error(f"Error registrando historial para orden {instance.id}: {str(e)}")

@receiver(post_save, sender=Cliente)
def procesar_cliente_referido(sender, instance, created, **kwargs):
    """
    Signal que procesa puntos cuando un cliente es referido por otro.
    """
    try:
        if created and instance.referido_por and instance.referido_por.activo:
            # Buscar configuración para referidos
            config_referido = ConfiguracionPuntos.objects.filter(
                regla='POR_REFERIDO',
                activo=True,
                fecha_inicio__lte=timezone.now().date()
            ).filter(
                Q(fecha_fin__isnull=True) | 
                Q(fecha_fin__gte=timezone.now().date())
            ).first()
            
            if config_referido:
                puntos_referido = int(config_referido.valor)
                
                # Dar puntos al cliente que refirió
                instance.referido_por.agregar_puntos(
                    puntos_referido,
                    f"Cliente referido: {instance.get_nombre_completo()}"
                )
                
                # Registrar en historial del cliente que refirió
                HistorialCliente.objects.create(
                    cliente=instance.referido_por,
                    tipo='OTRO',
                    descripcion=f"Puntos ganados por referir a {instance.get_nombre_completo()}",
                    importante=True
                )
                
                # Registrar en historial del cliente nuevo
                HistorialCliente.objects.create(
                    cliente=instance,
                    tipo='OTRO',
                    descripcion=f"Cliente registrado como referido de {instance.referido_por.get_nombre_completo()}"
                )
                
                logger.info(f"Puntos por referido: {instance.referido_por.identificacion} ganó {puntos_referido} puntos por referir a {instance.identificacion}")
                
    except Exception as e:
        logger.error(f"Error procesando cliente referido {instance.id}: {str(e)}")

@receiver(pre_save, sender=Cliente)
def validar_cambios_cliente(sender, instance, **kwargs):
    """
    Signal que valida cambios importantes en el cliente.
    """
    try:
        if instance.pk:  # Solo para clientes existentes
            try:
                cliente_anterior = Cliente.objects.get(pk=instance.pk)
                
                # Detectar cambios importantes
                cambios = []
                
                if cliente_anterior.nombres != instance.nombres:
                    cambios.append(f"Nombres: '{cliente_anterior.nombres}' → '{instance.nombres}'")
                
                if cliente_anterior.apellidos != instance.apellidos:
                    cambios.append(f"Apellidos: '{cliente_anterior.apellidos}' → '{instance.apellidos}'")
                
                if cliente_anterior.identificacion != instance.identificacion:
                    cambios.append(f"Identificación: '{cliente_anterior.identificacion}' → '{instance.identificacion}'")
                
                if cliente_anterior.telefono != instance.telefono:
                    cambios.append(f"Teléfono: '{cliente_anterior.telefono or 'N/A'}' → '{instance.telefono or 'N/A'}'")
                
                if cliente_anterior.email != instance.email:
                    cambios.append(f"Email: '{cliente_anterior.email or 'N/A'}' → '{instance.email or 'N/A'}'")
                
                if cliente_anterior.activo != instance.activo:
                    estado_anterior = 'Activo' if cliente_anterior.activo else 'Inactivo'
                    estado_nuevo = 'Activo' if instance.activo else 'Inactivo'
                    cambios.append(f"Estado: {estado_anterior} → {estado_nuevo}")
                
                # Si hay cambios, prepararlos para registrar en historial después del save
                if cambios:
                    instance._cambios_detectados = cambios
                    
            except Cliente.DoesNotExist:
                pass  # Cliente nuevo, no hay cambios que detectar
                
    except Exception as e:
        logger.error(f"Error validando cambios en cliente {instance.id}: {str(e)}")

@receiver(post_save, sender=Cliente)
def registrar_cambios_cliente(sender, instance, created, **kwargs):
    """
    Signal que registra cambios importantes en el historial del cliente.
    """
    try:
        if not created and hasattr(instance, '_cambios_detectados'):
            # Registrar cambios en historial
            cambios_texto = "; ".join(instance._cambios_detectados)
            
            HistorialCliente.objects.create(
                cliente=instance,
                tipo='OTRO',
                descripcion=f"Información actualizada: {cambios_texto}",
                importante=True
            )
            
            logger.info(f"Cambios registrados para cliente {instance.identificacion}: {cambios_texto}")
            
            # Limpiar cambios detectados
            delattr(instance, '_cambios_detectados')
            
    except Exception as e:
        logger.error(f"Error registrando cambios para cliente {instance.id}: {str(e)}")

# ========== SIGNALS PARA LIMPIEZA Y MANTENIMIENTO ==========

@receiver(post_save, sender='ventas.Venta')
def limpiar_puntos_vencidos(sender, instance, **kwargs):
    """
    Aprovecha el evento de venta para limpiar puntos vencidos periódicamente.
    """
    try:
        # Solo ejecutar ocasionalmente (1 de cada 10 ventas)
        if instance.id % 10 == 0:
            from .tasks import limpiar_puntos_vencidos_task
            limpiar_puntos_vencidos_task()  # ← Cambiar .delay() por ()
            
    except Exception as e:
        logger.error(f"Error programando limpieza de puntos vencidos: {str(e)}")
# ========== FUNCIONES DE UTILIDAD ==========

def notificar_puntos_ganados(cliente, puntos, venta):
    """
    Notifica al cliente sobre los puntos ganados.
    Puede expandirse para enviar SMS, email, etc.
    """
    try:
        # Por ahora solo registrar en el log
        logger.info(f"Notificación: Cliente {cliente.get_nombre_completo()} ganó {puntos} puntos")
        
        # TODO: Implementar notificaciones por email/SMS
        # if cliente.email:
        #     enviar_email_puntos_ganados(cliente, puntos, venta)
        # 
        # if cliente.celular:
        #     enviar_sms_puntos_ganados(cliente, puntos, venta)
        
    except Exception as e:
        logger.error(f"Error en notificación de puntos: {str(e)}")

def procesar_puntos_retroactivos():
    """
    Función para procesar puntos de ventas anteriores al sistema.
    Se puede ejecutar como comando de Django.
    """
    try:
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
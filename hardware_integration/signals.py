from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import TrabajoImpresion, Impresora

@receiver(post_save, sender=Impresora)
def notify_printer_status_update(sender, instance, created, **kwargs):
    """
    Notifica cuando el estado de una impresora cambia.
    """
    channel_layer = get_channel_layer()
    schema_name = connection.schema_name
    group_name = f"ventas_{schema_name}"
    
    data = {
        'id': str(instance.id),
        'nombre': instance.nombre,
        'estado': instance.estado,
        'ubicacion': instance.ubicacion
    }
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'printer_status_update',
            'data': data
        }
    )

from django.core.cache import cache

@receiver(post_save, sender=TrabajoImpresion)
def notify_print_job_update(sender, instance, created, **kwargs):
    """
    Notifica a través de WebSockets cuando hay un cambio en la cola de impresión.
    Y limpia el Escudo de RAM (Redis) para que el agente vea el cambio instantáneo.
    """
    channel_layer = get_channel_layer()
    schema_name = connection.schema_name
    
    # 0. Limpiar el Escudo de RAM (Redis) para el usuario del trabajo
    if instance.usuario_id:
        cache_key = f"printer_jobs_{instance.usuario_id}"
        cache.delete(cache_key)
        # logger.debug(f"RAM Shield cleared for user {instance.usuario_id}")
    
    # Nombre del grupo igual al definido en el Consumer
    group_name = f"ventas_{schema_name}"
    
    # Datos a enviar al frontend
    data = {
        'id': str(instance.id),
        'tipo': instance.tipo,
        'estado': instance.estado,
        'prioridad': instance.prioridad,
        'venta_id': instance.venta_id,
        'timestamp': instance.fecha_creacion.isoformat() if instance.fecha_creacion else None
    }
    
    # 1. Enviar al grupo del FRONTEND (Navegador)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'print_job_update',
            'data': data
        }
    )

    # 2. Enviar al grupo del AGENTE LOCAL (Windows)
    # ⚡ Esto es lo que permite la impresión instantánea sin polling
    async_to_sync(channel_layer.group_send)(
        "hardware_agent_global",
        {
            'type': 'new_print_job',
            'data': {
                'id': str(instance.id),
                'mensaje': 'Nuevo trabajo de impresión disponible'
            }
        }
    )

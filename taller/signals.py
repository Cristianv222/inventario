"""Avisa por WebSocket al monitor del taller cuando cambia algo que afecta el ranking."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .consumers import GRUPO_RANKING


def _notificar(**kwargs):
    def enviar():
        try:
            layer = get_channel_layer()
            if layer is not None:
                async_to_sync(layer.group_send)(GRUPO_RANKING, {'type': 'ranking.update'})
        except Exception:
            # Si Redis no responde, jamás debe fallar el guardado de una orden o venta
            pass
    transaction.on_commit(enviar)


def _notificar_detalle(sender, instance, **kwargs):
    if getattr(instance, 'es_servicio', False):
        _notificar()


def conectar():
    from django.db.models.signals import post_save, post_delete
    from .models import OrdenTrabajo, ServicioOrden
    from ventas.models import Venta, DetalleVenta

    for modelo in (OrdenTrabajo, ServicioOrden):
        post_save.connect(_notificar, sender=modelo, dispatch_uid=f'rk_save_{modelo.__name__}')
        post_delete.connect(_notificar, sender=modelo, dispatch_uid=f'rk_del_{modelo.__name__}')
    post_save.connect(_notificar, sender=Venta, dispatch_uid='rk_save_Venta')
    post_save.connect(_notificar_detalle, sender=DetalleVenta, dispatch_uid='rk_save_DetalleVenta')

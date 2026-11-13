"""
Conexión de la generación automática de asientos.

IMPORTANTE: el envío real está detrás de settings.FINANZAS_CONTABILIDAD_AUTO
(apagado por defecto). Mientras sea False, los handlers no hacen nada, de modo
que agregar esta app NO cambia el comportamiento del sistema en producción.

Además, cualquier error contable se registra en el log pero NUNCA interrumpe la
operación original (una venta jamás debe fallar porque la contabilidad falló).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _auto_activo():
    return getattr(settings, 'FINANZAS_CONTABILIDAD_AUTO', False)


def _on_venta(sender, instance, created, **kwargs):
    if not _auto_activo() or not created:
        return
    if getattr(instance, 'estado', None) != 'COMPLETADA':
        return
    try:
        from .services.contabilidad import generar_asiento_venta
        generar_asiento_venta(instance)
    except Exception:
        logger.exception('No se pudo generar el asiento de la venta %s', instance.pk)


def _on_gasto(sender, instance, created, **kwargs):
    if not _auto_activo() or not created:
        return
    try:
        from .services.contabilidad import generar_asiento_gasto
        generar_asiento_gasto(instance)
    except Exception:
        logger.exception('No se pudo generar el asiento del gasto %s', instance.pk)


def conectar():
    """Conecta los receptores. Se llama desde FinanzasConfig.ready()."""
    from django.db.models.signals import post_save

    try:
        from ventas.models import Venta
        post_save.connect(_on_venta, sender=Venta, dispatch_uid='finanzas_asiento_venta')
    except Exception:
        logger.exception('No se pudo conectar el signal de ventas')

    try:
        from reportes.models import GastoDiario
        post_save.connect(_on_gasto, sender=GastoDiario, dispatch_uid='finanzas_asiento_gasto')
    except Exception:
        logger.exception('No se pudo conectar el signal de gastos')

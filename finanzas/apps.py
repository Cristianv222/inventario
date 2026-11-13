from django.apps import AppConfig


class FinanzasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finanzas'
    verbose_name = 'Finanzas (ERP)'

    def ready(self):
        # Conecta la generación automática de asientos. El envío real está
        # controlado por settings.FINANZAS_CONTABILIDAD_AUTO (apagado por
        # defecto): mientras esté en False, los handlers no hacen nada.
        from . import signals
        signals.conectar()

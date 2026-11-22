from django.apps import AppConfig


class TallerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'taller'

    def ready(self):
        # Señales para el ranking en tiempo real (monitor del taller)
        try:
            from . import signals
            signals.conectar()
        except Exception:
            pass

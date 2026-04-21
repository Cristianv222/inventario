import os
from celery import Celery

# Establecer el módulo de configuración de Django predeterminado para el programa 'celery'.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vpmotos.settings')

app = Celery('vpmotos')

# Usar una cadena aquí significa que el trabajador no tiene que serializar
# el objeto de configuración a los procesos secundarios.
# - namespace='CELERY' significa que todas las claves de configuración relacionadas con celery
#   deben tener el prefijo `CELERY_`.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Cargar módulos de tareas de todas las configuraciones de aplicaciones de Django registradas.
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

import os
import django
import sys

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vpmotos.settings')
django.setup()

from hardware_integration.models import TrabajoImpresion, Impresora
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

def check_jobs():
    print("--- TRABAJOS PENDIENTES ---")
    jobs = TrabajoImpresion.objects.filter(estado__in=['PENDIENTE', 'PROCESANDO']).order_by('-fecha_creacion')
    print(f"Total pendientes/procesando: {jobs.count()}")
    for j in jobs:
        print(f"ID: {j.id} | Estado: {j.estado} | Tipo: {j.tipo} | Impresora: {j.impresora} | Usuario: {j.usuario} | Creado: {j.fecha_creacion}")

    print("\n--- ULTIMOS 5 TRABAJOS ---")
    last_jobs = TrabajoImpresion.objects.all().order_by('-fecha_creacion')[:5]
    for j in last_jobs:
        print(f"ID: {j.id} | Estado: {j.estado} | Tipo: {j.tipo} | Creado: {j.fecha_creacion} | Error: {j.mensaje_error}")

    print("\n--- IMPRESORAS ACTIVAS ---")
    printers = Impresora.objects.filter(estado='ACTIVA')
    for p in printers:
        print(f"Nombre: {p.nombre} | Driver: {p.nombre_driver} | ID: {p.id} | Principal: {p.es_principal_tickets}")

    print("\n--- USUARIOS ---")
    users = User.objects.filter(is_active=True)
    for u in users:
        print(f"ID: {u.id} | Username: {u.username} | Staff: {u.is_staff}")

if __name__ == "__main__":
    check_jobs()

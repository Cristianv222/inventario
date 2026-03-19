from hardware_integration.models import TrabajoImpresion
from django_tenants.utils import schema_context
from django.utils import timezone
from datetime import timedelta

with schema_context('principal'):
    total = TrabajoImpresion.objects.count()
    pendientes = TrabajoImpresion.objects.filter(estado='PENDIENTE').count()
    recientes = TrabajoImpresion.objects.filter(fecha_creacion__gte=timezone.now() - timedelta(minutes=15))
    
    print(f"TOTAL_JOBS: {total}")
    print(f"PENDING_JOBS: {pendientes}")
    print(f"RECENT_JOBS (15m): {recientes.count()}")
    for j in recientes:
        print(f"  - ID: {j.id}, Status: {j.estado}, Printer: {j.impresora}")

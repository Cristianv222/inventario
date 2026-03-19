from hardware_integration.models import Impresora
from django_tenants.utils import schema_context

with schema_context('principal'):
    # Asegurar que existe al menos una impresora
    p, created = Impresora.objects.get_or_create(
        nombre='Impresora Termica POS',
        defaults={
            'nombre_driver': 'POS-80',
            'tipo_impresora': 'TICKET',
            'tipo_conexion': 'USB',
            'estado': 'ACTIVA',
            'codigo': 'POS-001',
            'es_principal_tickets': True
        }
    )
    if created:
        print(f"Creada impresora: {p.nombre}")
    else:
        print(f"La impresora ya existia: {p.nombre}")
    
    print(f"Total impresoras en 'principal': {Impresora.objects.count()}")
    for imp in Impresora.objects.all():
        print(f" - [{imp.id}] {imp.nombre} (Driver: {imp.nombre_driver})")

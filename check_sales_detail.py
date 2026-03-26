import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from ventas.models import DetalleVenta
from datetime import date
from decimal import Decimal

d = date(2026, 3, 25)

detalles = DetalleVenta.objects.filter(
    venta__fecha_hora__date=d,
    venta__estado='COMPLETADA',
    es_servicio=True
)

for d in detalles:
    print(f"ID: {d.id}, Tec: {d.tecnico.id if d.tecnico else 'None'}, Subtotal: {d.subtotal}, Descuento: {d.descuento}, Total: {d.total}")

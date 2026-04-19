import os
import django
import sys

# Añadir el directorio actual al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vpmotos.settings')
django.setup()

from ventas.models import Venta, DetalleVenta

v = Venta.objects.filter(numero_factura__icontains='32').last()
if v:
    print(f"Venta encontrada: {v.numero_factura} (ID: {v.id})")
    for d in v.detalleventa_set.all():
        print(f"  Detalle ID: {d.id}")
        print(f"    Item: {d.get_nombre_item()}")
        print(f"    Personalizado: '{d.nombre_personalizado}'")
        print(f"    Tipo Servicio: {d.tipo_servicio.nombre if d.tipo_servicio else 'N/A'}")
        print(f"    Producto: {d.producto.nombre if d.producto else 'N/A'}")
else:
    print("Venta no encontrada.")

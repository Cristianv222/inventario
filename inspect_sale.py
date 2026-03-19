import os
import django
import sys

# Añadir el path del proyecto
sys.path.append('/app')

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventario.settings')
django.setup()

from ventas.models import Venta, DetalleVenta

def check_sale(numero_factura):
    try:
        venta = Venta.objects.get(numero_factura=numero_factura)
        print(f"Venta: {venta.numero_factura} (ID: {venta.id})")
        print(f"Estado: {venta.estado}")
        print(f"Orden vinculada: {venta.orden_trabajo_id}")
        
        detalles = DetalleVenta.objects.filter(venta=venta)
        print(f"\nDetalles ({detalles.count()}):")
        for d in detalles:
            print(f"- Tipo: {'Servicio' if d.es_servicio else 'Producto'}")
            print(f"  Item: {d.tipo_servicio.nombre if d.tipo_servicio else (d.producto.nombre if d.producto else 'N/A')}")
            print(f"  Nombre Personalizado: '{d.nombre_personalizado}'")
            print(f"  Cantidad: {d.cantidad}, Total: {d.total}")
            
    except Venta.DoesNotExist:
        print(f"Venta {numero_factura} no encontrada")

if __name__ == "__main__":
    check_sale("FAC-000032")

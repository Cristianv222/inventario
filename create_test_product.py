import os
from django.core.files.base import ContentFile
from inventario.models import Producto, CategoriaProducto, Marca
from decimal import Decimal

# Ensure category and brand exist
cat, _ = CategoriaProducto.objects.get_or_create(nombre='TestCat', defaults={'porcentaje_ganancia': 10})
marca, _ = Marca.objects.get_or_create(nombre='TestBrand')

# Create product
p = Producto(
    nombre='Test Product API',
    categoria=cat,
    marca=marca,
    precio_compra=Decimal('100.00'),
    precio_venta=Decimal('150.00'), # Base price
    incluye_iva=True,
    activo=True,
    stock_actual=10
)
# Save to generate ID
p.save()

# Add image
p.imagen.save('test_image.jpg', ContentFile(b'fakeimagecontent'))
p.save()

print(f"Product created: {p.nombre} (ID: {p.id})")
print(f"Base Price: {p.precio_venta}")
print(f"Final Price (Expected ~172.50 with 15%): {p.precio_final}")
print(f"Image URL: {p.imagen.url}")

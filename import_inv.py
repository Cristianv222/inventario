import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vpmotos.settings")
django.setup()

import csv
from decimal import Decimal
from django_tenants.utils import schema_context
from django.utils.text import slugify

with schema_context("principal"):
    from inventario.models import Producto, CategoriaProducto, Marca
    creados = 0
    actualizados = 0
    errores = []
    with open("/app/INVENTARIO.csv", encoding="latin-1") as f:
        reader = csv.DictReader(f)
        for i, fila in enumerate(reader, 2):
            try:
                cat = fila["categoria"].strip().upper()
                if cat in ["HOGAR","ROPA","ELECTRONICOS"]:
                    continue
                marca = fila["marca"].strip().upper()
                cat_codigo = slugify(cat)[:20]
                categoria_obj, _ = CategoriaProducto.objects.get_or_create(nombre=cat, defaults={"activa":True,"porcentaje_ganancia":Decimal("40.00"),"codigo":cat_codigo})
                marca_obj, _ = Marca.objects.get_or_create(nombre=marca, defaults={"activa":True})
                pc = Decimal(str(fila["precio_compra"]).replace(",",".") or "0")
                pv = Decimal(str(fila["precio_venta"]).replace(",",".") or "0")
                st = max(0,int(float(fila.get("stock_actual","0") or "0")))
                sm = max(0,int(float(fila.get("stock_minimo","1") or "1")))
                _, created = Producto.objects.update_or_create(codigo_unico=fila["codigo_unico"].strip().upper(), defaults={"nombre":fila["nombre"].strip(),"descripcion":fila.get("descripcion","").strip(),"categoria":categoria_obj,"marca":marca_obj,"precio_compra":pc,"precio_venta":pv,"stock_actual":st,"stock_minimo":sm,"activo":True})
                if created: creados += 1
                else: actualizados += 1
                if i % 100 == 0: print(f"Procesados: {i}...")
            except Exception as e:
                errores.append(f"Fila {i}: {e}")
    print(f"Creados: {creados}")
    print(f"Actualizados: {actualizados}")
    print(f"Errores: {len(errores)}")
    for err in errores[:10]: print(err)

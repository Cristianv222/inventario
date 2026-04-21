import csv, psycopg2, re
from datetime import datetime, timezone

CSV_FILE = '/app/ejemplo_productos (1).csv'
conn = psycopg2.connect(dbname="inventario_db", user="inventario_user", password="Inv3nt4r10Prod2026", host="db", port="5432")
cur = conn.cursor()
cur.execute("SET search_path TO principal")

filas = []
with open(CSV_FILE, 'r', encoding='latin-1') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) >= 6:
            filas.append({
                'codigo_unico': parts[0].strip(),
                'nombre':       parts[1].strip(),
                'categoria':    parts[2].strip(),
                'marca':        parts[3].strip() or 'GENERICA',
                'precio_compra': parts[4].strip(),
                'precio_venta':  parts[5].strip(),
            })

print("Total filas: " + str(len(filas)))

categorias = {}
cat_counter = 1
for fila in filas:
    n = fila['categoria']
    if n and n not in categorias:
        codigo = re.sub(r'[^A-Z0-9]', '', n.upper())[:18] + str(cat_counter)
        cat_counter += 1
        cur.execute("INSERT INTO inventario_categoriaproducto (nombre, descripcion, porcentaje_ganancia, activa, codigo) VALUES (%s,%s,0,true,%s) ON CONFLICT (codigo) DO UPDATE SET nombre=EXCLUDED.nombre RETURNING id", (n, n, codigo))
        row = cur.fetchone()
        if row:
            categorias[n] = row[0]
cur.execute("SELECT id, nombre FROM inventario_categoriaproducto")
for rid, rn in cur.fetchall():
    categorias[rn] = rid
print("Categorias: " + str(len(categorias)))

marcas = {}
for fila in filas:
    n = fila['marca']
    if n and n not in marcas:
        cur.execute("INSERT INTO inventario_marca (nombre, descripcion, activa) VALUES (%s,%s,true) ON CONFLICT (nombre) DO UPDATE SET nombre=EXCLUDED.nombre RETURNING id", (n, n))
        row = cur.fetchone()
        if row:
            marcas[n] = row[0]
cur.execute("SELECT id, nombre FROM inventario_marca")
for rid, rn in cur.fetchall():
    marcas[rn] = rid
print("Marcas: " + str(len(marcas)))

ok = 0
errores = []
now = datetime.now(timezone.utc)
for i, fila in enumerate(filas):
    try:
        codigo = fila['codigo_unico']
        nombre = fila['nombre']
        cat    = fila['categoria']
        marca  = fila['marca']
        pc     = float(fila['precio_compra'] or 0)
        pv     = float(fila['precio_venta'] or 0)
        if not codigo or not nombre:
            errores.append("Fila " + str(i+1) + ": vacio")
            continue
        cid = categorias.get(cat)
        mid = marcas.get(marca)
        if not cid or not mid:
            errores.append("Fila " + str(i+1) + ": cat=" + str(cat) + " marca=" + str(marca))
            continue
        cur.execute("INSERT INTO inventario_producto (codigo_unico, nombre, descripcion, precio_compra, precio_venta, stock_actual, stock_minimo, incluye_iva, activo, fecha_creacion, categoria_id, marca_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (codigo_unico) DO UPDATE SET nombre=EXCLUDED.nombre, precio_compra=EXCLUDED.precio_compra, precio_venta=EXCLUDED.precio_venta", (codigo, nombre, '', pc, pv, 0, 0, True, True, now, cid, mid))
        ok += 1
    except Exception as e:
        errores.append("Fila " + str(i+1) + ": " + str(e))
        conn.rollback()

conn.commit()
cur.close()
conn.close()
print("Importados: " + str(ok))
print("Errores: " + str(len(errores)))
for e in errores[:10]:
    print("  " + e)

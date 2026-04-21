import psycopg2, re

CSV_FILE = '/app/ejemplo_productos (1).csv'
conn = psycopg2.connect(dbname="inventario_db", user="inventario_user", password="Inv3nt4r10Prod2026", host="db", port="5432")
cur = conn.cursor()
cur.execute("SET search_path TO principal")

ok = 0
errores = []
with open(CSV_FILE, 'r', encoding='latin-1') as f:
    for i, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) < 7:
            continue
        codigo = parts[0].strip()
        col7   = parts[6].strip()
        match  = re.match(r'^(\d+)', col7)
        stock  = int(match.group(1)) if match else 0
        try:
            cur.execute("UPDATE inventario_producto SET stock_actual=%s WHERE codigo_unico=%s", (stock, codigo))
            ok += 1
        except Exception as e:
            errores.append("Fila " + str(i+1) + ": " + str(e))
            conn.rollback()

conn.commit()
cur.close()
conn.close()
print("Actualizados: " + str(ok))
print("Errores: " + str(len(errores)))
for e in errores[:5]:
    print("  " + e)

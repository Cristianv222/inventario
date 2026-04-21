#!/bin/bash
set -e

echo "Esperando a que la base de datos esté lista..."
while ! pg_isready -h db -p 5432 -U ${DB_USER} -d ${DB_NAME}; do
    echo "Esperando a PostgreSQL..."
    sleep 2
done
echo "Base de datos lista!"

# ============================================================
# SCRIPT DE MIGRACIÓN AUTOMÁTICA DE ESQUEMAS (PRODUCCIÓN)
# ============================================================
echo "Verificando si existen datos pendientes en esquema 'principal'..."
python manage.py shell << EOF
import os
import psycopg2
from django.db import connection

def migrate_schema():
    with connection.cursor() as cursor:
        # 1. Verificar si existe el esquema principal
        cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'principal'")
        if not cursor.fetchone():
            print("INFO: No se detectó esquema 'principal'. Saltando migración de datos.")
            return

        print("⚠️ DETECTADO ESQUEMA 'PRINCIPAL'. Iniciando migración de tablas a 'public'...")
        
        # 2. Mover tablas
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'principal'")
        tables = cursor.fetchall()
        for (table,) in tables:
            try:
                # Evitar mover tablas que ya existen en public y que son compartidas
                cursor.execute(f"SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table}'")
                if cursor.fetchone():
                    print(f"ℹ️ Tabla {table} ya existe en public. Omitiendo.")
                    continue
                    
                cursor.execute(f"ALTER TABLE principal.{table} SET SCHEMA public")
                print(f"✅ Movida tabla: {table}")
            except Exception as e:
                print(f"❌ Error al mover tabla {table}: {e}")
        
        # 3. Mover secuencias
        cursor.execute("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'principal' AND c.relkind = 'S'")
        sequences = cursor.fetchall()
        for (seq,) in sequences:
            try:
                # Evitar mover secuencias que ya existen
                cursor.execute(f"SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relname = '{seq}'")
                if cursor.fetchone():
                    continue
                    
                cursor.execute(f"ALTER SEQUENCE principal.{seq} SET SCHEMA public")
                print(f"✅ Movida secuencia: {seq}")
            except Exception as e:
                print(f"ℹ️ Secuencia {seq} saltada: {e}")

        print("🚀 Migración de datos completada satisfactoriamente.")

migrate_schema()
EOF

echo "Aplicando migraciones estándar..."
python manage.py migrate --noinput


echo "Recopilando archivos estáticos..."
python manage.py collectstatic --noinput --clear

# ============================================================
# Crear sucursal principal y dominios si no existen
# ============================================================
echo "Verificando sucursal principal..."
python manage.py shell << EOF
import datetime
from core.models import Sucursal, DominioSucursal
import os

if not Sucursal.objects.exists():
    print("Creando sucursal principal...")
    sucursal = Sucursal(
        codigo='PRINCIPAL',
        nombre='VPMOTOS Matriz',
        nombre_corto='Matriz',
        direccion='Dirección Principal',
        ciudad='Quito',
        provincia='Pichincha',
        es_principal=True,
        activa=True,
        fecha_apertura=datetime.date.today()
    )
    sucursal.save()
    print(f"Sucursal creada: {sucursal}")
else:
    sucursal = Sucursal.objects.filter(es_principal=True).first()
    print(f"Sucursal principal ya existe: {sucursal}")

# Dominios de producción
dominios_base = [
    {'domain': os.environ.get('PRIMARY_DOMAIN', 'vp-motos.valktek.com'), 'is_primary': True},
    {'domain': 'inventario-web', 'is_primary': False},
]

for d in dominios_base:
    obj, created = DominioSucursal.objects.get_or_create(
        domain=d['domain'],
        defaults={'tenant': sucursal, 'is_primary': d['is_primary']}
    )
    if created:
        print(f"Dominio creado: {obj.domain}")
    else:
        print(f"Dominio ya existe: {obj.domain}")
EOF

# ============================================================
# Crear superusuario desde variables de entorno
# ============================================================
echo "Verificando superusuario..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
import os

User = get_user_model()
admin_user = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
admin_email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@vp-motos.com')
admin_pass = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if not admin_pass:
    print('ERROR: DJANGO_SUPERUSER_PASSWORD no está definida')
    exit(1)

if not User.objects.filter(usuario=admin_user).exists():
    User.objects.create_superuser(
        usuario=admin_user,
        email=admin_email,
        password=admin_pass,
        nombre='Administrador',
        apellido='Sistema'
    )
    print(f'Superusuario creado: {admin_user}')
else:
    print(f'Superusuario ya existe: {admin_user}')
EOF


# Cargar datos iniciales si existen
if [ -f "/app/ventas/fixtures/initial_data.json" ]; then
    echo "Cargando datos iniciales..."
    python manage.py loaddata /app/ventas/fixtures/initial_data.json || echo "Datos iniciales ya cargados o error al cargar"
fi

echo "Iniciando servidor en modo producción con Daphne (ASGI)..."
exec daphne -b 0.0.0.0 -p 8000 vpmotos.asgi:application
#!/bin/bash

# Salir si algún comando falla
set -e

echo "Esperando a que la base de datos esté lista..."
while ! pg_isready -h db -p 5432 -U ${DB_USER} -d ${DB_NAME}; do
    echo "Esperando a PostgreSQL..."
    sleep 2
done

echo "Base de datos lista!"

# Ejecutar migraciones
echo "Aplicando migraciones..."
python manage.py migrate_schemas --noinput

# Recopilar archivos estáticos
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

# Solo crear si no existe
if not Sucursal.objects.exists():
    print("Creando sucursal principal...")
    sucursal = Sucursal(
        schema_name='principal',
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

# Dominios base siempre necesarios
dominios_base = [
    {'domain': 'localhost', 'is_primary': True},
    {'domain': 'web',       'is_primary': False},
    {'domain': '127.0.0.1', 'is_primary': False},
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

# Dominio ngrok si está definido en variable de entorno
ngrok_domain = os.environ.get('NGROK_DOMAIN', '')
if ngrok_domain:
    obj, created = DominioSucursal.objects.get_or_create(
        domain=ngrok_domain,
        defaults={'tenant': sucursal, 'is_primary': False}
    )
    if created:
        print(f"Dominio ngrok creado: {obj.domain}")
    else:
        print(f"Dominio ngrok ya existe: {obj.domain}")
EOF

# ============================================================
# Crear superusuario si no existe (en schema principal)
# ============================================================
echo "Verificando superusuario..."
python manage.py shell << EOF
from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model

with schema_context('principal'):
    User = get_user_model()
    if not User.objects.filter(usuario='admin').exists():
        User.objects.create_superuser(
            usuario='admin',
            email='admin@inventario.com',
            password='admin123',
            nombre='Administrador',
            apellido='Sistema'
        )
        print('Superusuario creado: admin / admin123')
    else:
        print('Superusuario ya existe')
EOF

# Cargar datos iniciales si existen
if [ -f "/app/ventas/fixtures/initial_data.json" ]; then
    echo "Cargando datos iniciales..."
    python manage.py loaddata /app/ventas/fixtures/initial_data.json || echo "Datos iniciales ya cargados o error al cargar"
fi

echo "Iniciando servidor Django..."

# Detectar DEBUG correctamente
DEBUG_LOWER=$(echo "$DEBUG" | tr '[:upper:]' '[:lower:]')

if [ "$DEBUG_LOWER" = "false" ]; then
    echo "Modo producción - usando Gunicorn..."
    exec gunicorn vpmotos.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 3 \
        --timeout 30 \
        --keep-alive 2 \
        --log-level info \
        --access-logfile - \
        --error-logfile -
else
    echo "Modo desarrollo - usando servidor de desarrollo..."
    exec python manage.py runserver 0.0.0.0:8000
fi
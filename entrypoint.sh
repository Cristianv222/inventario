#!/bin/bash
set -e

echo "Esperando a que la base de datos esté lista..."
while ! pg_isready -h db -p 5432 -U ${DB_USER} -d ${DB_NAME}; do
    echo "Esperando a PostgreSQL..."
    sleep 2
done
echo "Base de datos lista!"

echo "Aplicando migraciones..."
python manage.py migrate_schemas --noinput

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
from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model
import os

with schema_context('principal'):
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

echo "Iniciando servidor en modo producción con Gunicorn..."
exec gunicorn vpmotos.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 2 \
    --timeout 60 \
    --keep-alive 2 \
    --log-level warning \
    --access-logfile - \
    --error-logfile -
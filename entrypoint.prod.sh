#!/bin/bash
set -e

echo "🚀 Iniciando High Voltage - MODO PRODUCCIÓN..."

# Esperar PostgreSQL
echo "⏳ Esperando PostgreSQL..."
while ! pg_isready -h db -p 5432 -U ${DB_USER} -d ${DB_NAME}; do
    echo "PostgreSQL no disponible - esperando..."
    sleep 2
done
echo "✅ PostgreSQL listo!"

# Migraciones
echo "📦 Aplicando migraciones..."
python manage.py migrate --noinput

# Archivos estáticos
echo "📁 Recopilando archivos estáticos..."
python manage.py collectstatic --noinput --clear

# Crear superusuario
echo "👤 Configurando superusuario..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()

# Crear superusuario si no existe
if not User.objects.filter(usuario='hvadmin').exists():
    User.objects.create_superuser(
        usuario='hvadmin',
        email='admin@fronteratech.ec',
        password='HV@FronteraTech2025!',
        nombre='High Voltage',
        apellido='Administrator'
    )
    print('✅ Superusuario creado')
    print('👤 Usuario: hvadmin')
    print('🔑 Password: HV@FronteraTech2025!')
    print('🔗 https://high-voltage.fronteratech.ec/admin/')
    print('⚠️  CAMBIA LA CONTRASEÑA DESPUÉS DEL PRIMER LOGIN')
else:
    print('ℹ️  Superusuario "hvadmin" ya existe')
EOF

# Datos iniciales
if [ -f "/app/ventas/fixtures/initial_data.json" ]; then
    echo "📥 Cargando datos iniciales..."
    python manage.py loaddata /app/ventas/fixtures/initial_data.json || echo "⚠️  Datos ya cargados"
fi

echo "🔒 Iniciando Gunicorn..."
exec gunicorn vpmotos.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 1 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout 120 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance
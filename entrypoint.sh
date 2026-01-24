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

# Crear superusuario si no existe
echo "Creando superusuario si no existe..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
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

# ✅ CORRECCIÓN: Detectar DEBUG correctamente
# Convertir a minúsculas para comparar
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
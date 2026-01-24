"""
Django settings for vpmotos project.
CONFIGURACIÓN MULTI-SUCURSAL CON DJANGO-TENANTS
"""

from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-24ps2o^$&m@47b$evbyo5#&by5+y_^fd4-p761zv@h#niikhtn')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# ✅ HOSTS PERMITIDOS - Leer de variable de entorno
ALLOWED_HOSTS = []

# Hosts por defecto
default_hosts = ['localhost', '127.0.0.1', 'web', '.ngrok-free.app', '.ngrok.io', '.ngrok-free.dev']
ALLOWED_HOSTS.extend(default_hosts)

# Leer de variable de entorno
if os.environ.get('ALLOWED_HOSTS'):
    env_hosts = os.environ.get('ALLOWED_HOSTS')
    if env_hosts == '*':
        ALLOWED_HOSTS = ['*']
    else:
        additional_hosts = [host.strip() for host in env_hosts.split(',') if host.strip()]
        ALLOWED_HOSTS.extend(additional_hosts)

# Agregar Railway hosts si existe
if 'RAILWAY_ENVIRONMENT' in os.environ:
    ALLOWED_HOSTS.extend(['*.railway.app', '*.up.railway.app'])

# ✅ CSRF TRUSTED ORIGINS - Incluir dominio de producción
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://localhost:8001',
    'http://127.0.0.1:8000',
    'http://127.0.0.1:8001',
    'https://*.ngrok-free.app',
    'https://*.ngrok.io',
    'https://*.ngrok-free.dev',
]

# Agregar dominio de producción a CSRF_TRUSTED_ORIGINS
if not DEBUG:
    CSRF_TRUSTED_ORIGINS.extend([
        'https://high-voltage.fronteratech.ec',
        'https://www.high-voltage.fronteratech.ec',
        'https://fronteratech.ec',
    ])

# ✅ Para que ngrok y NPM funcionen correctamente
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# ==================== DJANGO-TENANTS CONFIGURATION ====================

# ✅ INSTALLED APPS - django_tenants DEBE SER EL PRIMERO
INSTALLED_APPS = [
    'django_tenants',  # ← DEBE IR PRIMERO SIEMPRE
    
    # Django apps - contenttypes DEBE ir antes de admin
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'widget_tweaks',

    # Aplicaciones propias
    'core.apps.CoreConfig',
    'usuarios.apps.UsuariosConfig',
    'inventario.apps.InventarioConfig',
    'clientes.apps.ClientesConfig',
    'ventas.apps.VentasConfig',
    'taller.apps.TallerConfig',
    'compras.apps.ComprasConfig',
    'reportes.apps.ReportesConfig',
]

# ✅ SHARED APPS - Apps en schema PUBLIC (compartidas entre todas las sucursales)
SHARED_APPS = [
    'django_tenants',  # Requerido
    
    # Django apps necesarias en PUBLIC
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.admin',
    'django.contrib.humanize',
    
    # Third party compartidas
    'widget_tweaks',
    
    # Apps compartidas entre sucursales
    'core.apps.CoreConfig',      # Sucursales, configuración global
    'usuarios.apps.UsuariosConfig',  # Usuarios globales (login centralizado)
]

# ✅ TENANT APPS - Apps en cada schema de sucursal (datos aislados por sucursal)
TENANT_APPS = [
    'django.contrib.contenttypes',  # Necesario para relaciones en cada schema
    
    # Apps con datos independientes por sucursal
    'inventario.apps.InventarioConfig',  # Stock independiente por sucursal
    'clientes.apps.ClientesConfig',      # Clientes independientes por sucursal
    'ventas.apps.VentasConfig',          # Ventas independientes por sucursal
    'taller.apps.TallerConfig',          # Órdenes de trabajo por sucursal
    'compras.apps.ComprasConfig',        # Compras por sucursal
    'reportes.apps.ReportesConfig',      # Reportes por sucursal
]

# ✅ TENANT MODEL CONFIGURATION
TENANT_MODEL = "core.Sucursal"  # Modelo que representa cada sucursal
TENANT_DOMAIN_MODEL = "core.DominioSucursal"  # Modelo de dominios/subdominios

# ✅ PUBLIC SCHEMA (Schema donde viven las apps compartidas)
PUBLIC_SCHEMA_NAME = 'public'
PUBLIC_SCHEMA_URLCONF = 'vpmotos.urls'  # URLs públicas (admin, login, etc.)

# ==================== MIDDLEWARE ====================

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',  # ← DEBE IR PRIMERO
    
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Middleware personalizado de roles
    'core.middleware.role_middleware.RoleMiddleware',
    
    # ✅ FASE 2 ACTIVADO - Middlewares de sucursales
    'core.middleware.tenant_middleware.TenantFromUserMiddleware',
    'core.middleware.schema_middleware.AutoSchemaMiddleware',
]

# Agregar WhiteNoise para archivos estáticos en producción
if not DEBUG:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'vpmotos.urls'

# ==================== TEMPLATES ====================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                
                # ✅ FASE 2 ACTIVADO - Context processor de sucursales
                'core.context_processors.sucursal_actual',
            ],
        },
    },
]

WSGI_APPLICATION = 'vpmotos.wsgi.application'

# ==================== DATABASE ====================

# ✅ CONFIGURACIÓN CON DJANGO-TENANTS
if 'DATABASE_URL' in os.environ:
    DATABASES = {
        'default': dj_database_url.parse(
            os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
    # ✅ CAMBIAR ENGINE para django-tenants
    DATABASES['default']['ENGINE'] = 'django_tenants.postgresql_backend'
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django_tenants.postgresql_backend',  # ✅ CAMBIO CRÍTICO AQUÍ
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }

# ✅ DATABASE ROUTER para django-tenants
DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

# ==================== PASSWORD VALIDATION ====================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==================== INTERNATIONALIZATION ====================

LANGUAGE_CODE = 'es-ec'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True

# ==================== STATIC FILES ====================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ==================== MEDIA FILES ====================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ==================== DEFAULT PRIMARY KEY ====================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==================== CUSTOM USER MODEL ====================

AUTH_USER_MODEL = 'usuarios.Usuario'

# ==================== VPMOTOS CONFIGURATION ====================

VPMOTOS_SETTINGS = {
    'COMPANY_NAME': os.environ.get('COMPANY_NAME', 'VPMOTOS - High Voltage'),
    'COMPANY_ADDRESS': os.environ.get('COMPANY_ADDRESS', 'Ecuador Pichincha Cayambe Panamericana E35'),
    'COMPANY_PHONE': os.environ.get('COMPANY_PHONE', '0961278095'),
    'COMPANY_EMAIL': os.environ.get('COMPANY_EMAIL', 'info@fronteratech.ec'),
    'COMPANY_TAX_ID': os.environ.get('COMPANY_TAX_ID', '0401234567001'),
    'IVA_PERCENTAGE': float(os.environ.get('IVA_PERCENTAGE', '15.0')),
    'DEFAULT_CURRENCY': os.environ.get('DEFAULT_CURRENCY', 'USD'),
}

# ==================== AUTHENTICATION ====================

LOGIN_URL = 'usuarios:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'usuarios:login'

# ==================== SECURITY (PRODUCTION) ====================

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_REFERRER_POLICY = 'same-origin'
"""
URL configuration for vpmotos project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from rest_framework.authtoken import views as authtoken_views
from django.conf.urls.static import static
from django.http import FileResponse, HttpResponse
import os

def serve_sw(request):
    path_sw = os.path.join(settings.BASE_DIR, 'sw.js')
    return FileResponse(open(path_sw, 'rb'), content_type='application/javascript')

def serve_manifest(request):
    path_manifest = os.path.join(settings.BASE_DIR, 'manifest.json')
    return FileResponse(open(path_manifest, 'rb'), content_type='application/manifest+json')

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sw.js', serve_sw, name='sw'),
    path('manifest.json', serve_manifest, name='manifest'),
    path('', include('core.urls', namespace='core')),
    path('usuarios/', include('usuarios.urls')),
    path('ventas/', include('ventas.urls')),
    path('clientes/', include('clientes.urls')),
    path('inventario/', include('inventario.urls')),
    path('taller/', include('taller.urls', namespace='taller')),
    path('reportes/', include('reportes.urls', namespace='reportes')),
    path('hardware/', include('hardware_integration.urls', namespace='hardware_integration')),
    path('api/hardware/', include('hardware_integration.api.urls', namespace='hardware_api')),
    path('electronic-invoicing/', include(('electronic_invoicing.urls', 'electronic_invoicing'), namespace='electronic_invoicing')),
    path('api/v1/token-auth/', authtoken_views.obtain_auth_token, name='api_token_auth'),
    
    # Endpoints JWT (JSON Web Token) ✅ NUEVO
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
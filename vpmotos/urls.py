"""
URL configuration for vpmotos project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import FileResponse, HttpResponse
import os

def serve_sw(request):
    path_sw = os.path.join(settings.BASE_DIR, 'sw.js')
    return FileResponse(open(path_sw, 'rb'), content_type='application/javascript')

def serve_manifest(request):
    path_manifest = os.path.join(settings.BASE_DIR, 'manifest.json')
    return FileResponse(open(path_manifest, 'rb'), content_type='application/manifest+json')

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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
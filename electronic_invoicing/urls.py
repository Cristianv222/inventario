from django.urls import path
from . import views

app_name = 'electronic_invoicing'

urlpatterns = [
    path('gestion/', views.gestion_facturacion, name='gestion'),
    path('api/config/guardar/', views.guardar_config_sri, name='guardar_config'),
    path('descargar/xml/<uuid:pk>/', views.descargar_xml_sri, name='descargar_xml'),
    path('descargar/pdf/<uuid:pk>/', views.descargar_pdf_sri, name='descargar_pdf'),
    path('ver/xml/<uuid:pk>/', views.ver_xml_sri, name='ver_xml'),
    path('api/xml/<uuid:pk>/', views.api_xml_sri, name='api_xml'),
    path('api/punto/actualizar-secuencial/', views.actualizar_secuencial_sri, name='actualizar_secuencial'),
    path('api/punto/crear/', views.crear_punto_emision, name='crear_punto'),
    path('api/punto/toggle/', views.toggle_punto_emision, name='toggle_punto'),
    path('api/certificado/subir/', views.subir_certificado_sri, name='subir_certificado'),
    path('reintentar/factura/<uuid:pk>/', views.reintentar_factura, name='reintentar_factura'),
    path('api/punto/editar/', views.editar_punto_emision, name='editar_punto'),
]

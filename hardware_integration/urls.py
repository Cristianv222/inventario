# apps/hardware_integration/urls.py

from django.urls import path
from . import views

app_name = 'hardware_integration'

urlpatterns = [
    # Dashboard principal
    path('', views.HardwareDashboardView.as_view(), name='dashboard'),
    path('test-impresion/', views.ImpresoraListView.as_view(), name='test_impresion'),
    
    # Impresoras
    path('impresoras/', views.ImpresoraListView.as_view(), name='impresora_list'),
    path('impresoras/nueva/', views.ImpresoraCreateView.as_view(), name='impresora_create'),
    path('impresoras/<uuid:pk>/', views.ImpresoraDetailView.as_view(), name='impresora_detail'),
    path('impresoras/<uuid:pk>/editar/', views.ImpresoraUpdateView.as_view(), name='impresora_update'),
    path('impresoras/<uuid:pk>/eliminar/', views.ImpresoraDeleteView.as_view(), name='impresora_delete'),
    
    # Acciones de Impresoras
    path('impresoras/<uuid:pk>/test-conexion/', views.TestConexionView.as_view(), name='impresora_test_conexion'),
    path('impresoras/<uuid:pk>/test-pagina/', views.TestPaginaPruebaView.as_view(), name='impresora_test_pagina'),
    path('impresoras/<uuid:pk>/test/', views.TestPaginaPruebaView.as_view(), name='impresora_test'),
    path('impresoras/<uuid:pk>/mantenimiento/', views.MantenimientoImpresoraView.as_view(), name='impresora_mantenimiento'),
    
    # Plantillas de Impresión
    path('plantillas/', views.PlantillaListView.as_view(), name='plantilla_list'),
    path('plantillas/nueva/', views.PlantillaCreateView.as_view(), name='plantilla_create'),
    path('plantillas/<uuid:pk>/', views.PlantillaDetailView.as_view(), name='plantilla_detail'),
    path('plantillas/<uuid:pk>/editar/', views.PlantillaUpdateView.as_view(), name='plantilla_update'),
    path('plantillas/<uuid:pk>/eliminar/', views.PlantillaDeleteView.as_view(), name='plantilla_delete'),
    
    # Configuraciones de Códigos de Barras
    path('codigos-barras/', views.ConfigCodigoBarrasListView.as_view(), name='config_codigo_list'),
    path('codigos-barras/nueva/', views.ConfigCodigoBarrasCreateView.as_view(), name='config_codigo_create'),
    path('codigos-barras/<uuid:pk>/', views.ConfigCodigoBarrasDetailView.as_view(), name='config_codigo_detail'),
    path('codigos-barras/<uuid:pk>/editar/', views.ConfigCodigoBarrasUpdateView.as_view(), name='config_codigo_update'),
    
    # Gavetas de Dinero
    path('gavetas/', views.GavetaDineroListView.as_view(), name='gaveta_list'),
    path('gavetas/nueva/', views.GavetaDineroCreateView.as_view(), name='gaveta_create'),
    path('gavetas/<uuid:pk>/', views.GavetaDineroDetailView.as_view(), name='gaveta_detail'),
    path('gavetas/<uuid:pk>/editar/', views.GavetaDineroUpdateView.as_view(), name='gaveta_update'),
    path('gavetas/<uuid:pk>/abrir/', views.AbrirGavetaView.as_view(), name='gaveta_abrir'),
    path('gavetas/test/', views.AbrirGavetaView.as_view(), name='gaveta_test'),
    
    # Escáneres
    path('escaneres/', views.EscanerListView.as_view(), name='escaner_list'),
    path('escaneres/nuevo/', views.EscanerCreateView.as_view(), name='escaner_create'),
    path('escaneres/<uuid:pk>/', views.EscanerDetailView.as_view(), name='escaner_detail'),
    path('escaneres/<uuid:pk>/editar/', views.EscanerUpdateView.as_view(), name='escaner_update'),
    
    # Registros de Impresión
    path('registros/', views.RegistroImpresionListView.as_view(), name='registro_impresion_list'),
    
    # APIs para Frontend
    path('api/estado-impresoras/', views.ImpresoraStatusAPIView.as_view(), name='api_estado_impresoras'),
    path('api/imprimir-etiqueta/', views.ImprimirEtiquetaAPIView.as_view(), name='api_imprimir_etiqueta'),
    path('api/generar-codigo/', views.GenerarCodigoBarrasAPIView.as_view(), name='api_generar_codigo'),
]

from django.urls import path
from . import views

app_name = 'clientes'

urlpatterns = [
    # ========== VISTAS PRINCIPALES (URLs específicas primero) ==========
    path('', views.lista_clientes, name='lista_clientes'),
    path('nuevo/', views.crear_cliente, name='crear_cliente'),
    path('reportes/', views.reporte_clientes, name='reporte_clientes'),
    
    # URLs con parámetros después
    path('<int:cliente_id>/', views.detalle_cliente, name='detalle_cliente'),
    path('<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
    path('<int:cliente_id>/eliminar/', views.eliminar_cliente, name='eliminar_cliente'),
    
    # ========== GESTIÓN DE MOTOS ==========
    path('<int:cliente_id>/motos/nueva/', views.agregar_moto, name='agregar_moto'),
    path('motos/<int:moto_id>/editar/', views.editar_moto, name='editar_moto'),
    
    # ========== SISTEMA DE PUNTOS ==========
    path('<int:cliente_id>/puntos/', views.gestionar_puntos, name='gestionar_puntos'),
    path('<int:cliente_id>/canjear-puntos/', views.canjear_puntos, name='canjear_puntos'),
    
    # ========== HISTORIAL ==========
    path('<int:cliente_id>/historial/', views.historial_completo, name='historial_completo'),
    path('<int:cliente_id>/historial/nuevo/', views.agregar_historial, name='agregar_historial'),
    
    # ========== APIs PARA INTEGRACIÓN ==========
    # URLs específicas de API primero
    path('api/buscar/', views.api_buscar_clientes, name='api_buscar_clientes'),
    path('api/buscar-simple/', views.buscar_cliente_api, name='buscar_cliente_api'),
    path('api/sri/buscar/', views.api_buscar_sri, name='api_buscar_sri'),
    path('api/puntos/procesar/', views.api_procesar_puntos_venta, name='api_procesar_puntos_venta'),
    
    # ✅ NUEVAS RUTAS PARA CREACIÓN RÁPIDA DESDE POS
    path('api/crear-rapido/', views.api_crear_cliente_rapido, name='api_crear_cliente_rapido'),
    path('api/validar-identificacion/', views.api_validar_identificacion, name='api_validar_identificacion'),
    
    # URLs de API con parámetros después
    path('api/<int:cliente_id>/puntos/', views.api_cliente_puntos, name='api_cliente_puntos'),
    path('<int:cliente_id>/historial/json/', views.api_historial_cliente, name='api_historial_cliente'),
]
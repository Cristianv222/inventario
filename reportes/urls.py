from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    # ================== DASHBOARD PRINCIPAL ==================
    path('', views.dashboard_reportes, name='dashboard'),
    
    # ================== CAJA DIARIA ==================
    path('caja/', views.caja_diaria, name='caja_diaria'),
    path('caja/cerrar/', views.cerrar_caja, name='cerrar_caja'),
    path('caja/reabrir/<str:fecha_str>/', views.reabrir_caja, name='reabrir_caja'),
    
    # ================== GASTOS ==================
    path('gastos/', views.lista_gastos, name='lista_gastos'),
    path('gastos/crear/', views.crear_gasto, name='crear_gasto'),
    path('gastos/<int:pk>/editar/', views.editar_gasto, name='editar_gasto'),
    path('gastos/<int:pk>/aprobar/', views.aprobar_gasto, name='aprobar_gasto'),
    path('gastos/<int:pk>/rechazar/', views.rechazar_gasto, name='rechazar_gasto'),
    
    # ================== ESTADÍSTICAS Y REPORTES ==================
    path('estadisticas/', views.estadisticas_ventas, name='estadisticas_ventas'),
    path('estadisticas/comparativo/', views.comparativo_ventas, name='comparativo_ventas'),
    
    # ================== MOVIMIENTOS DE CAJA ==================
    path('movimientos/', views.lista_movimientos, name='lista_movimientos'),
    
    # ================== REPORTES MENSUALES ==================
    path('mensuales/', views.reportes_mensuales, name='reportes_mensuales'),
    
    # ================== APIs PARA DASHBOARD ==================
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/caja-status/', views.api_caja_status, name='api_caja_status'),
    
    # ================== EXPORTACIONES ==================
    path('exportar/', views.exportar_reporte, name='exportar_reporte'),
]
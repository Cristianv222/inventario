from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    # ── Dashboard ─────────────────────────────────────────────────
    path('', views.dashboard_reportes, name='dashboard'),

    # ── Reporte de ventas unificado (POS + online + taller) ───────
    path('ventas/', views.reporte_ventas_completo, name='reporte_ventas_completo'),

    # ── Reportes por técnico ──────────────────────────────────────
    path('tecnicos/', views.reporte_tecnicos, name='reporte_tecnicos'),

    # ── Reportes por vendedor ─────────────────────────────────────
    path('vendedores/', views.reporte_vendedores, name='reporte_vendedores'),

    # ── Caja diaria ───────────────────────────────────────────────
    path('caja/', views.caja_diaria, name='caja_diaria'),
    path('caja/cerrar/', views.cerrar_caja, name='cerrar_caja'),
    path('caja/reabrir/<str:fecha_str>/', views.reabrir_caja, name='reabrir_caja'),
    path('caja/<int:cierre_id>/desglose/', views.guardar_desglose_billetes, name='guardar_desglose'),

    # ── Gastos (módulo independiente) ─────────────────────────────
    path('gastos/', views.lista_gastos, name='lista_gastos'),
    path('gastos/crear/', views.crear_gasto, name='crear_gasto'),
    path('gastos/<int:pk>/editar/', views.editar_gasto, name='editar_gasto'),
    path('gastos/<int:pk>/aprobar/', views.aprobar_gasto, name='aprobar_gasto'),
    path('gastos/<int:pk>/rechazar/', views.rechazar_gasto, name='rechazar_gasto'),

    # ── Estadísticas y reportes mensuales ────────────────────────
    path('estadisticas/', views.estadisticas_ventas, name='estadisticas_ventas'),
    path('estadisticas/comparativo/', views.comparativo_ventas, name='comparativo_ventas'),
    path('mensuales/', views.reportes_mensuales, name='reportes_mensuales'),

    # ── Movimientos de caja ───────────────────────────────────────
    path('movimientos/', views.lista_movimientos, name='lista_movimientos'),

    # ── APIs JSON ─────────────────────────────────────────────────
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/caja-status/', views.api_caja_status, name='api_caja_status'),

    # ── Exportar ──────────────────────────────────────────────────
    path('exportar/', views.exportar_reporte, name='exportar_reporte'),
]
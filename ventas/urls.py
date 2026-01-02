# ventas/urls.py
from django.urls import path
from . import views

app_name = 'ventas'

urlpatterns = [
    # ========== PUNTO DE VENTA (POS) - PÁGINA PRINCIPAL ==========
    path('', views.punto_venta, name='punto_venta'),  # POS como página principal
    path('pos/', views.punto_venta, name='pos'),  # Alias
    path('pos/procesar/', views.api_procesar_venta_pos, name='api_procesar_venta_pos'),
    path('pos/orden/<int:orden_id>/', views.pos_con_orden, name='pos_con_orden'),
    
    # ========== GESTIÓN DE VENTAS ==========
    path('lista/', views.lista_ventas, name='lista_ventas'),  # Lista de ventas movida aquí
    path('detalle/<int:venta_id>/', views.detalle_venta, name='detalle_venta'),
    path('crear/', views.crear_venta, name='crear_venta'),
    path('<int:venta_id>/editar/', views.editar_venta, name='editar_venta'),
    path('<int:venta_id>/anular/', views.anular_venta, name='anular_venta'),
    path('<int:venta_id>/agregar-producto/', views.agregar_producto, name='agregar_producto'),
    
    # ========== APIs DEL DASHBOARD ==========
    path('api/dashboard-stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/todas-ventas/', views.api_todas_ventas, name='api_todas_ventas'),
    path('api/grafico-ventas/', views.api_grafico_ventas, name='api_grafico_ventas'),
    path('api/productos-top/', views.api_productos_top, name='api_productos_top'),
    path('api/resumen-mensual/', views.api_resumen_mensual, name='api_resumen_mensual'),
    
    # ========== APIs DEL POS ==========
    path('api/buscar-producto/', views.api_buscar_producto, name='api_buscar_producto'),
    path('api/productos/', views.api_productos, name='api_productos'),
    path('api/productos-populares/', views.api_productos_populares, name='api_productos_populares'),
    path('api/clientes/', views.api_buscar_clientes, name='api_buscar_clientes'),
    path('api/tecnicos/', views.api_tecnicos, name='api_tecnicos'),
    path('api/servicios/', views.api_servicios, name='api_servicios'),
    path('api/ordenes-completadas/', views.api_ordenes_completadas, name='api_ordenes_completadas'),
    path('api/orden/<int:orden_id>/datos-pos/', views.api_orden_datos_pos, name='api_orden_datos_pos'),
    
    # ========== IMPRESIÓN TÉRMICA ==========
    path('api/impresoras-disponibles/', views.api_impresoras_disponibles, name='api_impresoras_disponibles'),
    path('api/probar-impresora/', views.api_probar_impresora, name='api_probar_impresora'),
    path('imprimir-ticket/<int:venta_id>/', views.imprimir_ticket_venta, name='imprimir_ticket_venta'),
    path('preview-ticket/<int:venta_id>/', views.preview_ticket, name='preview_ticket'),
    
    # ========== CONFIGURACIÓN ==========
    path('configuracion/impresoras/', views.configuracion_impresoras, name='configuracion_impresoras'),
    path('configuracion/impresoras/guardar/', views.guardar_configuracion_impresora, name='guardar_configuracion_impresora'),
    
    # ========== REPORTES Y PDFs ==========
    path('factura-pdf/', views.factura_pdf, name='factura_pdf'),
    path('imprimir-factura/', views.imprimir_factura, name='imprimir_factura'),
    path('imprimir-ticket/', views.imprimir_ticket, name='imprimir_ticket'),
    
    # ========== CIERRE DE CAJA ==========
    path('cierres/', views.lista_cierres, name='lista_cierres'),
    path('cierres/crear/', views.crear_cierre, name='crear_cierre'),
    
    # ========== UTILIDADES ==========
    path('importar-orden/<int:orden_id>/', views.importar_orden_trabajo, name='importar_orden_trabajo'),
    path('cotizacion/<int:orden_id>/', views.generar_cotizacion, name='generar_cotizacion'),
]
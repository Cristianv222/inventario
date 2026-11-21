from django.urls import path
from . import views

app_name = 'taller'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_taller, name='dashboard'),
    
    # Técnicos
    path('tecnicos/', views.TecnicoListView.as_view(), name='tecnico_list'),
    path('tecnicos/<int:pk>/', views.TecnicoDetailView.as_view(), name='tecnico_detail'),
    
    # Tipos de Servicio
    path('tipos-servicio/', views.TipoServicioListView.as_view(), name='tipo_servicio_list'),
    path('tipos-servicio/crear/', views.TipoServicioCreateView.as_view(), name='tipo_servicio_create'),
    path('tipos-servicio/<int:pk>/editar/', views.TipoServicioUpdateView.as_view(), name='tipo_servicio_update'),
    path('tipos-servicio/<int:pk>/toggle-estado/', views.toggle_estado_servicio, name='toggle_estado_servicio'),
    path('tipos-servicio/<int:pk>/duplicar/', views.duplicar_servicio, name='duplicar_servicio'),
    path('tipos-servicio/<int:pk>/historial/', views.historial_ventas_servicio, name='historial_ventas_servicio'),
    
    # Panel del Técnico (Multi-pantalla)
    path('mi-panel/', views.panel_tecnico, name='panel_tecnico'),
    path('mi-panel/ordenes/', views.panel_tecnico, {'seccion': 'ordenes'}, name='panel_tecnico_ordenes'),
    path('mi-panel/pos/', views.panel_tecnico, {'seccion': 'pos'}, name='panel_tecnico_pos'),
    path('mi-panel/cuenta/', views.panel_tecnico, {'seccion': 'cuenta'}, name='panel_tecnico_cuenta'),
    path('mi-panel/perfil/', views.panel_tecnico, {'seccion': 'perfil'}, name='panel_tecnico_perfil'),
    path('mi-perfil/', views.perfil_tecnico, name='perfil_tecnico'),

    # Cuenta del técnico (comisiones / adelantos / pagos)
    path('tecnicos/<int:pk>/cuenta/', views.cuenta_tecnico, name='cuenta_tecnico'),
    path('tecnicos/<int:pk>/adelanto/', views.registrar_adelanto, name='registrar_adelanto'),
    path('tecnicos/<int:pk>/pagar-comision/', views.pagar_comision, name='pagar_comision'),
    path('tecnicos/<int:pk>/consumo/', views.registrar_consumo, name='registrar_consumo'),
    path('consumos/<int:pk>/anular/', views.anular_consumo, name='anular_consumo'),

    # Órdenes de Trabajo
    path('ordenes/', views.OrdenTrabajoListView.as_view(), name='orden_list'),
    path('ordenes/crear/', views.OrdenTrabajoCreateView.as_view(), name='orden_create'),
    path('ordenes/<int:pk>/', views.OrdenTrabajoDetailView.as_view(), name='orden_detail'),
    path('ordenes/<int:pk>/editar/', views.OrdenTrabajoUpdateView.as_view(), name='orden_update'),
    path('ordenes/<int:pk>/cambiar-estado/', views.cambiar_estado_orden, name='cambiar_estado_orden'),
    path('ordenes/<int:pk>/exportar-pos/', views.exportar_orden_a_pos, name='exportar_orden_a_pos'),

    # APIs para el POS
    path('api/tecnicos/', views.api_tecnicos, name='api_tecnicos'),
    path('api/servicios/', views.api_servicios, name='api_servicios'),
    path('api/ordenes-completadas/', views.api_ordenes_completadas, name='api_ordenes_completadas'),
    path('api/orden/<int:orden_id>/datos-pos/', views.api_orden_datos_pos, name='api_orden_datos_pos'),
    
    # Cotización - MANTENER AMBOS NOMBRES
    # Para templates que usan 'generar_cotizacion_pdf'
    path('ordenes/<int:pk>/cotizacion/', views.generar_cotizacion_pdf, name='generar_cotizacion_pdf'),
    # Para templates que usan 'orden_cotizacion'
    path('ordenes/<int:pk>/cotizacion/alt/', views.generar_cotizacion_pdf, name='orden_cotizacion'),
    
    # Orden de Trabajo PDF
    path('ordenes/<int:pk>/pdf/', views.generar_orden_pdf, name='generar_orden_pdf'),
    
    # Evaluaciones
    path('ordenes/<int:orden_pk>/evaluar/', views.EvaluacionServicioCreateView.as_view(), name='evaluacion_create'),
    
    # Especialidades y Categorías
    path('especialidades/', views.EspecialidadTecnicaListView.as_view(), name='especialidad_list'),
    path('categorias/', views.CategoriaServicioListView.as_view(), name='categoria_list'),
    
    # Reportes
    path('reportes/tecnicos/', views.reporte_tecnicos, name='reporte_tecnicos'),
    path('reportes/servicios/', views.reporte_servicios, name='reporte_servicios'),
    
    # URLs AJAX
    path('ajax/motos-por-cliente/', views.ajax_motos_por_cliente, name='ajax_motos_por_cliente'),
    path('ajax/precio-servicio/', views.ajax_precio_servicio, name='ajax_precio_servicio'),
    path('ajax/precio-servicio/<int:pk>/', views.obtener_precio_servicio_ajax, name='precio_servicio_ajax'),
    path('ajax/precio-producto/', views.ajax_precio_producto, name='ajax_precio_producto'),
    path('ajax/servicios-disponibles/', views.ajax_servicios_disponibles, name='ajax_servicios_disponibles'),
    path('ajax/datos-servicio-pos/', views.ajax_datos_servicio_pos, name='ajax_datos_servicio_pos'),
    path('ajax/buscar-cliente/', views.buscar_cliente_ajax, name='buscar_cliente_ajax'),
    path('ajax/buscar-producto/', views.buscar_producto_ajax, name='buscar_producto_ajax'),
    path('categoria/crear-ajax/', views.crear_categoria_ajax, name='crear_categoria_ajax'),
]
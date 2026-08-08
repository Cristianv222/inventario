from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    # ========================================
    # PRODUCTOS
    # ========================================
    path('', views.lista_productos, name='lista_productos'),
    path('producto/<int:producto_id>/', views.detalle_producto, name='detalle_producto'),
    path('producto/nuevo/', views.crear_producto, name='crear_producto'),
    path('producto/form/', views.crear_producto, name='producto_form'),  # Alias para crear_producto
    path('producto/<int:producto_id>/editar/', views.editar_producto, name='editar_producto'),
    path('producto/<int:producto_id>/activar/', views.activar_desactivar_producto, name='activar_desactivar_producto'),
    path('producto/<int:producto_id>/toggle-destacado/', views.toggle_destacado_ajax, name='toggle_destacado_ajax'),
    path('producto/<int:producto_id>/regenerar-codigo/', views.regenerar_codigo_barras, name='regenerar_codigo_barras'),
    
    # ========================================
    # CATEGORÍAS
    # ========================================
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categoria/nueva/', views.crear_categoria, name='crear_categoria'),
    path('categoria/<int:categoria_id>/editar/', views.editar_categoria, name='editar_categoria'),
    path('categoria/<int:categoria_id>/activar/', views.activar_desactivar_categoria, name='activar_desactivar_categoria'),
    
    # ========================================
    # MARCAS
    # ========================================
    path('marcas/', views.lista_marcas, name='lista_marcas'),
    path('marca/nueva/', views.crear_marca, name='crear_marca'),
    path('marca/<int:marca_id>/editar/', views.editar_marca, name='editar_marca'),
    path('marca/<int:marca_id>/activar/', views.activar_desactivar_marca, name='activar_desactivar_marca'),
    
    # ========================================
    # AJUSTES DE INVENTARIO
    # ========================================
    path('ajustes/', views.lista_ajustes, name='lista_ajustes'),
    path('ajuste/nuevo/', views.crear_ajuste, name='crear_ajuste'),
    
    # ========================================
    # TRANSFERENCIAS ENTRE SUCURSALES ✅ NUEVO
    # ========================================
    path('transferencias/', views.transferencias_lista, name='transferencias_lista'),
    path('transferencias/crear/', views.transferencia_crear, name='transferencia_crear'),
    path('transferencias/<int:transferencia_id>/', views.transferencia_detalle, name='transferencia_detalle'),
    path('transferencias/<int:transferencia_id>/recibir/', views.transferencia_recibir, name='transferencia_recibir'),
    path('transferencias/<int:transferencia_id>/cancelar/', views.transferencia_cancelar, name='transferencia_cancelar'),
    path('transferencias/<int:transferencia_id>/detalles/', views.api_transferencia_detalles, name='api_transferencia_detalles'),
    
    # ========================================
    # ETIQUETAS
    # ========================================
    path('imprimir-etiqueta-rapida/<int:producto_id>/', views.imprimir_etiqueta_rapida, name='imprimir_etiqueta_rapida'),
    path('imprimir-etiquetas/', views.imprimir_etiquetas, name='imprimir_etiquetas'),
    path('etiquetas/generar/', views.generar_etiquetas_pdf, name='generar_etiquetas_pdf'),
    path('api/generar-pdf-etiquetas/', views.generar_etiquetas_pdf, name='generar_pdf_etiquetas'),  # Alias para compatibilidad
    
    # ========================================
    # APIs PARA POS
    # ========================================
    path('api/productos/', views.api_productos, name='api_productos'),
    path('api/buscar-producto-codigo/', views.api_buscar_producto_por_codigo, name='api_buscar_producto_por_codigo'),
    
    # ========================================
    # APIs PARA CÁLCULO DE PRECIOS
    # ========================================
    path('api/categoria-porcentaje/', views.api_categoria_porcentaje, name='api_categoria_porcentaje'),
    path('api/calcular-precio-venta/', views.calcular_precio_venta, name='calcular_precio_venta'),
    
    # ========================================
    # APIs PARA ETIQUETAS
    # ========================================
    path('api/buscar-productos-etiquetas/', views.api_buscar_productos_etiquetas, name='api_buscar_productos_etiquetas'),
    path('api/buscar-productos-etiquetas-legacy/', views.buscar_productos_etiquetas, name='buscar_productos_etiquetas'),  # Mantener para compatibilidad
    path('api/categorias-marcas/', views.api_categorias_marcas, name='api_categorias_marcas'),
    
    # ========================================
    # APIs PARA TRANSFERENCIAS ✅ NUEVO
    # ========================================
    path('api/transferencias/buscar-productos/', views.api_buscar_productos_transferencia, name='api_buscar_productos_transferencia'),
    path('api/transferencias/validar-stock/', views.api_validar_stock, name='api_validar_stock'),
    
    # ========================================
    # EXPORTACIÓN E IMPORTACIÓN CSV
    # ========================================
    path('exportar-productos/', views.exportar_productos, name='exportar_productos'),
    path('productos/importar/', views.importar_productos_csv, name='importar_productos'),
    path('productos/exportar/', views.exportar_productos_csv, name='exportar_productos_csv'),
    path('productos/csv-ejemplo/', views.descargar_csv_ejemplo, name='csv_ejemplo'),
    path('productos/validar-csv/', views.validar_csv_ajax, name='validar_csv'),
    path('productos/limpiar-errores/', views.limpiar_errores_sesion, name='limpiar_errores_sesion'),
    
    # ========================================
    # API PÚBLICA (E-COMMERCE) ✅ NUEVO
    # ========================================
    path('api/publica/productos/', views.api_publica_productos, name='api_publica_productos'),
    path('api/v1/productos/', views.api_publica_productos, name='api_v1_productos'),
    path('api/publica/validar-cupon/', views.api_validar_cupon, name='api_publica_validar_cupon'),
    path('api/v1/validar-cupon/', views.api_validar_cupon, name='api_v1_validar_cupon'),
    
    # ========================================
    # DIGITALIZACIÓN E IMPORTACIÓN PDF ✅ NUEVO
    # ========================================
    path('importar-pdf/', views.importar_pdf_view, name='importar_pdf'),
    path('api/procesar-importacion-pdf/', views.procesar_importacion_pdf, name='procesar_importacion_pdf'),
    
    # ========================================
    # MÓDULO ADMIN FRONTEND - TIENDA VIRTUAL ✅ NUEVO
    # ========================================
    path('admin/configuracion-tienda/', views.configuracion_tienda_view, name='configuracion_tienda'),
    path('admin/productos-web/', views.productos_web_admin_view, name='productos_web_admin'),
    path('admin/productos-web/<int:producto_id>/descuento/', views.actualizar_descuento_especial_ajax, name='actualizar_descuento_especial_ajax'),
    path('admin/cupones/', views.lista_cupones_view, name='lista_cupones'),
    path('admin/cupones/crear/', views.crear_cupon_view, name='crear_cupon'),
    path('admin/cupones/<int:cupon_id>/editar/', views.editar_cupon_view, name='editar_cupon'),
    path('admin/cupones/<int:cupon_id>/eliminar/', views.eliminar_cupon_view, name='eliminar_cupon'),
    path('admin/cupones/<int:cupon_id>/toggle/', views.toggle_cupon_ajax, name='toggle_cupon_ajax'),
]
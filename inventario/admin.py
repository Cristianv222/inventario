from django.contrib import admin
from .models import Producto, CategoriaProducto, Marca, ConfiguracionTienda, CodigoPromocional, InventarioAjuste, MovimientoInventario

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('codigo_unico', 'nombre', 'categoria', 'marca', 'precio_venta', 'stock_actual', 'es_destacado', 'activo')
    list_filter = ('es_destacado', 'activo', 'categoria', 'marca')
    search_fields = ('codigo_unico', 'nombre', 'descripcion')
    list_editable = ('es_destacado', 'activo')

@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre', 'codigo')

@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)

@admin.register(ConfiguracionTienda)
class ConfiguracionTiendaAdmin(admin.ModelAdmin):
    list_display = ('porcentaje_descuento_global', 'precio_minimo_descuento', 'descuento_activo', 'fecha_actualizacion')
    
    def has_add_permission(self, request):
        # Impedir crear múltiples configuraciones; solo debe existir 1
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

@admin.register(CodigoPromocional)
class CodigoPromocionalAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion', 'porcentaje_descuento', 'precio_minimo_aplicable', 'activo', 'fecha_inicio', 'fecha_fin')
    list_filter = ('activo', 'fecha_inicio', 'fecha_fin')
    search_fields = ('codigo', 'descripcion')
    list_editable = ('activo',)

@admin.register(InventarioAjuste)
class InventarioAjusteAdmin(admin.ModelAdmin):
    list_display = ('producto', 'tipo_ajuste', 'cantidad', 'usuario', 'fecha_hora')
    list_filter = ('tipo_ajuste', 'fecha_hora')
    search_fields = ('producto__nombre', 'producto__codigo_unico', 'motivo')

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('producto', 'tipo_movimiento', 'cantidad', 'stock_anterior', 'stock_nuevo', 'fecha_hora')
    list_filter = ('tipo_movimiento', 'fecha_hora')
    search_fields = ('producto__nombre', 'producto__codigo_unico', 'motivo')

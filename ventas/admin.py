from django.contrib import admin
from .models import Venta, DetalleVenta, CierreCaja

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ('subtotal', 'iva', 'total')
    
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('numero_factura', 'cliente', 'fecha_hora', 'total', 'tipo_pago', 'estado')
    list_filter = ('estado', 'tipo_pago', 'fecha_hora')
    search_fields = ('numero_factura', 'cliente__nombres', 'cliente__apellidos', 'cliente__identificacion')
    readonly_fields = ('numero_factura', 'fecha_hora', 'subtotal', 'iva', 'total')
    inlines = [DetalleVentaInline]
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si es un nuevo objeto
            obj.usuario = request.user
        super().save_model(request, obj, form, change)

@admin.register(CierreCaja)
class CierreCajaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'usuario', 'total_ventas', 'fecha_hora')
    list_filter = ('fecha', 'usuario')
    readonly_fields = ('total_productos', 'total_servicios', 'total_ventas')
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si es un nuevo objeto
            obj.usuario = request.user
        super().save_model(request, obj, form, change)
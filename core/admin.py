from django.contrib import admin
from django.utils.html import format_html
from .models import Sucursal, DominioSucursal, ParametroSistema


class DominioSucursalInline(admin.TabularInline):
    """Inline para gestionar dominios de la sucursal"""
    model = DominioSucursal
    extra = 1
    fields = ('domain', 'is_primary')


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    """Administración de Sucursales"""
    
    list_display = [
        'codigo',
        'nombre',
        'ciudad',
        'provincia',
        'estado_badge',
        'principal_badge',
        'usuarios_count',
        'fecha_apertura',
    ]
    
    list_filter = [
        'activa',
        'es_principal',
        'provincia',
        'ciudad',
        'fecha_apertura',
    ]
    
    search_fields = [
        'codigo',
        'nombre',
        'nombre_corto',
        'ciudad',
        'direccion',
        'ruc',
    ]
    
    readonly_fields = [
        'actualizado_en',
        'usuarios_count',
    ]
    
    # ✅ AGREGAR: Prepoblar schema_name basándose en código
    prepopulated_fields = {
        'schema_name': ('codigo',)
    }
    
    fieldsets = (
        ('Información Básica', {
            'fields': (
                'codigo',
                'schema_name',
                'nombre',
                'nombre_corto',
            ),
            'description': 'El schema_name se genera automáticamente del código en minúsculas'
        }),
        ('Ubicación', {
            'fields': (
                'direccion',
                'ciudad',
                'provincia',
                'telefono',
                'celular',
                'email',
            )
        }),
        ('Datos Fiscales', {
            'fields': (
                'ruc',
                'nombre_comercial',
            ),
            'classes': ('collapse',)
        }),
        ('Configuración', {
            'fields': (
                'es_principal',
                'activa',
                'prefijo_facturas',
                'prefijo_ordenes',
            )
        }),
        ('Fechas', {
            'fields': (
                'fecha_apertura',
                'fecha_cierre',
            )
        }),
        ('Observaciones', {
            'fields': ('observaciones',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'actualizado_en',
                'usuarios_count',
            ),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [DominioSucursalInline]
    
    def estado_badge(self, obj):
        """Badge de estado activo/inactivo"""
        if obj.activa:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px;">ACTIVA</span>'
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">INACTIVA</span>'
        )
    estado_badge.short_description = 'Estado'
    
    def principal_badge(self, obj):
        """Badge de sucursal principal"""
        if obj.es_principal:
            return format_html(
                '<span style="background-color: #007bff; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px;">⭐ MATRIZ</span>'
            )
        return '-'
    principal_badge.short_description = 'Tipo'
    
    def usuarios_count(self, obj):
        """Contador de usuarios"""
        count = obj.get_usuarios_count()
        return format_html(
            '<span style="font-weight: bold;">{}</span>', count
        )
    usuarios_count.short_description = 'Usuarios'
    
    def save_model(self, request, obj, form, change):
        """Guardar modelo con validaciones"""
        # Generar schema_name si no existe
        if not obj.schema_name and obj.codigo:
            obj.schema_name = obj.codigo.lower().replace('-', '_').replace(' ', '_')
        
        obj.full_clean()  # Ejecutar validaciones
        super().save_model(request, obj, form, change)
    
    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)
        }
        js = ('admin/js/prepopulate_schema.js',)


@admin.register(DominioSucursal)
class DominioSucursalAdmin(admin.ModelAdmin):
    """Administración de Dominios de Sucursales"""
    
    list_display = [
        'domain',
        'tenant',
        'is_primary',
    ]
    
    list_filter = [
        'is_primary',
        'tenant',
    ]
    
    search_fields = [
        'domain',
        'tenant__nombre',
        'tenant__codigo',
    ]
    
    fields = (
        'domain',
        'tenant',
        'is_primary',
    )


@admin.register(ParametroSistema)
class ParametroSistemaAdmin(admin.ModelAdmin):
    """Administración de Parámetros del Sistema"""
    
    list_display = [
        'nombre',
        'valor',
        'fecha_modificacion',
    ]
    
    search_fields = [
        'nombre',
        'valor',
        'descripcion',
    ]
    
    readonly_fields = ['fecha_modificacion']
    
    fields = (
        'nombre',
        'valor',
        'descripcion',
        'fecha_modificacion',
    )
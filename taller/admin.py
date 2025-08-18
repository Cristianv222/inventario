from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Tecnico, EspecialidadTecnica, CategoriaServicio, TipoServicio,
    OrdenTrabajo, ServicioOrden, RepuestoOrden, 
    SeguimientoOrden, CitaTaller, EvaluacionServicio
)

@admin.register(EspecialidadTecnica)
class EspecialidadTecnicaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)
    list_editable = ('activa',)

@admin.register(Tecnico)
class TecnicoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo', 'nombres', 'apellidos', 'identificacion', 
        'get_especialidades', 'estado', 'activo', 'fecha_ingreso'
    )
    list_filter = ('estado', 'activo', 'especialidades', 'fecha_ingreso')
    search_fields = ('nombres', 'apellidos', 'codigo', 'identificacion')
    readonly_fields = ('codigo',)
    filter_horizontal = ('especialidades',)
    list_editable = ('estado', 'activo')
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('codigo', 'nombres', 'apellidos', 'identificacion', 'tipo_identificacion', 'foto')
        }),
        ('Contacto', {
            'fields': ('telefono', 'celular', 'email', 'direccion')
        }),
        ('Información Laboral', {
            'fields': (
                'fecha_ingreso', 'fecha_salida', 'estado', 'activo', 
                'especialidades', 'porcentaje_comision', 'salario_base'
            )
        }),
        ('Sistema', {
            'fields': ('usuario', 'observaciones')
        }),
    )
    
    def get_especialidades(self, obj):
        """Mostrar especialidades del técnico"""
        especialidades = obj.especialidades.all()
        if especialidades:
            return ', '.join([esp.nombre for esp in especialidades])
        return '-'
    get_especialidades.short_description = 'Especialidades'

@admin.register(CategoriaServicio)
class CategoriaServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'activa', 'requiere_diagnostico', 'tiempo_estimado_horas')
    list_filter = ('activa', 'requiere_diagnostico')
    search_fields = ('nombre', 'codigo')
    list_editable = ('activa', 'requiere_diagnostico')

@admin.register(TipoServicio)
class TipoServicioAdmin(admin.ModelAdmin):
    list_display = (
        'codigo', 'nombre', 'categoria', 'get_precio_total', 
        'tiempo_estimado_horas', 'nivel_dificultad', 'activo'
    )
    list_filter = ('categoria', 'activo', 'nivel_dificultad', 'requiere_especialidad')
    search_fields = ('nombre', 'codigo')
    list_editable = ('activo',)
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('categoria', 'nombre', 'codigo', 'descripcion', 'activo')
        }),
        ('Precios y Tiempo', {
            'fields': (
                'precio_base', 'precio_mano_obra', 'incluye_iva', 
                'tiempo_estimado_horas'
            )
        }),
        ('Requisitos', {
            'fields': ('requiere_repuestos', 'requiere_especialidad', 'nivel_dificultad')
        }),
    )
    
    def get_precio_total(self, obj):
        """Mostrar precio total del servicio"""
        total = obj.precio_base + obj.precio_mano_obra
        return f"${total:,.2f}"
    get_precio_total.short_description = 'Precio Total'

class ServicioOrdenInline(admin.TabularInline):
    model = ServicioOrden
    extra = 1
    readonly_fields = ('precio_total',)
    fields = (
        'tipo_servicio', 'tecnico_asignado',
        'precio_base', 'precio_mano_obra', 'precio_total',
        'tiempo_estimado', 'completado', 'requiere_aprobacion'
    )

class RepuestoOrdenInline(admin.TabularInline):
    model = RepuestoOrden
    extra = 1
    readonly_fields = ('subtotal',)
    fields = (
        'producto',
        'cantidad', 'precio_unitario', 'subtotal', 'observaciones'
    )

class SeguimientoOrdenInline(admin.TabularInline):
    model = SeguimientoOrden
    extra = 0
    readonly_fields = ('usuario', 'fecha_hora')
    fields = ('usuario', 'fecha_hora', 'estado_anterior', 'estado_nuevo', 'observaciones')

@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = (
        'numero_orden', 'get_cliente_info', 'get_moto_info', 
        'tecnico_principal', 'get_estado_badge', 'get_prioridad_badge',
        'fecha_ingreso', 'get_precio_total'
    )
    list_filter = (
        'estado', 'prioridad', 'fecha_ingreso', 'tecnico_principal',
        'fecha_completado', 'facturado'
    )
    search_fields = (
        'numero_orden', 'cliente__nombres', 'cliente__apellidos',
        'moto_placa', 'moto_marca', 'moto_modelo'
    )
    readonly_fields = (
        'numero_orden', 'precio_total', 'saldo_pendiente', 
        'usuario_creacion', 'creado_en', 'actualizado_en'  # ✅ CORREGIDO
    )
    filter_horizontal = ('tecnicos_apoyo',)
    inlines = [ServicioOrdenInline, RepuestoOrdenInline, SeguimientoOrdenInline]
    date_hierarchy = 'fecha_ingreso'
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('numero_orden', 'cliente', 'tecnico_principal', 'tecnicos_apoyo')
        }),
        ('Información de la Motocicleta', {
            'fields': (
                'moto_marca', 'moto_modelo', 'moto_placa',
                'moto_color', 'moto_cilindraje'
            )
        }),
        ('Fechas', {
            'fields': ('fecha_prometida', 'fecha_completado', 'fecha_entrega')
        }),
        ('Detalles del Servicio', {
            'fields': (
                'motivo_ingreso', 'diagnostico_inicial', 'diagnostico_final', 
                'trabajo_realizado'
            )
        }),
        ('Estado y Prioridad', {
            'fields': ('estado', 'prioridad')
        }),
        ('Información Técnica', {
            'fields': (
                'kilometraje_entrada', 'kilometraje_salida', 'nivel_combustible'
            )
        }),
        ('Precios', {
            'fields': (
                'precio_mano_obra', 'precio_repuestos',
                'precio_total', 'anticipo', 'saldo_pendiente'
            )
        }),
        ('Observaciones', {
            'fields': ('observaciones_tecnico', 'observaciones_cliente')
        }),
        ('Control', {
            'fields': (
                'usuario_creacion', 'creado_en', 'actualizado_en',  # ✅ CORREGIDO
                'facturado'
            )
        }),
    )
    
    def get_cliente_info(self, obj):
        """Mostrar información del cliente"""
        return f"{obj.cliente.nombres} {obj.cliente.apellidos}"
    get_cliente_info.short_description = 'Cliente'
    
    def get_moto_info(self, obj):
        """Mostrar información de la moto"""
        return f"{obj.moto_marca} {obj.moto_modelo} - {obj.moto_placa}"
    get_moto_info.short_description = 'Motocicleta'
    
    def get_estado_badge(self, obj):
        """Mostrar estado con colores"""
        colors = {
            'PENDIENTE': '#ffc107',
            'EN_PROCESO': '#17a2b8',
            'ESPERANDO_REPUESTOS': '#fd7e14',
            'ESPERANDO_APROBACION': '#6f42c1',
            'COMPLETADO': '#28a745',
            'ENTREGADO': '#6c757d',
            'CANCELADO': '#dc3545',
        }
        color = colors.get(obj.estado, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_estado_display()
        )
    get_estado_badge.short_description = 'Estado'
    
    def get_prioridad_badge(self, obj):
        """Mostrar prioridad con colores"""
        colors = {
            'BAJA': '#28a745',
            'NORMAL': '#17a2b8',
            'ALTA': '#fd7e14',
            'URGENTE': '#dc3545',
        }
        color = colors.get(obj.prioridad, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 10px;">{}</span>',
            color, obj.get_prioridad_display()
        )
    get_prioridad_badge.short_description = 'Prioridad'
    
    def get_precio_total(self, obj):
        """Mostrar precio total formateado"""
        return f"${obj.precio_total:,.2f}"
    get_precio_total.short_description = 'Total'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si es nuevo
            obj.usuario_creacion = request.user
        super().save_model(request, obj, form, change)

@admin.register(CitaTaller)
class CitaTallerAdmin(admin.ModelAdmin):
    list_display = (
        'get_cliente_info', 'get_moto_info', 'fecha_hora', 
        'get_estado_badge', 'tecnico_preferido', 'tiene_orden'
    )
    list_filter = ('estado', 'fecha_hora', 'tecnico_preferido', 'recordatorio_enviado')
    search_fields = ('cliente__nombres', 'cliente__apellidos')
    readonly_fields = ('usuario_creacion', 'fecha_creacion', 'orden_trabajo')
    date_hierarchy = 'fecha_hora'
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('cliente', 'moto_descripcion', 'tecnico_preferido')
        }),
        ('Programación', {
            'fields': ('fecha_hora', 'duracion_estimada', 'estado')
        }),
        ('Detalles', {
            'fields': ('motivo', 'observaciones')
        }),
        ('Recordatorios', {
            'fields': ('recordatorio_enviado', 'fecha_recordatorio')
        }),
        ('Control', {
            'fields': ('usuario_creacion', 'fecha_creacion', 'orden_trabajo')
        }),
    )
    
    def get_cliente_info(self, obj):
        """Mostrar información del cliente"""
        return f"{obj.cliente.nombres} {obj.cliente.apellidos}"
    get_cliente_info.short_description = 'Cliente'
    
    def get_moto_info(self, obj):
        """Mostrar información de la moto"""
        return obj.moto_descripcion
    get_moto_info.short_description = 'Motocicleta'
    
    def get_estado_badge(self, obj):
        """Mostrar estado con colores"""
        colors = {
            'PROGRAMADA': '#17a2b8',
            'CONFIRMADA': '#28a745',
            'EN_CURSO': '#fd7e14',
            'COMPLETADA': '#6c757d',
            'CANCELADA': '#dc3545',
            'NO_ASISTIO': '#6f42c1',
        }
        color = colors.get(obj.estado, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_estado_display()
        )
    get_estado_badge.short_description = 'Estado'
    
    def tiene_orden(self, obj):
        """Verificar si tiene orden de trabajo asociada"""
        if obj.orden_trabajo:
            url = reverse('admin:taller_ordentrabajo_change', args=[obj.orden_trabajo.pk])
            return format_html('<a href="{}">Ver Orden</a>', url)
        return '-'
    tiene_orden.short_description = 'Orden'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si es nuevo
            obj.usuario_creacion = request.user
        super().save_model(request, obj, form, change)

@admin.register(EvaluacionServicio)
class EvaluacionServicioAdmin(admin.ModelAdmin):
    list_display = (
        'get_orden_info', 'calificacion_general', 'calificacion_tecnico', 
        'recomendaria', 'fecha_evaluacion'
    )
    list_filter = ('calificacion_general', 'recomendaria', 'fecha_evaluacion')
    search_fields = ('orden__numero_orden', 'orden__cliente__nombres')
    readonly_fields = ('fecha_evaluacion',)
    
    fieldsets = (
        ('Orden de Trabajo', {
            'fields': ('orden',)
        }),
        ('Calificaciones', {
            'fields': (
                'calificacion_general', 'calificacion_tecnico', 
                'calificacion_tiempo', 'calificacion_precio'
            )
        }),
        ('Comentarios', {
            'fields': ('comentarios', 'recomendaria')
        }),
        ('Control', {
            'fields': ('fecha_evaluacion',)
        }),
    )
    
    def get_orden_info(self, obj):
        """Mostrar información de la orden"""
        return f"{obj.orden.numero_orden} - {obj.orden.cliente.nombres} {obj.orden.cliente.apellidos}"
    get_orden_info.short_description = 'Orden'

# Configuración adicional del admin
admin.site.site_header = 'VPMOTOS - Administración del Taller'
admin.site.site_title = 'VPMOTOS Admin'
admin.site.index_title = 'Administración del Sistema de Taller'
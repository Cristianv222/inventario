from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Sum, Count
from django.contrib.admin import SimpleListFilter
from django.utils import timezone
from datetime import datetime, timedelta

from .models import (
    Cliente, Moto, MovimientoPuntos, ConfiguracionPuntos, 
    CanjeoPuntos, HistorialCliente
)
from .utils import formatear_identificacion, formatear_telefono

# ========== FILTROS PERSONALIZADOS ==========

class PuntosDisponiblesFilter(SimpleListFilter):
    title = 'Puntos Disponibles'
    parameter_name = 'puntos_range'

    def lookups(self, request, model_admin):
        return (
            ('sin_puntos', 'Sin puntos (0)'),
            ('pocos_puntos', 'Pocos puntos (1-99)'),
            ('puntos_medios', 'Puntos medios (100-499)'),
            ('muchos_puntos', 'Muchos puntos (500-999)'),
            ('puntos_altos', 'Puntos altos (1000+)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sin_puntos':
            return queryset.filter(puntos_disponibles=0)
        elif self.value() == 'pocos_puntos':
            return queryset.filter(puntos_disponibles__range=(1, 99))
        elif self.value() == 'puntos_medios':
            return queryset.filter(puntos_disponibles__range=(100, 499))
        elif self.value() == 'muchos_puntos':
            return queryset.filter(puntos_disponibles__range=(500, 999))
        elif self.value() == 'puntos_altos':
            return queryset.filter(puntos_disponibles__gte=1000)
        return queryset

class FechaRegistroFilter(SimpleListFilter):
    title = 'Fecha de Registro'
    parameter_name = 'fecha_registro'

    def lookups(self, request, model_admin):
        return (
            ('hoy', 'Hoy'),
            ('semana', 'Esta semana'),
            ('mes', 'Este mes'),
            ('trimestre', 'Este trimestre'),
            ('año', 'Este año'),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        
        if self.value() == 'hoy':
            return queryset.filter(fecha_registro__date=now.date())
        elif self.value() == 'semana':
            start_week = now - timedelta(days=now.weekday())
            return queryset.filter(fecha_registro__gte=start_week)
        elif self.value() == 'mes':
            return queryset.filter(fecha_registro__month=now.month, fecha_registro__year=now.year)
        elif self.value() == 'trimestre':
            quarter_start = datetime(now.year, ((now.month - 1) // 3) * 3 + 1, 1)
            return queryset.filter(fecha_registro__gte=quarter_start)
        elif self.value() == 'año':
            return queryset.filter(fecha_registro__year=now.year)
        return queryset

# ========== INLINE ADMINS ==========

class MotoInline(admin.TabularInline):
    model = Moto
    extra = 0
    fields = ('placa', 'marca', 'modelo', 'año', 'color', 'estado')
    readonly_fields = ('fecha_registro',)

class MovimientoPuntosInline(admin.TabularInline):
    model = MovimientoPuntos
    extra = 0
    fields = ('tipo', 'puntos', 'concepto', 'fecha', 'usuario')
    readonly_fields = ('fecha',)
    ordering = ('-fecha',)
    
    def has_add_permission(self, request, obj=None):
        return False  # Solo lectura desde aquí

class HistorialClienteInline(admin.TabularInline):
    model = HistorialCliente
    extra = 0
    fields = ('tipo', 'descripcion', 'fecha', 'importante', 'usuario')
    readonly_fields = ('fecha',)
    ordering = ('-fecha',)

class CanjeoPuntosInline(admin.TabularInline):
    model = CanjeoPuntos
    extra = 0
    fields = ('tipo_premio', 'descripcion_premio', 'puntos_utilizados', 'utilizado', 'fecha_canje')
    readonly_fields = ('fecha_canje',)
    ordering = ('-fecha_canje',)

# ========== ADMIN PRINCIPAL DE CLIENTE ==========

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        'get_avatar', 'get_nombre_completo', 'get_identificacion_formateada', 
        'get_telefono_formateado', 'get_puntos_display', 'get_estado_display',
        'get_ultima_actividad', 'fecha_registro'
    )
    
    list_filter = (
        'activo', 'tipo_identificacion', PuntosDisponiblesFilter, 
        FechaRegistroFilter, 'referido_por'
    )
    
    search_fields = (
        'nombres', 'apellidos', 'identificacion', 'telefono', 
        'celular', 'email'
    )
    
    ordering = ('-fecha_registro',)
    
    fieldsets = (
        ('Información Personal', {
            'fields': (
                ('nombres', 'apellidos'),
                ('tipo_identificacion', 'identificacion'),
                ('fecha_nacimiento', 'profesion'),
            ),
            'classes': ('wide',)
        }),
        ('Contacto', {
            'fields': (
                ('telefono', 'celular'),
                'email',
                'direccion',
            ),
            'classes': ('wide',)
        }),
        ('Sistema de Puntos', {
            'fields': (
                ('puntos_disponibles', 'puntos_acumulados', 'puntos_canjeados'),
                'get_puntos_info',
            ),
            'classes': ('wide',),
            'description': 'Información del sistema de fidelización por puntos'
        }),
        ('Información Comercial', {
            'fields': (
                'referido_por',
                'descuento_preferencial',
                'observaciones',
            ),
            'classes': ('collapse',)
        }),
        ('Estado y Fechas', {
            'fields': (
                'activo',
                'fecha_registro',
            ),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = (
        'fecha_registro', 'get_puntos_info', 'puntos_acumulados', 'puntos_canjeados'
    )
    
    inlines = [MotoInline, MovimientoPuntosInline, HistorialClienteInline, CanjeoPuntosInline]
    
    list_per_page = 25
    
    actions = ['activar_clientes', 'desactivar_clientes', 'resetear_puntos', 'exportar_clientes']
    
    # ========== MÉTODOS DE DISPLAY ==========
    
    def get_avatar(self, obj):
        """Muestra avatar del cliente"""
        iniciales = f"{obj.nombres[0] if obj.nombres else ''}{obj.apellidos[0] if obj.apellidos else ''}"
        color = "success" if obj.activo else "secondary"
        return format_html(
            '<span class="badge bg-{} rounded-circle" style="width: 35px; height: 35px; '
            'display: flex; align-items: center; justify-content: center; font-size: 12px;">{}</span>',
            color, iniciales
        )
    get_avatar.short_description = ""
    get_avatar.admin_order_field = 'nombres'
    
    def get_nombre_completo(self, obj):
        """Muestra nombre completo con enlace"""
        url = reverse('admin:clientes_cliente_change', args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.get_nombre_completo())
    get_nombre_completo.short_description = 'Cliente'
    get_nombre_completo.admin_order_field = 'nombres'
    
    def get_identificacion_formateada(self, obj):
        """Muestra identificación formateada"""
        formatted = formatear_identificacion(obj.identificacion, obj.tipo_identificacion)
        tipo_color = {
            'CEDULA': 'primary',
            'RUC': 'warning',
            'PASAPORTE': 'info'
        }.get(obj.tipo_identificacion, 'secondary')
        
        return format_html(
            '<span class="badge bg-{}">{}</span><br><small>{}</small>',
            tipo_color, obj.get_tipo_identificacion_display(), formatted
        )
    get_identificacion_formateada.short_description = 'Identificación'
    get_identificacion_formateada.admin_order_field = 'identificacion'
    
    def get_telefono_formateado(self, obj):
        """Muestra teléfono formateado"""
        telefonos = []
        if obj.telefono:
            telefonos.append(f"📞 {formatear_telefono(obj.telefono)}")
        if obj.celular:
            telefonos.append(f"📱 {formatear_telefono(obj.celular)}")
        
        if not telefonos:
            return format_html('<span class="text-muted">Sin teléfono</span>')
        
        return format_html('<br>'.join(telefonos))
    get_telefono_formateado.short_description = 'Contacto'
    
    def get_puntos_display(self, obj):
        """Muestra información de puntos"""
        if obj.puntos_disponibles == 0:
            return format_html('<span class="text-muted">Sin puntos</span>')
        
        color = 'success' if obj.puntos_disponibles >= 500 else 'warning' if obj.puntos_disponibles >= 100 else 'info'
        
        return format_html(
            '<span class="badge bg-{} fs-6">⭐ {} pts</span><br>'
            '<small class="text-muted">Total: {} | Canjeados: {}</small>',
            color, obj.puntos_disponibles, obj.puntos_acumulados, obj.puntos_canjeados
        )
    get_puntos_display.short_description = 'Puntos'
    get_puntos_display.admin_order_field = 'puntos_disponibles'
    
    def get_estado_display(self, obj):
        """Muestra estado del cliente"""
        if obj.activo:
            return format_html('<span class="badge bg-success">✓ Activo</span>')
        else:
            return format_html('<span class="badge bg-danger">✗ Inactivo</span>')
    get_estado_display.short_description = 'Estado'
    get_estado_display.admin_order_field = 'activo'
    
    def get_ultima_actividad(self, obj):
        """Muestra última actividad del cliente"""
        try:
            # Buscar última venta
            from ventas.models import Venta
            ultima_venta = Venta.objects.filter(
                cliente=obj, estado='COMPLETADA'
            ).order_by('-fecha_hora').first()
            
            if ultima_venta:
                days_ago = (timezone.now().date() - ultima_venta.fecha_hora.date()).days
                if days_ago == 0:
                    return format_html('<span class="text-success">Hoy</span>')
                elif days_ago <= 7:
                    return format_html('<span class="text-warning">{} días</span>', days_ago)
                elif days_ago <= 30:
                    return format_html('<span class="text-info">{} días</span>', days_ago)
                else:
                    return format_html('<span class="text-muted">{} días</span>', days_ago)
            else:
                return format_html('<span class="text-muted">Sin compras</span>')
        except:
            return format_html('<span class="text-muted">-</span>')
    get_ultima_actividad.short_description = 'Última Actividad'
    
    def get_puntos_info(self, obj):
        """Información detallada de puntos"""
        if not obj.pk:
            return "Guarde el cliente primero"
        
        total_movimientos = obj.movimientos_puntos.count()
        ultimo_movimiento = obj.movimientos_puntos.first()
        
        info = f"""
        <div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">
            <strong>Resumen de Puntos:</strong><br>
            • Disponibles: <span style="color: #28a745;">{obj.puntos_disponibles}</span><br>
            • Acumulados: <span style="color: #007bff;">{obj.puntos_acumulados}</span><br>
            • Canjeados: <span style="color: #ffc107;">{obj.puntos_canjeados}</span><br>
            • Total movimientos: {total_movimientos}<br>
        """
        
        if ultimo_movimiento:
            info += f"• Último movimiento: {ultimo_movimiento.get_tipo_display()} - {ultimo_movimiento.puntos} pts<br>"
        
        # Calcular descuento disponible
        descuento = obj.puntos_disponibles * 0.01
        info += f"• Descuento disponible: <span style='color: #dc3545;'>${descuento:.2f}</span><br>"
        
        info += "</div>"
        
        return mark_safe(info)
    get_puntos_info.short_description = "Información de Puntos"
    
    # ========== ACCIONES PERSONALIZADAS ==========
    
    def activar_clientes(self, request, queryset):
        """Activa clientes seleccionados"""
        count = queryset.update(activo=True)
        self.message_user(request, f"{count} clientes activados correctamente.")
    activar_clientes.short_description = "Activar clientes seleccionados"
    
    def desactivar_clientes(self, request, queryset):
        """Desactiva clientes seleccionados"""
        count = queryset.update(activo=False)
        self.message_user(request, f"{count} clientes desactivados correctamente.")
    desactivar_clientes.short_description = "Desactivar clientes seleccionados"
    
    def resetear_puntos(self, request, queryset):
        """Resetea los puntos de clientes seleccionados"""
        count = 0
        for cliente in queryset:
            if cliente.puntos_disponibles > 0:
                MovimientoPuntos.objects.create(
                    cliente=cliente,
                    tipo='AJUSTE',
                    puntos=cliente.puntos_disponibles,
                    concepto='Reset de puntos desde administración',
                    usuario=request.user
                )
                cliente.puntos_disponibles = 0
                cliente.save()
                count += 1
        
        self.message_user(request, f"Puntos reseteados para {count} clientes.")
    resetear_puntos.short_description = "Resetear puntos de clientes seleccionados"
    
    def exportar_clientes(self, request, queryset):
        """Exporta clientes seleccionados a CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="clientes_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Nombres', 'Apellidos', 'Identificación', 'Tipo ID', 'Teléfono', 
            'Email', 'Puntos Disponibles', 'Estado', 'Fecha Registro'
        ])
        
        for cliente in queryset:
            writer.writerow([
                cliente.nombres, cliente.apellidos, cliente.identificacion,
                cliente.get_tipo_identificacion_display(), cliente.telefono or cliente.celular,
                cliente.email, cliente.puntos_disponibles,
                'Activo' if cliente.activo else 'Inactivo',
                cliente.fecha_registro.strftime('%d/%m/%Y')
            ])
        
        return response
    exportar_clientes.short_description = "Exportar clientes seleccionados a CSV"

# ========== ADMIN DE MOTO ==========

@admin.register(Moto)
class MotoAdmin(admin.ModelAdmin):
    list_display = (
        'placa', 'get_cliente_link', 'marca', 'modelo', 'año', 
        'color', 'get_estado_display', 'fecha_registro'
    )
    
    list_filter = ('marca', 'estado', 'año')
    search_fields = ('placa', 'cliente__nombres', 'cliente__apellidos', 'modelo')
    ordering = ('-fecha_registro',)
    
    fieldsets = (
        ('Información Básica', {
            'fields': (
                'cliente',
                ('placa', 'marca'),
                ('modelo', 'año'),
                ('color', 'tipo'),
            )
        }),
        ('Especificaciones Técnicas', {
            'fields': (
                ('numero_chasis', 'numero_motor'),
                ('cilindraje', 'kilometraje'),
                'fecha_ultima_revision',
            ),
            'classes': ('collapse',)
        }),
        ('Estado y Observaciones', {
            'fields': (
                'estado',
                'descripcion',
            )
        }),
    )
    
    readonly_fields = ('fecha_registro',)
    
    def get_cliente_link(self, obj):
        """Enlace al cliente propietario"""
        url = reverse('admin:clientes_cliente_change', args=[obj.cliente.id])
        return format_html('<a href="{}">{}</a>', url, obj.cliente.get_nombre_completo())
    get_cliente_link.short_description = 'Cliente'
    get_cliente_link.admin_order_field = 'cliente__nombres'
    
    def get_estado_display(self, obj):
        """Estado con colores"""
        colors = {
            'Activo': 'success',
            'Inactivo': 'secondary',
            'En reparación': 'warning',
            'Vendido': 'info'
        }
        color = colors.get(obj.estado, 'secondary')
        return format_html('<span class="badge bg-{}">{}</span>', color, obj.estado)
    get_estado_display.short_description = 'Estado'
    get_estado_display.admin_order_field = 'estado'

# ========== ADMIN DE MOVIMIENTOS DE PUNTOS ==========

@admin.register(MovimientoPuntos)
class MovimientoPuntosAdmin(admin.ModelAdmin):
    list_display = (
        'get_cliente_link', 'get_tipo_display', 'puntos', 
        'concepto_corto', 'fecha', 'usuario', 'get_venta_link'
    )
    
    list_filter = ('tipo', 'fecha', 'usuario')
    search_fields = ('cliente__nombres', 'cliente__apellidos', 'concepto')
    ordering = ('-fecha',)
    date_hierarchy = 'fecha'
    
    fieldsets = (
        (None, {
            'fields': (
                'cliente',
                ('tipo', 'puntos'),
                'concepto',
                ('usuario', 'venta'),
            )
        }),
    )
    
    readonly_fields = ('fecha',)
    
    def get_cliente_link(self, obj):
        """Enlace al cliente"""
        url = reverse('admin:clientes_cliente_change', args=[obj.cliente.id])
        return format_html('<a href="{}">{}</a>', url, obj.cliente.get_nombre_completo())
    get_cliente_link.short_description = 'Cliente'
    get_cliente_link.admin_order_field = 'cliente__nombres'
    
    def get_tipo_display(self, obj):
        """Tipo con colores"""
        colors = {
            'GANADO': 'success',
            'CANJEADO': 'warning',
            'AJUSTE': 'info',
            'VENCIDO': 'danger'
        }
        color = colors.get(obj.tipo, 'secondary')
        icon = {
            'GANADO': '⬆️',
            'CANJEADO': '⬇️',
            'AJUSTE': '🔄',
            'VENCIDO': '⏰'
        }.get(obj.tipo, '📝')
        
        return format_html(
            '<span class="badge bg-{}">{} {}</span>', 
            color, icon, obj.get_tipo_display()
        )
    get_tipo_display.short_description = 'Tipo'
    get_tipo_display.admin_order_field = 'tipo'
    
    def concepto_corto(self, obj):
        """Concepto truncado"""
        if len(obj.concepto) > 50:
            return obj.concepto[:50] + "..."
        return obj.concepto
    concepto_corto.short_description = 'Concepto'
    
    def get_venta_link(self, obj):
        """Enlace a la venta si existe"""
        if obj.venta:
            try:
                url = reverse('admin:ventas_venta_change', args=[obj.venta.id])
                return format_html('<a href="{}">#{}</a>', url, obj.venta.numero_factura)
            except:
                return obj.venta.numero_factura
        return '-'
    get_venta_link.short_description = 'Venta'

# ========== ADMIN DE CONFIGURACIÓN DE PUNTOS ==========

@admin.register(ConfiguracionPuntos)
class ConfiguracionPuntosAdmin(admin.ModelAdmin):
    list_display = (
        'nombre', 'get_regla_display_custom', 'valor', 
        'get_activo_display', 'fecha_inicio', 'fecha_fin'
    )
    
    list_filter = ('regla', 'activo', 'fecha_inicio')
    search_fields = ('nombre', 'descripcion')
    ordering = ('-fecha_inicio',)
    
    fieldsets = (
        ('Configuración Básica', {
            'fields': (
                'nombre',
                ('regla', 'valor'),
                'descripcion',
            )
        }),
        ('Vigencia', {
            'fields': (
                'activo',
                ('fecha_inicio', 'fecha_fin'),
            )
        }),
    )
    
    def get_regla_display_custom(self, obj):
        """Regla con iconos"""
        icons = {
            'POR_DOLAR': '💰',
            'POR_VENTA': '🛒',
            'POR_REFERIDO': '👥'
        }
        icon = icons.get(obj.regla, '📋')
        return f"{icon} {obj.get_regla_display()}"
    get_regla_display_custom.short_description = 'Regla'
    get_regla_display_custom.admin_order_field = 'regla'
    
    def get_activo_display(self, obj):
        """Estado con colores"""
        if obj.activo:
            return format_html('<span class="badge bg-success">✓ Activo</span>')
        else:
            return format_html('<span class="badge bg-secondary">⏸️ Inactivo</span>')
    get_activo_display.short_description = 'Estado'
    get_activo_display.admin_order_field = 'activo'

# ========== ADMIN DE CANJES ==========

@admin.register(CanjeoPuntos)
class CanjeoPuntosAdmin(admin.ModelAdmin):
    list_display = (
        'get_cliente_link', 'descripcion_premio', 'puntos_utilizados',
        'get_utilizado_display', 'fecha_canje', 'fecha_vencimiento'
    )
    
    list_filter = ('tipo_premio', 'utilizado', 'fecha_canje')
    search_fields = ('cliente__nombres', 'cliente__apellidos', 'descripcion_premio')
    ordering = ('-fecha_canje',)
    date_hierarchy = 'fecha_canje'
    
    def get_cliente_link(self, obj):
        """Enlace al cliente"""
        url = reverse('admin:clientes_cliente_change', args=[obj.cliente.id])
        return format_html('<a href="{}">{}</a>', url, obj.cliente.get_nombre_completo())
    get_cliente_link.short_description = 'Cliente'
    get_cliente_link.admin_order_field = 'cliente__nombres'
    
    def get_utilizado_display(self, obj):
        """Estado de utilización"""
        if obj.utilizado:
            return format_html('<span class="badge bg-success">✓ Utilizado</span>')
        else:
            # Verificar si está vencido
            if obj.fecha_vencimiento and obj.fecha_vencimiento < timezone.now().date():
                return format_html('<span class="badge bg-danger">⏰ Vencido</span>')
            else:
                return format_html('<span class="badge bg-warning">⏳ Pendiente</span>')
    get_utilizado_display.short_description = 'Estado'
    get_utilizado_display.admin_order_field = 'utilizado'

# ========== ADMIN DE HISTORIAL ==========

@admin.register(HistorialCliente)
class HistorialClienteAdmin(admin.ModelAdmin):
    list_display = (
        'get_cliente_link', 'get_tipo_display_custom', 'descripcion_corta',
        'fecha', 'get_importante_display', 'usuario'
    )
    
    list_filter = ('tipo', 'importante', 'fecha', 'usuario')
    search_fields = ('cliente__nombres', 'cliente__apellidos', 'descripcion')
    ordering = ('-fecha',)
    date_hierarchy = 'fecha'
    
    def get_cliente_link(self, obj):
        """Enlace al cliente"""
        url = reverse('admin:clientes_cliente_change', args=[obj.cliente.id])
        return format_html('<a href="{}">{}</a>', url, obj.cliente.get_nombre_completo())
    get_cliente_link.short_description = 'Cliente'
    get_cliente_link.admin_order_field = 'cliente__nombres'
    
    def get_tipo_display_custom(self, obj):
        """Tipo con iconos"""
        icons = {
            'VENTA': '🛒',
            'SERVICIO': '🔧',
            'LLAMADA': '📞',
            'EMAIL': '📧',
            'WHATSAPP': '💬',
            'VISITA': '🏪',
            'RECLAMO': '⚠️',
            'FELICITACION': '🎉',
            'OTRO': '📝'
        }
        icon = icons.get(obj.tipo, '📝')
        return f"{icon} {obj.get_tipo_display()}"
    get_tipo_display_custom.short_description = 'Tipo'
    get_tipo_display_custom.admin_order_field = 'tipo'
    
    def descripcion_corta(self, obj):
        """Descripción truncada"""
        if len(obj.descripcion) > 60:
            return obj.descripcion[:60] + "..."
        return obj.descripcion
    descripcion_corta.short_description = 'Descripción'
    
    def get_importante_display(self, obj):
        """Indicador de importancia"""
        if obj.importante:
            return format_html('<span class="badge bg-warning">⭐ Importante</span>')
        else:
            return '-'
    get_importante_display.short_description = 'Importante'
    get_importante_display.admin_order_field = 'importante'

# ========== CONFIGURACIÓN GENERAL ==========

# Personalizar títulos del admin
admin.site.site_header = "VPMOTOS - Panel de Administración"
admin.site.site_title = "VPMOTOS Admin"
admin.site.index_title = "Gestión del Sistema"
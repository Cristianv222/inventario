from django.contrib import admin

from .models import AsientoContable, CuentaContable, LineaAsiento, PeriodoContable


@admin.register(CuentaContable)
class CuentaContableAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'naturaleza', 'es_movimiento', 'activa')
    list_filter = ('tipo', 'naturaleza', 'es_movimiento', 'activa')
    search_fields = ('codigo', 'nombre')
    ordering = ('codigo',)


class LineaAsientoInline(admin.TabularInline):
    model = LineaAsiento
    extra = 0
    autocomplete_fields = ('cuenta',)


@admin.register(AsientoContable)
class AsientoContableAdmin(admin.ModelAdmin):
    list_display = ('numero', 'fecha', 'glosa', 'origen', 'estado',
                    'total_debe', 'total_haber', 'cuadrado')
    list_filter = ('origen', 'estado', 'fecha')
    search_fields = ('numero', 'glosa', 'referencia_tipo')
    date_hierarchy = 'fecha'
    inlines = [LineaAsientoInline]
    readonly_fields = ('numero', 'created_at')


@admin.register(PeriodoContable)
class PeriodoContableAdmin(admin.ModelAdmin):
    list_display = ('anio', 'mes', 'cerrado', 'fecha_cierre')
    list_filter = ('cerrado', 'anio')

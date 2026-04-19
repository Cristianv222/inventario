from django.contrib import admin
from .models import SRIConfig, PuntoEmision, CertificadoDigital, ComprobanteElectronico

@admin.register(SRIConfig)
class SRIConfigAdmin(admin.ModelAdmin):
    list_display = ('ambiente', 'ruc', 'razon_social', 'obligado_contabilidad')
    fieldsets = (
        ('Ambiente de Trabajo', {
            'fields': ('ambiente', 'tipo_emision')
        }),
        ('Información de la Matriz', {
            'fields': ('ruc', 'razon_social', 'nombre_comercial', 'direccion_matriz', 'obligado_contabilidad')
        }),
        ('Contribuyente - Resoluciones', {
            'fields': ('contribuyente_especial', 'agente_retencion', 'regimen_microempresas', 'regimen_rimpe')
        }),
    )

    def has_add_permission(self, request):
        # Impedir agregar más de uno (Singleton)
        return not SRIConfig.objects.exists()

@admin.register(PuntoEmision)
class PuntoEmisionAdmin(admin.ModelAdmin):
    list_display = ('establecimiento', 'punto_emision', 'ultimo_secuencial', 'activo')
    list_filter = ('activo',)
    search_fields = ('establecimiento', 'punto_emision', 'ultimo_secuencial')

@admin.register(CertificadoDigital)
class CertificadoDigitalAdmin(admin.ModelAdmin):
    list_display = ('fecha_carga', 'fecha_vencimiento', 'activo')
    readonly_fields = ('fecha_vencimiento',)
    
    fields = ('archivo', 'password_raw', 'activo', 'fecha_vencimiento')
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Añadir un campo virtual para la contraseña en texto plano
        from django import forms
        form.base_fields['password_raw'] = forms.CharField(
            widget=forms.PasswordInput(render_value=False),
            label="Contraseña de la Firma",
            required=obj is None,
            help_text="Escribe la contraseña para actualizarla. Se guardará encriptada."
        )
        return form

    def save_model(self, request, obj, form, change):
        password_raw = form.cleaned_data.get('password_raw')
        if password_raw:
            obj.set_password(password_raw)
        super().save_model(request, obj, form, change)

@admin.register(ComprobanteElectronico)
class ComprobanteElectronicoAdmin(admin.ModelAdmin):
    list_display = ('id', 'venta', 'estado', 'fecha_registro', 'ambiente')
    list_filter = ('estado', 'ambiente')
    search_fields = ('clave_acceso', 'venta__numero_venta')
    readonly_fields = ('id', 'fecha_registro', 'fecha_actualizacion')

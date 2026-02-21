"""
Forms para la app Core — Sucursales
"""
import re
from django import forms
from django.core.exceptions import ValidationError
from .models import Sucursal, DominioSucursal


class SucursalForm(forms.ModelForm):
    # Campo extra solo para la creación (no es parte del modelo)
    dominio_primario = forms.CharField(
        required=False,
        max_length=253,
        help_text="Dominio principal (ej: cayambe.vpmotos.com)",
    )

    class Meta:
        model = Sucursal
        fields = [
            'codigo', 'schema_name', 'nombre', 'nombre_corto',
            'direccion', 'ciudad', 'provincia',
            'telefono', 'celular', 'email',
            'ruc', 'nombre_comercial',
            'es_principal', 'activa',
            'prefijo_facturas', 'prefijo_ordenes',
            'fecha_apertura', 'fecha_cierre',
            'observaciones',
        ]
        widgets = {
            'fecha_apertura': forms.DateInput(attrs={'type': 'date'}),
            'fecha_cierre':   forms.DateInput(attrs={'type': 'date'}),
            'observaciones':  forms.Textarea(attrs={'rows': 3}),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo', '').upper()
        if not re.match(r'^[A-Z0-9_-]+$', codigo):
            raise ValidationError(
                'Solo letras mayúsculas, números, guiones y guiones bajos'
            )
        return codigo

    def clean_schema_name(self):
        schema = self.cleaned_data.get('schema_name', '').strip()
        # Auto-generar si viene vacío
        if not schema:
            codigo = self.cleaned_data.get('codigo', '')
            schema = re.sub(r'[^a-z0-9_]', '_', codigo.lower()).strip('_')
        # Bloquear palabras reservadas de PostgreSQL
        reservadas = ['public', 'postgres', 'template0', 'template1']
        if schema.lower() in reservadas:
            raise ValidationError(f'"{schema}" es una palabra reservada de PostgreSQL')
        return schema


class DominioSucursalForm(forms.ModelForm):
    class Meta:
        model = DominioSucursal
        fields = ['domain', 'is_primary']

    def clean_domain(self):
        domain = self.cleaned_data.get('domain', '').lower().strip()
        if not re.match(r'^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$', domain):
            raise ValidationError(
                'Dominio inválido. Use formato: subdominio.dominio.com'
            )
        return domain
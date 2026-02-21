"""
Forms del módulo Usuarios - VPMOTOS
Autenticación, creación/edición de usuarios con sucursal y permisos
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Permission, ContentType

from .models import Usuario
from core.models import Sucursal


# ══════════════════════════════════════════════
# AUTENTICACIÓN
# ══════════════════════════════════════════════

class CustomAuthenticationForm(AuthenticationForm):
    """Formulario personalizado de inicio de sesión"""
    username = forms.CharField(
        label='Usuario',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre de usuario',
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña',
            'autocomplete': 'current-password',
        })
    )


class CustomPasswordChangeForm(PasswordChangeForm):
    """Formulario personalizado para cambio de contraseña"""
    old_password = forms.CharField(
        label='Contraseña actual',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese su contraseña actual',
            'autocomplete': 'current-password',
        })
    )
    new_password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese nueva contraseña',
            'autocomplete': 'new-password',
        }),
        help_text='Mínimo 8 caracteres. No puede ser completamente numérica.'
    )
    new_password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirme nueva contraseña',
            'autocomplete': 'new-password',
        })
    )


# ══════════════════════════════════════════════
# USUARIO
# ══════════════════════════════════════════════

class UsuarioForm(forms.ModelForm):
    """
    Formulario de creación y edición de usuario.
    Incluye contraseña, sucursal asignada y acceso global.
    """
    password1 = forms.CharField(
        label='Contraseña',
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña',
            'autocomplete': 'new-password',
        }),
        help_text='Dejar en blanco para mantener la contraseña actual (solo al editar). Mínimo 8 caracteres.'
    )
    password2 = forms.CharField(
        label='Confirmar Contraseña',
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirmar Contraseña',
            'autocomplete': 'new-password',
        })
    )

    # ── Campos de sucursal ──────────────────────
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.filter(activa=True).order_by('-es_principal', 'nombre'),
        required=False,
        empty_label='— Sin asignar —',
        label='Sucursal asignada',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Sucursal a la que pertenece el usuario. Dejar vacío si tiene acceso global.'
    )

    puede_ver_todas_sucursales = forms.BooleanField(
        required=False,
        label='Acceso a todas las sucursales',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Permite al usuario ver datos de todas las sucursales. Solo para administradores generales.'
    )

    class Meta:
        model = Usuario
        fields = [
            'usuario', 'nombre', 'apellido', 'email', 'telefono',
            'sucursal', 'puede_ver_todas_sucursales',
            'activo', 'is_staff', 'is_superuser',
        ]
        widgets = {
            'usuario': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de usuario único',
                'autocomplete': 'username',
            }),
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre',
                'autocomplete': 'given-name',
            }),
            'apellido': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Apellido',
                'autocomplete': 'family-name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@ejemplo.com',
                'autocomplete': 'email',
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Teléfono (opcional)',
                'autocomplete': 'tel',
            }),
            'activo':       forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_superuser': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'usuario':      'Nombre de Usuario',
            'nombre':       'Nombre',
            'apellido':     'Apellido',
            'email':        'Correo Electrónico',
            'telefono':     'Teléfono',
            'activo':       'Usuario Activo',
            'is_staff':     'Es Administrador',
            'is_superuser': 'Es Super Administrador (acceso total)',
        }
        help_texts = {
            'usuario':      'Nombre único para iniciar sesión. Solo letras, números y @/./+/-/_',
            'email':        'Correo electrónico válido del usuario',
            'is_staff':     'Puede acceder al panel de administración de Django',
            'is_superuser': 'Tiene todos los permisos automáticamente sin necesidad de asignarlos',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Contraseña obligatoria solo para usuarios nuevos
        self.fields['password1'].required = not self.instance.pk
        self.fields['password2'].required = not self.instance.pk

        # No permitir cambiar el username al editar
        if self.instance.pk:
            self.fields['usuario'].widget.attrs['readonly'] = True
            self.fields['usuario'].help_text = 'El nombre de usuario no se puede modificar'

    def clean_usuario(self):
        usuario = self.cleaned_data.get('usuario')
        if not self.instance.pk:
            if Usuario.objects.filter(usuario=usuario).exists():
                raise forms.ValidationError('Este nombre de usuario ya está en uso.')
        return usuario

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = Usuario.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Este correo electrónico ya está registrado.')
        return email

    def clean(self):
        cleaned = super().clean()
        password1  = cleaned.get('password1')
        password2  = cleaned.get('password2')
        is_su      = cleaned.get('is_superuser')
        puede_todas = cleaned.get('puede_ver_todas_sucursales')

        # Validar contraseñas
        if password1 and password1 != password2:
            self.add_error('password2', 'Las contraseñas no coinciden')

        if not self.instance.pk and not password1:
            self.add_error('password1', 'La contraseña es obligatoria para nuevos usuarios')

        if password1:
            try:
                validate_password(password1, self.instance)
            except forms.ValidationError as e:
                self.add_error('password1', e)

        # Superusuario siempre ve todas las sucursales
        if is_su:
            cleaned['puede_ver_todas_sucursales'] = True
            cleaned['sucursal'] = None

        # Si puede ver todas, no tiene sucursal específica
        if puede_todas:
            cleaned['sucursal'] = None

        return cleaned

    def save(self, commit=True):
        usuario = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            usuario.set_password(password)
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario


# ══════════════════════════════════════════════
# PERMISOS
# ══════════════════════════════════════════════

class PermisoForm(forms.Form):
    """Formulario para crear permisos personalizados"""

    modulo = forms.ModelChoiceField(
        queryset=ContentType.objects.all().order_by('app_label', 'model'),
        label='Módulo del Sistema',
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Selecciona el módulo donde se aplicará este permiso (Ej: Productos, Ventas, Usuarios)'
    )

    nombre = forms.CharField(
        max_length=255,
        required=True,
        label='Nombre del Permiso',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Puede ver reportes de ventas',
        }),
        help_text='Descripción clara de lo que permite hacer este permiso'
    )

    codigo = forms.CharField(
        max_length=100,
        required=True,
        label='Código del Permiso',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: puede_ver_reportes_ventas',
        }),
        help_text='Código único sin espacios ni caracteres especiales (usa guiones bajos)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modulo'].label_from_instance = lambda obj: (
            f"{obj.app_label.replace('_', ' ').title()} — "
            f"{obj.model.replace('_', ' ').title()}"
        )

    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo', '').lower().strip()
        if not codigo:
            raise forms.ValidationError('El código del permiso es obligatorio.')
        if len(codigo) < 3:
            raise forms.ValidationError('El código debe tener al menos 3 caracteres.')
        if not codigo.replace('_', '').isalnum():
            raise forms.ValidationError('El código solo puede contener letras, números y guiones bajos (_)')
        if Permission.objects.filter(codename=codigo).exists():
            raise forms.ValidationError(f'Ya existe un permiso con el código "{codigo}". Usa otro código único.')
        return codigo

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre del permiso es obligatorio.')
        if len(nombre) < 5:
            raise forms.ValidationError('El nombre debe tener al menos 5 caracteres.')
        return nombre
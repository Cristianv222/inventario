from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Permission, ContentType
from .models import Usuario, Rol

class CustomAuthenticationForm(AuthenticationForm):
    """Formulario personalizado de inicio de sesión"""
    username = forms.CharField(
        label="Usuario",
        widget=forms.TextInput(
            attrs={'class': 'form-control', 'placeholder': 'Nombre de usuario'}
        )
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Contraseña'}
        )
    )

class CustomPasswordChangeForm(PasswordChangeForm):
    """Formulario personalizado para cambio de contraseña"""
    old_password = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Ingrese su contraseña actual'}
        )
    )
    new_password1 = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Ingrese nueva contraseña'}
        )
    )
    new_password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Confirme nueva contraseña'}
        )
    )

class UsuarioForm(forms.ModelForm):
    """Formulario para creación y edición de usuarios"""
    password1 = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Contraseña'}
        )
    )
    password2 = forms.CharField(
        label="Confirmar Contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Confirmar Contraseña'}
        )
    )

    class Meta:
        model = Usuario
        fields = ['usuario', 'nombre', 'apellido', 'email', 'telefono', 'rol', 'activo', 'is_staff']
        widgets = {
            'usuario': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'rol': forms.Select(attrs={'class': 'form-select'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].required = not self.instance.pk
        self.fields['password2'].required = not self.instance.pk
        
        # Hacer campo opcional para edición
        if self.instance.pk:
            self.fields['usuario'].widget.attrs['readonly'] = True
            
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password1 != password2:
            self.add_error('password2', "Las contraseñas no coinciden")
            
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        
        if password:
            user.set_password(password)
            
        if commit:
            user.save()
            
        return user

class RolForm(forms.ModelForm):
    """Formulario para creación y edición de roles"""
    class Meta:
        model = Rol
        fields = ['nombre', 'descripcion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class RolPermisosForm(forms.ModelForm):
    """Formulario para asignar permisos a roles"""
    class Meta:
        model = Rol
        fields = ['nombre', 'descripcion', 'permisos', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'permisos': forms.CheckboxSelectMultiple(),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Organizar permisos por modelo/aplicación para facilitar selección
        permisos = Permission.objects.all().select_related('content_type').order_by('content_type__app_label', 'content_type__model')
        self.fields['permisos'].queryset = permisos
        self.fields['permisos'].widget.attrs['class'] = 'permisos-list'

class PermisoForm(forms.Form):
    """Formulario para crear permisos personalizados"""
    content_type = forms.ModelChoiceField(
        queryset=ContentType.objects.all().order_by('app_label', 'model'),
        label="Modelo",
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    nombre = forms.CharField(
        max_length=100, 
        required=True, 
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="Nombre descriptivo del permiso"
    )
    codename = forms.CharField(
        max_length=100, 
        required=True, 
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="Código único del permiso (sin espacios)"
    )
    
    def clean_codename(self):
        codename = self.cleaned_data.get('codename')
        if Permission.objects.filter(codename=codename).exists():
            raise forms.ValidationError("Este código de permiso ya existe")
        return codename
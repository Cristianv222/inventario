from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Permission, ContentType
from .models import Usuario

class CustomAuthenticationForm(AuthenticationForm):
    """Formulario personalizado de inicio de sesión"""
    username = forms.CharField(
        label="Usuario",
        widget=forms.TextInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Nombre de usuario',
                'autocomplete': 'username'
            }
        )
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Contraseña',
                'autocomplete': 'current-password'
            }
        )
    )

class CustomPasswordChangeForm(PasswordChangeForm):
    """Formulario personalizado para cambio de contraseña"""
    old_password = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Ingrese su contraseña actual',
                'autocomplete': 'current-password'
            }
        )
    )
    new_password1 = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Ingrese nueva contraseña',
                'autocomplete': 'new-password'
            }
        ),
        help_text='Mínimo 8 caracteres. No puede ser completamente numérica.'
    )
    new_password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Confirme nueva contraseña',
                'autocomplete': 'new-password'
            }
        )
    )

class UsuarioForm(forms.ModelForm):
    """Formulario para creación y edición de usuarios"""
    password1 = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Contraseña',
                'autocomplete': 'new-password'
            }
        ),
        help_text='Dejar en blanco para mantener la contraseña actual (solo al editar). Mínimo 8 caracteres.'
    )
    password2 = forms.CharField(
        label="Confirmar Contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control', 
                'placeholder': 'Confirmar Contraseña',
                'autocomplete': 'new-password'
            }
        )
    )

    class Meta:
        model = Usuario
        fields = ['usuario', 'nombre', 'apellido', 'email', 'telefono', 'activo', 'is_staff', 'is_superuser']
        widgets = {
            'usuario': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de usuario único',
                'autocomplete': 'username'
            }),
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre',
                'autocomplete': 'given-name'
            }),
            'apellido': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Apellido',
                'autocomplete': 'family-name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@ejemplo.com',
                'autocomplete': 'email'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Teléfono (opcional)',
                'autocomplete': 'tel'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_staff': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_superuser': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'usuario': 'Nombre de Usuario',
            'nombre': 'Nombre',
            'apellido': 'Apellido',
            'email': 'Correo Electrónico',
            'telefono': 'Teléfono',
            'activo': 'Usuario Activo',
            'is_staff': 'Es Administrador',
            'is_superuser': 'Es Super Administrador (acceso total)',
        }
        help_texts = {
            'usuario': 'Nombre único para iniciar sesión. Solo letras, números y @/./+/-/_',
            'email': 'Correo electrónico válido del usuario',
            'is_staff': 'Puede acceder al panel de administración de Django',
            'is_superuser': 'Tiene todos los permisos automáticamente sin necesidad de asignarlos',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La contraseña es obligatoria solo para nuevos usuarios
        self.fields['password1'].required = not self.instance.pk
        self.fields['password2'].required = not self.instance.pk
        
        # No permitir cambiar el nombre de usuario al editar
        if self.instance.pk:
            self.fields['usuario'].widget.attrs['readonly'] = True
            self.fields['usuario'].help_text = 'El nombre de usuario no se puede modificar'
            
    def clean_usuario(self):
        """Validar el nombre de usuario"""
        usuario = self.cleaned_data.get('usuario')
        
        # Si es un usuario nuevo, verificar que no exista
        if not self.instance.pk:
            if Usuario.objects.filter(usuario=usuario).exists():
                raise forms.ValidationError('Este nombre de usuario ya está en uso.')
        
        return usuario
    
    def clean_email(self):
        """Validar que el email sea único"""
        email = self.cleaned_data.get('email')
        
        # Verificar unicidad del email
        if self.instance.pk:
            # Al editar, excluir el email del usuario actual
            if Usuario.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Este correo electrónico ya está registrado.')
        else:
            # Al crear, verificar que no exista
            if Usuario.objects.filter(email=email).exists():
                raise forms.ValidationError('Este correo electrónico ya está registrado.')
        
        return email
            
    def clean(self):
        """Validaciones generales del formulario"""
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Validar que las contraseñas coincidan
        if password1 and password1 != password2:
            self.add_error('password2', "Las contraseñas no coinciden")
        
        # Validar que se proporcione contraseña para nuevos usuarios
        if not self.instance.pk and not password1:
            self.add_error('password1', "La contraseña es obligatoria para nuevos usuarios")
        
        # Validar complejidad de contraseña si se proporcionó una
        if password1:
            try:
                validate_password(password1, self.instance)
            except forms.ValidationError as e:
                self.add_error('password1', e)
            
        return cleaned_data
    
    def save(self, commit=True):
        """Guardar el usuario con contraseña hasheada si se proporcionó"""
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        
        # Solo cambiar la contraseña si se proporcionó una nueva
        if password:
            user.set_password(password)
            
        if commit:
            user.save()
            # Guardar relaciones many-to-many si existen
            self.save_m2m()
            
        return user

class PermisoForm(forms.Form):
    """Formulario para crear permisos personalizados"""
    
    # Campo para seleccionar en qué módulo del sistema aplica el permiso
    modulo = forms.ModelChoiceField(
        queryset=ContentType.objects.all().order_by('app_label', 'model'),
        label="Módulo del Sistema",
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        required=True,
        help_text="Selecciona el módulo donde se aplicará este permiso (Ej: Productos, Ventas, Usuarios)"
    )
    
    # Nombre descriptivo del permiso
    nombre = forms.CharField(
        max_length=255, 
        required=True, 
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Puede ver reportes de ventas'
        }),
        label="Nombre del Permiso",
        help_text="Descripción clara de lo que permite hacer este permiso"
    )
    
    # Código único del permiso (sin espacios)
    codigo = forms.CharField(
        max_length=100, 
        required=True, 
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: puede_ver_reportes_ventas'
        }),
        label="Código del Permiso",
        help_text="Código único sin espacios ni caracteres especiales (usa guiones bajos)"
    )
    
    def clean_codigo(self):
        """Validar que el código sea único y tenga formato correcto"""
        codigo = self.cleaned_data.get('codigo')
        
        if not codigo:
            raise forms.ValidationError("El código del permiso es obligatorio.")
        
        # Verificar que no exista ya
        if Permission.objects.filter(codename=codigo).exists():
            raise forms.ValidationError("Este código de permiso ya existe. Usa otro código único.")
        
        # Validar formato (solo letras, números y guiones bajos)
        if not codigo.replace('_', '').isalnum():
            raise forms.ValidationError("El código solo puede contener letras, números y guiones bajos (_)")
        
        # Validar longitud
        if len(codigo) < 3:
            raise forms.ValidationError("El código debe tener al menos 3 caracteres.")
            
        return codigo.lower()  # Convertir a minúsculas
    
    def clean_nombre(self):
        """Validar el nombre del permiso"""
        nombre = self.cleaned_data.get('nombre')
        
        if not nombre:
            raise forms.ValidationError("El nombre del permiso es obligatorio.")
        
        # Validar longitud mínima
        if len(nombre.strip()) < 5:
            raise forms.ValidationError("El nombre debe tener al menos 5 caracteres.")
        
        return nombre.strip()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Personalizar las opciones del campo modulo para que sean más legibles
        self.fields['modulo'].label_from_instance = lambda obj: (
            f"{obj.app_label.replace('_', ' ').title()} - "
            f"{obj.model.replace('_', ' ').title()}"
        )
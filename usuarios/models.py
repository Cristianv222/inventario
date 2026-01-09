from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _

class UsuarioManager(BaseUserManager):
    """Manager personalizado para el modelo Usuario"""
    
    def create_user(self, usuario, email, password=None, **extra_fields):
        if not usuario:
            raise ValueError('El nombre de usuario es obligatorio')
        if not email:
            raise ValueError('El correo electrónico es obligatorio')
        
        email = self.normalize_email(email)
        user = self.model(usuario=usuario, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, usuario, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('activo', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')
        
        return self.create_user(usuario, email, password, **extra_fields)

class Usuario(AbstractUser):
    """Modelo de usuario personalizado"""
    
    # Eliminar el campo username de AbstractUser
    username = None
    
    # Campos personalizados
    usuario = models.CharField(
        _('nombre de usuario'), 
        max_length=50, 
        unique=True,
        help_text=_('Requerido. 50 caracteres o menos.')
    )
    nombre = models.CharField(_('nombre'), max_length=100)
    apellido = models.CharField(_('apellido'), max_length=100)
    email = models.EmailField(_('dirección de correo'), unique=True)
    telefono = models.CharField(_('teléfono'), max_length=20, blank=True, null=True)
    activo = models.BooleanField(_('activo'), default=True)
    fecha_creacion = models.DateTimeField(_('fecha de creación'), auto_now_add=True)
    fecha_modificacion = models.DateTimeField(_('fecha de modificación'), auto_now=True)
    
    # Configuración del campo de autenticación
    USERNAME_FIELD = 'usuario'
    REQUIRED_FIELDS = ['email', 'nombre', 'apellido']
    
    # Manager personalizado
    objects = UsuarioManager()
    
    class Meta:
        verbose_name = _('Usuario')
        verbose_name_plural = _('Usuarios')
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.usuario})"
    
    def get_nombre_completo(self):
        """Retorna el nombre completo del usuario"""
        return f"{self.nombre} {self.apellido}".strip()
    
    def get_nombre_corto(self):
        """Retorna el nombre del usuario"""
        return self.nombre
    
    def save(self, *args, **kwargs):
        """Sobreescribir save para sincronizar activo con is_active"""
        self.is_active = self.activo
        super().save(*args, **kwargs)
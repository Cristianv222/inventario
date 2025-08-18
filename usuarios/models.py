from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, Permission
from django.utils.translation import gettext_lazy as _

class Rol(models.Model):
    """Roles de usuarios en el sistema"""
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    permisos = models.ManyToManyField(Permission, blank=True, verbose_name=_('permisos'))
    activo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = _('Rol')
        verbose_name_plural = _('Roles')
    
    def __str__(self):
        return self.nombre

class UsuarioManager(BaseUserManager):
    """Manager personalizado para el modelo Usuario"""
    
    def create_user(self, usuario, email, password=None, **extra_fields):
        if not usuario:
            raise ValueError('El nombre de usuario es obligatorio')
        email = self.normalize_email(email)
        user = self.model(usuario=usuario, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, usuario, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(usuario, email, password, **extra_fields)

class Usuario(AbstractUser):
    """Modelo de usuario personalizado"""
    username = None  # Eliminar el campo username de AbstractUser
    usuario = models.CharField(_('nombre de usuario'), max_length=50, unique=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(_('dirección de correo'), unique=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    rol = models.ForeignKey(Rol, on_delete=models.SET_NULL, null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    USERNAME_FIELD = 'usuario'
    REQUIRED_FIELDS = ['email', 'nombre', 'apellido']
    
    objects = UsuarioManager()
    
    class Meta:
        verbose_name = _('Usuario')
        verbose_name_plural = _('Usuarios')
    
    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.usuario})"
    
    def tiene_permiso(self, codename):
        """Verifica si el usuario tiene un permiso específico"""
        # Superusuarios tienen todos los permisos
        if self.is_superuser:
            return True
            
        # Verificar permisos basados en el rol
        if self.rol and self.rol.activo:
            return self.rol.permisos.filter(codename=codename).exists()
            
        return False
    
    def save(self, *args, **kwargs):
        """Sobreescribir save para sincronizar activo con is_active"""
        self.is_active = self.activo
        super().save(*args, **kwargs)
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django_tenants.models import TenantMixin, DomainMixin


class Sucursal(TenantMixin):
    """
    Sucursales de VPMOTOS
    Cada sucursal tiene su propio schema PostgreSQL con datos aislados
    """
    # TenantMixin agrega automáticamente:
    # - schema_name: Nombre del schema en PostgreSQL
    # - created_on: Fecha de creación
    
    # Información básica
    codigo = models.CharField(
        max_length=10, 
        unique=True,
        help_text="Código único de la sucursal (ej: QUITO, CAYAMBE)"
    )
    nombre = models.CharField(
        max_length=100, 
        unique=True,
        verbose_name="Nombre de la sucursal"
    )
    nombre_corto = models.CharField(
        max_length=50,
        help_text="Nombre corto para mostrar en reportes y pantallas"
    )
    
    # Ubicación
    direccion = models.CharField(max_length=200)
    ciudad = models.CharField(max_length=100)
    provincia = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    celular = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Datos fiscales
    ruc = models.CharField(
        max_length=13,
        blank=True,
        null=True,
        help_text="RUC de la sucursal si aplica"
    )
    nombre_comercial = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )
    
    # Configuración
    es_principal = models.BooleanField(
        default=False,
        help_text="Marca esta sucursal como principal/matriz"
    )
    activa = models.BooleanField(default=True)
    
    # Configuración de numeración de documentos
    prefijo_facturas = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        help_text="Prefijo para numeración de facturas (ej: 001)"
    )
    prefijo_ordenes = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        help_text="Prefijo para numeración de órdenes (ej: OT-A)"
    )
    
    # Metadata
    fecha_apertura = models.DateField()
    fecha_cierre = models.DateField(blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    # ✅ Configuración de django-tenants
    auto_create_schema = True  # Crear schema automáticamente
    auto_drop_schema = False   # NO borrar schema al eliminar registro
    
    class Meta:
        verbose_name = _('Sucursal')
        verbose_name_plural = _('Sucursales')
        ordering = ['-es_principal', 'nombre']
        indexes = [
            models.Index(fields=['codigo']),
            models.Index(fields=['activa']),
            models.Index(fields=['es_principal']),
        ]
    
    def __str__(self):
        if self.es_principal:
            return f"{self.nombre} (Matriz)"
        return self.nombre
    
    def save(self, *args, **kwargs):
        # Generar schema_name automáticamente del código
        if not self.schema_name:
            self.schema_name = self.codigo.lower().replace('-', '_').replace(' ', '_')
        
        # Validar que solo haya una sucursal principal
        if self.es_principal:
            Sucursal.objects.filter(es_principal=True).exclude(pk=self.pk).update(es_principal=False)
        
        # Si no hay ninguna sucursal principal, marcar esta como principal
        if not Sucursal.objects.filter(es_principal=True).exists():
            self.es_principal = True
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """Validaciones del modelo"""
        # Validar que el código solo tenga letras, números y guiones
        import re
        if not re.match(r'^[A-Z0-9_-]+$', self.codigo):
            raise ValidationError({
                'codigo': 'El código solo puede contener letras mayúsculas, números, guiones y guiones bajos'
            })
        
        # Validar que la sucursal principal no pueda ser desactivada
        if not self.activa and self.es_principal:
            raise ValidationError({
                'activa': 'La sucursal principal no puede ser desactivada'
            })
        
        # Validar que schema_name no sea una palabra reservada
        palabras_reservadas = ['public', 'postgres', 'template0', 'template1']
        if self.schema_name and self.schema_name.lower() in palabras_reservadas:
            raise ValidationError({
                'codigo': f'No puede usar "{self.codigo}" como código (palabra reservada)'
            })
    
    def get_usuarios_count(self):
        """Cuenta usuarios asignados a esta sucursal"""
        return self.usuarios.filter(activo=True).count()
    
    def get_direccion_completa(self):
        """Retorna la dirección completa"""
        return f"{self.direccion}, {self.ciudad}, {self.provincia}"
    
    @classmethod
    def get_sucursal_principal(cls):
        """Obtiene la sucursal principal/matriz"""
        return cls.objects.filter(es_principal=True, activa=True).first()
    
    @classmethod
    def get_sucursales_activas(cls):
        """Obtiene todas las sucursales activas"""
        return cls.objects.filter(activa=True)


class DominioSucursal(DomainMixin):
    """
    Dominios/subdominios para acceder a cada sucursal
    Ejemplo: cayambe.vpmotos.com, quito.vpmotos.com
    
    Para desarrollo local se usa: cayambe.localhost, quito.localhost
    """
    
    class Meta:
        verbose_name = _('Dominio de Sucursal')
        verbose_name_plural = _('Dominios de Sucursales')
    
    def __str__(self):
        return f"{self.domain} → {self.tenant.nombre}"


class ParametroSistema(models.Model):
    """Parámetros de configuración del sistema"""
    nombre = models.CharField(max_length=50, unique=True)
    valor = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Parámetro del Sistema')
        verbose_name_plural = _('Parámetros del Sistema')
    
    def __str__(self):
        return f"{self.nombre}: {self.valor}"
from django.db import models
from django.utils.translation import gettext_lazy as _

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
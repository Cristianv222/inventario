from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
from django.conf import settings
from usuarios.models import Usuario

class Marca(models.Model):
    """Marcas de productos"""
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    activa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = _('Marca')
        verbose_name_plural = _('Marcas')
    
    def __str__(self):
        return self.nombre

class CategoriaProducto(models.Model):
    """Categorías de productos"""
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    porcentaje_ganancia = models.DecimalField(max_digits=10, decimal_places=2)
    activa = models.BooleanField(default=True)
    codigo = models.CharField(max_length=20, unique=True)
    categoria_padre = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategorias')
    
    class Meta:
        verbose_name = _('Categoría de Producto')
        verbose_name_plural = _('Categorías de Productos')
    
    def __str__(self):
        return self.nombre
    
    def get_path(self):
        """Obtiene la ruta completa de la categoría (con padres)"""
        if self.categoria_padre:
            return f"{self.categoria_padre.get_path()} > {self.nombre}"
        return self.nombre

class Producto(models.Model):
    """Productos/repuestos en el inventario"""
    categoria = models.ForeignKey(CategoriaProducto, on_delete=models.CASCADE, related_name='productos')
    marca = models.ForeignKey(Marca, on_delete=models.CASCADE, related_name='productos')
    codigo_unico = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    stock_actual = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=0)
    incluye_iva = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_ultima_compra = models.DateTimeField(null=True, blank=True)
    ubicacion_almacen = models.CharField(max_length=100, blank=True, null=True)
    codigo_barras = models.ImageField(upload_to='codigos_barras/', blank=True, null=True)
    
    class Meta:
        verbose_name = _('Producto')
        verbose_name_plural = _('Productos')
        ordering = ['nombre']
    
    def __str__(self):
        return f"{self.nombre} ({self.codigo_unico})"
    
    def save(self, *args, **kwargs):
        # Si es un producto nuevo, generar código único y de barras
        if not self.pk:
            if not self.codigo_unico:
                # Generar código único si no existe
                categoria_prefix = self.categoria.codigo[:3] if self.categoria and self.categoria.codigo else "PRO"
                self.codigo_unico = f"{categoria_prefix}-{uuid.uuid4().hex[:8].upper()}"
            
            # Si no hay precio de venta, calcularlo
            if not self.precio_venta:
                self.precio_venta = self.calcular_precio_venta()
        
        super().save(*args, **kwargs)
    
    def es_stock_bajo(self):
        """Verifica si el stock está por debajo del mínimo"""
        return self.stock_actual <= self.stock_minimo
    
    def calcular_precio_venta(self):
        """Calcula el precio de venta basado en el precio de compra y el porcentaje de ganancia de la categoría"""
        if self.categoria and self.precio_compra:
            porcentaje = 1 + (self.categoria.porcentaje_ganancia / 100)
            precio_calculado = self.precio_compra * porcentaje
            return round(precio_calculado, 2)
        return self.precio_compra
    
    def generar_codigo_barras(self):
        """Genera la imagen del código de barras"""
        try:
            # Generar código de barras
            COD128 = barcode.get_barcode_class('code128')
            rv = BytesIO()
            code = COD128(self.codigo_unico, writer=ImageWriter())
            code.write(rv)
            
            # Guardar la imagen
            self.codigo_barras.save(
                f'{self.codigo_unico}.png', 
                File(rv), 
                save=True
            )
            return True
        except Exception as e:
            print(f"Error al generar código de barras: {e}")
            return False

class InventarioAjuste(models.Model):
    """Ajustes manuales al inventario"""
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
        ('AJUSTE', 'Ajuste'),
    ]
    
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='ajustes')
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    tipo_ajuste = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.TextField()
    fecha_hora = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('Ajuste de Inventario')
        verbose_name_plural = _('Ajustes de Inventario')
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.get_tipo_ajuste_display()} - {self.producto.nombre} ({self.cantidad})"
    
    def save(self, *args, **kwargs):
        # Si es un nuevo ajuste, actualizar el stock del producto
        if not self.pk:
            if self.tipo_ajuste == 'ENTRADA':
                self.producto.stock_actual += self.cantidad
            elif self.tipo_ajuste == 'SALIDA':
                self.producto.stock_actual -= self.cantidad
            elif self.tipo_ajuste == 'AJUSTE':
                # En ajuste, la cantidad es el nuevo valor absoluto
                diferencia = self.cantidad - self.producto.stock_actual
                self.producto.stock_actual = self.cantidad
                # Ajustar la cantidad al cambio real para el registro
                self.cantidad = diferencia
            
            self.producto.save()
        
        super().save(*args, **kwargs)

class MovimientoInventario(models.Model):
    """Movimientos automáticos de inventario (ventas, compras)"""
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
    ]
    
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='movimientos')
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    tipo_movimiento = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    motivo = models.TextField()
    fecha_hora = models.DateTimeField(auto_now_add=True)
    referencia = models.CharField(max_length=100, blank=True, null=True)
    venta = models.ForeignKey('ventas.Venta', on_delete=models.CASCADE, null=True, blank=True)
    
    # Reemplazar la relación con un campo de referencia temporal
    compra_ref = models.CharField(max_length=100, verbose_name=_('Referencia de Compra'), blank=True, null=True)
    # Comentar esta línea que causa el error:
    # compra = models.ForeignKey('compras.Compra', on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        verbose_name = _('Movimiento de Inventario')
        verbose_name_plural = _('Movimientos de Inventario')
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.get_tipo_movimiento_display()} - {self.producto.nombre} ({self.cantidad})"


# Señal para generar código de barras después de guardar
@receiver(post_save, sender=Producto)
def generar_barcode_post_save(sender, instance, created, **kwargs):
    """Genera el código de barras después de guardar el producto si no existe"""
    if not instance.codigo_barras:
        instance.generar_codigo_barras()
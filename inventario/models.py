from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import pre_save, post_save
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
    """CategorÃ­as de productos"""
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    porcentaje_ganancia = models.DecimalField(max_digits=10, decimal_places=2)
    activa = models.BooleanField(default=True)
    codigo = models.CharField(max_length=20, unique=True)
    categoria_padre = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategorias')
    
    class Meta:
        verbose_name = _('CategorÃ­a de Producto')
        verbose_name_plural = _('CategorÃ­as de Productos')
    
    def __str__(self):
        return self.nombre
    
    def get_path(self):
        """Obtiene la ruta completa de la categorÃ­a (con padres)"""
        if self.categoria_padre:
            return f"{self.categoria_padre.get_path()} > {self.nombre}"
        return self.nombre

class Producto(models.Model):
    """Productos/repuestos en el inventario"""
    categoria = models.ForeignKey(CategoriaProducto, on_delete=models.CASCADE, related_name='productos')
    marca = models.ForeignKey(Marca, on_delete=models.CASCADE, related_name='productos')
    codigo_unico = models.CharField(max_length=50, unique=True, verbose_name=_('CÃ³digo Ãšnico'))
    nombre = models.CharField(max_length=200, verbose_name=_('Nombre del Producto'))
    descripcion = models.TextField(blank=True, null=True, verbose_name=_('DescripciÃ³n'))
    
    # Precios
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Precio de Compra'))
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Precio de Venta'))
    incluye_iva = models.BooleanField(default=True, verbose_name=_('Incluye IVA'))
    
    # Stock
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Stock Actual'))
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Stock MÃ­nimo'))
    
    # Metadata
    activo = models.BooleanField(default=True, verbose_name=_('Activo'))
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    ubicacion_almacen = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('UbicaciÃ³n en AlmacÃ©n'))
    
    # ImÃ¡genes
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True, verbose_name=_('Imagen Principal'))
    imagen_2 = models.ImageField(upload_to='productos/', blank=True, null=True, verbose_name=_('Imagen 2'))
    imagen_3 = models.ImageField(upload_to='productos/', blank=True, null=True, verbose_name=_('Imagen 3'))
    
    # CÃ³digo de barras generado
    codigo_barras = models.ImageField(upload_to='barcodes/', blank=True, null=True, editable=False)
    
    class Meta:
        verbose_name = _('Producto')
        verbose_name_plural = _('Productos')
        ordering = ['nombre']
    
    def __str__(self):
        return f"{self.nombre} ({self.codigo_unico})"
    
    def save(self, *args, **kwargs):
        # Generar cÃ³digo de barras si no existe o si el cÃ³digo Ãºnico cambiÃ³
        if not self.codigo_barras or (self.pk and Producto.objects.get(pk=self.pk).codigo_unico != self.codigo_unico):
            self.generar_codigo_barras()
        super().save(*args, **kwargs)
    
    def generar_codigo_barras(self):
        """Genera una imagen de cÃ³digo de barras basada en el cÃ³digo Ãºnico"""
        if not self.codigo_unico:
            return False
            
        try:
            EAN = barcode.get_kind('code128')
            barcode_instance = EAN(self.codigo_unico, writer=ImageWriter())
            
            # Ajustar opciones del escritor para un diseÃ±o mÃ¡s limpio
            options = {
                'module_width': 0.2,
                'module_height': 7.0,
                'font_size': 8,
                'text_distance': 3.0,
                'quiet_zone': 2.0,
            }
            
            buffer = BytesIO()
            barcode_instance.write(buffer, options=options)
            
            file_name = f'barcode_{self.codigo_unico}.png'
            self.codigo_barras.save(file_name, File(buffer), save=False)
            return True
        except Exception as e:
            print(f"Error al generar cÃ³digo de barras: {e}")
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
            stock_anterior = self.producto.stock_actual
            cantidad_ajuste = self.cantidad
            
            if self.tipo_ajuste == 'ENTRADA':
                self.producto.stock_actual += int(self.cantidad)
            elif self.tipo_ajuste == 'SALIDA':
                self.producto.stock_actual -= int(self.cantidad)
            elif self.tipo_ajuste == 'AJUSTE':
                # En ajuste, la cantidad ingresada es el nuevo stock total
                # Calculamos la diferencia para el movimiento
                cantidad_ajuste = self.cantidad - stock_anterior
                self.producto.stock_actual = int(self.cantidad)
            
            # Guardar el producto con el nuevo stock
            self.producto.save()
            
            # Crear un MovimientoInventario para el historial general
            from .models import MovimientoInventario
            MovimientoInventario.objects.create(
                producto=self.producto,
                usuario=self.usuario,
                tipo_movimiento='ENTRADA' if cantidad_ajuste > 0 else 'SALIDA',
                cantidad=abs(cantidad_ajuste),
                motivo=f"Ajuste manual ({self.get_tipo_ajuste_display()}): {self.motivo}",
                referencia=f"AJUSTE-{self.id or 'NUEVO'}"
            )
        
        super().save(*args, **kwargs)

class MovimientoInventario(models.Model):
    """Movimientos automÃ¡ticos de inventario (ventas, compras)"""
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
    ]
    
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='movimientos')
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, null=True, blank=True)
    tipo_movimiento = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    stock_anterior = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_nuevo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    motivo = models.TextField()
    fecha_hora = models.DateTimeField(auto_now_add=True)
    referencia = models.CharField(max_length=100, blank=True, null=True)
    venta = models.ForeignKey('ventas.Venta', on_delete=models.CASCADE, null=True, blank=True)
    
    # Reemplazar la relaciÃ³n con un campo de referencia temporal
    compra_ref = models.CharField(max_length=100, verbose_name=_('Referencia de Compra'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('Movimiento de Inventario')
        verbose_name_plural = _('Movimientos de Inventario')
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.get_tipo_movimiento_display()} - {self.producto.nombre} ({self.cantidad})"


# SeÃ±al para generar cÃ³digo de barras despuÃ©s de guardar
@receiver(post_save, sender=Producto)
def generar_barcode_post_save(sender, instance, created, **kwargs):
    """Genera el cÃ³digo de barras despuÃ©s de guardar el producto si no existe"""
    if not instance.codigo_barras:
        instance.generar_codigo_barras()

class TransferenciaInventario(models.Model):
    """
    Transferencias de productos entre sucursales
    Este modelo vive en el schema PUBLIC para ser accesible desde todas las sucursales
    """
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de envÃ­o'),
        ('EN_TRANSITO', 'En trÃ¡nsito'),
        ('RECIBIDA', 'Recibida'),
        ('CANCELADA', 'Cancelada'),
    ]
    
    # RelaciÃ³n con sucursales (schema PUBLIC)
    sucursal_origen = models.ForeignKey(
        'core.Sucursal',
        on_delete=models.PROTECT,
        related_name='transferencias_enviadas',
        verbose_name=_('Sucursal Origen')
    )
    sucursal_destino = models.ForeignKey(
        'core.Sucursal',
        on_delete=models.PROTECT,
        related_name='transferencias_recibidas',
        verbose_name=_('Sucursal Destino')
    )
    
    # Usuarios involucrados
    usuario_envia = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='transferencias_enviadas',
        verbose_name=_('Usuario que envÃ­a')
    )
    usuario_recibe = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='transferencias_recibidas',
        null=True,
        blank=True,
        verbose_name=_('Usuario que recibe')
    )
    
    # Estado y fechas
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
        verbose_name=_('Estado')
    )
    fecha_envio = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Fecha de envÃ­o')
    )
    fecha_recepcion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Fecha de recepciÃ³n')
    )
    
    # InformaciÃ³n adicional
    numero_guia = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name=_('NÃºmero de guÃ­a')
    )
    observaciones_envio = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Observaciones del envÃ­o')
    )
    observaciones_recepcion = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Observaciones de la recepciÃ³n')
    )
    
    class Meta:
        verbose_name = _('Transferencia de Inventario')
        verbose_name_plural = _('Transferencias de Inventario')
        ordering = ['-fecha_envio']
        indexes = [
            models.Index(fields=['sucursal_origen', 'estado']),
            models.Index(fields=['sucursal_destino', 'estado']),
            models.Index(fields=['numero_guia']),
        ]
    
    def __str__(self):
        return f"Transferencia #{self.numero_guia} - {self.sucursal_origen.codigo} â†’ {self.sucursal_destino.codigo}"
    
    def save(self, *args, **kwargs):
        # Generar nÃºmero de guÃ­a Ãºnico
        if not self.numero_guia:
            import uuid
            from datetime import datetime
            fecha = datetime.now().strftime('%Y%m%d')
            self.numero_guia = f"TRF-{fecha}-{uuid.uuid4().hex[:8].upper()}"
        
        super().save(*args, **kwargs)
    
    def get_total_productos(self):
        """Obtiene el total de productos en la transferencia"""
        return self.detalles.count()
    
    def get_total_cantidad(self):
        """Obtiene la cantidad total de items"""
        from django.db.models import Sum
        total = self.detalles.aggregate(total=Sum('cantidad_enviada'))['total']
        return total or 0
    
    def puede_ser_recibida(self):
        """Verifica si la transferencia puede ser recibida"""
        return self.estado in ['PENDIENTE', 'EN_TRANSITO']
    
    def puede_ser_cancelada(self):
        """Verifica si la transferencia puede ser cancelada"""
        return self.estado == 'PENDIENTE'


class DetalleTransferencia(models.Model):
    """
    Detalle de productos en una transferencia
    Almacena cÃ³digo y nombre para mantener referencia aunque el producto cambie
    """
    transferencia = models.ForeignKey(
        TransferenciaInventario,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name=_('Transferencia')
    )
    
    # InformaciÃ³n del producto (guardada como texto para persistencia)
    producto_codigo = models.CharField(
        max_length=50,
        verbose_name=_('CÃ³digo del producto')
    )
    producto_nombre = models.CharField(
        max_length=200,
        verbose_name=_('Nombre del producto')
    )
    
    # Cantidades
    cantidad_enviada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Cantidad enviada')
    )
    cantidad_recibida = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Cantidad recibida')
    )
    
    # Observaciones sobre diferencias
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Observaciones')
    )
    
    class Meta:
        verbose_name = _('Detalle de Transferencia')
        verbose_name_plural = _('Detalles de Transferencia')
        ordering = ['producto_nombre']
    
    def __str__(self):
        return f"{self.producto_nombre} ({self.cantidad_enviada})"
    
    def tiene_diferencia(self):
        """Verifica si hay diferencia entre enviado y recibido"""
        if self.cantidad_recibida is None:
            return False
        return self.cantidad_enviada != self.cantidad_recibida
    
    def get_diferencia(self):
        """Obtiene la diferencia entre enviado y recibido"""
        if self.cantidad_recibida is None:
            return 0
        return self.cantidad_recibida - self.cantidad_enviada


# ============================================================================
# SIGNALS PARA TRAZABILIDAD DE STOCK
# ============================================================================

@receiver(pre_save, sender=Producto)
def track_stock_change(sender, instance, **kwargs):
    """Guarda el stock anterior antes de guardar para comparar"""
    if instance.pk:
        try:
            # Usar .only para eficiencia
            old_instance = Producto.objects.filter(pk=instance.pk).only('stock_actual').first()
            instance._old_stock = old_instance.stock_actual if old_instance else 0
        except Exception:
            instance._old_stock = 0
    else:
        instance._old_stock = 0

@receiver(post_save, sender=Producto)
def create_movement_on_stock_change(sender, instance, created, **kwargs):
    """Crea un movimiento de inventario automáticamente si el stock cambió"""
    old_stock = getattr(instance, '_old_stock', 0)
    new_stock = instance.stock_actual
    
    if created or old_stock != new_stock:
        diferencia = new_stock - old_stock
        tipo = 'ENTRADA' if diferencia > 0 else 'SALIDA'
        
        # MovimientoInventario ya acepta usuario=None
        from .models import MovimientoInventario
        MovimientoInventario.objects.create(
            producto=instance,
            tipo_movimiento=tipo,
            cantidad=abs(diferencia),
            stock_anterior=old_stock,
            stock_nuevo=new_stock,
            motivo=f"Ajuste automático por edición/creación de producto (Cambio: {diferencia})"
        )

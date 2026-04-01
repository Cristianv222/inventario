from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from clientes.models import Cliente
from inventario.models import Producto
from usuarios.models import Usuario
import random
import string

class Venta(models.Model):
    """Modelo para registro de ventas"""
    ESTADO_CHOICES = [
        ('COMPLETADA', 'Completada'),
        ('ANULADA', 'Anulada'),
    ]
    
    TIPO_PAGO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta de Crédito/Débito'),
        ('TRANSFERENCIA', 'Transferencia Bancaria'),
        ('CHEQUE', 'Cheque'),
        ('CREDITO', 'Crédito'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    numero_factura = models.CharField(max_length=20, unique=True)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    iva = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='COMPLETADA')
    tipo_pago = models.CharField(max_length=50, choices=TIPO_PAGO_CHOICES)
    observaciones = models.TextField(blank=True, null=True)
    datos_pago = models.CharField(max_length=255, blank=True, null=True)
    numero_autorizacion = models.CharField(max_length=50, blank=True, null=True)
    
    # ⭐ NUEVO CAMPO para vinculación con orden de trabajo
    orden_trabajo = models.ForeignKey(
        'taller.OrdenTrabajo', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name='ventas',
        help_text="Orden de trabajo asociada a esta venta"
    )
    
    class Meta:
        verbose_name = _('Venta')
        verbose_name_plural = _('Ventas')
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"Factura #{self.numero_factura}"
    
    def save(self, *args, **kwargs):
        # Si es una venta nueva, generar número de factura si no existe
        if not self.pk and not self.numero_factura:
            self.numero_factura = self.generar_numero_factura()
        
        # Ajustar el total si cambia el descuento
        self.total = self.subtotal + self.iva - self.descuento
        
        super().save(*args, **kwargs)
    
    def anular(self):
        """Anula la venta y revierte el inventario"""
        if self.estado == 'COMPLETADA':
            # Revertir inventario
            for detalle in self.detalleventa_set.filter(producto__isnull=False):
                producto = detalle.producto
                if producto:
                    producto.stock_actual += detalle.cantidad
                    producto.save()
            
            # Cambiar estado de la venta
            self.estado = 'ANULADA'
            self.save()
            return True
        return False
    
    def get_total_servicios_sin_iva(self):
        """Calcula el total de servicios sin IVA"""
        return self.detalleventa_set.filter(
            es_servicio=True
        ).aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0.00')
    
    def get_total_productos_con_iva(self):
        """Calcula el total de productos con IVA"""
        return self.detalleventa_set.filter(
            es_servicio=False
        ).aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0.00')
    
    @staticmethod
    def generar_numero_factura():
        """Genera un número único de factura"""
        ultimo_num = Venta.objects.order_by('-id').first()
        
        if ultimo_num:
            try:
                # Extraer el número y aumentarlo en 1
                numero = int(ultimo_num.numero_factura.split('-')[1])
                nuevo_numero = numero + 1
            except (ValueError, IndexError):
                # Si hay error, generar un nuevo número
                nuevo_numero = 1
        else:
            nuevo_numero = 1
            
        # Formatear con ceros a la izquierda (ej. FAC-000001)
        return f"FAC-{nuevo_numero:06d}"
    
    @staticmethod
    def get_ventas_por_dia(fecha=None):
        """Obtiene el total de ventas por día, incluyendo impacto de devoluciones"""
        from datetime import datetime, time
        if fecha is None:
            fecha = timezone.localdate()
            
        # Filtrar ventas por fecha (usando rangos para evitar problemas de tz locales en DB)
        start_dt = timezone.make_aware(datetime.combine(fecha, time.min))
        end_dt = timezone.make_aware(datetime.combine(fecha, time.max))
        
        ventas = Venta.objects.filter(
            fecha_hora__range=(start_dt, end_dt),
            estado='COMPLETADA'
        )
        
        # Calcular totales
        total_productos = sum(
            detalle.total for venta in ventas 
            for detalle in venta.detalleventa_set.filter(producto__isnull=False)
        )
        
        total_servicios = sum(
            detalle.total for venta in ventas 
            for detalle in venta.detalleventa_set.filter(servicio__isnull=False)
        )
        
        # Incluir servicios nuevos (es_servicio=True)
        total_servicios_nuevos = sum(
            detalle.total for venta in ventas 
            for detalle in venta.detalleventa_set.filter(es_servicio=True, tipo_servicio__isnull=False)
        )
        total_servicios += total_servicios_nuevos
        
        total_ventas = sum(venta.total for venta in ventas)
        
        # Devoluciones del día
        from django.apps import apps
        Devolucion = apps.get_model('ventas', 'Devolucion')
        devoluciones = Devolucion.objects.filter(
            fecha_hora__range=(start_dt, end_dt),
            estado='COMPLETADA'
        )
        
        total_reembolsos = sum(abs(d.diferencia) for d in devoluciones if d.diferencia < 0)
        total_ingresos_extra = sum(d.diferencia for d in devoluciones if d.diferencia > 0)
        
        return {
            'fecha': fecha,
            'total_productos': total_productos,
            'total_servicios': total_servicios,
            'total_ventas': total_ventas,
            'num_ventas': ventas.count(),
            'total_reembolsos': total_reembolsos,
            'total_ingresos_extra': total_ingresos_extra,
            'ventas_netas': total_ventas + total_ingresos_extra - total_reembolsos
        }

    

class DetalleVenta(models.Model):
    """Detalle de los productos o servicios vendidos"""
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, null=True, blank=True)
    
    # Campo antiguo - mantenido por compatibilidad con related_name único
    servicio = models.ForeignKey(
        'taller.TipoServicio', 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='detalles_venta_antiguos'  # ✅ Agregado related_name
    )
    
    tecnico = models.ForeignKey('taller.Tecnico', on_delete=models.SET_NULL, null=True, blank=True,
                               help_text="Técnico que realizó el servicio")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    iva = models.DecimalField(max_digits=10, decimal_places=2)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Porcentaje de descuento aplicado")
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    observaciones = models.TextField(blank=True, null=True)
    
    # ⭐ NUEVOS CAMPOS para servicios del taller
    tipo_servicio = models.ForeignKey(
        'taller.TipoServicio',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='detalles_venta',
        help_text="Tipo de servicio del taller"
    )
    
    nombre_personalizado = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Nombre para items manuales o genéricos"
    )
    
    es_servicio = models.BooleanField(
        default=False,
        help_text="Indica si este detalle es un servicio (sin IVA)"
    )
    
    class Meta:
        verbose_name = _('Detalle de Venta')
        verbose_name_plural = _('Detalles de Venta')
    
    def __str__(self):
        if self.tipo_servicio:
            return f"{self.tipo_servicio.nombre} - {self.cantidad} x ${self.precio_unitario}"
        elif self.producto:
            return f"{self.producto.nombre} - {self.cantidad} x ${self.precio_unitario}"
        elif self.servicio:
            return f"{self.servicio.nombre} - {self.cantidad} x ${self.precio_unitario}"
        return f"Detalle {self.id}"
    
    def save(self, *args, **kwargs):
        # Calcular subtotal
        self.subtotal = self.cantidad * self.precio_unitario
        
        # ⭐ NUEVO: Cálculo automático para servicios sin IVA y productos con/sin IVA
        if self.es_servicio:
            # Los servicios no tienen IVA (o según configuración de servicio, por ahora asumo 0)
            self.iva_porcentaje = Decimal('0.00')
            self.iva = Decimal('0.00')
            self.total = self.subtotal - self.descuento
        else:
            # Productos: Verificar si el producto lleva IVA
            if self.producto:
                if self.producto.incluye_iva:
                    # Usar configuración global o default 15%
                    iva_rate = Decimal(str(settings.VPMOTOS_SETTINGS.get('IVA_PERCENTAGE', 15.0)))
                    self.iva_porcentaje = iva_rate
                    self.iva = self.subtotal * (self.iva_porcentaje / 100)
                else:
                    self.iva_porcentaje = Decimal('0.00')
                    self.iva = Decimal('0.00')
            else:
                # Si no hay producto asociado (raro), usar default
                iva_rate = Decimal(str(settings.VPMOTOS_SETTINGS.get('IVA_PERCENTAGE', 15.0)))
                self.iva_porcentaje = iva_rate
                self.iva = self.subtotal * (self.iva_porcentaje / 100)
            
            self.total = self.subtotal + self.iva - self.descuento
        
        super().save(*args, **kwargs)
    
    def get_nombre_item(self):
        """Devuelve el nombre del producto o servicio"""
        if self.nombre_personalizado:
            return self.nombre_personalizado
        if self.tipo_servicio:
            return self.tipo_servicio.nombre
        elif self.producto:
            return self.producto.nombre
        elif self.servicio:  # Compatibilidad con modelo anterior
            return self.servicio.nombre
        return "Item desconocido"
    
    def get_codigo_item(self):
        """Devuelve el código del producto o servicio"""
        if self.tipo_servicio:
            return self.tipo_servicio.codigo
        elif self.producto:
            return self.producto.codigo_unico
        elif self.servicio:
            return self.servicio.codigo
        return ""


class CierreCaja(models.Model):
    """Registro de cierre de caja diario"""
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    fecha = models.DateField()
    fecha_hora = models.DateTimeField(auto_now_add=True)
    total_productos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_servicios = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_ventas = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_reembolsos = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Dinero devuelto a clientes")
    total_ingresos_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Dinero extra cobrado por cambios a mayor valor")
    ventas_netas = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Ventas + Ingresos Extras - Reembolsos")
    observaciones = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = _('Cierre de Caja')
        verbose_name_plural = _('Cierres de Caja')
        ordering = ['-fecha']
    
    def __str__(self):
        return f"Cierre de Caja {self.fecha}"
    
    def save(self, *args, **kwargs):
        # Si es un nuevo registro, calcular totales
        if not self.pk:
            ventas_dia = Venta.get_ventas_por_dia(self.fecha)
            self.total_productos = ventas_dia['total_productos']
            self.total_servicios = ventas_dia['total_servicios']
            self.total_ventas = ventas_dia['total_ventas']
            self.total_reembolsos = ventas_dia.get('total_reembolsos', Decimal('0.00'))
            self.total_ingresos_extra = ventas_dia.get('total_ingresos_extra', Decimal('0.00'))
            self.ventas_netas = ventas_dia.get('ventas_netas', self.total_ventas)
            
        super().save(*args, **kwargs)


class Devolucion(models.Model):
    """Registro de una devolución o cambio de productos"""
    ESTADO_CHOICES = [
        ('COMPLETADA', 'Completada'),
        ('ANULADA', 'Anulada'),
    ]
    
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name='devoluciones')
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    
    # Valores económicos
    total_devuelto = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Total de productos devueltos por el cliente")
    total_nuevo = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Total de productos nuevos entregados al cliente")
    diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Si es < 0, se reembolsa dinero. Si es > 0, el cliente paga más.")
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='COMPLETADA')
    observaciones = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = _('Devolución')
        verbose_name_plural = _('Devoluciones')
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"Devolución de Fac. {self.venta.numero_factura} ({self.fecha_hora.strftime('%d/%m/%Y')})"
    
    def save(self, *args, **kwargs):
        self.diferencia = self.total_nuevo - self.total_devuelto
        super().save(*args, **kwargs)
        
    def aplicar_inventario(self):
        """Aplica los cambios de stock basados en los detalles de esta devolución"""
        if self.estado != 'COMPLETADA':
            return False
            
        detalles = self.detalles.all()
        for detalle in detalles:
            if not detalle.producto:
                continue
                
            producto = detalle.producto
            if detalle.tipo == 'DEVUELTO':
                # El cliente devuelve el producto, sumamos al stock
                producto.stock_actual += detalle.cantidad
            elif detalle.tipo == 'NUEVO':
                # El cliente se lleva un nuevo producto, restamos del stock
                producto.stock_actual -= detalle.cantidad
                
            producto.save() # El signal de Inventario se encargará de crear el MovimientoInventario
            
        return True


class DetalleDevolucion(models.Model):
    """Detalle de los productos devueltos o llevados en cambio"""
    TIPO_CHOICES = [
        ('DEVUELTO', 'Producto Devuelto (Entra a Stock)'),
        ('NUEVO', 'Producto Nuevo (Sale de Stock)'),
    ]
    
    devolucion = models.ForeignKey(Devolucion, on_delete=models.CASCADE, related_name='detalles')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, null=True, blank=True)
    tipo_servicio = models.ForeignKey('taller.TipoServicio', on_delete=models.PROTECT, blank=True, null=True)
    nombre_personalizado = models.CharField(max_length=200, blank=True, null=True, help_text="Nombre para items manuales o genéricos")
    
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        verbose_name = _('Detalle de Devolución')
        verbose_name_plural = _('Detalles de Devolución')
    
    def __str__(self):
        if self.producto:
            item_name = self.producto.nombre
        elif self.tipo_servicio:
            item_name = self.tipo_servicio.nombre
        elif self.nombre_personalizado:
            item_name = self.nombre_personalizado
        else:
            item_name = "Item manual"
            
        return f"{self.get_tipo_display()}: {item_name} x {self.cantidad}"
    
    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

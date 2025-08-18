from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Count, Q
from decimal import Decimal
import datetime


class TipoMovimiento(models.Model):
    """Tipos de movimientos de caja"""
    TIPO_CHOICES = [
        ('INGRESO', 'Ingreso'),
        ('EGRESO', 'Egreso'),
    ]
    
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Tipo de Movimiento'
        verbose_name_plural = 'Tipos de Movimientos'
        ordering = ['tipo', 'nombre']
    
    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class MovimientoCaja(models.Model):
    """Registro de todos los movimientos de caja diarios"""
    TIPO_CHOICES = [
        ('VENTA_PRODUCTO', 'Venta de Producto'),
        ('VENTA_SERVICIO', 'Venta de Servicio'),
        ('GASTO_OPERATIVO', 'Gasto Operativo'),
        ('GASTO_ADMINISTRATIVO', 'Gasto Administrativo'),
        ('COMPRA_INVENTARIO', 'Compra de Inventario'),
        ('PAGO_SERVICIOS', 'Pago de Servicios'),
        ('OTROS_INGRESOS', 'Otros Ingresos'),
        ('OTROS_EGRESOS', 'Otros Egresos'),
    ]
    
    METODO_PAGO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('CHEQUE', 'Cheque'),
        ('CREDITO', 'Crédito'),
    ]
    
    fecha = models.DateField(default=timezone.now)
    hora = models.TimeField(auto_now_add=True)
    tipo_movimiento = models.ForeignKey(TipoMovimiento, on_delete=models.PROTECT)
    concepto = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    
    # Montos
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    es_ingreso = models.BooleanField()  # True = Ingreso, False = Egreso
    
    # Método de pago
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default='EFECTIVO')
    
    # Referencias
    venta = models.ForeignKey('ventas.Venta', on_delete=models.CASCADE, blank=True, null=True)
    orden_trabajo = models.ForeignKey('taller.OrdenTrabajo', on_delete=models.CASCADE, blank=True, null=True)
    
    # Documento soporte
    numero_documento = models.CharField(max_length=50, blank=True, null=True)
    archivo_soporte = models.FileField(upload_to='soportes_caja/', blank=True, null=True)
    
    # Auditoria
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Movimiento de Caja'
        verbose_name_plural = 'Movimientos de Caja'
        ordering = ['-fecha', '-hora']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['es_ingreso']),
            models.Index(fields=['tipo_movimiento']),
        ]
    
    def __str__(self):
        tipo = "Ingreso" if self.es_ingreso else "Egreso"
        return f"{self.fecha} - {tipo}: ${self.monto} ({self.concepto})"


class GastoDiario(models.Model):
    """Gastos específicos del día"""
    CATEGORIA_CHOICES = [
        ('OPERATIVO', 'Gasto Operativo'),
        ('ADMINISTRATIVO', 'Gasto Administrativo'), 
        ('MANTENIMIENTO', 'Mantenimiento'),
        ('SERVICIOS_PUBLICOS', 'Servicios Públicos'),
        ('NOMINA', 'Nómina'),
        ('IMPUESTOS', 'Impuestos'),
        ('MARKETING', 'Marketing'),
        ('OTROS', 'Otros'),
    ]
    
    fecha = models.DateField(default=timezone.now)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    concepto = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Documento soporte
    proveedor = models.CharField(max_length=100, blank=True, null=True)
    numero_factura = models.CharField(max_length=50, blank=True, null=True)
    archivo_factura = models.FileField(upload_to='facturas_gastos/', blank=True, null=True)
    
    # Auditoria
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    aprobado = models.BooleanField(default=False)
    fecha_aprobacion = models.DateTimeField(blank=True, null=True)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='gastos_aprobados', blank=True, null=True)
    
    class Meta:
        verbose_name = 'Gasto Diario'
        verbose_name_plural = 'Gastos Diarios'
        ordering = ['-fecha', '-fecha_creacion']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['categoria']),
            models.Index(fields=['aprobado']),
        ]
    
    def __str__(self):
        return f"{self.fecha} - {self.concepto}: ${self.monto}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Crear movimiento de caja automáticamente
        MovimientoCaja.objects.get_or_create(
            fecha=self.fecha,
            concepto=f"Gasto: {self.concepto}",
            monto=self.monto,
            defaults={
                'tipo_movimiento': TipoMovimiento.objects.get_or_create(
                    codigo='GASTO',
                    defaults={'nombre': 'Gasto Operativo', 'tipo': 'EGRESO'}
                )[0],
                'descripcion': self.descripcion,
                'es_ingreso': False,
                'usuario': self.usuario,
                'numero_documento': self.numero_factura,
            }
        )


class CierreDiario(models.Model):
    """Cierre de caja diario mejorado"""
    ESTADO_CHOICES = [
        ('ABIERTO', 'Abierto'),
        ('CERRADO', 'Cerrado'),
        ('REVISADO', 'Revisado'),
    ]
    
    fecha = models.DateField(unique=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='ABIERTO')
    
    # Saldos
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Ventas del día
    total_ventas_productos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ventas_servicios = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_iva_cobrado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cantidad_ventas = models.IntegerField(default=0)
    
    # Gastos del día
    total_gastos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cantidad_gastos = models.IntegerField(default=0)
    
    # Métodos de pago
    efectivo_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tarjeta_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transferencia_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credito_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Conteo físico
    efectivo_contado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    diferencia_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Totales finales
    total_ingresos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_egresos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_final = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Observaciones
    observaciones = models.TextField(blank=True, null=True)
    observaciones_diferencias = models.TextField(blank=True, null=True)
    
    # Auditoria
    usuario_cierre = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    usuario_revision = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cierres_revisados', blank=True, null=True)
    fecha_revision = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Cierre Diario'
        verbose_name_plural = 'Cierres Diarios'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['estado']),
        ]
    
    def __str__(self):
        return f"Cierre {self.fecha} - {self.estado}"
    
    def calcular_totales(self):
        """Calcula automáticamente todos los totales del día"""
        from ventas.models import Venta, DetalleVenta
        
        # Ventas del día
        ventas_dia = Venta.objects.filter(
            fecha_hora__date=self.fecha,
            estado='COMPLETADA'
        )
        
        # Total ventas
        self.cantidad_ventas = ventas_dia.count()
        totales_ventas = ventas_dia.aggregate(
            total_productos=Sum('subtotal'),
            total_servicios=Sum('subtotal', filter=Q(detalleventa__es_servicio=True)),
            total_iva=Sum('iva'),
            efectivo=Sum('total', filter=Q(tipo_pago='EFECTIVO')),
            tarjeta=Sum('total', filter=Q(tipo_pago='TARJETA')),
            transferencia=Sum('total', filter=Q(tipo_pago='TRANSFERENCIA')),
            credito=Sum('total', filter=Q(tipo_pago='CREDITO')),
        )
        
        # Separar productos y servicios
        detalles_productos = DetalleVenta.objects.filter(
            venta__fecha_hora__date=self.fecha,
            venta__estado='COMPLETADA',
            es_servicio=False
        ).aggregate(total=Sum('subtotal'))
        
        detalles_servicios = DetalleVenta.objects.filter(
            venta__fecha_hora__date=self.fecha,
            venta__estado='COMPLETADA',
            es_servicio=True
        ).aggregate(total=Sum('subtotal'))
        
        self.total_ventas_productos = detalles_productos['total'] or Decimal('0.00')
        self.total_ventas_servicios = detalles_servicios['total'] or Decimal('0.00')
        self.total_iva_cobrado = totales_ventas['total_iva'] or Decimal('0.00')
        
        # Métodos de pago
        self.efectivo_ventas = totales_ventas['efectivo'] or Decimal('0.00')
        self.tarjeta_ventas = totales_ventas['tarjeta'] or Decimal('0.00')
        self.transferencia_ventas = totales_ventas['transferencia'] or Decimal('0.00')
        self.credito_ventas = totales_ventas['credito'] or Decimal('0.00')
        
        # Gastos del día
        gastos_dia = GastoDiario.objects.filter(fecha=self.fecha, aprobado=True)
        self.total_gastos = gastos_dia.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        self.cantidad_gastos = gastos_dia.count()
        
        # Totales finales
        self.total_ingresos = self.total_ventas_productos + self.total_ventas_servicios + self.total_iva_cobrado
        self.total_egresos = self.total_gastos
        self.saldo_final = self.saldo_inicial + self.total_ingresos - self.total_egresos
        
        # Diferencia en efectivo
        if self.efectivo_contado is not None:
            efectivo_esperado = self.saldo_inicial + self.efectivo_ventas - self.total_gastos
            self.diferencia_efectivo = self.efectivo_contado - efectivo_esperado
    
    def cerrar_caja(self, usuario, efectivo_contado=None, observaciones=None):
        """Cierra la caja del día"""
        if self.estado != 'ABIERTO':
            raise ValueError("Solo se pueden cerrar cajas abiertas")
        
        self.efectivo_contado = efectivo_contado
        self.observaciones = observaciones
        self.calcular_totales()
        
        self.estado = 'CERRADO'
        self.usuario_cierre = usuario
        self.fecha_cierre = timezone.now()
        self.save()
        
        # Crear saldo inicial para el día siguiente
        fecha_siguiente = self.fecha + datetime.timedelta(days=1)
        CierreDiario.objects.get_or_create(
            fecha=fecha_siguiente,
            defaults={
                'saldo_inicial': self.saldo_final,
                'usuario_cierre': usuario,
            }
        )
    
    @classmethod
    def get_o_crear_hoy(cls, usuario=None):
        """Obtiene o crea el cierre de hoy"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        hoy = timezone.now().date()
        cierre, created = cls.objects.get_or_create(
            fecha=hoy,
            defaults={
                'usuario_cierre': usuario or User.objects.first(),
            }
        )
        
        if created or cierre.estado == 'ABIERTO':
            # Obtener saldo inicial del día anterior
            try:
                cierre_anterior = cls.objects.filter(
                    fecha__lt=hoy,
                    estado='CERRADO'
                ).latest('fecha')
                cierre.saldo_inicial = cierre_anterior.saldo_final
            except cls.DoesNotExist:
                cierre.saldo_inicial = Decimal('0.00')
            
            cierre.calcular_totales()
            cierre.save()
        
        return cierre


class ResumenMensual(models.Model):
    """Resumen mensual de ventas y gastos"""
    año = models.IntegerField()
    mes = models.IntegerField()
    
    # Totales del mes
    total_ventas = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ventas_productos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ventas_servicios = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_gastos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_iva = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Cantidades
    cantidad_ventas = models.IntegerField(default=0)
    cantidad_gastos = models.IntegerField(default=0)
    dias_operacion = models.IntegerField(default=0)
    
    # Promedios
    promedio_venta_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    promedio_gasto_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Utilidad
    utilidad_bruta = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    margen_utilidad = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Porcentaje
    
    fecha_generacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Resumen Mensual'
        verbose_name_plural = 'Resúmenes Mensuales'
        unique_together = ['año', 'mes']
        ordering = ['-año', '-mes']
    
    def __str__(self):
        meses = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        return f"{meses[self.mes]} {self.año}"
    
    def calcular_resumen(self):
        """Calcula el resumen basado en los cierres diarios del mes"""
        from datetime import date
        import calendar
        
        primer_dia = date(self.año, self.mes, 1)
        ultimo_dia = date(self.año, self.mes, calendar.monthrange(self.año, self.mes)[1])
        
        cierres = CierreDiario.objects.filter(
            fecha__range=[primer_dia, ultimo_dia],
            estado='CERRADO'
        )
        
        # Sumar totales
        totales = cierres.aggregate(
            ventas=Sum('total_ingresos'),
            productos=Sum('total_ventas_productos'),
            servicios=Sum('total_ventas_servicios'),
            gastos=Sum('total_gastos'),
            iva=Sum('total_iva_cobrado'),
            cant_ventas=Sum('cantidad_ventas'),
            cant_gastos=Sum('cantidad_gastos'),
        )
        
        self.total_ventas = totales['ventas'] or Decimal('0.00')
        self.total_ventas_productos = totales['productos'] or Decimal('0.00')
        self.total_ventas_servicios = totales['servicios'] or Decimal('0.00')
        self.total_gastos = totales['gastos'] or Decimal('0.00')
        self.total_iva = totales['iva'] or Decimal('0.00')
        self.cantidad_ventas = totales['cant_ventas'] or 0
        self.cantidad_gastos = totales['cant_gastos'] or 0
        self.dias_operacion = cierres.count()
        
        # Promedios
        if self.dias_operacion > 0:
            self.promedio_venta_dia = self.total_ventas / self.dias_operacion
            self.promedio_gasto_dia = self.total_gastos / self.dias_operacion
        
        # Utilidad
        self.utilidad_bruta = self.total_ventas - self.total_gastos
        if self.total_ventas > 0:
            self.margen_utilidad = (self.utilidad_bruta / self.total_ventas) * 100
        
        self.save()


# Señales para crear movimientos automáticamente
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender='ventas.Venta')
def crear_movimiento_venta(sender, instance, created, **kwargs):
    """Crear movimiento de caja automáticamente cuando se crea una venta"""
    if created and instance.estado == 'COMPLETADA':
        # Crear movimiento por venta de productos
        if instance.subtotal > 0:
            MovimientoCaja.objects.create(
                fecha=instance.fecha_hora.date(),
                tipo_movimiento=TipoMovimiento.objects.get_or_create(
                    codigo='VENTA',
                    defaults={'nombre': 'Venta', 'tipo': 'INGRESO'}
                )[0],
                concepto=f"Venta #{instance.numero_factura}",
                descripcion=f"Cliente: {instance.cliente}",
                monto=instance.total,
                es_ingreso=True,
                metodo_pago=instance.tipo_pago,
                venta=instance,
                usuario=instance.usuario,
            )
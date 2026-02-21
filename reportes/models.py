from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Count, Q
from decimal import Decimal
import datetime


class TipoMovimiento(models.Model):
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
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    es_ingreso = models.BooleanField()
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default='EFECTIVO')
    venta = models.ForeignKey('ventas.Venta', on_delete=models.CASCADE, blank=True, null=True)
    orden_trabajo = models.ForeignKey('taller.OrdenTrabajo', on_delete=models.CASCADE, blank=True, null=True)
    numero_documento = models.CharField(max_length=50, blank=True, null=True)
    archivo_soporte = models.FileField(upload_to='soportes_caja/', blank=True, null=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Movimiento de Caja'
        verbose_name_plural = 'Movimientos de Caja'
        ordering = ['-fecha', '-hora']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['es_ingreso']),
        ]

    def __str__(self):
        tipo = "Ingreso" if self.es_ingreso else "Egreso"
        return f"{self.fecha} - {tipo}: ${self.monto} ({self.concepto})"


class GastoDiario(models.Model):
    """Gastos del negocio — módulo independiente, NO ligado a caja"""
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
    proveedor = models.CharField(max_length=100, blank=True, null=True)
    numero_factura = models.CharField(max_length=50, blank=True, null=True)
    archivo_factura = models.FileField(upload_to='facturas_gastos/', blank=True, null=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    aprobado = models.BooleanField(default=False)
    fecha_aprobacion = models.DateTimeField(blank=True, null=True)
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='gastos_aprobados', blank=True, null=True
    )

    class Meta:
        verbose_name = 'Gasto'
        verbose_name_plural = 'Gastos'
        ordering = ['-fecha', '-fecha_creacion']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['categoria']),
            models.Index(fields=['aprobado']),
        ]

    def __str__(self):
        return f"{self.fecha} - {self.concepto}: ${self.monto}"

    # ★ Ya NO crea MovimientoCaja automáticamente — los gastos son módulo independiente


class DesgloseBilletes(models.Model):
    """
    Conteo físico de billetes y monedas al cerrar caja.
    Cada registro representa una denominación y cuántas hay.
    """
    TIPO_CHOICES = [
        ('BILLETE', 'Billete'),
        ('MONEDA', 'Moneda'),
    ]

    # Denominaciones Ecuador (USD)
    DENOMINACION_CHOICES = [
        # Billetes
        ('100.00', '$100'),
        ('50.00', '$50'),
        ('20.00', '$20'),
        ('10.00', '$10'),
        ('5.00', '$5'),
        ('1.00', '$1'),
        # Monedas
        ('0.50', '50 centavos'),
        ('0.25', '25 centavos'),
        ('0.10', '10 centavos'),
        ('0.05', '5 centavos'),
        ('0.01', '1 centavo'),
    ]

    cierre = models.ForeignKey(
        'CierreDiario',
        on_delete=models.CASCADE,
        related_name='desglose_billetes'
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    denominacion = models.DecimalField(max_digits=8, decimal_places=2)
    cantidad = models.PositiveIntegerField(default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Desglose de Billetes'
        verbose_name_plural = 'Desglose de Billetes'
        ordering = ['-denominacion']

    def __str__(self):
        return f"${self.denominacion} x {self.cantidad} = ${self.subtotal}"

    def save(self, *args, **kwargs):
        self.subtotal = self.denominacion * self.cantidad
        super().save(*args, **kwargs)


class CierreDiario(models.Model):
    ESTADO_CHOICES = [
        ('ABIERTO', 'Abierto'),
        ('CERRADO', 'Cerrado'),
        ('REVISADO', 'Revisado'),
    ]

    fecha = models.DateField(unique=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='ABIERTO')

    # Saldos
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Ventas del día (POS + online + órdenes completadas)
    total_ventas_productos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ventas_servicios = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ventas_online = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ordenes_taller = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_iva_cobrado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cantidad_ventas = models.IntegerField(default=0)

    # Métodos de pago
    efectivo_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tarjeta_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transferencia_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credito_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Conteo físico de caja (billetes + monedas)
    efectivo_contado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    diferencia_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Gastos (referencial, no ligado directamente)
    total_gastos_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Totales finales
    total_ingresos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_egresos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_final = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    observaciones = models.TextField(blank=True, null=True)
    observaciones_diferencias = models.TextField(blank=True, null=True)

    usuario_cierre = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='cierres_realizados'
    )
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    usuario_revision = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='cierres_revisados', blank=True, null=True
    )
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
        """
        Calcula todos los totales del día incluyendo:
        - Ventas POS (ventas_venta estado=COMPLETADA)
        - Pedidos online (clientes_pedidoonline estado=ENTREGADO)
        - Órdenes de taller (taller_ordentrabajo estado=COMPLETADO o ENTREGADO)
        """
        from ventas.models import Venta, DetalleVenta
        from clientes.models import PedidoOnline
        from taller.models import OrdenTrabajo

        # ── Ventas POS ────────────────────────────────────────────
        ventas_pos = Venta.objects.filter(
            fecha_hora__date=self.fecha,
            estado='COMPLETADA'
        )
        self.cantidad_ventas = ventas_pos.count()

        detalles_productos = DetalleVenta.objects.filter(
            venta__fecha_hora__date=self.fecha,
            venta__estado='COMPLETADA',
            es_servicio=False
        ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')

        detalles_servicios = DetalleVenta.objects.filter(
            venta__fecha_hora__date=self.fecha,
            venta__estado='COMPLETADA',
            es_servicio=True
        ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')

        self.total_ventas_productos = detalles_productos
        self.total_ventas_servicios = detalles_servicios
        self.total_iva_cobrado = ventas_pos.aggregate(
            total=Sum('iva'))['total'] or Decimal('0.00')

        # Métodos de pago POS
        self.efectivo_ventas = ventas_pos.filter(tipo_pago='EFECTIVO').aggregate(
            total=Sum('total'))['total'] or Decimal('0.00')
        self.tarjeta_ventas = ventas_pos.filter(tipo_pago='TARJETA').aggregate(
            total=Sum('total'))['total'] or Decimal('0.00')
        self.transferencia_ventas = ventas_pos.filter(tipo_pago='TRANSFERENCIA').aggregate(
            total=Sum('total'))['total'] or Decimal('0.00')
        self.credito_ventas = ventas_pos.filter(tipo_pago='CREDITO').aggregate(
            total=Sum('total'))['total'] or Decimal('0.00')

        # ── Pedidos Online entregados ese día ─────────────────────
        pedidos_online = PedidoOnline.objects.filter(
            fecha_entrega__date=self.fecha,
            estado='ENTREGADO'
        )
        self.total_ventas_online = pedidos_online.aggregate(
            total=Sum('total'))['total'] or Decimal('0.00')

        # ── Órdenes de taller completadas/entregadas ese día ──────
        ordenes = OrdenTrabajo.objects.filter(
            estado__in=['COMPLETADO', 'ENTREGADO'],
            fecha_completado__date=self.fecha
        )
        self.total_ordenes_taller = ordenes.aggregate(
            total=Sum('precio_total'))['total'] or Decimal('0.00')

        # ── Gastos aprobados del día (solo referencial) ───────────
        self.total_gastos_dia = GastoDiario.objects.filter(
            fecha=self.fecha,
            aprobado=True
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

        # ── Totales finales ───────────────────────────────────────
        self.total_ingresos = (
            self.total_ventas_productos
            + self.total_ventas_servicios
            + self.total_iva_cobrado
            + self.total_ventas_online
            + self.total_ordenes_taller
        )
        self.total_egresos = self.total_gastos_dia
        self.saldo_final = self.saldo_inicial + self.total_ingresos - self.total_egresos

        # ── Diferencia efectivo (si ya hay conteo físico) ─────────
        if self.efectivo_contado is not None:
            efectivo_esperado = self.saldo_inicial + self.efectivo_ventas - self.total_gastos_dia
            self.diferencia_efectivo = self.efectivo_contado - efectivo_esperado

    def calcular_efectivo_desde_desglose(self):
        """Suma los billetes/monedas del desglose y actualiza efectivo_contado"""
        total = self.desglose_billetes.aggregate(
            total=Sum('subtotal'))['total'] or Decimal('0.00')
        self.efectivo_contado = total
        if self.efectivo_contado is not None:
            from ventas.models import Venta
            ventas_efectivo = Venta.objects.filter(
                fecha_hora__date=self.fecha,
                estado='COMPLETADA',
                tipo_pago='EFECTIVO'
            ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
            efectivo_esperado = self.saldo_inicial + ventas_efectivo - self.total_gastos_dia
            self.diferencia_efectivo = self.efectivo_contado - efectivo_esperado
        self.save(update_fields=['efectivo_contado', 'diferencia_efectivo'])
        return self.efectivo_contado

    @classmethod
    def get_o_crear_hoy(cls, usuario=None):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        hoy = timezone.now().date()
        cierre, created = cls.objects.get_or_create(
            fecha=hoy,
            defaults={'usuario_cierre': usuario or User.objects.first()}
        )
        if created or cierre.estado == 'ABIERTO':
            try:
                anterior = cls.objects.filter(
                    fecha__lt=hoy, estado='CERRADO'
                ).latest('fecha')
                cierre.saldo_inicial = anterior.saldo_final
            except cls.DoesNotExist:
                cierre.saldo_inicial = Decimal('0.00')
            cierre.calcular_totales()
            cierre.save()
        return cierre


class ResumenMensual(models.Model):
    año = models.IntegerField()
    mes = models.IntegerField()

    total_ventas = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ventas_productos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ventas_servicios = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ventas_online = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ordenes_taller = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_gastos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_iva = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    cantidad_ventas = models.IntegerField(default=0)
    cantidad_gastos = models.IntegerField(default=0)
    dias_operacion = models.IntegerField(default=0)

    promedio_venta_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    promedio_gasto_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    utilidad_bruta = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    margen_utilidad = models.DecimalField(max_digits=5, decimal_places=2, default=0)

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
        from datetime import date
        import calendar
        primer_dia = date(self.año, self.mes, 1)
        ultimo_dia = date(self.año, self.mes, calendar.monthrange(self.año, self.mes)[1])

        cierres = CierreDiario.objects.filter(
            fecha__range=[primer_dia, ultimo_dia],
            estado='CERRADO'
        )
        totales = cierres.aggregate(
            ventas=Sum('total_ingresos'),
            productos=Sum('total_ventas_productos'),
            servicios=Sum('total_ventas_servicios'),
            online=Sum('total_ventas_online'),
            taller=Sum('total_ordenes_taller'),
            gastos=Sum('total_gastos_dia'),
            iva=Sum('total_iva_cobrado'),
            cant_ventas=Sum('cantidad_ventas'),
        )
        self.total_ventas = totales['ventas'] or Decimal('0.00')
        self.total_ventas_productos = totales['productos'] or Decimal('0.00')
        self.total_ventas_servicios = totales['servicios'] or Decimal('0.00')
        self.total_ventas_online = totales['online'] or Decimal('0.00')
        self.total_ordenes_taller = totales['taller'] or Decimal('0.00')
        self.total_gastos = totales['gastos'] or Decimal('0.00')
        self.total_iva = totales['iva'] or Decimal('0.00')
        self.cantidad_ventas = totales['cant_ventas'] or 0
        self.dias_operacion = cierres.count()

        if self.dias_operacion > 0:
            self.promedio_venta_dia = self.total_ventas / self.dias_operacion
            self.promedio_gasto_dia = self.total_gastos / self.dias_operacion

        self.utilidad_bruta = self.total_ventas - self.total_gastos
        if self.total_ventas > 0:
            self.margen_utilidad = (self.utilidad_bruta / self.total_ventas) * 100
        self.save()


# ── Señal para crear movimiento de caja al completar una venta ────────
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender='ventas.Venta')
def crear_movimiento_venta(sender, instance, created, **kwargs):
    if created and instance.estado == 'COMPLETADA':
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
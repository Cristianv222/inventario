"""
Motor contable (partida doble) del ERP de Finanzas.

Fuente de la verdad de los estados financieros: los asientos contables.
Reglas de oro:
  - Todo asiento debe cuadrar (suma Debe == suma Haber).
  - La contabilidad se calcula con lógica determinista, nunca con IA.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

CERO = Decimal('0.00')


class CuentaContable(models.Model):
    """Una cuenta del plan de cuentas (estructura jerárquica por código)."""

    TIPO_ACTIVO = 'ACTIVO'
    TIPO_PASIVO = 'PASIVO'
    TIPO_PATRIMONIO = 'PATRIMONIO'
    TIPO_INGRESO = 'INGRESO'
    TIPO_COSTO = 'COSTO'
    TIPO_GASTO = 'GASTO'
    TIPO_CHOICES = [
        (TIPO_ACTIVO, 'Activo'),
        (TIPO_PASIVO, 'Pasivo'),
        (TIPO_PATRIMONIO, 'Patrimonio'),
        (TIPO_INGRESO, 'Ingreso'),
        (TIPO_COSTO, 'Costo'),
        (TIPO_GASTO, 'Gasto'),
    ]

    NATURALEZA_DEUDORA = 'DEUDORA'
    NATURALEZA_ACREEDORA = 'ACREEDORA'
    NATURALEZA_CHOICES = [
        (NATURALEZA_DEUDORA, 'Deudora'),
        (NATURALEZA_ACREEDORA, 'Acreedora'),
    ]

    codigo = models.CharField(max_length=20, unique=True, db_index=True)
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES)
    naturaleza = models.CharField(max_length=10, choices=NATURALEZA_CHOICES)
    padre = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='hijas',
    )
    nivel = models.PositiveSmallIntegerField(default=1)
    # Solo las cuentas de movimiento (hojas) aceptan líneas de asiento.
    # Las de agrupación (padres) sirven para totalizar en los reportes.
    es_movimiento = models.BooleanField(
        default=True,
        help_text='Si acepta asientos directos (hoja) o es de agrupación.',
    )
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Cuenta contable'
        verbose_name_plural = 'Plan de cuentas'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'

    @staticmethod
    def naturaleza_para_tipo(tipo):
        """Naturaleza contable estándar según el tipo de cuenta."""
        if tipo in (CuentaContable.TIPO_ACTIVO, CuentaContable.TIPO_COSTO,
                    CuentaContable.TIPO_GASTO):
            return CuentaContable.NATURALEZA_DEUDORA
        return CuentaContable.NATURALEZA_ACREEDORA

    def saldo(self, fecha_inicio=None, fecha_fin=None):
        """Saldo propio de la cuenta (solo asientos mayorizados).

        Positivo = saldo en su naturaleza natural. No incluye cuentas hijas;
        la totalización por grupo se arma en la capa de reportes.
        """
        qs = self.lineas.filter(asiento__estado=AsientoContable.ESTADO_MAYORIZADO)
        if fecha_inicio:
            qs = qs.filter(asiento__fecha__gte=fecha_inicio)
        if fecha_fin:
            qs = qs.filter(asiento__fecha__lte=fecha_fin)
        agg = qs.aggregate(d=Sum('debe'), h=Sum('haber'))
        debe = agg['d'] or CERO
        haber = agg['h'] or CERO
        if self.naturaleza == self.NATURALEZA_DEUDORA:
            return debe - haber
        return haber - debe


class PeriodoContable(models.Model):
    """Período mensual. Un período cerrado no admite nuevos asientos."""

    anio = models.PositiveIntegerField()
    mes = models.PositiveSmallIntegerField()
    cerrado = models.BooleanField(default=False)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='periodos_cerrados',
    )

    class Meta:
        unique_together = ('anio', 'mes')
        ordering = ['-anio', '-mes']
        verbose_name = 'Período contable'
        verbose_name_plural = 'Períodos contables'

    def __str__(self):
        return f'{self.anio}-{self.mes:02d}' + (' (cerrado)' if self.cerrado else '')


class AsientoContable(models.Model):
    """Cabecera del asiento contable. Debe cuadrar: Debe == Haber."""

    ORIGEN_MANUAL = 'MANUAL'
    ORIGEN_VENTA = 'VENTA'
    ORIGEN_COMPRA = 'COMPRA'
    ORIGEN_GASTO = 'GASTO'
    ORIGEN_NOMINA = 'NOMINA'
    ORIGEN_APERTURA = 'APERTURA'
    ORIGEN_AJUSTE = 'AJUSTE'
    ORIGEN_CHOICES = [
        (ORIGEN_MANUAL, 'Manual'),
        (ORIGEN_VENTA, 'Venta'),
        (ORIGEN_COMPRA, 'Compra'),
        (ORIGEN_GASTO, 'Gasto'),
        (ORIGEN_NOMINA, 'Nómina'),
        (ORIGEN_APERTURA, 'Apertura'),
        (ORIGEN_AJUSTE, 'Ajuste'),
    ]

    ESTADO_BORRADOR = 'BORRADOR'
    ESTADO_MAYORIZADO = 'MAYORIZADO'
    ESTADO_ANULADO = 'ANULADO'
    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, 'Borrador'),
        (ESTADO_MAYORIZADO, 'Mayorizado'),
        (ESTADO_ANULADO, 'Anulado'),
    ]

    numero = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    fecha = models.DateField(default=timezone.now, db_index=True)
    glosa = models.CharField(max_length=255)
    origen = models.CharField(max_length=12, choices=ORIGEN_CHOICES, default=ORIGEN_MANUAL)
    # Referencia blanda al documento de origen (sin FK dura, para mantener el
    # motor desacoplado y reutilizable en otras empresas).
    referencia_tipo = models.CharField(max_length=30, blank=True, null=True)
    referencia_id = models.PositiveIntegerField(blank=True, null=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
    )
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=ESTADO_MAYORIZADO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'Asiento contable'
        verbose_name_plural = 'Asientos contables'
        indexes = [
            models.Index(fields=['referencia_tipo', 'referencia_id']),
        ]

    def __str__(self):
        return f'{self.numero or "s/n"} · {self.glosa}'

    @property
    def total_debe(self):
        return self.lineas.aggregate(s=Sum('debe'))['s'] or CERO

    @property
    def total_haber(self):
        return self.lineas.aggregate(s=Sum('haber'))['s'] or CERO

    @property
    def cuadrado(self):
        return self.total_debe == self.total_haber

    def save(self, *args, **kwargs):
        if not self.numero:
            prefijo = self.fecha.strftime('%Y%m')
            correlativo = AsientoContable.objects.filter(
                numero__startswith=prefijo
            ).count() + 1
            self.numero = f'{prefijo}-{correlativo:04d}'
        super().save(*args, **kwargs)


class LineaAsiento(models.Model):
    """Detalle de un asiento: un cargo (Debe) o un abono (Haber) a una cuenta."""

    asiento = models.ForeignKey(
        AsientoContable, related_name='lineas', on_delete=models.CASCADE,
    )
    cuenta = models.ForeignKey(
        CuentaContable, on_delete=models.PROTECT, related_name='lineas',
    )
    debe = models.DecimalField(max_digits=14, decimal_places=2, default=CERO)
    haber = models.DecimalField(max_digits=14, decimal_places=2, default=CERO)
    detalle = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Línea de asiento'
        verbose_name_plural = 'Líneas de asiento'

    def __str__(self):
        return f'{self.cuenta.codigo}  D {self.debe}  H {self.haber}'

    def clean(self):
        if self.debe < CERO or self.haber < CERO:
            raise ValidationError('Los montos Debe/Haber no pueden ser negativos.')
        if self.debe > CERO and self.haber > CERO:
            raise ValidationError('Una línea no puede tener Debe y Haber a la vez.')

"""
Servicio del motor contable: crea asientos cuadrados y los genera
automáticamente a partir de las operaciones del negocio (ventas, gastos, ...).

Nada de esto usa IA: es lógica contable determinista.
"""
import logging
from decimal import Decimal

from django.db import transaction

from finanzas.models import AsientoContable, CuentaContable, LineaAsiento

logger = logging.getLogger(__name__)

CERO = Decimal('0.00')

# Códigos de las cuentas clave del plan (deben existir tras sembrar el plan).
# Centralizados aquí para no regar códigos por todo el código.
CUENTAS = {
    'CAJA': '1.1.01.01',
    'BANCOS': '1.1.01.02',
    'CLIENTES': '1.1.02.01',
    'INVENTARIO': '1.1.03.01',
    'IVA_CREDITO': '1.1.04.01',
    'PROVEEDORES': '2.1.01.01',
    'IVA_VENTAS': '2.1.02.01',
    'SUELDOS_PAGAR': '2.1.03.01',
    'IESS_PAGAR': '2.1.03.02',
    'VENTAS': '4.1.01.01',
    'DESCUENTO_VENTAS': '4.1.02.01',
    'COSTO_VENTAS': '5.1.01.01',
    'GASTO_GENERAL': '6.1.03.01',
}


class ErrorContable(Exception):
    """Error de negocio del motor contable (p. ej. asiento descuadrado)."""


def _dec(valor):
    return Decimal(str(valor or 0)).quantize(CERO)


def cuenta(codigo):
    """Devuelve la CuentaContable por código, o lanza ErrorContable."""
    try:
        return CuentaContable.objects.get(codigo=codigo)
    except CuentaContable.DoesNotExist:
        raise ErrorContable(
            f'No existe la cuenta {codigo}. ¿Sembraste el plan de cuentas '
            f'(python manage.py sembrar_plan_cuentas)?'
        )


def _cuenta_clave(clave):
    return cuenta(CUENTAS[clave])


@transaction.atomic
def crear_asiento(fecha, glosa, lineas, origen=AsientoContable.ORIGEN_MANUAL,
                  referencia=None, usuario=None,
                  estado=AsientoContable.ESTADO_MAYORIZADO):
    """Crea un asiento cuadrado.

    `lineas`: lista de dicts {'cuenta': <codigo o CuentaContable>,
                              'debe': x, 'haber': y, 'detalle': '...'}
    `referencia`: tupla ('TIPO', id) del documento de origen (opcional).
    Lanza ErrorContable si no cuadra o si no hay al menos dos líneas.
    """
    total_debe = sum((_dec(l.get('debe')) for l in lineas), CERO)
    total_haber = sum((_dec(l.get('haber')) for l in lineas), CERO)

    if total_debe != total_haber:
        raise ErrorContable(
            f'Asiento descuadrado: Debe {total_debe} != Haber {total_haber} '
            f'({glosa}).'
        )
    if total_debe == CERO:
        raise ErrorContable(f'Asiento sin montos: {glosa}.')
    if len(lineas) < 2:
        raise ErrorContable('Un asiento necesita al menos dos líneas.')

    ref_tipo, ref_id = (referencia or (None, None))
    asiento = AsientoContable.objects.create(
        fecha=fecha, glosa=glosa, origen=origen,
        referencia_tipo=ref_tipo, referencia_id=ref_id,
        usuario=usuario, estado=estado,
    )

    for l in lineas:
        c = l['cuenta']
        if not isinstance(c, CuentaContable):
            c = cuenta(c)
        if not c.es_movimiento:
            raise ErrorContable(
                f'La cuenta {c.codigo} es de agrupación; no admite asientos.'
            )
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=c,
            debe=_dec(l.get('debe')), haber=_dec(l.get('haber')),
            detalle=l.get('detalle', ''),
        )
    return asiento


def _asiento_existente(ref_tipo, ref_id):
    return AsientoContable.objects.filter(
        referencia_tipo=ref_tipo, referencia_id=ref_id,
    ).exclude(estado=AsientoContable.ESTADO_ANULADO).first()


# --------------------------------------------------------------------------- #
# Generadores automáticos desde operaciones del negocio
# --------------------------------------------------------------------------- #

# A qué cuenta de activo entra el cobro según la forma de pago de la venta.
_CUENTA_COBRO_POR_PAGO = {
    'EFECTIVO': 'CAJA',
    'TARJETA': 'BANCOS',
    'TRANSFERENCIA': 'BANCOS',
    'CREDITO': 'CLIENTES',
}


def generar_asiento_venta(venta, usuario=None):
    """Genera (una sola vez) el asiento de una venta.

    Debe:  cobro (caja/bancos/clientes) = total   [+ descuento, si hay]
    Haber: ventas (ingreso neto) + IVA por pagar
    El ingreso se calcula como total + descuento - IVA, de modo que el
    asiento cuadra siempre, sin depender de cómo esté definido 'subtotal'.
    """
    existente = _asiento_existente(AsientoContable.ORIGEN_VENTA, venta.id)
    if existente:
        return existente

    total = _dec(venta.total)
    iva = _dec(venta.iva)
    descuento = _dec(getattr(venta, 'descuento', 0))
    ingreso = total + descuento - iva

    clave_cobro = _CUENTA_COBRO_POR_PAGO.get(
        (venta.tipo_pago or '').upper(), 'CAJA'
    )

    lineas = [
        {'cuenta': _cuenta_clave(clave_cobro), 'debe': total,
         'detalle': f'Cobro venta {venta.numero_factura}'},
        {'cuenta': _cuenta_clave('VENTAS'), 'haber': ingreso,
         'detalle': f'Venta {venta.numero_factura}'},
    ]
    if iva > CERO:
        lineas.append({'cuenta': _cuenta_clave('IVA_VENTAS'), 'haber': iva,
                       'detalle': 'IVA en ventas'})
    if descuento > CERO:
        lineas.append({'cuenta': _cuenta_clave('DESCUENTO_VENTAS'), 'debe': descuento,
                       'detalle': 'Descuento en ventas'})

    return crear_asiento(
        fecha=venta.fecha_hora.date() if hasattr(venta.fecha_hora, 'date') else venta.fecha_hora,
        glosa=f'Venta {venta.numero_factura}',
        lineas=lineas,
        origen=AsientoContable.ORIGEN_VENTA,
        referencia=(AsientoContable.ORIGEN_VENTA, venta.id),
        usuario=usuario or getattr(venta, 'usuario', None),
    )


def generar_asiento_gasto(gasto, usuario=None):
    """Genera (una sola vez) el asiento de un gasto diario.

    Debe:  gasto (según categoría; por ahora cuenta de gasto general)
    Haber: caja
    """
    existente = _asiento_existente(AsientoContable.ORIGEN_GASTO, gasto.id)
    if existente:
        return existente

    monto = _dec(gasto.monto)
    lineas = [
        {'cuenta': _cuenta_clave('GASTO_GENERAL'), 'debe': monto,
         'detalle': gasto.concepto},
        {'cuenta': _cuenta_clave('CAJA'), 'haber': monto,
         'detalle': f'Pago gasto {gasto.concepto}'},
    ]
    return crear_asiento(
        fecha=gasto.fecha,
        glosa=f'Gasto: {gasto.concepto}',
        lineas=lineas,
        origen=AsientoContable.ORIGEN_GASTO,
        referencia=(AsientoContable.ORIGEN_GASTO, gasto.id),
        usuario=usuario or getattr(gasto, 'usuario', None),
    )

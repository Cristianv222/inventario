"""
Servicio del motor contable: crea asientos cuadrados y los genera
automáticamente a partir de las operaciones del negocio (ventas, gastos, ...).

Nada de esto usa IA: es lógica contable determinista.
"""
import logging
from decimal import Decimal

from django.db import transaction

from finanzas.models import (
    AsientoContable, CuentaContable, LineaAsiento, PeriodoContable,
)

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
    'CAPITAL': '3.1.01',
    'UTILIDAD_EJERCICIO': '3.2.01',
    'UTILIDADES_RETENIDAS': '3.2.03',
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

    # No se permiten asientos en un período contable cerrado.
    periodo = PeriodoContable.objects.filter(
        anio=fecha.year, mes=fecha.month, cerrado=True,
    ).first()
    if periodo is not None:
        raise ErrorContable(
            f'El período {fecha.year}-{fecha.month:02d} está cerrado; '
            f'no admite nuevos asientos.'
        )

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


# --------------------------------------------------------------------------- #
# Asiento de apertura (saldos iniciales)
# --------------------------------------------------------------------------- #
def generar_asiento_apertura(fecha, saldos, usuario=None,
                             cuenta_capital='CAPITAL', glosa='Asiento de apertura'):
    """Crea el asiento de apertura a partir de saldos iniciales.

    `saldos`: dict {codigo_cuenta: monto} donde monto es el saldo en la
              naturaleza natural de la cuenta (positivo). Los activos van al
              Debe; pasivos y patrimonio al Haber, según su naturaleza.
    `cuenta_capital`: clave de CUENTAS (o código) que absorbe la diferencia
              para cuadrar (típicamente el capital social). Si los saldos ya
              cuadran, no se agrega ninguna línea de ajuste.

    Idempotente por año: solo un asiento de apertura vigente por ejercicio.
    """
    ref = (AsientoContable.ORIGEN_APERTURA, fecha.year)
    existente = _asiento_existente(*ref)
    if existente:
        return existente

    lineas = []
    total_debe = total_haber = CERO
    for codigo, monto in saldos.items():
        c = cuenta(codigo) if not isinstance(codigo, CuentaContable) else codigo
        m = _dec(monto)
        if m == CERO:
            continue
        if c.naturaleza == CuentaContable.NATURALEZA_DEUDORA:
            lineas.append({'cuenta': c, 'debe': m, 'detalle': 'Saldo inicial'})
            total_debe += m
        else:
            lineas.append({'cuenta': c, 'haber': m, 'detalle': 'Saldo inicial'})
            total_haber += m

    diferencia = total_debe - total_haber
    if diferencia != CERO:
        cap = (CUENTAS.get(cuenta_capital, cuenta_capital))
        c_cap = cuenta(cap)
        if diferencia > CERO:  # faltan haberes -> acreditar capital
            lineas.append({'cuenta': c_cap, 'haber': diferencia,
                           'detalle': 'Capital (cuadre de apertura)'})
        else:  # faltan débitos
            lineas.append({'cuenta': c_cap, 'debe': -diferencia,
                           'detalle': 'Capital (cuadre de apertura)'})

    return crear_asiento(
        fecha=fecha, glosa=glosa, lineas=lineas,
        origen=AsientoContable.ORIGEN_APERTURA, referencia=ref, usuario=usuario,
    )


# --------------------------------------------------------------------------- #
# Cierre de período y cierre anual
# --------------------------------------------------------------------------- #
def cerrar_periodo(anio, mes, usuario=None):
    """Marca un período mensual como cerrado (bloquea nuevos asientos)."""
    from django.utils import timezone
    periodo, _ = PeriodoContable.objects.get_or_create(anio=anio, mes=mes)
    if periodo.cerrado:
        return periodo
    periodo.cerrado = True
    periodo.fecha_cierre = timezone.now()
    periodo.cerrado_por = usuario
    periodo.save()
    return periodo


def reabrir_periodo(anio, mes):
    """Reabre un período cerrado (operación administrativa)."""
    periodo = PeriodoContable.objects.filter(anio=anio, mes=mes).first()
    if periodo and periodo.cerrado:
        periodo.cerrado = False
        periodo.fecha_cierre = None
        periodo.cerrado_por = None
        periodo.save()
    return periodo


def asiento_cierre_anual(anio, usuario=None, cuenta_resultado='UTILIDAD_EJERCICIO'):
    """Genera el asiento de cierre anual de cuentas de resultado.

    Salda las cuentas de Ingreso, Costo y Gasto del año contra la cuenta de
    resultado (Utilidad del ejercicio). Tras mayorizar, esas cuentas quedan en
    cero y la utilidad/pérdida se refleja en patrimonio.

    Idempotente por año.
    """
    import datetime

    existente = AsientoContable.objects.filter(
        referencia_tipo='CIERRE_ANUAL', referencia_id=anio,
    ).exclude(estado=AsientoContable.ESTADO_ANULADO).first()
    if existente:
        return existente

    inicio = datetime.date(anio, 1, 1)
    fin = datetime.date(anio, 12, 31)

    tipos_resultado = (CuentaContable.TIPO_INGRESO, CuentaContable.TIPO_COSTO,
                       CuentaContable.TIPO_GASTO)
    lineas = []
    neto = CERO  # positivo => utilidad
    for c in CuentaContable.objects.filter(es_movimiento=True, tipo__in=tipos_resultado):
        saldo = c.saldo(inicio, fin)  # saldo natural (>=0 normalmente)
        if saldo == CERO:
            continue
        # Para saldar: aplicar el lado contrario a la naturaleza de la cuenta.
        if c.naturaleza == CuentaContable.NATURALEZA_ACREEDORA:  # ingresos
            lineas.append({'cuenta': c, 'debe': saldo, 'detalle': 'Cierre anual'})
            neto += saldo
        else:  # costos y gastos (deudora)
            lineas.append({'cuenta': c, 'haber': saldo, 'detalle': 'Cierre anual'})
            neto -= saldo

    if not lineas:
        raise ErrorContable(f'No hay cuentas de resultado con saldo en {anio}.')

    c_res = cuenta(CUENTAS.get(cuenta_resultado, cuenta_resultado))
    if neto > CERO:  # utilidad -> se acredita a patrimonio
        lineas.append({'cuenta': c_res, 'haber': neto, 'detalle': 'Utilidad del ejercicio'})
    else:  # pérdida -> se debita
        lineas.append({'cuenta': c_res, 'debe': -neto, 'detalle': 'Pérdida del ejercicio'})

    asiento = crear_asiento(
        fecha=fin, glosa=f'Cierre anual {anio}', lineas=lineas,
        origen=AsientoContable.ORIGEN_AJUSTE, usuario=usuario,
    )
    # Marca blanda específica de cierre (para idempotencia por año).
    asiento.referencia_tipo = 'CIERRE_ANUAL'
    asiento.referencia_id = anio
    asiento.save(update_fields=['referencia_tipo', 'referencia_id'])
    return asiento

"""
Reportes y estados financieros — cálculo 100% determinista.

Fuente de la verdad: los asientos MAYORIZADOS. Nada aquí usa IA.
Todas las cifras se derivan de LineaAsiento agregando Debe/Haber.

Convención de saldo:
  - Cuentas de naturaleza DEUDORA (Activo, Costo, Gasto): saldo = Debe - Haber.
  - Cuentas de naturaleza ACREEDORA (Pasivo, Patrimonio, Ingreso): saldo = Haber - Debe.
"""
from decimal import Decimal

from django.db.models import Sum

from finanzas.models import AsientoContable, CuentaContable, LineaAsiento

CERO = Decimal('0.00')
MAYOR = AsientoContable.ESTADO_MAYORIZADO

# Cuentas de efectivo para el flujo de caja (código -> etiqueta).
CUENTAS_EFECTIVO = {
    '1.1.01.01': 'Caja',
    '1.1.01.02': 'Bancos',
}

TIPOS_DEUDORES = (CuentaContable.TIPO_ACTIVO, CuentaContable.TIPO_COSTO,
                  CuentaContable.TIPO_GASTO)


# --------------------------------------------------------------------------- #
# Helpers de agregación
# --------------------------------------------------------------------------- #
def _lineas(fecha_inicio=None, fecha_fin=None):
    qs = LineaAsiento.objects.filter(asiento__estado=MAYOR)
    if fecha_inicio:
        qs = qs.filter(asiento__fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(asiento__fecha__lte=fecha_fin)
    return qs


def _agregado_por_cuenta(fecha_inicio=None, fecha_fin=None):
    """dict: codigo_cuenta -> {'debe': Decimal, 'haber': Decimal} (cuentas de movimiento)."""
    filas = (_lineas(fecha_inicio, fecha_fin)
             .values('cuenta__codigo')
             .annotate(debe=Sum('debe'), haber=Sum('haber')))
    return {
        f['cuenta__codigo']: {'debe': f['debe'] or CERO, 'haber': f['haber'] or CERO}
        for f in filas
    }


def _saldo(cuenta, debe, haber):
    """Saldo con signo natural según la naturaleza de la cuenta."""
    if cuenta.naturaleza == CuentaContable.NATURALEZA_DEUDORA:
        return (debe or CERO) - (haber or CERO)
    return (haber or CERO) - (debe or CERO)


def _cuentas_movimiento():
    return {c.codigo: c for c in CuentaContable.objects.filter(es_movimiento=True)}


# --------------------------------------------------------------------------- #
# 1) Libro Mayor
# --------------------------------------------------------------------------- #
def libro_mayor(fecha_inicio=None, fecha_fin=None, cuenta_codigo=None):
    """Movimientos por cuenta con saldo anterior, corriente y final.

    Devuelve lista de dicts, una entrada por cuenta con movimiento:
      {cuenta, saldo_anterior, movimientos:[...], total_debe, total_haber, saldo_final}
    """
    cuentas = CuentaContable.objects.filter(es_movimiento=True)
    if cuenta_codigo:
        cuentas = cuentas.filter(codigo=cuenta_codigo)

    resultado = []
    for c in cuentas:
        # Saldo anterior: todo lo mayorizado antes de fecha_inicio.
        if fecha_inicio:
            prev = (LineaAsiento.objects
                    .filter(asiento__estado=MAYOR, cuenta=c,
                            asiento__fecha__lt=fecha_inicio)
                    .aggregate(d=Sum('debe'), h=Sum('haber')))
            saldo_ant = _saldo(c, prev['d'], prev['h'])
        else:
            saldo_ant = CERO

        lineas = (LineaAsiento.objects
                  .filter(asiento__estado=MAYOR, cuenta=c)
                  .select_related('asiento')
                  .order_by('asiento__fecha', 'asiento__id', 'id'))
        if fecha_inicio:
            lineas = lineas.filter(asiento__fecha__gte=fecha_inicio)
        if fecha_fin:
            lineas = lineas.filter(asiento__fecha__lte=fecha_fin)

        movimientos = []
        saldo = saldo_ant
        td = th = CERO
        for l in lineas:
            td += l.debe
            th += l.haber
            if c.naturaleza == CuentaContable.NATURALEZA_DEUDORA:
                saldo += l.debe - l.haber
            else:
                saldo += l.haber - l.debe
            movimientos.append({
                'fecha': l.asiento.fecha,
                'numero': l.asiento.numero,
                'glosa': l.asiento.glosa,
                'detalle': l.detalle,
                'debe': l.debe,
                'haber': l.haber,
                'saldo': saldo,
            })

        if not movimientos and saldo_ant == CERO:
            continue
        resultado.append({
            'cuenta': c,
            'saldo_anterior': saldo_ant,
            'movimientos': movimientos,
            'total_debe': td,
            'total_haber': th,
            'saldo_final': saldo,
        })
    return resultado


# --------------------------------------------------------------------------- #
# 2) Balance de Comprobación (sumas y saldos)
# --------------------------------------------------------------------------- #
def balance_comprobacion(fecha_inicio=None, fecha_fin=None):
    """Sumas (Debe/Haber) y saldos (Deudor/Acreedor) por cuenta de movimiento.

    Cuadres garantizados: sum(debe)==sum(haber) y sum(deudor)==sum(acreedor).
    """
    agg = _agregado_por_cuenta(fecha_inicio, fecha_fin)
    cuentas = _cuentas_movimiento()

    filas = []
    tot_debe = tot_haber = tot_deudor = tot_acreedor = CERO
    for codigo, mov in sorted(agg.items()):
        c = cuentas.get(codigo)
        if c is None:
            continue
        debe, haber = mov['debe'], mov['haber']
        neto = debe - haber  # positivo => saldo deudor
        deudor = neto if neto > CERO else CERO
        acreedor = -neto if neto < CERO else CERO
        filas.append({
            'codigo': codigo,
            'nombre': c.nombre,
            'tipo': c.get_tipo_display(),
            'debe': debe,
            'haber': haber,
            'deudor': deudor,
            'acreedor': acreedor,
        })
        tot_debe += debe
        tot_haber += haber
        tot_deudor += deudor
        tot_acreedor += acreedor

    return {
        'filas': filas,
        'total_debe': tot_debe,
        'total_haber': tot_haber,
        'total_deudor': tot_deudor,
        'total_acreedor': tot_acreedor,
        'cuadra_sumas': tot_debe == tot_haber,
        'cuadra_saldos': tot_deudor == tot_acreedor,
    }


# --------------------------------------------------------------------------- #
# 3) Estado de Resultados
# --------------------------------------------------------------------------- #
def _detalle_por_tipo(agg, cuentas, tipo):
    """Lista de cuentas de un tipo con saldo natural != 0."""
    filas = []
    total = CERO
    for codigo, mov in sorted(agg.items()):
        c = cuentas.get(codigo)
        if c is None or c.tipo != tipo:
            continue
        saldo = _saldo(c, mov['debe'], mov['haber'])
        if saldo == CERO:
            continue
        filas.append({'codigo': codigo, 'nombre': c.nombre, 'saldo': saldo})
        total += saldo
    return filas, total


def estado_resultados(fecha_inicio=None, fecha_fin=None):
    """Ingresos - Costos - Gastos = Utilidad del ejercicio."""
    agg = _agregado_por_cuenta(fecha_inicio, fecha_fin)
    cuentas = _cuentas_movimiento()

    ingresos, tot_ing = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_INGRESO)
    costos, tot_cos = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_COSTO)
    gastos, tot_gas = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_GASTO)

    utilidad_bruta = tot_ing - tot_cos
    utilidad_neta = utilidad_bruta - tot_gas
    return {
        'ingresos': ingresos, 'total_ingresos': tot_ing,
        'costos': costos, 'total_costos': tot_cos,
        'gastos': gastos, 'total_gastos': tot_gas,
        'utilidad_bruta': utilidad_bruta,
        'utilidad_neta': utilidad_neta,
    }


# --------------------------------------------------------------------------- #
# 4) Balance General (Estado de Situación Financiera)
# --------------------------------------------------------------------------- #
def balance_general(fecha_fin=None):
    """Activo = Pasivo + Patrimonio + Resultado del ejercicio (acumulado a fecha_fin)."""
    agg = _agregado_por_cuenta(None, fecha_fin)
    cuentas = _cuentas_movimiento()

    activos, tot_act = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_ACTIVO)
    pasivos, tot_pas = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_PASIVO)
    patrimonio, tot_pat = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_PATRIMONIO)

    # Resultado del ejercicio acumulado hasta la fecha (va al patrimonio).
    _, tot_ing = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_INGRESO)
    _, tot_cos = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_COSTO)
    _, tot_gas = _detalle_por_tipo(agg, cuentas, CuentaContable.TIPO_GASTO)
    resultado = tot_ing - tot_cos - tot_gas

    total_pasivo_patrimonio = tot_pas + tot_pat + resultado
    return {
        'activos': activos, 'total_activo': tot_act,
        'pasivos': pasivos, 'total_pasivo': tot_pas,
        'patrimonio': patrimonio, 'total_patrimonio': tot_pat,
        'resultado_ejercicio': resultado,
        'total_patrimonio_con_resultado': tot_pat + resultado,
        'total_pasivo_patrimonio': total_pasivo_patrimonio,
        'cuadra': tot_act == total_pasivo_patrimonio,
        'descuadre': tot_act - total_pasivo_patrimonio,
    }


# --------------------------------------------------------------------------- #
# 5) Flujo de Caja (método directo sobre cuentas de efectivo)
# --------------------------------------------------------------------------- #
def flujo_caja(fecha_inicio=None, fecha_fin=None):
    """Saldo inicial + Entradas - Salidas = Saldo final para Caja y Bancos."""
    codigos = list(CUENTAS_EFECTIVO.keys())

    # Saldo inicial (antes de fecha_inicio).
    if fecha_inicio:
        prev = (LineaAsiento.objects
                .filter(asiento__estado=MAYOR, cuenta__codigo__in=codigos,
                        asiento__fecha__lt=fecha_inicio)
                .aggregate(d=Sum('debe'), h=Sum('haber')))
        saldo_inicial = (prev['d'] or CERO) - (prev['h'] or CERO)
    else:
        saldo_inicial = CERO

    lineas = (_lineas(fecha_inicio, fecha_fin)
              .filter(cuenta__codigo__in=codigos)
              .select_related('asiento', 'cuenta')
              .order_by('asiento__fecha', 'asiento__id', 'id'))

    movimientos = []
    entradas = salidas = CERO
    saldo = saldo_inicial
    for l in lineas:
        entradas += l.debe
        salidas += l.haber
        saldo += l.debe - l.haber
        movimientos.append({
            'fecha': l.asiento.fecha,
            'numero': l.asiento.numero,
            'cuenta': CUENTAS_EFECTIVO.get(l.cuenta.codigo, l.cuenta.nombre),
            'glosa': l.asiento.glosa,
            'entrada': l.debe,
            'salida': l.haber,
            'saldo': saldo,
        })

    return {
        'saldo_inicial': saldo_inicial,
        'movimientos': movimientos,
        'total_entradas': entradas,
        'total_salidas': salidas,
        'saldo_final': saldo_inicial + entradas - salidas,
    }

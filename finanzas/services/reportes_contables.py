"""
Reportes contables derivados de los asientos (100% lógica determinista):

  - libro_mayor(cuenta)        → movimientos y saldo corrido de una cuenta
  - balance_comprobacion()     → sumas y saldos de todas las cuentas de movimiento
  - estado_resultados()        → Ingresos − Costos − Gastos = Utilidad/Pérdida
  - balance_general()          → Activo = Pasivo + Patrimonio (+ resultado)
  - flujo_caja()               → entradas/salidas de efectivo y bancos

Todos consideran solo asientos MAYORIZADOS. No interviene IA.
"""
from decimal import Decimal

from django.db.models import Sum

from finanzas.models import AsientoContable, CuentaContable, LineaAsiento

CERO = Decimal('0.00')

# Prefijos de cuentas de efectivo y equivalentes (para el flujo de caja).
PREFIJOS_EFECTIVO = ('1.1.01',)


def _q(qs, fecha_inicio=None, fecha_fin=None):
    qs = qs.filter(asiento__estado=AsientoContable.ESTADO_MAYORIZADO)
    if fecha_inicio:
        qs = qs.filter(asiento__fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(asiento__fecha__lte=fecha_fin)
    return qs


def _filas_por_cuenta(fecha_inicio=None, fecha_fin=None, tipos=None, solo_con_movimiento=True):
    """Devuelve filas agregadas por cuenta de movimiento con debe/haber/saldo."""
    qs = _q(LineaAsiento.objects.all(), fecha_inicio, fecha_fin)
    if tipos:
        qs = qs.filter(cuenta__tipo__in=tipos)
    qs = (qs.values('cuenta__codigo', 'cuenta__nombre', 'cuenta__tipo',
                    'cuenta__naturaleza')
            .annotate(debe=Sum('debe'), haber=Sum('haber'))
            .order_by('cuenta__codigo'))

    filas = []
    for r in qs:
        debe = r['debe'] or CERO
        haber = r['haber'] or CERO
        if r['cuenta__naturaleza'] == CuentaContable.NATURALEZA_DEUDORA:
            saldo = debe - haber
        else:
            saldo = haber - debe
        if solo_con_movimiento and debe == CERO and haber == CERO:
            continue
        filas.append({
            'codigo': r['cuenta__codigo'],
            'nombre': r['cuenta__nombre'],
            'tipo': r['cuenta__tipo'],
            'naturaleza': r['cuenta__naturaleza'],
            'debe': debe,
            'haber': haber,
            'saldo': saldo,
        })
    return filas


def libro_mayor(codigo_cuenta, fecha_inicio=None, fecha_fin=None):
    """Movimientos de una cuenta con saldo corrido."""
    cuenta = CuentaContable.objects.get(codigo=codigo_cuenta)
    qs = _q(cuenta.lineas.all(), fecha_inicio, fecha_fin).select_related('asiento').order_by(
        'asiento__fecha', 'asiento__id', 'id')
    deudora = cuenta.naturaleza == CuentaContable.NATURALEZA_DEUDORA
    saldo = CERO
    movimientos = []
    for l in qs:
        saldo += (l.debe - l.haber) if deudora else (l.haber - l.debe)
        movimientos.append({
            'fecha': l.asiento.fecha,
            'asiento': l.asiento.numero,
            'glosa': l.asiento.glosa,
            'detalle': l.detalle,
            'debe': l.debe,
            'haber': l.haber,
            'saldo': saldo,
        })
    return {'cuenta': cuenta, 'movimientos': movimientos, 'saldo_final': saldo}


def balance_comprobacion(fecha_inicio=None, fecha_fin=None):
    """Sumas y saldos. Total Debe debe igualar Total Haber."""
    filas = _filas_por_cuenta(fecha_inicio, fecha_fin)
    total_debe = sum((f['debe'] for f in filas), CERO)
    total_haber = sum((f['haber'] for f in filas), CERO)
    for f in filas:
        f['saldo_deudor'] = f['saldo'] if f['saldo'] > 0 and f['naturaleza'] == 'DEUDORA' else (
            -f['saldo'] if f['saldo'] < 0 and f['naturaleza'] == 'ACREEDORA' else CERO)
        f['saldo_acreedor'] = f['saldo'] if f['saldo'] > 0 and f['naturaleza'] == 'ACREEDORA' else (
            -f['saldo'] if f['saldo'] < 0 and f['naturaleza'] == 'DEUDORA' else CERO)
    return {
        'filas': filas,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'cuadrado': total_debe == total_haber,
    }


def estado_resultados(fecha_inicio=None, fecha_fin=None):
    """Ingresos − Costos − Gastos = Resultado del período."""
    ingresos = _filas_por_cuenta(fecha_inicio, fecha_fin, tipos=[CuentaContable.TIPO_INGRESO])
    costos = _filas_por_cuenta(fecha_inicio, fecha_fin, tipos=[CuentaContable.TIPO_COSTO])
    gastos = _filas_por_cuenta(fecha_inicio, fecha_fin, tipos=[CuentaContable.TIPO_GASTO])

    total_ingresos = sum((f['saldo'] for f in ingresos), CERO)
    total_costos = sum((f['saldo'] for f in costos), CERO)
    total_gastos = sum((f['saldo'] for f in gastos), CERO)
    utilidad_bruta = total_ingresos - total_costos
    resultado = utilidad_bruta - total_gastos

    return {
        'ingresos': ingresos, 'total_ingresos': total_ingresos,
        'costos': costos, 'total_costos': total_costos,
        'utilidad_bruta': utilidad_bruta,
        'gastos': gastos, 'total_gastos': total_gastos,
        'resultado': resultado,
        'es_perdida': resultado < 0,
    }


def balance_general(fecha_corte=None):
    """Activo = Pasivo + Patrimonio + Resultado del ejercicio.

    El resultado del ejercicio (ingresos − costos − gastos hasta la fecha de
    corte) se suma al patrimonio para que la ecuación cuadre aun sin asiento
    de cierre.
    """
    activos = _filas_por_cuenta(None, fecha_corte, tipos=[CuentaContable.TIPO_ACTIVO])
    pasivos = _filas_por_cuenta(None, fecha_corte, tipos=[CuentaContable.TIPO_PASIVO])
    patrimonio = _filas_por_cuenta(None, fecha_corte, tipos=[CuentaContable.TIPO_PATRIMONIO])

    er = estado_resultados(None, fecha_corte)
    resultado = er['resultado']

    total_activos = sum((f['saldo'] for f in activos), CERO)
    total_pasivos = sum((f['saldo'] for f in pasivos), CERO)
    total_patrimonio_base = sum((f['saldo'] for f in patrimonio), CERO)
    total_patrimonio = total_patrimonio_base + resultado

    return {
        'activos': activos, 'total_activos': total_activos,
        'pasivos': pasivos, 'total_pasivos': total_pasivos,
        'patrimonio': patrimonio, 'total_patrimonio_base': total_patrimonio_base,
        'resultado_ejercicio': resultado,
        'total_patrimonio': total_patrimonio,
        'total_pasivo_patrimonio': total_pasivos + total_patrimonio,
        'patrimonio_negativo': total_patrimonio < 0,
        'cuadrado': total_activos == (total_pasivos + total_patrimonio),
    }


def flujo_caja(fecha_inicio=None, fecha_fin=None):
    """Flujo de efectivo (método directo simplificado) sobre caja y bancos."""
    cuentas_efectivo = CuentaContable.objects.filter(es_movimiento=True)
    cuentas_efectivo = [c for c in cuentas_efectivo
                        if any(c.codigo.startswith(p) for p in PREFIJOS_EFECTIVO)]
    codigos = [c.codigo for c in cuentas_efectivo]

    # Saldo inicial: todo lo anterior a fecha_inicio.
    saldo_inicial = CERO
    if fecha_inicio:
        prev = _q(LineaAsiento.objects.filter(cuenta__codigo__in=codigos),
                  None, None).filter(asiento__fecha__lt=fecha_inicio).aggregate(
            d=Sum('debe'), h=Sum('haber'))
        saldo_inicial = (prev['d'] or CERO) - (prev['h'] or CERO)

    periodo = _q(LineaAsiento.objects.filter(cuenta__codigo__in=codigos),
                 fecha_inicio, fecha_fin).aggregate(d=Sum('debe'), h=Sum('haber'))
    entradas = periodo['d'] or CERO
    salidas = periodo['h'] or CERO
    flujo_neto = entradas - salidas

    return {
        'saldo_inicial': saldo_inicial,
        'entradas': entradas,
        'salidas': salidas,
        'flujo_neto': flujo_neto,
        'saldo_final': saldo_inicial + flujo_neto,
        'flujo_negativo': flujo_neto < 0,
    }

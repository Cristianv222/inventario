"""
Vistas del ERP de Finanzas.

Por ahora renderizan HTML mínimo y autónomo (sin depender de base.html) para
mostrar los estados financieros en pantalla. La versión con el diseño del
sistema y la descarga en PDF/Excel se construye en la siguiente fase.
"""
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import reverse

from .models import AsientoContable, CuentaContable
from .services import reportes_contables as R


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _rango(request):
    return _fecha(request.GET.get('desde')), _fecha(request.GET.get('hasta'))


def _money(x):
    neg = x < 0
    s = f'{abs(x):,.2f}'
    return f'(${s})' if neg else f'${s}'


def _page(titulo, cuerpo, con_rango=True, request=None):
    desde = (request.GET.get('desde', '') if request else '')
    hasta = (request.GET.get('hasta', '') if request else '')
    nav = ' · '.join(
        f'<a href="{reverse("finanzas:" + n)}">{t}</a>' for n, t in [
            ('estado_motor', 'Inicio'),
            ('balance_comprobacion', 'Balance comprobación'),
            ('estado_resultados', 'Estado de resultados'),
            ('balance_general', 'Balance general'),
            ('flujo_caja', 'Flujo de caja'),
        ]
    )
    filtro = ''
    if con_rango:
        filtro = f"""
        <form method="get" style="margin:1rem 0; display:flex; gap:.5rem; align-items:end; flex-wrap:wrap;">
          <label>Desde <input type="date" name="desde" value="{desde}"></label>
          <label>Hasta <input type="date" name="hasta" value="{hasta}"></label>
          <button type="submit">Aplicar</button>
        </form>"""
    return HttpResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{titulo} · Finanzas</title>
      <style>
        body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1f2430;}}
        h1{{font-size:1.4rem;}} nav{{font-size:.85rem;margin-bottom:1rem;}}
        nav a{{color:#3f51b5;text-decoration:none;margin-right:.3rem;}}
        table{{width:100%;border-collapse:collapse;margin:.5rem 0;}}
        th,td{{padding:.4rem .6rem;border-bottom:1px solid #e5e7eb;text-align:left;}}
        td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;}}
        tr.tot td{{font-weight:700;border-top:2px solid #333;}}
        .ok{{color:#0f5132;}} .bad{{color:#b02a37;}}
        .grp{{background:#f5f6fa;font-weight:600;}}
      </style></head><body>
      <nav>{nav}</nav><h1>{titulo}</h1>{filtro}{cuerpo}</body></html>""")


@login_required
def estado_motor(request):
    cuentas = CuentaContable.objects.count()
    asientos = AsientoContable.objects.count()
    cuerpo = f"""
      <p>Motor contable instalado.</p>
      <ul>
        <li>Cuentas en el plan: <strong>{cuentas}</strong></li>
        <li>Asientos registrados: <strong>{asientos}</strong></li>
      </ul>
      <p>Usa el menú para ver los estados financieros. La descarga PDF/Excel
      y el diseño integrado al sistema vienen en la siguiente fase.</p>"""
    return _page('Finanzas — Motor contable', cuerpo, con_rango=False, request=request)


@login_required
def balance_comprobacion(request):
    desde, hasta = _rango(request)
    bc = R.balance_comprobacion(desde, hasta)
    filas = ''.join(
        f"<tr><td>{f['codigo']}</td><td>{f['nombre']}</td>"
        f"<td class='n'>{_money(f['debe'])}</td><td class='n'>{_money(f['haber'])}</td>"
        f"<td class='n'>{_money(f['saldo'])}</td></tr>"
        for f in bc['filas'])
    estado = ('<span class="ok">cuadrado</span>' if bc['cuadrado']
              else '<span class="bad">DESCUADRADO</span>')
    cuerpo = f"""
      <table><thead><tr><th>Código</th><th>Cuenta</th>
        <th class="n">Debe</th><th class="n">Haber</th><th class="n">Saldo</th></tr></thead>
      <tbody>{filas}
        <tr class="tot"><td colspan="2">TOTALES ({estado})</td>
          <td class="n">{_money(bc['total_debe'])}</td>
          <td class="n">{_money(bc['total_haber'])}</td><td></td></tr>
      </tbody></table>"""
    return _page('Balance de Comprobación', cuerpo, request=request)


@login_required
def estado_resultados(request):
    desde, hasta = _rango(request)
    er = R.estado_resultados(desde, hasta)

    def seccion(titulo, filas, total):
        rows = ''.join(
            f"<tr><td>{f['codigo']}</td><td>{f['nombre']}</td>"
            f"<td class='n'>{_money(f['saldo'])}</td></tr>" for f in filas)
        return (f"<tr class='grp'><td colspan='2'>{titulo}</td>"
                f"<td class='n'>{_money(total)}</td></tr>{rows}")

    resultado_cls = 'bad' if er['es_perdida'] else 'ok'
    etiqueta = 'PÉRDIDA NETA' if er['es_perdida'] else 'UTILIDAD NETA'
    cuerpo = f"""
      <table><tbody>
        {seccion('INGRESOS', er['ingresos'], er['total_ingresos'])}
        {seccion('COSTOS', er['costos'], er['total_costos'])}
        <tr class="tot"><td colspan="2">UTILIDAD BRUTA</td>
          <td class="n">{_money(er['utilidad_bruta'])}</td></tr>
        {seccion('GASTOS', er['gastos'], er['total_gastos'])}
        <tr class="tot"><td colspan="2" class="{resultado_cls}">{etiqueta}</td>
          <td class="n {resultado_cls}">{_money(er['resultado'])}</td></tr>
      </tbody></table>"""
    return _page('Estado de Resultados', cuerpo, request=request)


@login_required
def balance_general(request):
    _, hasta = _rango(request)
    bg = R.balance_general(hasta)

    def bloque(titulo, filas, total, extra=''):
        rows = ''.join(
            f"<tr><td>{f['codigo']}</td><td>{f['nombre']}</td>"
            f"<td class='n'>{_money(f['saldo'])}</td></tr>" for f in filas)
        return (f"<tr class='grp'><td colspan='2'>{titulo}</td>"
                f"<td class='n'>{_money(total)}</td></tr>{rows}{extra}")

    patr_cls = 'bad' if bg['patrimonio_negativo'] else ''
    extra_patr = (
        f"<tr><td colspan='2'>Resultado del ejercicio</td>"
        f"<td class='n'>{_money(bg['resultado_ejercicio'])}</td></tr>"
        f"<tr class='tot'><td colspan='2' class='{patr_cls}'>TOTAL PATRIMONIO</td>"
        f"<td class='n {patr_cls}'>{_money(bg['total_patrimonio'])}</td></tr>")
    cuadre = ('<span class="ok">cuadra</span>' if bg['cuadrado']
              else '<span class="bad">NO CUADRA</span>')
    cuerpo = f"""
      <table><tbody>
        {bloque('ACTIVOS', bg['activos'], bg['total_activos'])}
        <tr class="tot"><td colspan="2">TOTAL ACTIVOS</td>
          <td class="n">{_money(bg['total_activos'])}</td></tr>
        {bloque('PASIVOS', bg['pasivos'], bg['total_pasivos'])}
        <tr class="tot"><td colspan="2">TOTAL PASIVOS</td>
          <td class="n">{_money(bg['total_pasivos'])}</td></tr>
        {bloque('PATRIMONIO', bg['patrimonio'], bg['total_patrimonio_base'], extra_patr)}
        <tr class="tot"><td colspan="2">PASIVO + PATRIMONIO ({cuadre})</td>
          <td class="n">{_money(bg['total_pasivo_patrimonio'])}</td></tr>
      </tbody></table>
      {'<p class="bad"><strong>⚠️ Patrimonio neto negativo.</strong></p>' if bg['patrimonio_negativo'] else ''}"""
    return _page('Balance General', cuerpo, request=request)


@login_required
def flujo_caja(request):
    desde, hasta = _rango(request)
    fc = R.flujo_caja(desde, hasta)
    cls = 'bad' if fc['flujo_negativo'] else 'ok'
    cuerpo = f"""
      <table><tbody>
        <tr><td>Saldo inicial</td><td class="n">{_money(fc['saldo_inicial'])}</td></tr>
        <tr><td>(+) Entradas de efectivo</td><td class="n">{_money(fc['entradas'])}</td></tr>
        <tr><td>(−) Salidas de efectivo</td><td class="n">{_money(fc['salidas'])}</td></tr>
        <tr class="tot"><td class="{cls}">FLUJO NETO</td>
          <td class="n {cls}">{_money(fc['flujo_neto'])}</td></tr>
        <tr class="tot"><td>Saldo final</td>
          <td class="n">{_money(fc['saldo_final'])}</td></tr>
      </tbody></table>
      {'<p class="bad"><strong>⚠️ Flujo de caja negativo.</strong></p>' if fc['flujo_negativo'] else ''}"""
    return _page('Flujo de Caja', cuerpo, request=request)

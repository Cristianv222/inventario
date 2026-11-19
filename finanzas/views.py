"""
Vistas del ERP de Finanzas: dashboard y estados financieros en pantalla,
con exportación a PDF (WeasyPrint) y Excel (openpyxl).

Todo lo que se muestra se calcula de forma determinista en
finanzas.services.reportes_contables. La IA no interviene en ninguna cifra.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from .models import AsientoContable, CuentaContable, PeriodoContable
from .services import reportes_contables as rc


# --------------------------------------------------------------------------- #
# Utilidades de rango de fechas
# --------------------------------------------------------------------------- #
def _parse_fecha(valor):
    try:
        return datetime.datetime.strptime(valor, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _rango(request):
    """(fecha_inicio, fecha_fin) desde GET; por defecto el mes en curso."""
    hoy = timezone.localdate()
    ini = _parse_fecha(request.GET.get('fecha_inicio'))
    fin = _parse_fecha(request.GET.get('fecha_fin'))
    if ini is None:
        ini = hoy.replace(day=1)
    if fin is None:
        fin = hoy
    if fin < ini:
        ini, fin = fin, ini
    return ini, fin


def _ctx_rango(request, ini, fin):
    q = request.GET.copy()
    q.pop('export', None)
    return {'fecha_inicio': ini, 'fecha_fin': fin,
            'fecha_inicio_str': ini.isoformat(), 'fecha_fin_str': fin.isoformat(),
            'export_base': q.urlencode()}


# --------------------------------------------------------------------------- #
# Exportación
# --------------------------------------------------------------------------- #
def _pdf_response(partial, contexto, titulo, filename):
    """Renderiza un parcial de reporte dentro del wrapper de impresión -> PDF."""
    from weasyprint import HTML
    html = render_to_string('finanzas/print/documento.html', {
        'partial': partial, 'titulo': titulo, **contexto,
    })
    pdf = HTML(string=html).write_pdf()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    return resp


def _excel_response(filename, titulo, encabezados, filas, totales=None):
    """Construye un .xlsx simple (una hoja) con encabezados, filas y totales.

    `filas`: lista de listas (valores de celda).
    `totales`: lista opcional de celdas para la fila de totales (en negrita).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31]

    azul = PatternFill('solid', fgColor='2563EB')
    blanco_bold = Font(bold=True, color='FFFFFF')

    ws.append([titulo])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([])

    fila_enc = ws.max_row + 1
    ws.append(encabezados)
    for col in range(1, len(encabezados) + 1):
        celda = ws.cell(row=fila_enc, column=col)
        celda.font = blanco_bold
        celda.fill = azul
        celda.alignment = Alignment(horizontal='center')

    for fila in filas:
        ws.append(fila)

    if totales:
        ws.append(totales)
        for col in range(1, len(totales) + 1):
            ws.cell(row=ws.max_row, column=col).font = Font(bold=True)

    for col in ws.columns:
        ancho = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(ancho + 3, 48)

    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    wb.save(resp)
    return resp


def _num(v):
    return float(v or 0)


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@login_required
def dashboard(request):
    ini, fin = _rango(request)
    er = rc.estado_resultados(ini, fin)
    bg = rc.balance_general(fin)
    fc = rc.flujo_caja(ini, fin)
    ctx = {
        'titulo': 'Finanzas · ERP',
        'num_cuentas': CuentaContable.objects.filter(activa=True).count(),
        'num_asientos': AsientoContable.objects.filter(
            estado=AsientoContable.ESTADO_MAYORIZADO).count(),
        'periodos_abiertos': PeriodoContable.objects.filter(cerrado=False).count(),
        'total_ingresos': er['total_ingresos'],
        'total_gastos': er['total_gastos'] + er['total_costos'],
        'utilidad_neta': er['utilidad_neta'],
        'total_activo': bg['total_activo'],
        'saldo_caja': fc['saldo_final'],
        'balance_cuadra': bg['cuadra'],
        **_ctx_rango(request, ini, fin),
    }
    return render(request, 'finanzas/dashboard.html', ctx)


# --------------------------------------------------------------------------- #
# 1) Libro Mayor
# --------------------------------------------------------------------------- #
@login_required
def libro_mayor(request):
    ini, fin = _rango(request)
    codigo = request.GET.get('cuenta') or None
    data = rc.libro_mayor(ini, fin, codigo)
    ctx = {
        'titulo': 'Libro Mayor',
        'partial': 'finanzas/partials/libro_mayor.html',
        'cuentas_data': data,
        'cuenta_sel': codigo,
        'cuentas': CuentaContable.objects.filter(es_movimiento=True),
        **_ctx_rango(request, ini, fin),
    }
    export = request.GET.get('export')
    if export == 'pdf':
        return _pdf_response(ctx['partial'], ctx, 'Libro Mayor',
                             f'libro_mayor_{ini}_{fin}')
    if export == 'excel':
        encabezados = ['Fecha', 'Asiento', 'Cuenta', 'Glosa', 'Debe', 'Haber', 'Saldo']
        filas = []
        for grupo in data:
            c = grupo['cuenta']
            filas.append([f'{c.codigo} - {c.nombre}', '', '', 'Saldo anterior',
                          '', '', _num(grupo['saldo_anterior'])])
            for m in grupo['movimientos']:
                filas.append([m['fecha'].isoformat(), m['numero'], c.codigo,
                              m['glosa'], _num(m['debe']), _num(m['haber']),
                              _num(m['saldo'])])
            filas.append(['', '', '', 'Saldo final', _num(grupo['total_debe']),
                          _num(grupo['total_haber']), _num(grupo['saldo_final'])])
        return _excel_response(f'libro_mayor_{ini}_{fin}', 'Libro Mayor',
                               encabezados, filas)
    return render(request, 'finanzas/libro_mayor.html', ctx)


# --------------------------------------------------------------------------- #
# 2) Balance de Comprobación
# --------------------------------------------------------------------------- #
@login_required
def balance_comprobacion(request):
    ini, fin = _rango(request)
    data = rc.balance_comprobacion(ini, fin)
    ctx = {
        'titulo': 'Balance de Comprobación',
        'partial': 'finanzas/partials/balance_comprobacion.html',
        'data': data,
        **_ctx_rango(request, ini, fin),
    }
    export = request.GET.get('export')
    if export == 'pdf':
        return _pdf_response(ctx['partial'], ctx, 'Balance de Comprobación',
                             f'balance_comprobacion_{ini}_{fin}')
    if export == 'excel':
        encabezados = ['Código', 'Cuenta', 'Tipo', 'Debe', 'Haber',
                       'Saldo Deudor', 'Saldo Acreedor']
        filas = [[f['codigo'], f['nombre'], f['tipo'], _num(f['debe']),
                  _num(f['haber']), _num(f['deudor']), _num(f['acreedor'])]
                 for f in data['filas']]
        totales = ['', 'TOTALES', '', _num(data['total_debe']),
                   _num(data['total_haber']), _num(data['total_deudor']),
                   _num(data['total_acreedor'])]
        return _excel_response(f'balance_comprobacion_{ini}_{fin}',
                               'Balance de Comprobación', encabezados, filas, totales)
    return render(request, 'finanzas/balance_comprobacion.html', ctx)


# --------------------------------------------------------------------------- #
# 3) Estado de Resultados
# --------------------------------------------------------------------------- #
@login_required
def estado_resultados(request):
    ini, fin = _rango(request)
    data = rc.estado_resultados(ini, fin)
    ctx = {
        'titulo': 'Estado de Resultados',
        'partial': 'finanzas/partials/estado_resultados.html',
        'data': data,
        **_ctx_rango(request, ini, fin),
    }
    export = request.GET.get('export')
    if export == 'pdf':
        return _pdf_response(ctx['partial'], ctx, 'Estado de Resultados',
                             f'estado_resultados_{ini}_{fin}')
    if export == 'excel':
        encabezados = ['Sección', 'Código', 'Cuenta', 'Monto']
        filas = []
        for f in data['ingresos']:
            filas.append(['Ingreso', f['codigo'], f['nombre'], _num(f['saldo'])])
        filas.append(['', '', 'TOTAL INGRESOS', _num(data['total_ingresos'])])
        for f in data['costos']:
            filas.append(['Costo', f['codigo'], f['nombre'], _num(f['saldo'])])
        filas.append(['', '', 'TOTAL COSTOS', _num(data['total_costos'])])
        filas.append(['', '', 'UTILIDAD BRUTA', _num(data['utilidad_bruta'])])
        for f in data['gastos']:
            filas.append(['Gasto', f['codigo'], f['nombre'], _num(f['saldo'])])
        filas.append(['', '', 'TOTAL GASTOS', _num(data['total_gastos'])])
        totales = ['', '', 'UTILIDAD NETA', _num(data['utilidad_neta'])]
        return _excel_response(f'estado_resultados_{ini}_{fin}',
                               'Estado de Resultados', encabezados, filas, totales)
    return render(request, 'finanzas/estado_resultados.html', ctx)


# --------------------------------------------------------------------------- #
# 4) Balance General
# --------------------------------------------------------------------------- #
@login_required
def balance_general(request):
    ini, fin = _rango(request)
    data = rc.balance_general(fin)
    ctx = {
        'titulo': 'Balance General',
        'partial': 'finanzas/partials/balance_general.html',
        'data': data,
        **_ctx_rango(request, ini, fin),
    }
    export = request.GET.get('export')
    if export == 'pdf':
        return _pdf_response(ctx['partial'], ctx, 'Balance General',
                             f'balance_general_{fin}')
    if export == 'excel':
        encabezados = ['Sección', 'Código', 'Cuenta', 'Monto']
        filas = []
        for f in data['activos']:
            filas.append(['Activo', f['codigo'], f['nombre'], _num(f['saldo'])])
        filas.append(['', '', 'TOTAL ACTIVO', _num(data['total_activo'])])
        for f in data['pasivos']:
            filas.append(['Pasivo', f['codigo'], f['nombre'], _num(f['saldo'])])
        filas.append(['', '', 'TOTAL PASIVO', _num(data['total_pasivo'])])
        for f in data['patrimonio']:
            filas.append(['Patrimonio', f['codigo'], f['nombre'], _num(f['saldo'])])
        filas.append(['Patrimonio', '', 'Resultado del ejercicio',
                      _num(data['resultado_ejercicio'])])
        filas.append(['', '', 'TOTAL PATRIMONIO + RESULTADO',
                      _num(data['total_patrimonio'] + data['resultado_ejercicio'])])
        totales = ['', '', 'TOTAL PASIVO + PATRIMONIO',
                   _num(data['total_pasivo_patrimonio'])]
        return _excel_response(f'balance_general_{fin}', 'Balance General',
                               encabezados, filas, totales)
    return render(request, 'finanzas/balance_general.html', ctx)


# --------------------------------------------------------------------------- #
# 5) Flujo de Caja
# --------------------------------------------------------------------------- #
@login_required
def flujo_caja(request):
    ini, fin = _rango(request)
    data = rc.flujo_caja(ini, fin)
    ctx = {
        'titulo': 'Flujo de Caja',
        'partial': 'finanzas/partials/flujo_caja.html',
        'data': data,
        **_ctx_rango(request, ini, fin),
    }
    export = request.GET.get('export')
    if export == 'pdf':
        return _pdf_response(ctx['partial'], ctx, 'Flujo de Caja',
                             f'flujo_caja_{ini}_{fin}')
    if export == 'excel':
        encabezados = ['Fecha', 'Asiento', 'Cuenta', 'Glosa', 'Entrada', 'Salida', 'Saldo']
        filas = [['', '', '', 'Saldo inicial', '', '', _num(data['saldo_inicial'])]]
        for m in data['movimientos']:
            filas.append([m['fecha'].isoformat(), m['numero'], m['cuenta'],
                          m['glosa'], _num(m['entrada']), _num(m['salida']),
                          _num(m['saldo'])])
        totales = ['', '', '', 'TOTALES / Saldo final', _num(data['total_entradas']),
                   _num(data['total_salidas']), _num(data['saldo_final'])]
        return _excel_response(f'flujo_caja_{ini}_{fin}', 'Flujo de Caja',
                               encabezados, filas, totales)
    return render(request, 'finanzas/flujo_caja.html', ctx)

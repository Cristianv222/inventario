from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, Avg, F
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.db import transaction
from datetime import datetime, timedelta, date
import json
import calendar
from decimal import Decimal

from .models import (
    MovimientoCaja, GastoDiario, CierreDiario, TipoMovimiento,
    ResumenMensual, DesgloseBilletes
)
from .forms import (
    GastoDiarioForm, CierreDiarioForm, ReporteVentasForm, FiltroFechasForm,
    FiltroMovimientosForm, FiltroGastosForm, ComparativoVentasForm, ExportarReporteForm
)
from ventas.models import Venta, DetalleVenta

try:
    from taller.models import OrdenTrabajo, ServicioOrden, Tecnico, TipoServicio
    TALLER_DISPONIBLE = True
except ImportError:
    TALLER_DISPONIBLE = False

try:
    from clientes.models import PedidoOnline
    ONLINE_DISPONIBLE = True
except ImportError:
    ONLINE_DISPONIBLE = False


# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════

def _rango_periodo(tipo, fecha_ref=None):
    """Devuelve (fecha_inicio, fecha_fin) para dia/semana/mes/año"""
    hoy = fecha_ref or timezone.now().date()
    if tipo == 'dia':
        return hoy, hoy
    elif tipo == 'semana':
        inicio = hoy - timedelta(days=hoy.weekday())
        return inicio, inicio + timedelta(days=6)
    elif tipo == 'mes':
        inicio = hoy.replace(day=1)
        ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
        return inicio, hoy.replace(day=ultimo)
    elif tipo == 'año':
        return hoy.replace(month=1, day=1), hoy.replace(month=12, day=31)
    return hoy, hoy


def _ventas_pos(fecha_inicio, fecha_fin):
    return Venta.objects.filter(
        fecha_hora__date__range=[fecha_inicio, fecha_fin],
        estado='COMPLETADA'
    )


def _pedidos_online(fecha_inicio, fecha_fin):
    if not ONLINE_DISPONIBLE:
        return PedidoOnline.objects.none() if ONLINE_DISPONIBLE else []
    return PedidoOnline.objects.filter(
        fecha_entrega__date__range=[fecha_inicio, fecha_fin],
        estado='ENTREGADO'
    )


def _ordenes_taller(fecha_inicio, fecha_fin):
    if not TALLER_DISPONIBLE:
        return []
    return OrdenTrabajo.objects.filter(
        estado__in=['COMPLETADO', 'ENTREGADO'],
        fecha_completado__date__range=[fecha_inicio, fecha_fin]
    )


# ══════════════════════════════════════════════════════════════════════
#  DASHBOARD PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

@login_required
def dashboard_reportes(request):
    hoy = timezone.now().date()
    cierre_hoy = CierreDiario.get_o_crear_hoy(request.user)

    # ── Hoy ───────────────────────────────────────────────────────
    ventas_pos_hoy = _ventas_pos(hoy, hoy)
    total_pos_hoy = ventas_pos_hoy.aggregate(t=Sum('total'))['t'] or Decimal('0')

    total_online_hoy = Decimal('0')
    if ONLINE_DISPONIBLE:
        total_online_hoy = PedidoOnline.objects.filter(
            fecha_entrega__date=hoy, estado='ENTREGADO'
        ).aggregate(t=Sum('total'))['t'] or Decimal('0')

    total_taller_hoy = Decimal('0')
    if TALLER_DISPONIBLE:
        total_taller_hoy = OrdenTrabajo.objects.filter(
            estado__in=['COMPLETADO', 'ENTREGADO'],
            fecha_completado__date=hoy
        ).aggregate(t=Sum('precio_total'))['t'] or Decimal('0')

    total_gastos_hoy = GastoDiario.objects.filter(
        fecha=hoy, aprobado=True
    ).aggregate(t=Sum('monto'))['t'] or Decimal('0')

    stats_hoy = {
        'total_pos': total_pos_hoy,
        'total_online': total_online_hoy,
        'total_taller': total_taller_hoy,
        'total_ingresos': total_pos_hoy + total_online_hoy + total_taller_hoy,
        'total_gastos': total_gastos_hoy,
        'cantidad_ventas': ventas_pos_hoy.count(),
        'efectivo': ventas_pos_hoy.filter(tipo_pago='EFECTIVO').aggregate(t=Sum('total'))['t'] or Decimal('0'),
        'tarjeta': ventas_pos_hoy.filter(tipo_pago='TARJETA').aggregate(t=Sum('total'))['t'] or Decimal('0'),
        'transferencia': ventas_pos_hoy.filter(tipo_pago='TRANSFERENCIA').aggregate(t=Sum('total'))['t'] or Decimal('0'),
    }

    # ── Semana ────────────────────────────────────────────────────
    inicio_sem, fin_sem = _rango_periodo('semana', hoy)
    ventas_sem = _ventas_pos(inicio_sem, fin_sem)
    stats_semana = {
        'total_ventas': ventas_sem.aggregate(t=Sum('total'))['t'] or Decimal('0'),
        'cantidad_ventas': ventas_sem.count(),
        'total_gastos': GastoDiario.objects.filter(
            fecha__range=[inicio_sem, fin_sem], aprobado=True
        ).aggregate(t=Sum('monto'))['t'] or Decimal('0'),
    }

    # ── Mes ───────────────────────────────────────────────────────
    inicio_mes, fin_mes = _rango_periodo('mes', hoy)
    ventas_mes = _ventas_pos(inicio_mes, fin_mes)
    stats_mes = {
        'total_ventas': ventas_mes.aggregate(t=Sum('total'))['t'] or Decimal('0'),
        'cantidad_ventas': ventas_mes.count(),
        'total_gastos': GastoDiario.objects.filter(
            fecha__range=[inicio_mes, fin_mes], aprobado=True
        ).aggregate(t=Sum('monto'))['t'] or Decimal('0'),
    }

    # ── Top 5 días con más ventas del mes ─────────────────────────
    top_dias = ventas_mes.extra(
        select={'dia': 'DATE(fecha_hora)'}
    ).values('dia').annotate(
        total_dia=Sum('total'), cantidad=Count('id')
    ).order_by('-total_dia')[:5]

    # ── Gastos pendientes ─────────────────────────────────────────
    gastos_pendientes = GastoDiario.objects.filter(
        aprobado=False, fecha__gte=hoy - timedelta(days=7)
    ).count()

    context = {
        'active_page': 'reportes',
        'cierre_hoy': cierre_hoy,
        'stats_hoy': stats_hoy,
        'stats_semana': stats_semana,
        'stats_mes': stats_mes,
        'top_dias': top_dias,
        'gastos_pendientes': gastos_pendientes,
        'hoy': hoy,
        'taller_disponible': TALLER_DISPONIBLE,
        'online_disponible': ONLINE_DISPONIBLE,
    }
    return render(request, 'reportes/dashboard.html', context)


# ══════════════════════════════════════════════════════════════════════
#  REPORTES DE VENTAS (POS + ONLINE + TALLER)
# ══════════════════════════════════════════════════════════════════════

@login_required
def reporte_ventas_completo(request):
    """
    Reporte unificado: ventas POS + pedidos online + órdenes taller.
    Filtros: periodo (dia/semana/mes/año) o fechas personalizadas.
    """
    hoy = timezone.now().date()
    periodo = request.GET.get('periodo', 'mes')
    fecha_desde_str = request.GET.get('fecha_desde')
    fecha_hasta_str = request.GET.get('fecha_hasta')

    # Resolver rango de fechas
    if fecha_desde_str and fecha_hasta_str:
        try:
            fecha_inicio = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_inicio, fecha_fin = _rango_periodo(periodo, hoy)
    else:
        fecha_inicio, fecha_fin = _rango_periodo(periodo, hoy)

    # ── Ventas POS ────────────────────────────────────────────────
    ventas_pos = _ventas_pos(fecha_inicio, fecha_fin)
    stats_pos = ventas_pos.aggregate(
        total=Sum('total'),
        subtotal=Sum('subtotal'),
        iva=Sum('iva'),
        cantidad=Count('id'),
        efectivo=Sum('total', filter=Q(tipo_pago='EFECTIVO')),
        tarjeta=Sum('total', filter=Q(tipo_pago='TARJETA')),
        transferencia=Sum('total', filter=Q(tipo_pago='TRANSFERENCIA')),
    )

    detalles_productos = DetalleVenta.objects.filter(
        venta__fecha_hora__date__range=[fecha_inicio, fecha_fin],
        venta__estado='COMPLETADA',
        es_servicio=False
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0')

    detalles_servicios = DetalleVenta.objects.filter(
        venta__fecha_hora__date__range=[fecha_inicio, fecha_fin],
        venta__estado='COMPLETADA',
        es_servicio=True
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0')

    # ── Pedidos Online ────────────────────────────────────────────
    stats_online = {'total': Decimal('0'), 'cantidad': 0}
    pedidos_por_metodo = []
    if ONLINE_DISPONIBLE:
        pedidos = _pedidos_online(fecha_inicio, fecha_fin)
        stats_online = pedidos.aggregate(
            total=Sum('total'), cantidad=Count('id')
        )
        stats_online['total'] = stats_online['total'] or Decimal('0')
        stats_online['cantidad'] = stats_online['cantidad'] or 0
        pedidos_por_metodo = pedidos.values('metodo_pago').annotate(
            total=Sum('total'), cantidad=Count('id')
        ).order_by('-total')

    # ── Órdenes Taller ────────────────────────────────────────────
    stats_taller = {'total': Decimal('0'), 'cantidad': 0}
    if TALLER_DISPONIBLE:
        ordenes = _ordenes_taller(fecha_inicio, fecha_fin)
        agg = ordenes.aggregate(total=Sum('precio_total'), cantidad=Count('id'))
        stats_taller = {
            'total': agg['total'] or Decimal('0'),
            'cantidad': agg['cantidad'] or 0,
        }

    # ── Totales consolidados ──────────────────────────────────────
    total_general = (
        (stats_pos['total'] or Decimal('0'))
        + stats_online['total']
        + stats_taller['total']
    )

    # ── Ventas POS por día (para gráfico) ─────────────────────────
    ventas_por_dia = ventas_pos.extra(
        select={'dia': 'DATE(fecha_hora)'}
    ).values('dia').annotate(
        total=Sum('total'), cantidad=Count('id')
    ).order_by('dia')

    # ── Top productos vendidos ────────────────────────────────────
    top_productos = DetalleVenta.objects.filter(
        venta__fecha_hora__date__range=[fecha_inicio, fecha_fin],
        venta__estado='COMPLETADA',
        es_servicio=False,
        producto__isnull=False
    ).values('producto__nombre').annotate(
        cantidad=Sum('cantidad'), total=Sum('subtotal')
    ).order_by('-total')[:10]

    # ── Top servicios vendidos ────────────────────────────────────
    top_servicios = DetalleVenta.objects.filter(
        venta__fecha_hora__date__range=[fecha_inicio, fecha_fin],
        venta__estado='COMPLETADA',
        es_servicio=True,
        tipo_servicio__isnull=False
    ).values('tipo_servicio__nombre').annotate(
        cantidad=Sum('cantidad'), total=Sum('subtotal')
    ).order_by('-total')[:10]

    # ── Vendedores (usuarios que hicieron ventas) ─────────────────
    ventas_por_usuario = ventas_pos.values(
        'usuario__nombre', 'usuario__apellido'
    ).annotate(
        total=Sum('total'), cantidad=Count('id')
    ).order_by('-total')

    context = {
        'active_page': 'reportes',
        'periodo': periodo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'stats_pos': stats_pos,
        'detalles_productos': detalles_productos,
        'detalles_servicios': detalles_servicios,
        'stats_online': stats_online,
        'pedidos_por_metodo': pedidos_por_metodo,
        'stats_taller': stats_taller,
        'total_general': total_general,
        'ventas_por_dia': list(ventas_por_dia),
        'top_productos': top_productos,
        'top_servicios': top_servicios,
        'ventas_por_usuario': ventas_por_usuario,
        'taller_disponible': TALLER_DISPONIBLE,
        'online_disponible': ONLINE_DISPONIBLE,
    }
    return render(request, 'reportes/ventas_completo.html', context)


# ══════════════════════════════════════════════════════════════════════
#  REPORTES POR TÉCNICO
# ══════════════════════════════════════════════════════════════════════

@login_required
def reporte_tecnicos(request):
    """
    Reporte de rendimiento por técnico.
    Muestra: cantidad de servicios, total facturado, promedio evaluación.
    Filtros: dia/semana/mes/año + técnico específico.
    """
    if not TALLER_DISPONIBLE:
        messages.warning(request, 'El módulo de taller no está disponible.')
        return redirect('reportes:dashboard')

    hoy = timezone.now().date()
    periodo = request.GET.get('periodo', 'mes')
    tecnico_id = request.GET.get('tecnico_id')
    fecha_desde_str = request.GET.get('fecha_desde')
    fecha_hasta_str = request.GET.get('fecha_hasta')

    if fecha_desde_str and fecha_hasta_str:
        try:
            fecha_inicio = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_inicio, fecha_fin = _rango_periodo(periodo, hoy)
    else:
        fecha_inicio, fecha_fin = _rango_periodo(periodo, hoy)

    tecnicos = Tecnico.objects.filter(activo=True).order_by('nombres', 'apellidos')

    # ── Resumen general de todos los técnicos ─────────────────────
    ordenes_periodo = OrdenTrabajo.objects.filter(
        estado__in=['COMPLETADO', 'ENTREGADO'],
        fecha_completado__date__range=[fecha_inicio, fecha_fin]
    )

    resumen_tecnicos = []
    for tec in tecnicos:
        ordenes_tec = ordenes_periodo.filter(tecnico_principal=tec)

        # Servicios realizados por este técnico en el período
        servicios_tec = ServicioOrden.objects.filter(
            orden__in=ordenes_tec,
            tecnico_asignado=tec
        )

        # Servicios más realizados por este técnico
        top_servicios_tec = servicios_tec.values(
            'tipo_servicio__nombre'
        ).annotate(
            cantidad=Count('id'),
            total=Sum('precio_servicio')
        ).order_by('-cantidad')[:5]

        # Promedio de evaluación
        from taller.models import EvaluacionServicio
        evaluaciones = EvaluacionServicio.objects.filter(
            orden__in=ordenes_tec,
            calificacion_tecnico__isnull=False
        )
        promedio_eval = evaluaciones.aggregate(
            p=Avg('calificacion_tecnico')
        )['p'] or 0

        total_facturado = ordenes_tec.aggregate(
            t=Sum('precio_total')
        )['t'] or Decimal('0')

        resumen_tecnicos.append({
            'tecnico': tec,
            'ordenes_completadas': ordenes_tec.count(),
            'total_servicios': servicios_tec.count(),
            'total_facturado': total_facturado,
            'promedio_evaluacion': round(promedio_eval, 1),
            'comision_estimada': total_facturado * (tec.porcentaje_comision / 100) if tec.porcentaje_comision else Decimal('0'),
            'top_servicios': list(top_servicios_tec),
        })

    # Ordenar por total facturado desc
    resumen_tecnicos.sort(key=lambda x: x['total_facturado'], reverse=True)

    # ── Detalle de un técnico específico ──────────────────────────
    detalle_tecnico = None
    if tecnico_id:
        try:
            tec_sel = Tecnico.objects.get(id=tecnico_id)
            ordenes_sel = ordenes_periodo.filter(tecnico_principal=tec_sel)

            # Servicios agrupados por tipo
            servicios_agrupados = ServicioOrden.objects.filter(
                orden__in=ordenes_sel,
                tecnico_asignado=tec_sel
            ).values(
                'tipo_servicio__nombre',
                'tipo_servicio__categoria__nombre'
            ).annotate(
                cantidad=Count('id'),
                total=Sum('precio_servicio'),
                tiempo_promedio=Avg('tiempo_real')
            ).order_by('-cantidad')

            # Órdenes del período con detalle
            ordenes_detalle = ordenes_sel.select_related(
                'cliente'
            ).prefetch_related('servicios').order_by('-fecha_completado')

            # Estadísticas por semana dentro del período
            from django.db.models.functions import TruncWeek
            por_semana = ordenes_sel.annotate(
                semana=TruncWeek('fecha_completado')
            ).values('semana').annotate(
                total=Sum('precio_total'),
                cantidad=Count('id')
            ).order_by('semana')

            detalle_tecnico = {
                'tecnico': tec_sel,
                'ordenes': ordenes_detalle,
                'servicios_agrupados': servicios_agrupados,
                'por_semana': list(por_semana),
                'stats': resumen_tecnicos[
                    next((i for i, r in enumerate(resumen_tecnicos)
                          if r['tecnico'].id == tec_sel.id), 0)
                ] if resumen_tecnicos else {},
            }
        except Tecnico.DoesNotExist:
            pass

    # ── Servicios más realizados en general ───────────────────────
    top_servicios_global = ServicioOrden.objects.filter(
        orden__in=ordenes_periodo
    ).values(
        'tipo_servicio__nombre',
        'tipo_servicio__categoria__nombre'
    ).annotate(
        cantidad=Count('id'),
        total=Sum('precio_servicio')
    ).order_by('-cantidad')[:15]

    context = {
        'active_page': 'reportes',
        'periodo': periodo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'tecnicos': tecnicos,
        'resumen_tecnicos': resumen_tecnicos,
        'detalle_tecnico': detalle_tecnico,
        'tecnico_id_sel': int(tecnico_id) if tecnico_id else None,
        'top_servicios_global': top_servicios_global,
    }
    return render(request, 'reportes/tecnicos.html', context)


# ══════════════════════════════════════════════════════════════════════
#  REPORTES POR VENDEDOR (USUARIO)
# ══════════════════════════════════════════════════════════════════════

@login_required
def reporte_vendedores(request):
    """
    Rendimiento de cada usuario que realiza ventas.
    Filtros: dia/semana/mes/año.
    """
    hoy = timezone.now().date()
    periodo = request.GET.get('periodo', 'mes')
    fecha_desde_str = request.GET.get('fecha_desde')
    fecha_hasta_str = request.GET.get('fecha_hasta')

    if fecha_desde_str and fecha_hasta_str:
        try:
            fecha_inicio = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_inicio, fecha_fin = _rango_periodo(periodo, hoy)
    else:
        fecha_inicio, fecha_fin = _rango_periodo(periodo, hoy)

    ventas = _ventas_pos(fecha_inicio, fecha_fin)

    # Agrupar por usuario
    por_usuario = ventas.values(
        'usuario__id',
        'usuario__nombre',
        'usuario__apellido',
    ).annotate(
        total_ventas=Sum('total'),
        cantidad_ventas=Count('id'),
        promedio_venta=Avg('total'),
        efectivo=Sum('total', filter=Q(tipo_pago='EFECTIVO')),
        tarjeta=Sum('total', filter=Q(tipo_pago='TARJETA')),
        transferencia=Sum('total', filter=Q(tipo_pago='TRANSFERENCIA')),
    ).order_by('-total_ventas')

    # Detalle de un vendedor específico
    usuario_id = request.GET.get('usuario_id')
    detalle_vendedor = None
    if usuario_id:
        ventas_usr = ventas.filter(usuario__id=usuario_id)
        top_productos_usr = DetalleVenta.objects.filter(
            venta__in=ventas_usr,
            es_servicio=False,
            producto__isnull=False
        ).values('producto__nombre').annotate(
            cantidad=Sum('cantidad'), total=Sum('subtotal')
        ).order_by('-total')[:10]

        top_servicios_usr = DetalleVenta.objects.filter(
            venta__in=ventas_usr,
            es_servicio=True,
            tipo_servicio__isnull=False
        ).values('tipo_servicio__nombre').annotate(
            cantidad=Sum('cantidad'), total=Sum('subtotal')
        ).order_by('-total')[:10]

        ventas_por_dia_usr = ventas_usr.extra(
            select={'dia': 'DATE(fecha_hora)'}
        ).values('dia').annotate(
            total=Sum('total'), cantidad=Count('id')
        ).order_by('dia')

        detalle_vendedor = {
            'ventas': ventas_usr.select_related('cliente').order_by('-fecha_hora')[:50],
            'top_productos': top_productos_usr,
            'top_servicios': top_servicios_usr,
            'ventas_por_dia': list(ventas_por_dia_usr),
        }

    context = {
        'active_page': 'reportes',
        'periodo': periodo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'por_usuario': por_usuario,
        'detalle_vendedor': detalle_vendedor,
        'usuario_id_sel': int(usuario_id) if usuario_id else None,
    }
    return render(request, 'reportes/vendedores.html', context)


# ══════════════════════════════════════════════════════════════════════
#  CAJA DIARIA CON DESGLOSE DE BILLETES
# ══════════════════════════════════════════════════════════════════════

@login_required
def caja_diaria(request):
    fecha_str = request.GET.get('fecha')
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha = timezone.now().date()
    else:
        fecha = timezone.now().date()

    cierre, created = CierreDiario.objects.get_or_create(
        fecha=fecha,
        defaults={'usuario_cierre': request.user}
    )
    if created or cierre.estado == 'ABIERTO':
        cierre.calcular_totales()
        cierre.save()

    # Ventas del día
    ventas_dia = _ventas_pos(fecha, fecha).select_related('cliente', 'usuario')

    # Pedidos online del día
    pedidos_dia = []
    if ONLINE_DISPONIBLE:
        pedidos_dia = PedidoOnline.objects.filter(
            fecha_entrega__date=fecha, estado='ENTREGADO'
        ).select_related()

    # Órdenes taller del día
    ordenes_dia = []
    if TALLER_DISPONIBLE:
        ordenes_dia = OrdenTrabajo.objects.filter(
            estado__in=['COMPLETADO', 'ENTREGADO'],
            fecha_completado__date=fecha
        ).select_related('cliente', 'tecnico_principal')

    # Gastos del día
    gastos_dia = GastoDiario.objects.filter(fecha=fecha).order_by('-fecha_creacion')

    # Desglose de billetes existente
    desglose = cierre.desglose_billetes.all().order_by('-denominacion')

    # Denominaciones para el formulario de conteo
    denominaciones_billetes = [
        ('100.00', '$100'), ('50.00', '$50'), ('20.00', '$20'),
        ('10.00', '$10'), ('5.00', '$5'), ('1.00', '$1'),
    ]
    denominaciones_monedas = [
        ('0.50', '50¢'), ('0.25', '25¢'), ('0.10', '10¢'),
        ('0.05', '5¢'), ('0.01', '1¢'),
    ]

    # Métodos de pago
    metodos_pago = ventas_dia.values('tipo_pago').annotate(
        total=Sum('total'), cantidad=Count('id')
    ).order_by('-total')

    # Comparativo día anterior
    fecha_anterior = fecha - timedelta(days=1)
    comparativo = None
    try:
        cierre_ant = CierreDiario.objects.get(fecha=fecha_anterior, estado='CERRADO')
        comparativo = {
            'ventas_anterior': cierre_ant.total_ingresos,
            'diferencia': cierre.total_ingresos - cierre_ant.total_ingresos,
        }
    except CierreDiario.DoesNotExist:
        pass

    context = {
        'active_page': 'reportes',
        'cierre': cierre,
        'fecha': fecha,
        'ventas_dia': ventas_dia,
        'pedidos_dia': pedidos_dia,
        'ordenes_dia': ordenes_dia,
        'gastos_dia': gastos_dia,
        'desglose': desglose,
        'metodos_pago': metodos_pago,
        'comparativo': comparativo,
        'denominaciones_billetes': denominaciones_billetes,
        'denominaciones_monedas': denominaciones_monedas,
        'puede_cerrar': fecha <= timezone.now().date() and cierre.estado == 'ABIERTO',
        'hoy': timezone.now().date(),
        'taller_disponible': TALLER_DISPONIBLE,
        'online_disponible': ONLINE_DISPONIBLE,
    }
    return render(request, 'reportes/caja_diaria.html', context)


@login_required
@require_POST
def guardar_desglose_billetes(request, cierre_id):
    """
    Guarda el conteo físico de billetes y monedas.
    Recibe JSON con lista de {denominacion, cantidad, tipo}.
    """
    cierre = get_object_or_404(CierreDiario, pk=cierre_id)

    if cierre.estado == 'CERRADO' and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Caja ya cerrada'}, status=400)

    try:
        data = json.loads(request.body)
        items = data.get('items', [])

        with transaction.atomic():
            # Eliminar desglose anterior
            cierre.desglose_billetes.all().delete()

            total_contado = Decimal('0')
            for item in items:
                cantidad = int(item.get('cantidad', 0))
                if cantidad <= 0:
                    continue
                denominacion = Decimal(str(item['denominacion']))
                tipo = item.get('tipo', 'BILLETE')
                subtotal = denominacion * cantidad
                total_contado += subtotal

                DesgloseBilletes.objects.create(
                    cierre=cierre,
                    tipo=tipo,
                    denominacion=denominacion,
                    cantidad=cantidad,
                    subtotal=subtotal,
                )

            # Actualizar efectivo contado y diferencia
            cierre.efectivo_contado = total_contado
            efectivo_esperado = cierre.saldo_inicial + cierre.efectivo_ventas - cierre.total_gastos_dia
            cierre.diferencia_efectivo = total_contado - efectivo_esperado
            cierre.save(update_fields=['efectivo_contado', 'diferencia_efectivo'])

        return JsonResponse({
            'success': True,
            'total_contado': float(total_contado),
            'diferencia': float(cierre.diferencia_efectivo),
            'cuadra': cierre.diferencia_efectivo == 0,
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def cerrar_caja(request):
    fecha_str = request.POST.get('fecha')
    observaciones = request.POST.get('observaciones', '')

    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        if fecha > timezone.now().date():
            messages.error(request, 'No se puede cerrar caja de fechas futuras.')
            return redirect('reportes:caja_diaria')

        cierre = get_object_or_404(CierreDiario, fecha=fecha)

        if cierre.estado != 'ABIERTO':
            messages.error(request, 'Esta caja ya está cerrada.')
            return redirect('reportes:caja_diaria')

        cierre.observaciones = observaciones
        cierre.calcular_totales()
        cierre.estado = 'CERRADO'
        cierre.usuario_cierre = request.user
        cierre.fecha_cierre = timezone.now()
        cierre.save()

        # Saldo inicial para el día siguiente
        fecha_sig = fecha + timedelta(days=1)
        CierreDiario.objects.get_or_create(
            fecha=fecha_sig,
            defaults={'saldo_inicial': cierre.saldo_final, 'usuario_cierre': request.user}
        )

        if cierre.diferencia_efectivo and cierre.diferencia_efectivo != 0:
            if cierre.diferencia_efectivo > 0:
                messages.warning(request, f'Caja cerrada con sobrante de ${cierre.diferencia_efectivo:.2f}')
            else:
                messages.warning(request, f'Caja cerrada con faltante de ${abs(cierre.diferencia_efectivo):.2f}')
        else:
            messages.success(request, 'Caja cerrada correctamente. Sin diferencias.')

        return redirect('reportes:caja_diaria')

    except Exception as e:
        messages.error(request, f'Error al cerrar caja: {str(e)}')
        return redirect('reportes:caja_diaria')


@login_required
def reabrir_caja(request, fecha_str):
    if not request.user.is_superuser:
        messages.error(request, 'Solo administradores pueden reabrir cajas.')
        return redirect('reportes:caja_diaria')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        cierre = get_object_or_404(CierreDiario, fecha=fecha)
        if cierre.estado == 'ABIERTO':
            messages.error(request, 'Esta caja ya está abierta.')
            return redirect('reportes:caja_diaria')
        cierre.estado = 'ABIERTO'
        cierre.fecha_cierre = None
        cierre.efectivo_contado = None
        cierre.diferencia_efectivo = Decimal('0.00')
        cierre.save()
        messages.success(request, f'Caja del {fecha} reabierta.')
        return redirect('reportes:caja_diaria')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
        return redirect('reportes:caja_diaria')


# ══════════════════════════════════════════════════════════════════════
#  GASTOS (MÓDULO INDEPENDIENTE)
# ══════════════════════════════════════════════════════════════════════

@login_required
def lista_gastos(request):
    gastos = GastoDiario.objects.all().select_related('usuario', 'aprobado_por')

    # Filtros
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    categoria = request.GET.get('categoria')
    aprobado = request.GET.get('aprobado')
    busqueda = request.GET.get('q', '').strip()

    if fecha_desde:
        try:
            gastos = gastos.filter(fecha__gte=datetime.strptime(fecha_desde, '%Y-%m-%d').date())
        except ValueError:
            pass
    if fecha_hasta:
        try:
            gastos = gastos.filter(fecha__lte=datetime.strptime(fecha_hasta, '%Y-%m-%d').date())
        except ValueError:
            pass
    if categoria:
        gastos = gastos.filter(categoria=categoria)
    if aprobado == 'True':
        gastos = gastos.filter(aprobado=True)
    elif aprobado == 'False':
        gastos = gastos.filter(aprobado=False)
    if busqueda:
        gastos = gastos.filter(
            Q(concepto__icontains=busqueda) | Q(proveedor__icontains=busqueda)
        )

    gastos = gastos.order_by('-fecha', '-fecha_creacion')

    # Stats
    total_gastos = gastos.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    aprobados = gastos.filter(aprobado=True).aggregate(t=Sum('monto'))['t'] or Decimal('0')
    pendientes = gastos.filter(aprobado=False).aggregate(t=Sum('monto'))['t'] or Decimal('0')

    gastos_por_categoria = gastos.values('categoria').annotate(
        total=Sum('monto'), cantidad=Count('id')
    ).order_by('-total')

    paginator = Paginator(gastos, 25)
    gastos_paginados = paginator.get_page(request.GET.get('page'))

    context = {
        'active_page': 'reportes',
        'gastos': gastos_paginados,
        'total_gastos': total_gastos,
        'gastos_aprobados': aprobados,
        'gastos_pendientes': pendientes,
        'gastos_por_categoria': gastos_por_categoria,
        'categorias': GastoDiario.CATEGORIA_CHOICES,
        'filtros': {
            'fecha_desde': fecha_desde or '',
            'fecha_hasta': fecha_hasta or '',
            'categoria': categoria or '',
            'aprobado': aprobado or '',
            'q': busqueda,
        }
    }
    return render(request, 'reportes/lista_gastos.html', context)


@login_required
def crear_gasto(request):
    if request.method == 'POST':
        form = GastoDiarioForm(request.POST, request.FILES)
        if form.is_valid():
            gasto = form.save(commit=False)
            gasto.usuario = request.user
            if gasto.monto <= Decimal('100.00'):
                gasto.aprobado = True
                gasto.aprobado_por = request.user
                gasto.fecha_aprobacion = timezone.now()
            gasto.save()
            messages.success(request, 'Gasto registrado.')
            if 'save_and_new' in request.POST:
                return redirect('reportes:crear_gasto')
            return redirect('reportes:lista_gastos')
    else:
        form = GastoDiarioForm()

    return render(request, 'reportes/gasto_form.html', {
        'active_page': 'reportes',
        'form': form,
        'titulo': 'Registrar Gasto'
    })


@login_required
def editar_gasto(request, pk):
    gasto = get_object_or_404(GastoDiario, pk=pk)
    if gasto.usuario != request.user and not request.user.is_superuser:
        messages.error(request, 'Sin permisos para editar este gasto.')
        return redirect('reportes:lista_gastos')
    if gasto.aprobado and not request.user.is_superuser:
        messages.error(request, 'No se pueden editar gastos aprobados.')
        return redirect('reportes:lista_gastos')

    if request.method == 'POST':
        form = GastoDiarioForm(request.POST, request.FILES, instance=gasto)
        if form.is_valid():
            form.save()
            messages.success(request, 'Gasto actualizado.')
            return redirect('reportes:lista_gastos')
    else:
        form = GastoDiarioForm(instance=gasto)

    return render(request, 'reportes/gasto_form.html', {
        'active_page': 'reportes',
        'form': form,
        'gasto': gasto,
        'titulo': 'Editar Gasto'
    })


@login_required
@require_POST
def aprobar_gasto(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Solo administradores pueden aprobar gastos.')
        return redirect('reportes:lista_gastos')
    gasto = get_object_or_404(GastoDiario, pk=pk)
    if gasto.aprobado:
        messages.info(request, 'Este gasto ya estaba aprobado.')
        return redirect('reportes:lista_gastos')
    gasto.aprobado = True
    gasto.aprobado_por = request.user
    gasto.fecha_aprobacion = timezone.now()
    gasto.save()
    messages.success(request, f'Gasto "{gasto.concepto}" aprobado.')
    return redirect('reportes:lista_gastos')


@login_required
@require_POST
def rechazar_gasto(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Solo administradores pueden rechazar gastos.')
        return redirect('reportes:lista_gastos')
    gasto = get_object_or_404(GastoDiario, pk=pk)
    concepto = gasto.concepto
    gasto.delete()
    messages.warning(request, f'Gasto "{concepto}" eliminado.')
    return redirect('reportes:lista_gastos')


# ══════════════════════════════════════════════════════════════════════
#  ESTADÍSTICAS Y REPORTES MENSUALES (mantenidos del original)
# ══════════════════════════════════════════════════════════════════════

@login_required
def estadisticas_ventas(request):
    hoy = timezone.now().date()
    fecha_inicio, fecha_fin = _rango_periodo('mes', hoy)

    fecha_desde_str = request.GET.get('fecha_desde')
    fecha_hasta_str = request.GET.get('fecha_hasta')
    if fecha_desde_str and fecha_hasta_str:
        try:
            fecha_inicio = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    ventas = _ventas_pos(fecha_inicio, fecha_fin)

    stats = {
        'total_ventas': ventas.aggregate(t=Sum('total'))['t'] or Decimal('0'),
        'cantidad_ventas': ventas.count(),
        'promedio_venta': Decimal('0'),
        'venta_mayor': ventas.aggregate(m=Sum('total'))['m'] or Decimal('0'),
    }
    if stats['cantidad_ventas'] > 0:
        stats['promedio_venta'] = stats['total_ventas'] / stats['cantidad_ventas']

    ventas_por_metodo = ventas.values('tipo_pago').annotate(
        total=Sum('total'), cantidad=Count('id')
    ).order_by('-total')

    ventas_por_dia = ventas.extra(
        select={'dia': 'DATE(fecha_hora)'}
    ).values('dia').annotate(
        total=Sum('total'), cantidad=Count('id')
    ).order_by('dia')

    context = {
        'active_page': 'reportes',
        'stats': stats,
        'ventas_por_metodo': ventas_por_metodo,
        'ventas_por_dia': list(ventas_por_dia),
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
    }
    return render(request, 'reportes/estadisticas_ventas.html', context)


@login_required
def reportes_mensuales(request):
    año = int(request.GET.get('año', timezone.now().year))
    mes = int(request.GET.get('mes', timezone.now().month))

    resumen, _ = ResumenMensual.objects.get_or_create(año=año, mes=mes)
    if request.GET.get('recalcular'):
        resumen.calcular_resumen()

    primer_dia = date(año, mes, 1)
    ultimo_dia = date(año, mes, calendar.monthrange(año, mes)[1])
    cierres_mes = CierreDiario.objects.filter(
        fecha__range=[primer_dia, ultimo_dia], estado='CERRADO'
    ).order_by('fecha')

    datos_diarios = [{
        'fecha': c.fecha,
        'ventas': c.total_ingresos,
        'gastos': c.total_gastos_dia,
        'utilidad': c.total_ingresos - c.total_gastos_dia,
        'cantidad_ventas': c.cantidad_ventas,
    } for c in cierres_mes]

    meses_disponibles = ResumenMensual.objects.values_list(
        'año', 'mes'
    ).distinct().order_by('-año', '-mes')

    context = {
        'active_page': 'reportes',
        'resumen': resumen,
        'año': año,
        'mes': mes,
        'nombre_mes': calendar.month_name[mes],
        'datos_diarios': datos_diarios,
        'meses_disponibles': meses_disponibles,
    }
    return render(request, 'reportes/reportes_mensuales.html', context)


@login_required
def lista_movimientos(request):
    try:
        movimientos = MovimientoCaja.objects.all().select_related(
            'tipo_movimiento', 'usuario'
        ).order_by('-fecha', '-hora')

        fecha_desde = request.GET.get('fecha_desde')
        fecha_hasta = request.GET.get('fecha_hasta')
        if fecha_desde:
            movimientos = movimientos.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            movimientos = movimientos.filter(fecha__lte=fecha_hasta)

        total_ingresos = movimientos.filter(es_ingreso=True).aggregate(
            t=Sum('monto'))['t'] or Decimal('0')
        total_egresos = movimientos.filter(es_ingreso=False).aggregate(
            t=Sum('monto'))['t'] or Decimal('0')

        paginator = Paginator(movimientos, 50)
        movimientos_paginados = paginator.get_page(request.GET.get('page'))
    except Exception:
        movimientos_paginados = []
        total_ingresos = total_egresos = Decimal('0')

    return render(request, 'reportes/lista_movimientos.html', {
        'active_page': 'reportes',
        'movimientos': movimientos_paginados,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'balance': total_ingresos - total_egresos,
    })


# ══════════════════════════════════════════════════════════════════════
#  APIs JSON
# ══════════════════════════════════════════════════════════════════════

@login_required
def api_dashboard_data(request):
    hoy = timezone.now().date()
    ventas_7_dias = []
    for i in range(6, -1, -1):
        fecha = hoy - timedelta(days=i)
        total = Venta.objects.filter(
            fecha_hora__date=fecha, estado='COMPLETADA'
        ).aggregate(t=Sum('total'))['t'] or Decimal('0')
        ventas_7_dias.append({'fecha': fecha.strftime('%d/%m'), 'total': float(total)})

    inicio_mes, fin_mes = _rango_periodo('mes', hoy)
    productos_mes = DetalleVenta.objects.filter(
        venta__fecha_hora__date__range=[inicio_mes, fin_mes],
        venta__estado='COMPLETADA', es_servicio=False
    ).aggregate(t=Sum('subtotal'))['t'] or Decimal('0')

    servicios_mes = DetalleVenta.objects.filter(
        venta__fecha_hora__date__range=[inicio_mes, fin_mes],
        venta__estado='COMPLETADA', es_servicio=True
    ).aggregate(t=Sum('subtotal'))['t'] or Decimal('0')

    return JsonResponse({
        'ventas_7_dias': ventas_7_dias,
        'productos_vs_servicios': {
            'productos': float(productos_mes),
            'servicios': float(servicios_mes),
        }
    })


@login_required
def api_caja_status(request):
    hoy = timezone.now().date()
    try:
        cierre = CierreDiario.objects.get(fecha=hoy)
        return JsonResponse({
            'existe': True,
            'estado': cierre.estado,
            'total_ingresos': float(cierre.total_ingresos),
            'total_gastos': float(cierre.total_gastos_dia),
            'saldo_final': float(cierre.saldo_final),
            'puede_cerrar': cierre.estado == 'ABIERTO',
        })
    except CierreDiario.DoesNotExist:
        return JsonResponse({'existe': False, 'puede_cerrar': False})


@login_required
def comparativo_ventas(request):
    """Mantiene compatibilidad con URL existente"""
    return redirect('reportes:reporte_ventas_completo')


@login_required
def exportar_reporte(request):
    messages.info(request, 'Exportación en desarrollo.')
    return redirect('reportes:dashboard')
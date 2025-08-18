from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Sum, Avg, F, Max, Min
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from datetime import datetime, timedelta, date
import json
import calendar
from decimal import Decimal

from .models import (
    MovimientoCaja, GastoDiario, CierreDiario, TipoMovimiento, ResumenMensual
)
from .forms import (
    GastoDiarioForm, CierreDiarioForm, ReporteVentasForm, FiltroFechasForm,
    FiltroMovimientosForm, FiltroGastosForm, ComparativoVentasForm, ExportarReporteForm
)
from ventas.models import Venta, DetalleVenta

# Intentar importar modelos de taller de forma segura
try:
    from taller.models import OrdenTrabajo, ServicioOrden
    TALLER_DISPONIBLE = True
except ImportError:
    TALLER_DISPONIBLE = False


# ================== DASHBOARD PRINCIPAL ==================

@login_required
def dashboard_reportes(request):
    """Dashboard principal del módulo de reportes"""
    hoy = timezone.now().date()
    
    # Obtener o crear cierre de hoy
    cierre_hoy = CierreDiario.get_o_crear_hoy(request.user)
    
    # Estadísticas del día
    ventas_hoy = Venta.objects.filter(
        fecha_hora__date=hoy
    )
    
    # Filtrar por estado si existe el campo
    if hasattr(Venta, 'estado'):
        ventas_hoy = ventas_hoy.filter(estado='COMPLETADA')
    
    stats_hoy = {
        'total_ventas': ventas_hoy.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
        'cantidad_ventas': ventas_hoy.count(),
        'promedio_venta': Decimal('0.00'),
        'efectivo_dia': ventas_hoy.filter(tipo_pago='EFECTIVO').aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
        'tarjeta_dia': ventas_hoy.filter(tipo_pago='TARJETA').aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
    }
    
    if stats_hoy['cantidad_ventas'] > 0:
        stats_hoy['promedio_venta'] = stats_hoy['total_ventas'] / stats_hoy['cantidad_ventas']
    
    # Gastos del día
    gastos_hoy = GastoDiario.objects.filter(fecha=hoy)
    total_gastos_hoy = gastos_hoy.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    # Estadísticas de la semana
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    
    ventas_semana = Venta.objects.filter(
        fecha_hora__date__range=[inicio_semana, fin_semana]
    )
    
    if hasattr(Venta, 'estado'):
        ventas_semana = ventas_semana.filter(estado='COMPLETADA')
    
    stats_semana = {
        'total_ventas': ventas_semana.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
        'cantidad_ventas': ventas_semana.count(),
        'total_gastos': GastoDiario.objects.filter(
            fecha__range=[inicio_semana, fin_semana]
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00'),
    }
    
    # Estadísticas del mes
    inicio_mes = hoy.replace(day=1)
    ventas_mes = Venta.objects.filter(
        fecha_hora__date__gte=inicio_mes
    )
    
    if hasattr(Venta, 'estado'):
        ventas_mes = ventas_mes.filter(estado='COMPLETADA')
    
    stats_mes = {
        'total_ventas': ventas_mes.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
        'cantidad_ventas': ventas_mes.count(),
        'total_gastos': GastoDiario.objects.filter(
            fecha__gte=inicio_mes
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00'),
    }
    
    # Ventas por producto vs servicios (últimos 7 días)
    hace_7_dias = hoy - timedelta(days=7)
    
    # Filtros base para detalles
    filtros_detalle = {
        'venta__fecha_hora__date__gte': hace_7_dias,
    }
    
    if hasattr(Venta, 'estado'):
        filtros_detalle['venta__estado'] = 'COMPLETADA'
    
    detalles_productos = DetalleVenta.objects.filter(
        **filtros_detalle,
        es_servicio=False
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')
    
    detalles_servicios = DetalleVenta.objects.filter(
        **filtros_detalle,
        es_servicio=True
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')
    
    # Top 5 días con más ventas (último mes)
    ventas_mes_filtradas = Venta.objects.filter(
        fecha_hora__date__gte=inicio_mes
    )
    
    if hasattr(Venta, 'estado'):
        ventas_mes_filtradas = ventas_mes_filtradas.filter(estado='COMPLETADA')
    
    top_dias = ventas_mes_filtradas.extra(
        select={'dia': 'DATE(fecha_hora)'}
    ).values('dia').annotate(
        total_dia=Sum('total'),
        cantidad=Count('id')
    ).order_by('-total_dia')[:5]
    
    # Movimientos recientes de caja
    try:
        movimientos_recientes = MovimientoCaja.objects.filter(
            fecha=hoy
        ).order_by('-hora')[:10]
    except:
        movimientos_recientes = []
    
    # Gastos pendientes de aprobación
    gastos_pendientes = GastoDiario.objects.filter(
        aprobado=False,
        fecha__gte=hoy - timedelta(days=7)
    ).count()
    
    # Diferencias en caja (últimos 5 días)
    diferencias_caja = CierreDiario.objects.filter(
        fecha__gte=hoy - timedelta(days=5),
        estado='CERRADO',
        diferencia_efectivo__isnull=False
    ).exclude(diferencia_efectivo=0).order_by('-fecha')[:5]
    
    context = {
        'active_page': 'reportes',
        'cierre_hoy': cierre_hoy,
        'stats_hoy': stats_hoy,
        'total_gastos_hoy': total_gastos_hoy,
        'stats_semana': stats_semana,
        'stats_mes': stats_mes,
        'detalles_productos': detalles_productos,
        'detalles_servicios': detalles_servicios,
        'top_dias': top_dias,
        'movimientos_recientes': movimientos_recientes,
        'gastos_pendientes': gastos_pendientes,
        'diferencias_caja': diferencias_caja,
        'hoy': hoy,
    }
    
    return render(request, 'reportes/dashboard.html', context)


# ================== CAJA DIARIA ==================

@login_required
def caja_diaria(request):
    """Vista principal de caja diaria"""
    fecha_str = request.GET.get('fecha')
    
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha = timezone.now().date()
    else:
        fecha = timezone.now().date()
    
    # Obtener o crear cierre del día
    cierre, created = CierreDiario.objects.get_or_create(
        fecha=fecha,
        defaults={'usuario_cierre': request.user}
    )
    
    if created or cierre.estado == 'ABIERTO':
        cierre.calcular_totales()
        cierre.save()
    
    # Ventas del día detalladas
    ventas_dia = Venta.objects.filter(
        fecha_hora__date=fecha
    ).select_related('cliente', 'usuario').order_by('-fecha_hora')
    
    if hasattr(Venta, 'estado'):
        ventas_dia = ventas_dia.filter(estado='COMPLETADA')
    
    # Separar ventas por tipo
    ventas_productos = []
    ventas_servicios = []
    
    for venta in ventas_dia:
        detalles = venta.detalleventa_set.all()
        tiene_productos = detalles.filter(es_servicio=False).exists()
        tiene_servicios = detalles.filter(es_servicio=True).exists()
        
        if tiene_productos:
            ventas_productos.append(venta)
        if tiene_servicios:
            ventas_servicios.append(venta)
    
    # Gastos del día
    gastos_dia = GastoDiario.objects.filter(fecha=fecha).order_by('-fecha_creacion')
    
    # Movimientos del día
    try:
        movimientos_dia = MovimientoCaja.objects.filter(fecha=fecha).order_by('-hora')
    except:
        movimientos_dia = []
    
    # Distribución por método de pago
    metodos_pago = ventas_dia.values('tipo_pago').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('-total')
    
    # Estadísticas comparativas
    fecha_anterior = fecha - timedelta(days=1)
    try:
        cierre_anterior = CierreDiario.objects.get(fecha=fecha_anterior, estado='CERRADO')
        comparativo = {
            'ventas_anterior': cierre_anterior.total_ingresos,
            'gastos_anterior': cierre_anterior.total_gastos,
            'diferencia_ventas': cierre.total_ingresos - cierre_anterior.total_ingresos,
            'diferencia_gastos': cierre.total_gastos - cierre_anterior.total_gastos,
        }
    except CierreDiario.DoesNotExist:
        comparativo = None
    
    context = {
        'active_page': 'reportes',
        'cierre': cierre,
        'fecha': fecha,
        'ventas_dia': ventas_dia,
        'ventas_productos': ventas_productos,
        'ventas_servicios': ventas_servicios,
        'gastos_dia': gastos_dia,
        'movimientos_dia': movimientos_dia,
        'metodos_pago': metodos_pago,
        'comparativo': comparativo,
        'puede_cerrar': fecha <= timezone.now().date() and cierre.estado == 'ABIERTO',
        'hoy': timezone.now().date(),
    }
    
    return render(request, 'reportes/caja_diaria.html', context)


@login_required
@require_POST
def cerrar_caja(request):
    """Cerrar caja del día"""
    fecha_str = request.POST.get('fecha')
    efectivo_contado = request.POST.get('efectivo_contado')
    observaciones = request.POST.get('observaciones', '')
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        
        if fecha > timezone.now().date():
            messages.error(request, 'No se puede cerrar caja de fechas futuras')
            return redirect('reportes:caja_diaria')
        
        cierre = get_object_or_404(CierreDiario, fecha=fecha)
        
        if cierre.estado != 'ABIERTO':
            messages.error(request, 'Esta caja ya está cerrada')
            return redirect('reportes:caja_diaria')
        
        # Convertir efectivo contado
        efectivo_decimal = None
        if efectivo_contado:
            try:
                efectivo_decimal = Decimal(str(efectivo_contado))
            except (ValueError, TypeError):
                messages.error(request, 'Monto de efectivo inválido')
                return redirect('reportes:caja_diaria')
        
        # Cerrar caja
        cierre.efectivo_contado = efectivo_decimal
        cierre.observaciones = observaciones
        cierre.calcular_totales()
        
        cierre.estado = 'CERRADO'
        cierre.usuario_cierre = request.user
        cierre.fecha_cierre = timezone.now()
        cierre.save()
        
        # Crear saldo inicial para el día siguiente
        fecha_siguiente = fecha + timedelta(days=1)
        CierreDiario.objects.get_or_create(
            fecha=fecha_siguiente,
            defaults={
                'saldo_inicial': cierre.saldo_final,
                'usuario_cierre': request.user,
            }
        )
        
        # Mensaje según si hay diferencias
        if cierre.diferencia_efectivo != 0:
            if cierre.diferencia_efectivo > 0:
                messages.warning(
                    request, 
                    f'Caja cerrada. Sobrante de ${cierre.diferencia_efectivo}'
                )
            else:
                messages.warning(
                    request, 
                    f'Caja cerrada. Faltante de ${abs(cierre.diferencia_efectivo)}'
                )
        else:
            messages.success(request, 'Caja cerrada correctamente. Sin diferencias.')
        
        return redirect('reportes:caja_diaria')
        
    except Exception as e:
        messages.error(request, f'Error al cerrar caja: {str(e)}')
        return redirect('reportes:caja_diaria')


@login_required
def reabrir_caja(request, fecha_str):
    """Reabrir caja cerrada (solo administradores)"""
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        cierre = get_object_or_404(CierreDiario, fecha=fecha)
        
        if not request.user.is_superuser:
            messages.error(request, 'Solo administradores pueden reabrir cajas')
            return redirect('reportes:caja_diaria')
        
        if cierre.estado == 'ABIERTO':
            messages.error(request, 'Esta caja ya está abierta')
            return redirect('reportes:caja_diaria')
        
        cierre.estado = 'ABIERTO'
        cierre.fecha_cierre = None
        cierre.efectivo_contado = None
        cierre.diferencia_efectivo = Decimal('0.00')
        cierre.save()
        
        messages.success(request, f'Caja del {fecha} reabierta correctamente')
        return redirect('reportes:caja_diaria')
        
    except Exception as e:
        messages.error(request, f'Error al reabrir caja: {str(e)}')
        return redirect('reportes:caja_diaria')


# ================== GASTOS ==================

@login_required
def lista_gastos(request):
    """Lista de gastos con filtros"""
    form = FiltroGastosForm(request.GET or None)
    gastos = GastoDiario.objects.all().select_related('usuario', 'aprobado_por')
    
    if form and form.is_valid():
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        categoria = form.cleaned_data.get('categoria')
        aprobado = form.cleaned_data.get('aprobado')
        proveedor = form.cleaned_data.get('proveedor')
        
        if fecha_desde:
            gastos = gastos.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            gastos = gastos.filter(fecha__lte=fecha_hasta)
        if categoria:
            gastos = gastos.filter(categoria=categoria)
        if aprobado:
            gastos = gastos.filter(aprobado=aprobado == 'True')
        if proveedor:
            gastos = gastos.filter(proveedor__icontains=proveedor)
    
    gastos = gastos.order_by('-fecha', '-fecha_creacion')
    
    # Paginación
    paginator = Paginator(gastos, 25)
    page_number = request.GET.get('page')
    gastos_paginados = paginator.get_page(page_number)
    
    # Estadísticas del período
    total_gastos = gastos.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    gastos_aprobados = gastos.filter(aprobado=True).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    gastos_pendientes = gastos.filter(aprobado=False).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    # Gastos por categoría
    gastos_por_categoria = gastos.values('categoria').annotate(
        total=Sum('monto'),
        cantidad=Count('id')
    ).order_by('-total')
    
    context = {
        'active_page': 'reportes',
        'form': form,
        'gastos': gastos_paginados,
        'total_gastos': total_gastos,
        'gastos_aprobados': gastos_aprobados,
        'gastos_pendientes': gastos_pendientes,
        'gastos_por_categoria': gastos_por_categoria,
    }
    
    return render(request, 'reportes/lista_gastos.html', context)


@login_required
def crear_gasto(request):
    """Crear nuevo gasto"""
    if request.method == 'POST':
        form = GastoDiarioForm(request.POST, request.FILES)
        if form.is_valid():
            gasto = form.save(commit=False)
            gasto.usuario = request.user
            
            # Auto-aprobar gastos pequeños si está configurado
            if gasto.monto <= Decimal('100.00'):
                gasto.aprobado = True
                gasto.aprobado_por = request.user
                gasto.fecha_aprobacion = timezone.now()
            
            gasto.save()
            
            messages.success(request, 'Gasto registrado correctamente')
            
            # Redirigir según el botón presionado
            if 'save_and_new' in request.POST:
                return redirect('reportes:crear_gasto')
            else:
                return redirect('reportes:lista_gastos')
    else:
        form = GastoDiarioForm()
    
    context = {
        'active_page': 'reportes',
        'form': form,
        'titulo': 'Registrar Nuevo Gasto'
    }
    
    return render(request, 'reportes/gasto_form.html', context)


@login_required
def editar_gasto(request, pk):
    """Editar gasto existente"""
    gasto = get_object_or_404(GastoDiario, pk=pk)
    
    # Solo el creador o admin puede editar
    if gasto.usuario != request.user and not request.user.is_superuser:
        messages.error(request, 'No tiene permisos para editar este gasto')
        return redirect('reportes:lista_gastos')
    
    # No se pueden editar gastos aprobados
    if gasto.aprobado and not request.user.is_superuser:
        messages.error(request, 'No se pueden editar gastos ya aprobados')
        return redirect('reportes:lista_gastos')
    
    if request.method == 'POST':
        form = GastoDiarioForm(request.POST, request.FILES, instance=gasto)
        if form.is_valid():
            form.save()
            messages.success(request, 'Gasto actualizado correctamente')
            return redirect('reportes:lista_gastos')
    else:
        form = GastoDiarioForm(instance=gasto)
    
    context = {
        'active_page': 'reportes',
        'form': form,
        'gasto': gasto,
        'titulo': 'Editar Gasto'
    }
    
    return render(request, 'reportes/gasto_form.html', context)


@login_required
@require_POST
def aprobar_gasto(request, pk):
    """Aprobar un gasto"""
    gasto = get_object_or_404(GastoDiario, pk=pk)
    
    if not request.user.is_superuser:
        messages.error(request, 'Solo administradores pueden aprobar gastos')
        return redirect('reportes:lista_gastos')
    
    if gasto.aprobado:
        messages.error(request, 'Este gasto ya está aprobado')
        return redirect('reportes:lista_gastos')
    
    gasto.aprobado = True
    gasto.aprobado_por = request.user
    gasto.fecha_aprobacion = timezone.now()
    gasto.save()
    
    messages.success(request, f'Gasto "{gasto.concepto}" aprobado correctamente')
    return redirect('reportes:lista_gastos')


@login_required
@require_POST
def rechazar_gasto(request, pk):
    """Rechazar un gasto"""
    gasto = get_object_or_404(GastoDiario, pk=pk)
    
    if not request.user.is_superuser:
        messages.error(request, 'Solo administradores pueden rechazar gastos')
        return redirect('reportes:lista_gastos')
    
    concepto = gasto.concepto
    gasto.delete()
    
    messages.warning(request, f'Gasto "{concepto}" eliminado')
    return redirect('reportes:lista_gastos')


# ================== ESTADÍSTICAS ==================

@login_required
def estadisticas_ventas(request):
    """Vista de estadísticas de ventas por períodos"""
    form = ReporteVentasForm(request.GET or None)
    
    # Valores por defecto
    hoy = timezone.now().date()
    fecha_desde = hoy.replace(day=1)  # Primer día del mes
    fecha_hasta = hoy
    agrupacion = 'dia'
    tipo_reporte = 'general'
    
    if form and form.is_valid():
        fecha_desde = form.cleaned_data.get('fecha_desde') or fecha_desde
        fecha_hasta = form.cleaned_data.get('fecha_hasta') or fecha_hasta
        agrupacion = form.cleaned_data.get('agrupacion') or agrupacion
        tipo_reporte = form.cleaned_data.get('tipo_reporte') or tipo_reporte
    
    # Obtener ventas del período
    ventas = Venta.objects.filter(
        fecha_hora__date__range=[fecha_desde, fecha_hasta]
    )
    
    if hasattr(Venta, 'estado'):
        ventas = ventas.filter(estado='COMPLETADA')
    
    # Estadísticas generales
    stats_generales = {
        'total_ventas': ventas.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
        'total_subtotal': ventas.aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00'),
        'total_iva': ventas.aggregate(total=Sum('iva'))['total'] or Decimal('0.00'),
        'cantidad_ventas': ventas.count(),
        'promedio_venta': Decimal('0.00'),
        'venta_mayor': ventas.aggregate(mayor=Max('total'))['mayor'] or Decimal('0.00'),
        'venta_menor': ventas.aggregate(menor=Min('total'))['menor'] or Decimal('0.00'),
    }
    
    if stats_generales['cantidad_ventas'] > 0:
        stats_generales['promedio_venta'] = stats_generales['total_ventas'] / stats_generales['cantidad_ventas']
    
    # Ventas por método de pago
    ventas_por_metodo = ventas.values('tipo_pago').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('-total')
    
    # Ventas por producto vs servicios
    filtros_detalle = {
        'venta__fecha_hora__date__range': [fecha_desde, fecha_hasta]
    }
    
    if hasattr(Venta, 'estado'):
        filtros_detalle['venta__estado'] = 'COMPLETADA'
    
    detalles = DetalleVenta.objects.filter(**filtros_detalle)
    
    productos_vs_servicios = {
        'productos': detalles.filter(es_servicio=False).aggregate(
            total=Sum('subtotal'),
            cantidad=Count('id')
        ),
        'servicios': detalles.filter(es_servicio=True).aggregate(
            total=Sum('subtotal'),
            cantidad=Count('id')
        )
    }
    
    # Datos para gráficos según agrupación
    if agrupacion == 'dia':
        ventas_agrupadas = ventas.extra(
            select={'periodo': 'DATE(fecha_hora)'}
        ).values('periodo').annotate(
            total=Sum('total'),
            cantidad=Count('id')
        ).order_by('periodo')
    elif agrupacion == 'semana':
        ventas_agrupadas = ventas.extra(
            select={'periodo': 'WEEK(fecha_hora)'}
        ).values('periodo').annotate(
            total=Sum('total'),
            cantidad=Count('id')
        ).order_by('periodo')
    elif agrupacion == 'mes':
        ventas_agrupadas = ventas.extra(
            select={'periodo': 'MONTH(fecha_hora)'}
        ).values('periodo').annotate(
            total=Sum('total'),
            cantidad=Count('id')
        ).order_by('periodo')
    else:
        ventas_agrupadas = []
    
    # Top productos más vendidos
    top_productos = detalles.filter(
        producto__isnull=False
    ).values(
        'producto__nombre'
    ).annotate(
        cantidad_vendida=Sum('cantidad'),
        total_vendido=Sum('subtotal')
    ).order_by('-cantidad_vendida')[:10]
    
    # Top servicios más solicitados
    top_servicios = detalles.filter(
        tipo_servicio__isnull=False
    ).values(
        'tipo_servicio__nombre'
    ).annotate(
        cantidad_vendida=Sum('cantidad'),
        total_vendido=Sum('subtotal')
    ).order_by('-cantidad_vendida')[:10]
    
    # Comparativo con período anterior
    dias_periodo = (fecha_hasta - fecha_desde).days + 1
    fecha_desde_anterior = fecha_desde - timedelta(days=dias_periodo)
    fecha_hasta_anterior = fecha_desde - timedelta(days=1)
    
    ventas_anterior = Venta.objects.filter(
        fecha_hora__date__range=[fecha_desde_anterior, fecha_hasta_anterior]
    )
    
    if hasattr(Venta, 'estado'):
        ventas_anterior = ventas_anterior.filter(estado='COMPLETADA')
    
    comparativo = {
        'total_anterior': ventas_anterior.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
        'cantidad_anterior': ventas_anterior.count(),
        'diferencia_total': Decimal('0.00'),
        'diferencia_cantidad': 0,
        'porcentaje_crecimiento': Decimal('0.00'),
    }
    
    comparativo['diferencia_total'] = stats_generales['total_ventas'] - comparativo['total_anterior']
    comparativo['diferencia_cantidad'] = stats_generales['cantidad_ventas'] - comparativo['cantidad_anterior']
    
    if comparativo['total_anterior'] > 0:
        comparativo['porcentaje_crecimiento'] = (
            comparativo['diferencia_total'] / comparativo['total_anterior']
        ) * 100
    
    context = {
        'active_page': 'reportes',
        'form': form,
        'stats_generales': stats_generales,
        'ventas_por_metodo': ventas_por_metodo,
        'productos_vs_servicios': productos_vs_servicios,
        'ventas_agrupadas': ventas_agrupadas,
        'top_productos': top_productos,
        'top_servicios': top_servicios,
        'comparativo': comparativo,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'agrupacion': agrupacion,
        'tipo_reporte': tipo_reporte,
    }
    
    return render(request, 'reportes/estadisticas_ventas.html', context)


@login_required
def comparativo_ventas(request):
    """Vista para comparar ventas entre períodos"""
    form = ComparativoVentasForm(request.GET or None)
    datos_comparativo = None
    
    if form and form.is_valid():
        periodo_actual = form.cleaned_data['periodo_actual']
        fecha_actual = form.cleaned_data['fecha_actual']
        comparar_con = form.cleaned_data['comparar_con']
        fecha_comparacion = form.cleaned_data.get('fecha_comparacion')
        
        # Calcular fechas del período actual
        if periodo_actual == 'dia':
            inicio_actual = fecha_actual
            fin_actual = fecha_actual
        elif periodo_actual == 'semana':
            inicio_actual = fecha_actual - timedelta(days=fecha_actual.weekday())
            fin_actual = inicio_actual + timedelta(days=6)
        elif periodo_actual == 'mes':
            inicio_actual = fecha_actual.replace(day=1)
            fin_actual = date(fecha_actual.year, fecha_actual.month, 
                             calendar.monthrange(fecha_actual.year, fecha_actual.month)[1])
        elif periodo_actual == 'trimestre':
            mes_inicio = ((fecha_actual.month - 1) // 3) * 3 + 1
            inicio_actual = fecha_actual.replace(month=mes_inicio, day=1)
            mes_fin = mes_inicio + 2
            fin_actual = date(fecha_actual.year, mes_fin, 
                             calendar.monthrange(fecha_actual.year, mes_fin)[1])
        elif periodo_actual == 'año':
            inicio_actual = fecha_actual.replace(month=1, day=1)
            fin_actual = fecha_actual.replace(month=12, day=31)
        else:
            inicio_actual = fecha_actual
            fin_actual = fecha_actual
        
        # Calcular fechas del período de comparación
        if comparar_con == 'anterior':
            dias_periodo = (fin_actual - inicio_actual).days + 1
            fin_comparacion = inicio_actual - timedelta(days=1)
            inicio_comparacion = fin_comparacion - timedelta(days=dias_periodo - 1)
        elif comparar_con == 'mismo_año_anterior':
            inicio_comparacion = inicio_actual.replace(year=inicio_actual.year - 1)
            fin_comparacion = fin_actual.replace(year=fin_actual.year - 1)
        elif comparar_con == 'personalizado' and fecha_comparacion:
            if periodo_actual == 'dia':
                inicio_comparacion = fecha_comparacion
                fin_comparacion = fecha_comparacion
            else:
                # Para otros períodos, usar la misma lógica que el período actual
                inicio_comparacion = fecha_comparacion
                fin_comparacion = fecha_comparacion
        else:
            inicio_comparacion = inicio_actual
            fin_comparacion = fin_actual
        
        # Obtener datos del período actual
        ventas_actual = Venta.objects.filter(
            fecha_hora__date__range=[inicio_actual, fin_actual]
        )
        
        if hasattr(Venta, 'estado'):
            ventas_actual = ventas_actual.filter(estado='COMPLETADA')
        
        # Obtener datos del período de comparación
        ventas_comparacion = Venta.objects.filter(
            fecha_hora__date__range=[inicio_comparacion, fin_comparacion]
        )
        
        if hasattr(Venta, 'estado'):
            ventas_comparacion = ventas_comparacion.filter(estado='COMPLETADA')
        
        # Calcular estadísticas
        datos_comparativo = {
            'periodo_actual': {
                'inicio': inicio_actual,
                'fin': fin_actual,
                'total': ventas_actual.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
                'cantidad': ventas_actual.count(),
                'promedio': Decimal('0.00'),
            },
            'periodo_comparacion': {
                'inicio': inicio_comparacion,
                'fin': fin_comparacion,
                'total': ventas_comparacion.aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
                'cantidad': ventas_comparacion.count(),
                'promedio': Decimal('0.00'),
            },
            'diferencias': {},
        }
        
        # Calcular promedios
        if datos_comparativo['periodo_actual']['cantidad'] > 0:
            datos_comparativo['periodo_actual']['promedio'] = (
                datos_comparativo['periodo_actual']['total'] / 
                datos_comparativo['periodo_actual']['cantidad']
            )
        
        if datos_comparativo['periodo_comparacion']['cantidad'] > 0:
            datos_comparativo['periodo_comparacion']['promedio'] = (
                datos_comparativo['periodo_comparacion']['total'] / 
                datos_comparativo['periodo_comparacion']['cantidad']
            )
        
        # Calcular diferencias
        datos_comparativo['diferencias'] = {
            'total': datos_comparativo['periodo_actual']['total'] - datos_comparativo['periodo_comparacion']['total'],
            'cantidad': datos_comparativo['periodo_actual']['cantidad'] - datos_comparativo['periodo_comparacion']['cantidad'],
            'promedio': datos_comparativo['periodo_actual']['promedio'] - datos_comparativo['periodo_comparacion']['promedio'],
        }
        
        # Calcular porcentajes de crecimiento
        if datos_comparativo['periodo_comparacion']['total'] > 0:
            datos_comparativo['diferencias']['porcentaje_total'] = (
                datos_comparativo['diferencias']['total'] / 
                datos_comparativo['periodo_comparacion']['total']
            ) * 100
        else:
            datos_comparativo['diferencias']['porcentaje_total'] = Decimal('0.00')
    
    context = {
        'active_page': 'reportes',
        'form': form,
        'datos_comparativo': datos_comparativo,
    }
    
    return render(request, 'reportes/comparativo_ventas.html', context)


# ================== MOVIMIENTOS DE CAJA ==================

@login_required
def lista_movimientos(request):
    """Lista de movimientos de caja"""
    try:
        form = FiltroMovimientosForm(request.GET or None)
        movimientos = MovimientoCaja.objects.all().select_related('tipo_movimiento', 'usuario')
        
        if form and form.is_valid():
            fecha_desde = form.cleaned_data.get('fecha_desde')
            fecha_hasta = form.cleaned_data.get('fecha_hasta')
            es_ingreso = form.cleaned_data.get('es_ingreso')
            busqueda = form.cleaned_data.get('busqueda')
            
            if fecha_desde:
                movimientos = movimientos.filter(fecha__gte=fecha_desde)
            if fecha_hasta:
                movimientos = movimientos.filter(fecha__lte=fecha_hasta)
            if es_ingreso:
                movimientos = movimientos.filter(es_ingreso=es_ingreso == 'True')
            if busqueda:
                movimientos = movimientos.filter(
                    Q(concepto__icontains=busqueda) |
                    Q(descripcion__icontains=busqueda)
                )
        
        movimientos = movimientos.order_by('-fecha', '-hora')
        
        # Paginación
        paginator = Paginator(movimientos, 50)
        page_number = request.GET.get('page')
        movimientos_paginados = paginator.get_page(page_number)
        
        # Estadísticas del período
        total_ingresos = movimientos.filter(es_ingreso=True).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        total_egresos = movimientos.filter(es_ingreso=False).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        balance = total_ingresos - total_egresos
        
    except Exception as e:
        # Si el modelo MovimientoCaja no existe, mostrar vista vacía
        form = None
        movimientos_paginados = []
        total_ingresos = Decimal('0.00')
        total_egresos = Decimal('0.00')
        balance = Decimal('0.00')
        messages.warning(request, 'El módulo de movimientos no está disponible aún.')
    
    context = {
        'active_page': 'reportes',
        'form': form,
        'movimientos': movimientos_paginados,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'balance': balance,
    }
    
    return render(request, 'reportes/lista_movimientos.html', context)


# ================== REPORTES MENSUALES ==================

@login_required
def reportes_mensuales(request):
    """Vista de reportes mensuales"""
    año = int(request.GET.get('año', timezone.now().year))
    mes = int(request.GET.get('mes', timezone.now().month))
    
    # Obtener o crear resumen mensual
    resumen, created = ResumenMensual.objects.get_or_create(
        año=año,
        mes=mes
    )
    
    if created or request.GET.get('recalcular'):
        resumen.calcular_resumen()
    
    # Obtener cierres del mes
    primer_dia = date(año, mes, 1)
    ultimo_dia = date(año, mes, calendar.monthrange(año, mes)[1])
    
    cierres_mes = CierreDiario.objects.filter(
        fecha__range=[primer_dia, ultimo_dia],
        estado='CERRADO'
    ).order_by('fecha')
    
    # Estadísticas por día
    datos_diarios = []
    for cierre in cierres_mes:
        datos_diarios.append({
            'fecha': cierre.fecha,
            'ventas': cierre.total_ingresos,
            'gastos': cierre.total_gastos,
            'utilidad': cierre.total_ingresos - cierre.total_gastos,
            'cantidad_ventas': cierre.cantidad_ventas,
        })
    
    # Comparativo con mes anterior
    if mes == 1:
        mes_anterior = 12
        año_anterior = año - 1
    else:
        mes_anterior = mes - 1
        año_anterior = año
    
    try:
        resumen_anterior = ResumenMensual.objects.get(año=año_anterior, mes=mes_anterior)
        comparativo_anterior = {
            'existe': True,
            'ventas': resumen_anterior.total_ventas,
            'gastos': resumen_anterior.total_gastos,
            'utilidad': resumen_anterior.utilidad_bruta,
            'diferencia_ventas': resumen.total_ventas - resumen_anterior.total_ventas,
            'diferencia_gastos': resumen.total_gastos - resumen_anterior.total_gastos,
            'diferencia_utilidad': resumen.utilidad_bruta - resumen_anterior.utilidad_bruta,
        }
        
        # Porcentajes de crecimiento
        if resumen_anterior.total_ventas > 0:
            comparativo_anterior['crecimiento_ventas'] = (
                comparativo_anterior['diferencia_ventas'] / resumen_anterior.total_ventas
            ) * 100
        else:
            comparativo_anterior['crecimiento_ventas'] = Decimal('0.00')
            
    except ResumenMensual.DoesNotExist:
        comparativo_anterior = {'existe': False}
    
    # Lista de meses para navegación
    meses_disponibles = ResumenMensual.objects.values_list('año', 'mes').distinct().order_by('-año', '-mes')
    
    context = {
        'active_page': 'reportes',
        'resumen': resumen,
        'año': año,
        'mes': mes,
        'nombre_mes': calendar.month_name[mes],
        'datos_diarios': datos_diarios,
        'comparativo_anterior': comparativo_anterior,
        'meses_disponibles': meses_disponibles,
    }
    
    return render(request, 'reportes/reportes_mensuales.html', context)


# ================== API ENDPOINTS ==================

@login_required
def api_dashboard_data(request):
    """API para datos del dashboard"""
    hoy = timezone.now().date()
    
    # Ventas de los últimos 7 días
    ventas_7_dias = []
    for i in range(7):
        fecha = hoy - timedelta(days=i)
        ventas_fecha = Venta.objects.filter(
            fecha_hora__date=fecha
        )
        
        if hasattr(Venta, 'estado'):
            ventas_fecha = ventas_fecha.filter(estado='COMPLETADA')
            
        total = ventas_fecha.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        ventas_7_dias.append({
            'fecha': fecha.strftime('%d/%m'),
            'total': float(total)
        })
    
    ventas_7_dias.reverse()
    
    # Distribución productos vs servicios (último mes)
    inicio_mes = hoy.replace(day=1)
    
    filtros_detalle = {
        'venta__fecha_hora__date__gte': inicio_mes,
    }
    
    if hasattr(Venta, 'estado'):
        filtros_detalle['venta__estado'] = 'COMPLETADA'
    
    productos_mes = DetalleVenta.objects.filter(
        **filtros_detalle,
        es_servicio=False
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')
    
    servicios_mes = DetalleVenta.objects.filter(
        **filtros_detalle,
        es_servicio=True
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')
    
    data = {
        'ventas_7_dias': ventas_7_dias,
        'productos_vs_servicios': {
            'productos': float(productos_mes),
            'servicios': float(servicios_mes)
        }
    }
    
    return JsonResponse(data)


@login_required
def api_caja_status(request):
    """API para verificar estado de caja"""
    hoy = timezone.now().date()
    
    try:
        cierre = CierreDiario.objects.get(fecha=hoy)
        data = {
            'existe': True,
            'estado': cierre.estado,
            'total_ventas': float(cierre.total_ingresos),
            'total_gastos': float(cierre.total_gastos),
            'saldo_final': float(cierre.saldo_final),
            'puede_cerrar': cierre.estado == 'ABIERTO',
        }
    except CierreDiario.DoesNotExist:
        data = {
            'existe': False,
            'puede_cerrar': False,
        }
    
    return JsonResponse(data)


# ================== EXPORTACIONES ==================

@login_required
def exportar_reporte(request):
    """Exportar reportes en diferentes formatos"""
    if request.method == 'POST':
        form = ExportarReporteForm(request.POST)
        
        if form.is_valid():
            formato = form.cleaned_data['formato']
            
            if formato == 'pdf':
                response = HttpResponse(content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="reporte.pdf"'
                # Aquí iría la lógica para generar PDF
                return response
            
            elif formato == 'excel':
                response = HttpResponse(
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = 'attachment; filename="reporte.xlsx"'
                # Aquí iría la lógica para generar Excel
                return response
            
            elif formato == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="reporte.csv"'
                # Aquí iría la lógica para generar CSV
                return response
    
    messages.error(request, 'Error al generar el reporte')
    return redirect('reportes:dashboard')
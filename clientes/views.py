from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models, transaction
from django.db.models.functions import TruncDate, TruncMonth, TruncYear  # ✅ Correcto
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from decimal import Decimal
import json
import requests
from datetime import datetime, date

from .models import (
    Cliente, Moto, MovimientoPuntos, ConfiguracionPuntos, 
    CanjeoPuntos, HistorialCliente
)
from .forms import (
    ClienteForm, MotoForm, ConfiguracionPuntosForm, 
    CanjeoPuntosForm, HistorialClienteForm
)
from .services.sri_service import SRIService

# ========== VISTAS PRINCIPALES ==========

@login_required
def lista_clientes(request):
    """Lista todos los clientes con filtros y búsqueda"""
    search = request.GET.get('search', '').strip()
    activo = request.GET.get('activo', '')
    tipo_id = request.GET.get('tipo_identificacion', '')
    
    clientes = Cliente.objects.exclude(identificacion='9999999999')
    
    # Aplicar filtros
    if search:
        clientes = clientes.filter(
            Q(nombres__icontains=search) |
            Q(apellidos__icontains=search) |
            Q(identificacion__icontains=search) |
            Q(telefono__icontains=search) |
            Q(email__icontains=search)
        )
    
    if activo != '':
        clientes = clientes.filter(activo=bool(int(activo)))
    
    if tipo_id:
        clientes = clientes.filter(tipo_identificacion=tipo_id)
    
    # Agregar estadísticas
    clientes = clientes.annotate(
        total_compras=Count('venta', filter=Q(venta__estado='COMPLETADA')),
        valor_total_compras=Sum('venta__total', filter=Q(venta__estado='COMPLETADA')),
        total_motos=Count('motos')
    )
    
    clientes = clientes.order_by('-fecha_registro')
    
    # Paginación
    paginator = Paginator(clientes, 25)
    page_number = request.GET.get('page')
    clientes_paginados = paginator.get_page(page_number)
    
    # Estadísticas generales
    stats = {
        'total_clientes': Cliente.objects.filter(activo=True).exclude(identificacion='9999999999').count(),
        'clientes_con_puntos': Cliente.objects.filter(puntos_disponibles__gt=0).count(),
        'total_puntos_sistema': Cliente.objects.aggregate(total=Sum('puntos_disponibles'))['total'] or 0,
        'nuevos_este_mes': Cliente.objects.filter(
            fecha_registro__month=timezone.now().month,
            fecha_registro__year=timezone.now().year
        ).exclude(identificacion='9999999999').count()
    }
    
    context = {
        'active_page': 'clientes',
        'clientes': clientes_paginados,
        'filtros': {
            'search': search,
            'activo': activo,
            'tipo_identificacion': tipo_id
        },
        'tipos_identificacion': Cliente.TIPO_IDENTIFICACION_CHOICES,
        'stats': stats
    }
    
    return render(request, 'clientes/lista_clientes.html', context)

@login_required
def detalle_cliente(request, cliente_id):
    """Muestra el detalle completo de un cliente"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    # Estadísticas del cliente
    stats = {
        'total_compras': 0,
        'valor_total_compras': Decimal('0.00'),
        'total_ordenes': 0,
        'ordenes_completadas': 0,
        'ultima_compra': None,
        'ultima_orden': None
    }
    
    # Intentar obtener estadísticas de ventas si el módulo existe
    try:
        # Verificar si existe relación con ventas
        if hasattr(cliente, 'venta_set'):
            stats['total_compras'] = cliente.venta_set.filter(estado='COMPLETADA').count()
            stats['valor_total_compras'] = cliente.venta_set.filter(estado='COMPLETADA').aggregate(
                total=Sum('total'))['total'] or Decimal('0.00')
            stats['ultima_compra'] = cliente.venta_set.filter(estado='COMPLETADA').order_by('-fecha_hora').first()
    except Exception as e:
        print(f"Error al obtener estadísticas de ventas: {e}")
    
    # Intentar obtener estadísticas de órdenes de trabajo si el módulo existe
    try:
        # Verificar si existe relación con órdenes de trabajo
        if hasattr(cliente, 'ordentrabajo_set'):
            stats['total_ordenes'] = cliente.ordentrabajo_set.count()
            stats['ordenes_completadas'] = cliente.ordentrabajo_set.filter(estado='COMPLETADO').count()
            stats['ultima_orden'] = cliente.ordentrabajo_set.order_by('-fecha_ingreso').first()
        elif hasattr(cliente, 'ordenes_trabajo'):
            # Si el related_name es diferente
            stats['total_ordenes'] = cliente.ordenes_trabajo.count()
            stats['ordenes_completadas'] = cliente.ordenes_trabajo.filter(estado='COMPLETADO').count()
            stats['ultima_orden'] = cliente.ordenes_trabajo.order_by('-fecha_ingreso').first()
    except Exception as e:
        print(f"Error al obtener estadísticas de órdenes: {e}")
    
    # Motos del cliente
    motos = []
    try:
        if hasattr(cliente, 'motos'):
            motos = cliente.motos.all().order_by('-fecha_registro')
    except Exception as e:
        print(f"Error al obtener motos: {e}")
    
    # Historial de puntos (últimos 10)
    movimientos_puntos = []
    try:
        if hasattr(cliente, 'movimientos_puntos'):
            movimientos_puntos = cliente.movimientos_puntos.all()[:10]
    except Exception as e:
        print(f"Error al obtener movimientos de puntos: {e}")
    
    # Canjes activos
    canjes_activos = []
    try:
        if hasattr(cliente, 'canjes'):
            canjes_activos = cliente.canjes.filter(utilizado=False)
    except Exception as e:
        print(f"Error al obtener canjes: {e}")
    
    # Historial de interacciones (últimos 10)
    historial = []
    try:
        if hasattr(cliente, 'historial'):
            historial = cliente.historial.all()[:10]
    except Exception as e:
        print(f"Error al obtener historial: {e}")
    
    # Ventas recientes (últimas 5)
    ventas_recientes = []
    try:
        if hasattr(cliente, 'venta_set'):
            ventas_recientes = cliente.venta_set.filter(estado='COMPLETADA').order_by('-fecha_hora')[:5]
    except Exception as e:
        print(f"Error al obtener ventas recientes: {e}")
    
    context = {
        'active_page': 'clientes',
        'cliente': cliente,
        'stats': stats,
        'motos': motos,
        'movimientos_puntos': movimientos_puntos,
        'canjes_activos': canjes_activos,
        'historial': historial,
        'ventas_recientes': ventas_recientes
    }
    
    return render(request, 'clientes/detalle_cliente.html', context)

@login_required
def crear_cliente(request):
    """Crea un nuevo cliente"""
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        
        if form.is_valid():
            try:
                cliente = form.save()
                
                # Registrar en historial
                HistorialCliente.objects.create(
                    cliente=cliente,
                    tipo='OTRO',
                    descripcion='Cliente registrado en el sistema',
                    usuario=request.user
                )
                
                messages.success(request, f'Cliente {cliente.get_nombre_completo()} creado correctamente')
                return redirect('clientes:detalle_cliente', cliente_id=cliente.id)
                
            except Exception as e:
                messages.error(request, f'Error al crear cliente: {str(e)}')
    else:
        form = ClienteForm()
    
    context = {
        'active_page': 'clientes',
        'form': form,
        'titulo': 'Nuevo Cliente',
        'es_edicion': False
    }
    
    return render(request, 'clientes/cliente_form.html', context)

@login_required
def editar_cliente(request, cliente_id):
    """Edita un cliente existente"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        
        if form.is_valid():
            try:
                cliente = form.save()
                
                # Registrar en historial
                HistorialCliente.objects.create(
                    cliente=cliente,
                    tipo='OTRO',
                    descripcion='Información del cliente actualizada',
                    usuario=request.user
                )
                
                messages.success(request, f'Cliente {cliente.get_nombre_completo()} actualizado correctamente')
                return redirect('clientes:detalle_cliente', cliente_id=cliente.id)
                
            except Exception as e:
                messages.error(request, f'Error al actualizar cliente: {str(e)}')
    else:
        form = ClienteForm(instance=cliente)
    
    context = {
        'active_page': 'clientes',
        'form': form,
        'cliente': cliente,
        'titulo': f'Editar Cliente - {cliente.get_nombre_completo()}',
        'es_edicion': True
    }
    
    return render(request, 'clientes/cliente_form.html', context)

@login_required
@require_POST
def eliminar_cliente(request, cliente_id):
    """Desactiva un cliente (no elimina físicamente)"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    try:
        cliente.activo = False
        cliente.save()
        
        # Registrar en historial
        HistorialCliente.objects.create(
            cliente=cliente,
            tipo='OTRO',
            descripcion='Cliente desactivado',
            usuario=request.user
        )
        
        messages.success(request, f'Cliente {cliente.get_nombre_completo()} desactivado correctamente')
    except Exception as e:
        messages.error(request, f'Error al desactivar cliente: {str(e)}')
    
    return redirect('clientes:lista_clientes')

# ========== GESTIÓN DE MOTOS ==========

@login_required
def agregar_moto(request, cliente_id):
    """Agrega una moto a un cliente"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    if request.method == 'POST':
        form = MotoForm(request.POST)
        
        if form.is_valid():
            try:
                moto = form.save(commit=False)
                moto.cliente = cliente
                moto.save()
                
                # Registrar en historial
                HistorialCliente.objects.create(
                    cliente=cliente,
                    tipo='OTRO',
                    descripcion=f'Moto agregada: {moto.marca} {moto.modelo} - {moto.placa}',
                    usuario=request.user
                )
                
                messages.success(request, f'Moto {moto.marca} {moto.modelo} agregada correctamente')
                return redirect('clientes:detalle_cliente', cliente_id=cliente.id)
                
            except Exception as e:
                messages.error(request, f'Error al agregar moto: {str(e)}')
    else:
        form = MotoForm()
    
    context = {
        'active_page': 'clientes',
        'form': form,
        'cliente': cliente,
        'titulo': f'Agregar Moto - {cliente.get_nombre_completo()}',
        'es_edicion': False
    }
    
    return render(request, 'clientes/moto_form.html', context)

@login_required
def editar_moto(request, moto_id):
    """Edita una moto existente"""
    moto = get_object_or_404(Moto, pk=moto_id)
    
    if request.method == 'POST':
        form = MotoForm(request.POST, instance=moto)
        
        if form.is_valid():
            try:
                moto = form.save()
                
                # Registrar en historial
                HistorialCliente.objects.create(
                    cliente=moto.cliente,
                    tipo='OTRO',
                    descripcion=f'Moto actualizada: {moto.marca} {moto.modelo} - {moto.placa}',
                    usuario=request.user
                )
                
                messages.success(request, f'Moto {moto.marca} {moto.modelo} actualizada correctamente')
                return redirect('clientes:detalle_cliente', cliente_id=moto.cliente.id)
                
            except Exception as e:
                messages.error(request, f'Error al actualizar moto: {str(e)}')
    else:
        form = MotoForm(instance=moto)
    
    context = {
        'active_page': 'clientes',
        'form': form,
        'moto': moto,
        'cliente': moto.cliente,
        'titulo': f'Editar Moto - {moto.marca} {moto.modelo}',
        'es_edicion': True
    }
    
    return render(request, 'clientes/moto_form.html', context)

# ========== SISTEMA DE PUNTOS ==========

@login_required
def gestionar_puntos(request, cliente_id):
    """Gestiona los puntos de un cliente"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    if request.method == 'POST':
        accion = request.POST.get('accion')
        puntos = int(request.POST.get('puntos', 0))
        concepto = request.POST.get('concepto', '')
        
        try:
            if accion == 'agregar' and puntos > 0:
                cliente.agregar_puntos(puntos, concepto)
                messages.success(request, f'Se agregaron {puntos} puntos al cliente')
                
            elif accion == 'canjear' and puntos > 0:
                if cliente.canjear_puntos(puntos, concepto):
                    messages.success(request, f'Se canjearon {puntos} puntos del cliente')
                else:
                    messages.error(request, 'Puntos insuficientes para el canje')
                    
        except Exception as e:
            messages.error(request, f'Error al procesar puntos: {str(e)}')
    
    # Obtener historial de puntos
    movimientos = cliente.movimientos_puntos.all()[:20]
    
    # Canjes disponibles
    configuraciones = ConfiguracionPuntos.objects.filter(activo=True)
    
    context = {
        'active_page': 'clientes',
        'cliente': cliente,
        'movimientos': movimientos,
        'configuraciones': configuraciones
    }
    
    return render(request, 'clientes/gestionar_puntos.html', context)

@login_required
def canjear_puntos(request, cliente_id):
    """Permite al cliente canjear puntos por premios"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    if request.method == 'POST':
        form = CanjeoPuntosForm(request.POST)
        
        if form.is_valid():
            try:
                canje = form.save(commit=False)
                canje.cliente = cliente
                canje.usuario = request.user
                
                # Verificar puntos suficientes
                if cliente.puntos_disponibles >= canje.puntos_utilizados:
                    # Realizar el canje
                    cliente.canjear_puntos(
                        canje.puntos_utilizados, 
                        f"Canje: {canje.descripcion_premio}"
                    )
                    canje.save()
                    
                    # Registrar en historial
                    HistorialCliente.objects.create(
                        cliente=cliente,
                        tipo='OTRO',
                        descripcion=f'Canje de puntos: {canje.descripcion_premio}',
                        usuario=request.user
                    )
                    
                    messages.success(request, 'Canje realizado correctamente')
                    return redirect('clientes:detalle_cliente', cliente_id=cliente.id)
                else:
                    messages.error(request, 'Puntos insuficientes para realizar el canje')
                    
            except Exception as e:
                messages.error(request, f'Error al realizar canje: {str(e)}')
    else:
        form = CanjeoPuntosForm()
    
    context = {
        'active_page': 'clientes',
        'cliente': cliente,
        'form': form
    }
    
    return render(request, 'clientes/canjear_puntos.html', context)

# ========== HISTORIAL ==========

@login_required
def agregar_historial(request, cliente_id):
    """Agrega una entrada al historial del cliente"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    if request.method == 'POST':
        form = HistorialClienteForm(request.POST)
        
        if form.is_valid():
            try:
                historial = form.save(commit=False)
                historial.cliente = cliente
                historial.usuario = request.user
                historial.save()
                
                messages.success(request, 'Entrada agregada al historial')
                return redirect('clientes:detalle_cliente', cliente_id=cliente.id)
                
            except Exception as e:
                messages.error(request, f'Error al agregar historial: {str(e)}')
    else:
        form = HistorialClienteForm()
    
    context = {
        'active_page': 'clientes',
        'cliente': cliente,
        'form': form
    }
    
    return render(request, 'clientes/agregar_historial.html', context)

@login_required
def historial_completo(request, cliente_id):
    """Muestra el historial completo del cliente"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    
    tipo_filtro = request.GET.get('tipo', '')
    
    historial = cliente.historial.all()
    
    if tipo_filtro:
        historial = historial.filter(tipo=tipo_filtro)
    
    # Paginación
    paginator = Paginator(historial, 20)
    page_number = request.GET.get('page')
    historial_paginado = paginator.get_page(page_number)
    
    context = {
        'active_page': 'clientes',
        'cliente': cliente,
        'historial': historial_paginado,
        'tipos_interaccion': HistorialCliente.TIPO_INTERACCION_CHOICES,
        'tipo_filtro': tipo_filtro
    }
    
    return render(request, 'clientes/historial_completo.html', context)

# ========== APIS ==========

@login_required
def api_buscar_clientes(request):
    """API para buscar clientes en el POS y otros módulos"""
    try:
        q = request.GET.get('q', '').strip()
        
        if len(q) < 2:
            return JsonResponse({
                'success': True,
                'clientes': []
            })
        
        clientes = Cliente.objects.filter(
            Q(nombres__icontains=q) |
            Q(apellidos__icontains=q) |
            Q(identificacion__icontains=q) |
            Q(telefono__icontains=q) |
            Q(email__icontains=q)
        ).exclude(
            identificacion='9999999999'
        ).filter(activo=True)[:10]
        
        clientes_data = []
        for cliente in clientes:
            clientes_data.append({
                'id': cliente.id,
                'nombre_completo': cliente.get_nombre_completo(),
                'identificacion': cliente.identificacion,
                'telefono': cliente.telefono or '',
                'email': cliente.email or '',
                'puntos_disponibles': cliente.puntos_disponibles,
                'descuento_preferencial': float(cliente.descuento_preferencial)
            })
        
        return JsonResponse({
            'success': True,
            'clientes': clientes_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

def buscar_cliente_api(request):
    """API para buscar un cliente por identificación"""
    identificacion = request.GET.get('identificacion', '')
    
    if not identificacion:
        return JsonResponse({'success': False, 'mensaje': 'Identificación requerida'})
    
    try:
        cliente = Cliente.objects.get(identificacion=identificacion, activo=True)
        return JsonResponse({
            'success': True,
            'cliente': {
                'id': cliente.id,
                'nombres': cliente.nombres,
                'apellidos': cliente.apellidos,
                'identificacion': cliente.identificacion,
                'tipo_identificacion': cliente.tipo_identificacion,
                'direccion': cliente.direccion,
                'telefono': cliente.telefono,
                'email': cliente.email,
                'puntos_disponibles': cliente.puntos_disponibles,
                'descuento_preferencial': float(cliente.descuento_preferencial)
            }
        })
    except Cliente.DoesNotExist:
        return JsonResponse({'success': False, 'mensaje': 'Cliente no encontrado'})

@login_required
def api_buscar_sri(request):
    """API para buscar cliente en el SRI por cédula/RUC"""
    identificacion = request.GET.get('identificacion', '').strip()
    
    if not identificacion:
        return JsonResponse({'success': False, 'mensaje': 'Número de identificación requerido'})
    
    try:
        # Buscar en SRI
        sri_service = SRIService()
        datos_sri = sri_service.consultar_contribuyente(identificacion)
        
        if datos_sri:
            return JsonResponse({
                'success': True,
                'datos': datos_sri
            })
        else:
            return JsonResponse({
                'success': False, 
                'mensaje': 'No se encontraron datos en el SRI'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'mensaje': f'Error al consultar SRI: {str(e)}'
        })

@login_required
def api_cliente_puntos(request, cliente_id):
    """API para obtener información de puntos de un cliente"""
    try:
        cliente = get_object_or_404(Cliente, pk=cliente_id)
        
        # Calcular descuento disponible por puntos
        total_ejemplo = Decimal(request.GET.get('total', '100.00'))
        descuento_disponible = cliente.calcular_descuento_puntos(total_ejemplo)
        
        return JsonResponse({
            'success': True,
            'puntos_disponibles': cliente.puntos_disponibles,
            'puntos_acumulados': cliente.puntos_acumulados,
            'puntos_canjeados': cliente.puntos_canjeados,
            'descuento_disponible': float(descuento_disponible),
            'descuento_preferencial': float(cliente.descuento_preferencial)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
@require_POST
def api_procesar_puntos_venta(request):
    """API para procesar puntos cuando se realiza una venta"""
    try:
        data = json.loads(request.body)
        cliente_id = data.get('cliente_id')
        total_venta = Decimal(str(data.get('total_venta', '0.00')))
        venta_id = data.get('venta_id')
        
        if cliente_id and total_venta > 0:
            cliente = Cliente.objects.get(id=cliente_id)
            
            # Calcular puntos a otorgar
            puntos_ganados = ConfiguracionPuntos.calcular_puntos_venta(total_venta)
            
            if puntos_ganados > 0:
                # Importar aquí para evitar importación circular
                from ventas.models import Venta
                venta = Venta.objects.get(id=venta_id) if venta_id else None
                
                cliente.agregar_puntos(
                    puntos_ganados, 
                    f"Compra por ${total_venta}",
                    venta
                )
                
                return JsonResponse({
                    'success': True,
                    'puntos_ganados': puntos_ganados,
                    'puntos_totales': cliente.puntos_disponibles
                })
        
        return JsonResponse({'success': False, 'message': 'Datos insuficientes'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

# ========== REPORTES ==========

@login_required
def reporte_clientes(request):
    """Genera reportes de clientes"""
    # Clientes más frecuentes
    clientes_frecuentes = Cliente.objects.annotate(
        total_compras=Count('venta', filter=Q(venta__estado='COMPLETADA')),
        valor_total=Sum('venta__total', filter=Q(venta__estado='COMPLETADA'))
    ).filter(total_compras__gt=0).order_by('-total_compras')[:10]
    
    # Clientes con más puntos
    clientes_puntos = Cliente.objects.filter(
        puntos_disponibles__gt=0
    ).order_by('-puntos_disponibles')[:10]
    
    # Estadísticas por mes
    from django.db.models import DateTrunc
    registros_mes = Cliente.objects.filter(
        fecha_registro__year=timezone.now().year
    ).annotate(
        mes=DateTrunc('month', 'fecha_registro')
    ).values('mes').annotate(
        total=Count('id')
    ).order_by('mes')
    
    context = {
        'active_page': 'clientes',
        'clientes_frecuentes': clientes_frecuentes,
        'clientes_puntos': clientes_puntos,
        'registros_mes': registros_mes
    }
    
    return render(request, 'clientes/reporte_clientes.html', context)

# ========== HISTORIAL DEL CLIENTE ==========

@login_required
def api_historial_cliente(request, cliente_id):
    """API para obtener historial de ventas y órdenes de trabajo del cliente"""
    try:
        cliente = get_object_or_404(Cliente, pk=cliente_id)
        
        historial = []
        
        # ========== OBTENER VENTAS ==========
        try:
            from ventas.models import Venta
            
            ventas = Venta.objects.filter(
                cliente=cliente, 
                estado='COMPLETADA'
            ).order_by('-fecha_hora')
            
            for venta in ventas:
                historial.append({
                    'tipo': 'venta',
                    'tipo_texto': 'Venta',
                    'id': venta.id,
                    'numero': venta.numero_factura,
                    'fecha': venta.fecha_hora.strftime('%d/%m/%Y %H:%M'),
                    'fecha_ordenar': venta.fecha_hora.isoformat(),
                    'monto': float(venta.total),
                    'estado': venta.get_estado_display(),
                    'estado_codigo': venta.estado,
                    'url_detalle': f'/ventas/detalle/{venta.id}/',
                    'detalles': {
                        'Subtotal': f'${float(venta.subtotal):.2f}',
                        'IVA': f'${float(venta.iva):.2f}',
                        'Descuento': f'${float(venta.descuento):.2f}',
                        'Total': f'${float(venta.total):.2f}',
                        'Tipo de Pago': venta.get_tipo_pago_display(),
                    }
                })
                
        except ImportError:
            print("Módulo de ventas no disponible")
        except Exception as e:
            print(f"Error al obtener ventas: {e}")
        
        # ========== OBTENER ÓRDENES DE TRABAJO ==========
        try:
            from taller.models import OrdenTrabajo
            
            ordenes = OrdenTrabajo.objects.filter(
                cliente=cliente
            ).order_by('-fecha_ingreso')
            
            for orden in ordenes:
                # Determinar color del estado
                if orden.estado in ['COMPLETADO', 'ENTREGADO']:
                    estado_color = 'success'
                elif orden.estado == 'CANCELADO':
                    estado_color = 'danger'
                elif orden.estado in ['PENDIENTE', 'ESPERANDO_REPUESTOS', 'ESPERANDO_APROBACION']:
                    estado_color = 'warning'
                elif orden.estado == 'EN_PROCESO':
                    estado_color = 'info'
                else:
                    estado_color = 'secondary'
                
                # Información de la moto
                moto_info = f"{orden.moto_marca} {orden.moto_modelo}"
                if orden.moto_placa:
                    moto_info += f" - {orden.moto_placa}"
                
                # Técnico
                tecnico_nombre = orden.tecnico_principal.get_nombre_completo() if orden.tecnico_principal else 'Sin asignar'
                
                historial.append({
                    'tipo': 'orden',
                    'tipo_texto': 'Orden de Trabajo',
                    'id': orden.id,
                    'numero': orden.numero_orden,
                    'fecha': orden.fecha_ingreso.strftime('%d/%m/%Y %H:%M'),
                    'fecha_ordenar': orden.fecha_ingreso.isoformat(),
                    'monto': float(orden.precio_total),
                    'estado': orden.get_estado_display(),
                    'estado_codigo': orden.estado,
                    'estado_color': estado_color,
                    'url_detalle': f'/taller/ordenes/{orden.id}/',
                    'detalles': {
                        'Moto': moto_info,
                        'Técnico': tecnico_nombre,
                        'Mano de Obra': f'${float(orden.precio_mano_obra):.2f}',
                        'Repuestos': f'${float(orden.precio_repuestos):.2f}',
                        'Total': f'${float(orden.precio_total):.2f}',
                        'Anticipo': f'${float(orden.anticipo):.2f}',
                        'Saldo': f'${float(orden.saldo_pendiente):.2f}',
                    }
                })
                
        except ImportError:
            print("Módulo de taller no disponible")
        except Exception as e:
            print(f"Error al obtener órdenes: {e}")
        
        # Ordenar por fecha descendente
        historial.sort(key=lambda x: x['fecha_ordenar'], reverse=True)
        
        # Calcular estadísticas
        total_ventas = sum(1 for item in historial if item['tipo'] == 'venta')
        total_ordenes = sum(1 for item in historial if item['tipo'] == 'orden')
        monto_total_ventas = sum(item['monto'] for item in historial if item['tipo'] == 'venta')
        monto_total_ordenes = sum(item['monto'] for item in historial if item['tipo'] == 'orden')
        
        return JsonResponse({
            'success': True,
            'historial': historial,
            'estadisticas': {
                'total_ventas': total_ventas,
                'total_ordenes': total_ordenes,
                'monto_total_ventas': round(monto_total_ventas, 2),
                'monto_total_ordenes': round(monto_total_ordenes, 2),
                'total_registros': len(historial),
                'monto_total': round(monto_total_ventas + monto_total_ordenes, 2)
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

@login_required
@require_POST
@transaction.atomic
def api_crear_cliente_rapido(request):
    """API para crear cliente rápidamente desde el POS"""
    try:
        data = json.loads(request.body)
        
        # Validar campos requeridos
        nombres = data.get('nombres', '').strip()
        apellidos = data.get('apellidos', '').strip()
        identificacion = data.get('identificacion', '').strip()
        tipo_identificacion = data.get('tipo_identificacion', 'CEDULA')
        
        if not nombres:
            return JsonResponse({
                'success': False,
                'mensaje': 'Los nombres son requeridos'
            })
        
        if not apellidos:
            return JsonResponse({
                'success': False,
                'mensaje': 'Los apellidos son requeridos'
            })
        
        if not identificacion:
            return JsonResponse({
                'success': False,
                'mensaje': 'La identificación es requerida'
            })
        
        # Validar que no exista el cliente
        if Cliente.objects.filter(identificacion=identificacion).exists():
            return JsonResponse({
                'success': False,
                'mensaje': 'Ya existe un cliente con esta identificación'
            })
        
        # Validar cédula ecuatoriana si es tipo CEDULA
        if tipo_identificacion == 'CEDULA':
            if not _validar_cedula_ecuatoriana(identificacion):
                return JsonResponse({
                    'success': False,
                    'mensaje': 'Número de cédula inválido'
                })
        
        # Validar RUC si es tipo RUC
        if tipo_identificacion == 'RUC':
            if not _validar_ruc_ecuatoriano(identificacion):
                return JsonResponse({
                    'success': False,
                    'mensaje': 'Número de RUC inválido'
                })
        
        # Crear el cliente
        cliente = Cliente.objects.create(
            nombres=nombres,
            apellidos=apellidos,
            identificacion=identificacion,
            tipo_identificacion=tipo_identificacion,
            telefono=data.get('telefono', '').strip() or None,
            celular=data.get('celular', '').strip() or None,
            email=data.get('email', '').strip() or None,
            direccion=data.get('direccion', '').strip() or None,
            activo=True
        )
        
        # Registrar en historial
        HistorialCliente.objects.create(
            cliente=cliente,
            tipo='OTRO',
            descripcion='Cliente creado desde el POS',
            usuario=request.user
        )
        
        return JsonResponse({
            'success': True,
            'mensaje': 'Cliente creado exitosamente',
            'cliente': {
                'id': cliente.id,
                'nombre_completo': cliente.get_nombre_completo(),
                'identificacion': cliente.identificacion,
                'telefono': cliente.telefono or '',
                'email': cliente.email or ''
            }
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creando cliente rápido: {str(e)}", exc_info=True)
        
        return JsonResponse({
            'success': False,
            'mensaje': f'Error al crear cliente: {str(e)}'
        })

def _validar_cedula_ecuatoriana(cedula):
    """Valida cédula ecuatoriana (10 dígitos)"""
    if not cedula or len(cedula) != 10 or not cedula.isdigit():
        return False
    
    # Validar provincia (primeros 2 dígitos)
    provincia = int(cedula[:2])
    if provincia < 1 or provincia > 24:
        return False
    
    # Algoritmo de validación de cédula ecuatoriana
    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    suma = 0
    
    for i in range(9):
        valor = int(cedula[i]) * coeficientes[i]
        if valor >= 10:
            valor = valor - 9
        suma += valor
    
    digito_verificador = 10 - (suma % 10)
    if digito_verificador == 10:
        digito_verificador = 0
    
    return digito_verificador == int(cedula[9])

def _validar_ruc_ecuatoriano(ruc):
    """Valida RUC ecuatoriano (13 dígitos)"""
    if not ruc or len(ruc) != 13 or not ruc.isdigit():
        return False
    
    # RUC de persona natural (cédula + 001)
    if ruc.endswith('001'):
        return _validar_cedula_ecuatoriana(ruc[:10])
    
    # RUC de empresa (validación básica)
    tercero = int(ruc[2])
    if tercero >= 6 and tercero <= 9:
        return True
    
    return False

@login_required
def api_validar_identificacion(request):
    """API para validar identificación en tiempo real"""
    try:
        identificacion = request.GET.get('identificacion', '').strip()
        tipo = request.GET.get('tipo', 'CEDULA')
        
        if not identificacion:
            return JsonResponse({
                'success': False,
                'valido': False,
                'mensaje': 'Identificación requerida'
            })
        
        # Verificar si ya existe
        existe = Cliente.objects.filter(identificacion=identificacion).exists()
        
        if existe:
            return JsonResponse({
                'success': True,
                'valido': False,
                'existe': True,
                'mensaje': 'Ya existe un cliente con esta identificación'
            })
        
        # Validar formato según tipo
        valido = False
        mensaje = ''
        
        if tipo == 'CEDULA':
            valido = _validar_cedula_ecuatoriana(identificacion)
            mensaje = 'Cédula válida' if valido else 'Cédula inválida'
        elif tipo == 'RUC':
            valido = _validar_ruc_ecuatoriano(identificacion)
            mensaje = 'RUC válido' if valido else 'RUC inválido'
        elif tipo == 'PASAPORTE':
            valido = len(identificacion) >= 6
            mensaje = 'Pasaporte válido' if valido else 'Pasaporte debe tener al menos 6 caracteres'
        else:
            valido = True
            mensaje = 'Identificación aceptada'
        
        return JsonResponse({
            'success': True,
            'valido': valido,
            'existe': False,
            'mensaje': mensaje
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'valido': False,
            'mensaje': f'Error: {str(e)}'
        })
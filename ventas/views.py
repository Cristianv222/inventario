from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db import transaction, models
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.conf import settings
from django.db.models.functions import TruncDate
import json
import os
import base64
import imghdr
import logging
import datetime
from datetime import datetime, timedelta
from decimal import Decimal
from .services.ticket_service import TicketThermalService
from .models import Venta, DetalleVenta, CierreCaja
from .forms import VentaForm, DetalleVentaFormSet, CierreCajaForm, AgregarProductoForm
# from .services.factura_service import FacturaService  # ← COMENTADO PARA EVITAR ERROR AL INICIAR
from clientes.models import Cliente, PedidoOnline, DetallePedidoOnline
from inventario.models import Producto
from inventario.views import requiere_token_api
from taller.models import TipoServicio, OrdenTrabajo, Tecnico

logger = logging.getLogger(__name__)
# ========== FUNCIONES AUXILIARES ==========

def obtener_venta_por_id_o_numero(identificador):
    """
    Obtiene una venta por ID numérico o por número de factura
    """
    try:
        # Primero intentar como ID numérico
        if identificador.isdigit():
            return get_object_or_404(Venta, pk=int(identificador))
    except (ValueError, TypeError):
        pass
    
    # Si no es numérico o falló, buscar por número de factura
    return get_object_or_404(Venta, numero_factura=identificador)

# ========== VISTAS PRINCIPALES DE VENTAS ==========

@login_required
def lista_ventas(request):
    """Dashboard principal de ventas con métricas en tiempo real"""
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    
    # ========== ESTADÍSTICAS PRINCIPALES ==========
    
    # Ventas de hoy
    ventas_hoy = Venta.objects.filter(
        fecha_hora__date=today,
        estado='COMPLETADA'
    )
    
    # Ventas de ayer para comparación
    ventas_ayer = Venta.objects.filter(
        fecha_hora__date=yesterday,
        estado='COMPLETADA'
    )
    
    # Estadísticas básicas
    total_ventas_hoy = ventas_hoy.count()
    total_ventas_ayer = ventas_ayer.count()
    
    ingresos_hoy = ventas_hoy.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    ingresos_ayer = ventas_ayer.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # Cálculo de crecimiento
    crecimiento_ventas = 0
    if total_ventas_ayer > 0:
        crecimiento_ventas = ((total_ventas_hoy - total_ventas_ayer) / total_ventas_ayer) * 100
    
    crecimiento_ingresos = 0
    if ingresos_ayer > 0:
        crecimiento_ingresos = ((ingresos_hoy - ingresos_ayer) / ingresos_ayer) * 100
    
    # ✅ CAMBIO: Órdenes pendientes (no completadas)
    ordenes_pendientes = OrdenTrabajo.objects.filter(
        estado='PENDIENTE',
        facturado=False
    ).select_related('cliente')
    
    ordenes_pendientes_count = ordenes_pendientes.count()
    ordenes_ayer = OrdenTrabajo.objects.filter(
        fecha_ingreso__date=yesterday,
        estado='PENDIENTE',
        facturado=False
    ).count()
    
    variacion_ordenes = ordenes_pendientes_count - ordenes_ayer
    
    # Productos bajo stock
    productos_bajo_stock = Producto.objects.filter(
        stock_actual__lte=5,
        activo=True
    ).count()
    
    # Progreso de metas (puedes ajustar estos valores)
    meta_ventas_diaria = 50  # Meta de ventas por día
    meta_ingresos_diaria = Decimal('10000.00')  # Meta de ingresos por día
    
    progreso_ventas = min((total_ventas_hoy / meta_ventas_diaria) * 100, 100) if meta_ventas_diaria > 0 else 0
    progreso_ingresos = min((float(ingresos_hoy) / float(meta_ingresos_diaria)) * 100, 100) if meta_ingresos_diaria > 0 else 0
    
    # Urgencia de órdenes (porcentaje basado en antigüedad)
    urgencia_ordenes = 0
    if ordenes_pendientes_count > 0:
        ordenes_urgentes = ordenes_pendientes.filter(
            fecha_ingreso__lt=today - timedelta(days=2)
        ).count()
        urgencia_ordenes = (ordenes_urgentes / ordenes_pendientes_count) * 100
    
    # Nivel de stock (inverso - menos productos bajo stock = mejor nivel)
    total_productos = Producto.objects.filter(activo=True).count()
    nivel_stock = 100 - ((productos_bajo_stock / total_productos) * 100) if total_productos > 0 else 100
    
    # ========== GRÁFICO DE VENTAS DE LOS ÚLTIMOS 7 DÍAS ==========
    
    grafico_ventas = []
    dias_semana = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    
    for i in range(7):
        fecha = today - timedelta(days=6-i)
        
        ventas_dia = Venta.objects.filter(
            fecha_hora__date=fecha,
            estado='COMPLETADA'
        ).aggregate(
            total=Sum('total'),
            cantidad=Count('id')
        )
        
        total_dia = float(ventas_dia['total'] or 0)
        cantidad_dia = ventas_dia['cantidad'] or 0
        
        # Calcular altura para el gráfico (máximo 180px)
        max_ingresos = float(ingresos_hoy) if ingresos_hoy > 0 else 1000
        altura = min((total_dia / max_ingresos) * 180, 180) if total_dia > 0 else 5
        
        grafico_ventas.append({
            'fecha': fecha.strftime('%Y-%m-%d'),
            'dia': dias_semana[fecha.weekday()],
            'total': total_dia,
            'cantidad': cantidad_dia,
            'altura': altura
        })
    
    # ========== VENTAS RECIENTES ==========
    
    ventas_recientes = Venta.objects.filter(
        fecha_hora__date=today,
        estado='COMPLETADA'
    ).select_related('cliente').order_by('-fecha_hora')[:5]
    
    # ========== PRODUCTOS MÁS VENDIDOS ==========
    
    try:
        productos_top = DetalleVenta.objects.filter(
            venta__fecha_hora__date__gte=week_ago,
            venta__estado='COMPLETADA',
            producto__isnull=False
        ).values(
            'producto__nombre'
        ).annotate(
            total_vendido=Sum('cantidad'),
            ingresos=Sum('total')
        ).order_by('-total_vendido')[:5]
        
        # Renombrar para el template
        for producto in productos_top:
            producto['nombre'] = producto['producto__nombre']
    except:
        productos_top = []
    
    # ========== VENTAS PARA EL MODAL ==========
    
    ventas_modal = Venta.objects.filter(
        fecha_hora__date__gte=week_ago
    ).select_related('cliente').order_by('-fecha_hora')[:20]
    
    # ========== COMPILAR ESTADÍSTICAS ==========
    
    estadisticas = {
        'ventas_hoy': total_ventas_hoy,
        'ingresos_hoy': float(ingresos_hoy),
        'ordenes_pendientes': ordenes_pendientes_count,
        'productos_bajo_stock': productos_bajo_stock,
        'crecimiento_ventas': crecimiento_ventas,
        'crecimiento_ingresos': crecimiento_ingresos,
        'variacion_ordenes': variacion_ordenes,
        'progreso_ventas': progreso_ventas,
        'progreso_ingresos': progreso_ingresos,
        'urgencia_ordenes': urgencia_ordenes,
        'nivel_stock': nivel_stock,
    }
    
    context = {
        'active_page': 'ventas',
        'estadisticas': estadisticas,
        'grafico_ventas': grafico_ventas,
        'ventas_recientes': ventas_recientes,
        'productos_top': productos_top,
        'ordenes_pendientes': ordenes_pendientes,
        'ventas_modal': ventas_modal,
    }
    
    return render(request, 'ventas/lista_ventas.html', context)

@login_required
@transaction.atomic
def crear_venta(request):
    """Crea una nueva venta"""
    if request.method == 'POST':
        form = VentaForm(request.POST)
        
        if form.is_valid():
            venta = form.save(commit=False)
            venta.usuario = request.user
            
            if form.cleaned_data['consumidor_final']:
                venta.cliente = Cliente.get_consumidor_final()
            else:
                identificacion = form.cleaned_data['cliente_identificacion']
                try:
                    venta.cliente = Cliente.objects.get(identificacion=identificacion)
                except Cliente.DoesNotExist:
                    messages.error(request, "Cliente no encontrado")
                    return render(request, 'ventas/venta_form.html', {
                        'active_page': 'ventas',
                        'form': form,
                        'modo_venta': True
                    })
            
            venta.subtotal = Decimal('0.00')
            venta.iva = Decimal('0.00')
            venta.total = Decimal('0.00')
            venta.save()
            
            messages.success(request, "Venta creada correctamente. Agregue productos o servicios.")
            return redirect('ventas:editar_venta', venta_id=venta.id)
    else:
        form = VentaForm(initial={'consumidor_final': True})
    
    return render(request, 'ventas/venta_form.html', {
        'active_page': 'ventas',
        'form': form,
        'modo_venta': True
    })

@login_required
@transaction.atomic
def editar_venta(request, venta_id):
    """Edita una venta existente"""
    venta = get_object_or_404(Venta, pk=venta_id)
    
    if venta.estado == 'ANULADA':
        messages.error(request, "No se puede editar una venta anulada")
        return redirect('ventas:lista_ventas')
    
    if request.method == 'POST':
        form = VentaForm(request.POST, instance=venta)
        formset = DetalleVentaFormSet(request.POST, instance=venta)
        
        if form.is_valid() and formset.is_valid():
            venta = form.save(commit=False)
            detalles = formset.save(commit=False)
            subtotal = sum(detalle.subtotal for detalle in detalles)
            iva = sum(detalle.iva for detalle in detalles)
            descuento = venta.descuento or Decimal('0.00')
            total = subtotal + iva - descuento
            
            venta.subtotal = subtotal
            venta.iva = iva
            venta.total = total
            venta.save()
            
            for obj in formset.deleted_objects:
                obj.delete()
            
            for detalle in detalles:
                detalle.save()
            
            messages.success(request, "Venta actualizada correctamente.")
            return redirect('ventas:detalle_venta', venta_id=venta.id)
    else:
        form = VentaForm(instance=venta)
        formset = DetalleVentaFormSet(instance=venta)
    
    productos = Producto.objects.filter(activo=True)
    
    return render(request, 'ventas/venta_form.html', {
        'active_page': 'ventas',
        'form': form,
        'formset': formset,
        'venta': venta,
        'productos': productos,
        'modo_venta': True,
        'es_edicion': True
    })

@login_required
@require_POST
@transaction.atomic
def anular_venta(request, venta_id):
    """Anula una venta"""
    venta = get_object_or_404(Venta, pk=venta_id)
    
    if venta.estado == 'ANULADA':
        messages.error(request, "Esta venta ya está anulada")
        return redirect('ventas:detalle_venta', venta_id=venta.id)
    
    if venta.anular():
        messages.success(request, "Venta anulada correctamente")
    else:
        messages.error(request, "No se pudo anular la venta")
    
    return redirect('ventas:detalle_venta', venta_id=venta.id)

@login_required
@require_POST
@transaction.atomic
def agregar_producto(request, venta_id):
    """Agrega un producto a una venta"""
    venta = get_object_or_404(Venta, pk=venta_id)
    
    if venta.estado == 'ANULADA':
        messages.error(request, "No se pueden agregar productos a una venta anulada")
        return redirect('ventas:editar_venta', venta_id=venta.id)
    
    form = AgregarProductoForm(request.POST)
    
    if form.is_valid():
        codigo = form.cleaned_data['codigo']
        cantidad = form.cleaned_data['cantidad']
        
        try:
            producto = Producto.objects.get(codigo_unico=codigo)
            
            if producto.stock_actual < cantidad:
                messages.error(request, f"Stock insuficiente. Disponible: {producto.stock_actual}")
                return redirect('ventas:editar_venta', venta_id=venta.id)
            
            try:
                detalle = DetalleVenta.objects.get(venta=venta, producto=producto)
                detalle.cantidad += cantidad
                detalle.subtotal = detalle.cantidad * detalle.precio_unitario
                detalle.iva = detalle.subtotal * (detalle.iva_porcentaje / 100)
                detalle.total = detalle.subtotal + detalle.iva - detalle.descuento
                detalle.save()
                
                messages.success(request, f"Se actualizó la cantidad del producto {producto.nombre}")
            except DetalleVenta.DoesNotExist:
                detalle = DetalleVenta(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=producto.precio_venta,
                    subtotal=producto.precio_venta * cantidad,
                    iva_porcentaje=Decimal('15.00'),
                    iva=(producto.precio_venta * cantidad) * Decimal('0.15'),
                    descuento=Decimal('0.00'),
                    total=(producto.precio_venta * cantidad) * Decimal('1.15')
                )
                detalle.save()
                
                messages.success(request, f"Producto {producto.nombre} agregado correctamente")
            
            producto.stock_actual -= cantidad
            producto.save()
            
            detalles_subtotal = venta.detalleventa_set.aggregate(total=models.Sum('subtotal'))
            detalles_iva = venta.detalleventa_set.aggregate(total=models.Sum('iva'))
            
            venta.subtotal = detalles_subtotal['total'] or Decimal('0.00')
            venta.iva = detalles_iva['total'] or Decimal('0.00')
            venta.total = venta.subtotal + venta.iva - venta.descuento
            venta.save()
            
        except Producto.DoesNotExist:
            messages.error(request, "Producto no encontrado")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, error)
    
    return redirect('ventas:editar_venta', venta_id=venta.id)

# ========== PUNTO DE VENTA (POS) ==========

@login_required
@transaction.atomic
def punto_venta(request):
    """Vista para el punto de venta (POS)"""
    productos = Producto.objects.filter(activo=True, stock_actual__gt=0)[:30]
    
    if request.method == 'POST':
        try:
            # Logging para debugging
            import logging
            logger = logging.getLogger(__name__)
            
            data = json.loads(request.body)
            logger.info(f"Datos recibidos en POS: {data}")
            
            if not data.get('items') and not data.get('orden_trabajo_id'):
                return JsonResponse({'success': False, 'mensaje': 'No hay productos en la venta ni orden de trabajo'})
            
            # ========== OBTENER O CREAR CLIENTE ==========
            cliente = None
            if data.get('cliente_id'):
                try:
                    cliente = Cliente.objects.get(id=data['cliente_id'])
                    logger.info(f"Cliente encontrado: {cliente.nombres} {cliente.apellidos}")
                except Cliente.DoesNotExist:
                    logger.error(f"Cliente con ID {data['cliente_id']} no encontrado")
                    return JsonResponse({'success': False, 'mensaje': 'Cliente no encontrado'})
            else:
                cliente = Cliente.get_consumidor_final()
                logger.info("Usando consumidor final")
            
            # ========== CREAR VENTA ==========
            venta = Venta.objects.create(
                cliente=cliente,
                usuario=request.user,
                subtotal=Decimal(str(data.get('subtotal', '0.00'))),
                iva=Decimal(str(data.get('iva', '0.00'))),
                descuento=Decimal(str(data.get('descuento', '0.00'))),
                total=Decimal(str(data.get('total', '0.00'))),
                tipo_pago=data.get('tipo_pago', 'EFECTIVO'),
                observaciones=data.get('observaciones', ''),
                orden_trabajo_id=data.get('orden_trabajo_id')
            )
            logger.info(f"Venta creada con ID: {venta.id}, Número: {venta.numero_factura}")
            
            # ========== PROCESAR ITEMS (si existen) ==========
            detalles_creados = 0
            
            for item_index, item in enumerate(data.get('items', [])):
                logger.info(f"Procesando item {item_index + 1}: {item}")
                
                if item['tipo'] == 'producto':
                    try:
                        producto = Producto.objects.get(id=item['id'])
                        logger.info(f"Producto encontrado: {producto.nombre}, Stock actual: {producto.stock_actual}")
                        
                        cantidad = Decimal(str(item['cantidad']))
                        if producto.stock_actual < cantidad:
                            venta.delete()
                            logger.error(f'Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_actual}')
                            return JsonResponse({
                                'success': False, 
                                'mensaje': f'Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_actual}'
                            })
                        
                        # Crear detalle de venta para PRODUCTO (con IVA 15%)
                        detalle = DetalleVenta.objects.create(
                            venta=venta,
                            producto=producto,
                            cantidad=cantidad,
                            precio_unitario=Decimal(str(item['precio_unitario'])),
                            subtotal=Decimal(str(item['subtotal'])),
                            iva_porcentaje=Decimal('15.00'),
                            iva=Decimal(str(item['iva'])),
                            descuento=Decimal(str(item.get('descuento', '0.00'))),
                            total=Decimal(str(item['total']))
                        )
                        
                        # ✅ ACTUALIZAR STOCK - CRÍTICO
                        stock_anterior = producto.stock_actual
                        producto.stock_actual -= cantidad
                        producto.save()
                        
                        detalles_creados += 1
                        logger.info(f"Detalle creado para producto {producto.nombre}. Stock: {stock_anterior} -> {producto.stock_actual}")
                        
                    except Producto.DoesNotExist:
                        venta.delete()
                        logger.error(f'Producto ID {item["id"]} no encontrado')
                        return JsonResponse({'success': False, 'mensaje': f'Producto ID {item["id"]} no encontrado'})
                
                elif item['tipo'] == 'servicio':
                    try:
                        tipo_servicio = TipoServicio.objects.get(id=item['id'])
                        tecnico = None
                        
                        if item.get('tecnico_id'):
                            tecnico = Tecnico.objects.get(id=item['tecnico_id'])
                            logger.info(f"Técnico asignado: {tecnico.get_nombre_completo()}")
                        
                        # ✅ Crear detalle de servicio SIN IVA
                        cantidad = Decimal(str(item['cantidad']))
                        precio_unitario = Decimal(str(item['precio_unitario']))
                        subtotal = cantidad * precio_unitario
                        descuento = Decimal(str(item.get('descuento', '0.00')))
                        
                        detalle = DetalleVenta.objects.create(
                            venta=venta,
                            tipo_servicio=tipo_servicio,
                            tecnico=tecnico,
                            cantidad=cantidad,
                            precio_unitario=precio_unitario,
                            subtotal=subtotal,
                            iva_porcentaje=Decimal('0.00'),  # ✅ Servicios SIN IVA
                            iva=Decimal('0.00'),              # ✅ Servicios SIN IVA
                            descuento=descuento,
                            total=subtotal - descuento,       # ✅ Total = Subtotal - Descuento
                            es_servicio=True
                        )
                        
                        detalles_creados += 1
                        logger.info(f"Detalle creado para servicio: {tipo_servicio.nombre} SIN IVA")
                        
                    except (TipoServicio.DoesNotExist, Tecnico.DoesNotExist) as e:
                        venta.delete()
                        logger.error(f'Servicio o técnico no encontrado: {str(e)}')
                        return JsonResponse({'success': False, 'mensaje': f'Servicio o técnico no encontrado: {str(e)}'})
                
                else:
                    logger.warning(f"Tipo de item desconocido: {item.get('tipo')}")
            
            logger.info(f"Detalles creados: {detalles_creados} de {len(data.get('items', []))} items")
            
            # ========== MANEJAR ORDEN DE TRABAJO ==========
            if data.get('orden_trabajo_id'):
                try:
                    orden = OrdenTrabajo.objects.get(id=data['orden_trabajo_id'])
                    
                    # ✅ MARCAR COMO COMPLETADA Y FACTURADA AL MISMO TIEMPO
                    orden.estado = 'COMPLETADO'
                    orden.fecha_completado = timezone.now()
                    orden.facturado = True
                    orden.venta = venta
                    orden.save()
                    
                    logger.info(f"Orden de trabajo {orden.numero_orden} marcada como COMPLETADA y facturada")
                        
                except OrdenTrabajo.DoesNotExist:
                    logger.warning(f"Orden de trabajo ID {data['orden_trabajo_id']} no encontrada")
            
            # ========== VERIFICAR DETALLES CREADOS (solo si hay items) ==========
            if data.get('items'):
                detalles_en_bd = DetalleVenta.objects.filter(venta=venta).count()
                logger.info(f"Detalles en BD después de crear venta: {detalles_en_bd}")
                
                if detalles_en_bd == 0:
                    logger.error("No se crearon detalles de venta")
                    return JsonResponse({'success': False, 'mensaje': 'Error: No se pudieron crear los detalles de la venta'})
            
            # ========== MANEJO DE IMPRESIÓN ==========
            if data.get('imprimir'):
                try:
                    # IMPORT LOCAL AQUÍ:
                    from .services.factura_service import FacturaService
                    
                    if data.get('tipo_impresion') == 'ticket':
                        FacturaService.imprimir_ticket(venta)
                        logger.info("Ticket enviado a impresión")
                    else:
                        FacturaService.imprimir_factura(venta)
                        logger.info("Factura enviada a impresión")
                except Exception as e:
                    logger.error(f"Error en impresión: {str(e)}")
                    # No fallar la venta por error de impresión
            
            # ========== RESPUESTA EXITOSA ==========
            response_data = {
                'success': True,
                'venta_id': venta.id,
                'numero_factura': venta.numero_factura,
                'mensaje': 'Venta registrada correctamente',
                'detalles_creados': DetalleVenta.objects.filter(venta=venta).count(),
                'total': float(venta.total)
            }
            
            logger.info(f"Venta procesada exitosamente: {response_data}")
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error procesando venta: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'mensaje': f'Error interno: {str(e)}'})
    
    # GET request - mostrar la página del POS
    return render(request, 'ventas/punto_venta.html', {
        'active_page': 'ventas',
        'productos': productos,
        'fecha_actual': timezone.now().strftime('%d/%m/%Y')
    })

@login_required
def pos_con_orden(request, orden_id):
    """Redirige al POS con una orden específica cargada"""
    try:
        orden = get_object_or_404(OrdenTrabajo, pk=orden_id)
        
        # ✅ CAMBIAR VALIDACIÓN A PENDIENTES
        if orden.estado != 'PENDIENTE':
            messages.error(request, f'Solo se pueden facturar órdenes PENDIENTES. Estado actual: {orden.get_estado_display()}')
            return redirect('taller:detalle_orden', orden_id=orden_id)
        
        if orden.facturado:
            messages.error(request, 'Esta orden ya ha sido facturada')
            return redirect('taller:detalle_orden', orden_id=orden_id)
        
        from django.urls import reverse
        return redirect(f"{reverse('ventas:punto_venta')}?orden_id={orden_id}")
        
    except Exception as e:
        messages.error(request, f'Error al cargar la orden: {str(e)}')
        return redirect('ventas:punto_venta')

# ========== APIs PARA EL POS ==========

@login_required
def api_buscar_producto(request):
    """API para buscar producto por código en el POS"""
    codigo = request.GET.get('codigo', '').strip().upper()
    
    if not codigo:
        return JsonResponse({'success': False, 'message': 'Código requerido'})
    
    try:
        producto = Producto.objects.filter(
            Q(codigo_unico=codigo) | Q(codigo_barras=codigo),
            activo=True
        ).first()
        
        if producto:
            return JsonResponse({
                'success': True,
                'producto': {
                    'id': producto.id,
                    'codigo': producto.codigo_unico or producto.codigo_barras,
                    'nombre': producto.nombre,
                    'precio': float(producto.precio_venta),
                    'stock': float(producto.stock_actual),
                    'categoria': producto.categoria.nombre if producto.categoria else None,
                    'activo': producto.activo,
                    'incluye_iva': producto.incluye_iva  # ✅ NUEVO
                }
            })
        else:
            return JsonResponse({'success': False, 'message': 'Producto no encontrado'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def api_productos(request):
    """API para obtener lista de productos"""
    search = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 50))
    
    productos = Producto.objects.filter(activo=True)
    
    if search:
        productos = productos.filter(
            Q(nombre__icontains=search) |
            Q(codigo_unico__icontains=search) |
            Q(codigo_barras__icontains=search)
        )
    
    productos = productos.select_related('categoria')[:limit]
    
    productos_data = []
    for producto in productos:
        productos_data.append({
            'id': producto.id,
            'codigo': producto.codigo_unico or producto.codigo_barras,
            'nombre': producto.nombre,
            'precio': float(producto.precio_venta),
            'stock': float(producto.stock_actual),
            'categoria': producto.categoria.nombre if producto.categoria else None,
            'activo': producto.activo,
            'descripcion': producto.descripcion or '',
            'incluye_iva': producto.incluye_iva  # ✅ NUEVO
        })
    
    return JsonResponse({
        'success': True,
        'productos': productos_data
    })

@login_required
def api_tecnicos(request):
    """API para obtener lista de técnicos"""
    try:
        tecnicos = Tecnico.objects.filter(activo=True)
        
        tecnicos_data = []
        for tecnico in tecnicos:
            ordenes_activas = OrdenTrabajo.objects.filter(
                tecnico_principal=tecnico,
                estado__in=['PENDIENTE', 'EN_PROCESO']
            ).count()
            
            disponible = ordenes_activas == 0
            
            tecnicos_data.append({
                'id': tecnico.id,
                'nombre': tecnico.get_nombre_completo(),
                'telefono': tecnico.telefono or '',
                'especialidad': ', '.join([esp.nombre for esp in tecnico.especialidades.all()]) or 'Técnico general',
                'disponible': disponible,
                'activo': tecnico.activo
            })
        
        return JsonResponse({
            'success': True,
            'tecnicos': tecnicos_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def api_servicios(request):
    """API para obtener lista de servicios"""
    try:
        search = request.GET.get('q', '').strip()
        
        servicios = TipoServicio.objects.filter(activo=True)
        
        if search:
            servicios = servicios.filter(
                Q(nombre__icontains=search) |
                Q(codigo__icontains=search)
            )
        
        servicios = servicios.select_related('categoria')[:50]
        
        servicios_data = []
        for servicio in servicios:
            # ✅ SIMPLIFICADO - solo un precio
            servicios_data.append({
                'id': servicio.id,
                'codigo': servicio.codigo,
                'nombre': servicio.nombre,
                'descripcion': servicio.descripcion or '',
                'precio': float(servicio.precio),  # ✅ CAMBIADO
                'precio_total': float(servicio.precio),  # ✅ CAMBIADO
                'categoria': servicio.categoria.nombre if servicio.categoria else None,
                'tiempo_estimado': float(servicio.tiempo_estimado_horas or 0),
                'nivel_dificultad': servicio.nivel_dificultad,
                'requiere_especialidad': servicio.requiere_especialidad.nombre if servicio.requiere_especialidad else None
            })
        
        return JsonResponse({
            'success': True,
            'servicios': servicios_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def api_ordenes_completadas(request):
    """API para obtener órdenes PENDIENTES listas para facturar"""
    try:
        search = request.GET.get('q', '').strip()
        
        # ✅ CAMBIAR A PENDIENTES en lugar de COMPLETADAS
        ordenes = OrdenTrabajo.objects.filter(
            estado='PENDIENTE',
            facturado=False
        ).select_related('cliente', 'tecnico_principal')
        
        if search:
            ordenes = ordenes.filter(
                Q(numero_orden__icontains=search) |
                Q(cliente__nombres__icontains=search) |
                Q(cliente__apellidos__icontains=search) |
                Q(moto_placa__icontains=search)
            )
        
        ordenes = ordenes.order_by('-fecha_ingreso')[:20]
        
        ordenes_data = []
        for orden in ordenes:
            # ✅ CALCULAR PRECIO REAL DESDE SERVICIOS Y REPUESTOS
            servicios_total = orden.servicios.aggregate(
                total=Sum('precio_servicio')
            )['total'] or Decimal('0.00')
            
            repuestos_total = orden.repuestos_utilizados.aggregate(
                total=Sum('subtotal')
            )['total'] or Decimal('0.00')
            
            precio_total_real = float(servicios_total + repuestos_total)
            
            # ✅ ACTUALIZAR LA ORDEN SI HAY INCONSISTENCIA
            precio_almacenado = float(orden.precio_total)
            if abs(precio_total_real - precio_almacenado) > 0.01:
                # Corregir automáticamente
                orden.precio_mano_obra = servicios_total
                orden.precio_repuestos = repuestos_total  
                orden.precio_total = servicios_total + repuestos_total
                orden.saldo_pendiente = orden.precio_total - orden.anticipo
                orden.save(update_fields=[
                    'precio_mano_obra', 'precio_repuestos', 
                    'precio_total', 'saldo_pendiente'
                ])
                
                # Log para debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Auto-corregida orden {orden.numero_orden}: "
                    f"{precio_almacenado} -> {precio_total_real}"
                )
            
            cliente_nombre = f"{orden.cliente.nombres} {orden.cliente.apellidos}".strip()
            vehiculo = f"{orden.moto_marca} {orden.moto_modelo}".strip()
            tecnico_principal = orden.tecnico_principal.get_nombre_completo() if orden.tecnico_principal else 'Sin técnico'
            fecha_ingreso = orden.fecha_ingreso.strftime('%d/%m/%Y %H:%M')
            
            ordenes_data.append({
                'id': orden.id,
                'numero_orden': orden.numero_orden,
                'cliente_nombre': cliente_nombre,
                'cliente_id': orden.cliente.id,
                'vehiculo': vehiculo,
                'placa': orden.moto_placa,
                'precio_total': precio_total_real,
                'fecha_ingreso': fecha_ingreso,
                'tecnico_principal': tecnico_principal,
                'estado': orden.estado,
                'descripcion_problema': orden.motivo_ingreso[:100] + '...' if len(orden.motivo_ingreso or '') > 100 else orden.motivo_ingreso or ''
            })
        
        return JsonResponse({
            'success': True,
            'ordenes': ordenes_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required  
def api_orden_datos_pos(request, orden_id):
    """API para obtener datos SIMPLIFICADOS de una orden para el POS"""
    try:
        orden = get_object_or_404(OrdenTrabajo, pk=orden_id)
        
        # ✅ VALIDAR QUE LA ORDEN ESTÉ PENDIENTE
        if orden.estado != 'PENDIENTE':
            return JsonResponse({
                'success': False, 
                'message': f'Solo se pueden facturar órdenes PENDIENTES. Estado actual: {orden.get_estado_display()}'
            })
        
        if orden.facturado:
            return JsonResponse({
                'success': False, 
                'message': 'Esta orden ya ha sido facturada'
            })
        
        # ✅ CALCULAR PRECIO TOTAL
        servicios_total = orden.servicios.aggregate(
            total=Sum('precio_servicio')
        )['total'] or Decimal('0.00')
        
        repuestos_total = orden.repuestos_utilizados.aggregate(
            total=Sum('subtotal')
        )['total'] or Decimal('0.00')
        
        precio_total_calculado = servicios_total + repuestos_total
        
        # Actualizar orden si hay inconsistencias
        if abs(float(orden.precio_total) - float(precio_total_calculado)) > 0.01:
            orden.precio_mano_obra = servicios_total
            orden.precio_repuestos = repuestos_total
            orden.precio_total = precio_total_calculado
            orden.saldo_pendiente = precio_total_calculado - orden.anticipo
            orden.save(update_fields=[
                'precio_mano_obra', 'precio_repuestos',
                'precio_total', 'saldo_pendiente'
            ])
        
        # ✅ DATOS DEL CLIENTE
        cliente_nombre = f"{orden.cliente.nombres} {orden.cliente.apellidos}".strip()
        vehiculo_info = f"{orden.moto_marca} {orden.moto_modelo} - {orden.moto_placa}"
        tecnico_principal = orden.tecnico_principal.get_nombre_completo() if orden.tecnico_principal else 'Sin técnico'
        
        # ✅ ESTRUCTURA SIMPLIFICADA - SIN DESGLOSE
        orden_data = {
            'id': orden.id,
            'numero_orden': str(orden.numero_orden),
            'cliente': {
                'id': orden.cliente.id,
                'nombre_completo': str(cliente_nombre),
                'identificacion': str(orden.cliente.identificacion)
            },
            'vehiculo': str(vehiculo_info),
            'tecnico_principal': str(tecnico_principal),
            'precio_total': float(orden.precio_total),
            'descripcion_problema': str(orden.motivo_ingreso or ''),
            'observaciones': str(orden.observaciones_tecnico or ''),
            # ✅ NO SE ENVÍAN servicios ni repuestos desglosados
        }
        
        return JsonResponse({
            'success': True,
            'orden': orden_data
        })
        
    except OrdenTrabajo.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Orden de trabajo no encontrada'
        }, status=404)
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error en api_orden_datos_pos: {str(e)}")
        logger.error(traceback.format_exc())
        
        return JsonResponse({
            'success': False,
            'message': f'Error al cargar orden: {str(e)}'
        }, status=500)
        
@login_required
def api_buscar_clientes(request):
    """API para buscar clientes"""
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
            Q(telefono__icontains=q)
        ).exclude(
            identificacion='9999999999'
        )[:10]
        
        clientes_data = []
        for cliente in clientes:
            clientes_data.append({
                'id': cliente.id,
                'nombre_completo': f"{cliente.nombres} {cliente.apellidos}".strip(),
                'identificacion': cliente.identificacion,
                'telefono': cliente.telefono or '',
                'email': cliente.email or ''
            })
        
        return JsonResponse({
            'success': True,
            'clientes': clientes_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

# ========== NUEVAS APIS PARA IMPRESIÓN DE TICKETS TÉRMICOS ==========

@login_required
def api_impresoras_disponibles(request):
    """API para obtener impresoras disponibles en el sistema"""
    try:
        printers = TicketThermalService.get_available_printers()
        
        return JsonResponse({
            'success': True,
            'printers': printers,
            'message': f'Se encontraron {len(printers)} impresoras'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'printers': [],
            'message': f'Error al obtener impresoras: {str(e)}'
        })

@login_required
@require_POST
def api_probar_impresora(request):
    """API para probar una impresora térmica"""
    try:
        data = json.loads(request.body)
        printer_name = data.get('printer_name')
        printer_type = data.get('printer_type', 'GENERIC_80MM')
        
        if not printer_name:
            return JsonResponse({
                'success': False,
                'message': 'Nombre de impresora requerido'
            })
        
        success, message = TicketThermalService.test_printer(printer_name, printer_type)
        
        return JsonResponse({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error al probar impresora: {str(e)}'
        })

@login_required
@transaction.atomic
def api_procesar_venta_pos_mejorado(request):
    """API mejorada para procesar venta desde el POS con opciones de impresión"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'})
    
    try:
        data = json.loads(request.body)
        
        if not data.get('items'):
            return JsonResponse({'success': False, 'message': 'No hay productos en la venta'})
        
        # Obtener cliente
        cliente = None
        if data.get('customer_id'):
            try:
                cliente = Cliente.objects.get(id=data['customer_id'])
            except Cliente.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Cliente no encontrado'})
        else:
            cliente = Cliente.get_consumidor_final()
        
        # Crear la venta
        venta = Venta.objects.create(
            cliente=cliente,
            usuario=request.user,
            subtotal=Decimal(str(data.get('subtotal', '0.00'))),
            iva=Decimal(str(data.get('tax_amount', '0.00'))),
            descuento=Decimal(str(data.get('discount_amount', '0.00'))),
            total=Decimal(str(data.get('total_amount', '0.00'))),
            tipo_pago=data.get('payment_method', 'EFECTIVO'),
            observaciones=data.get('observaciones', '')
        )
        
        # Procesar items de la venta
        for item in data['items']:
            if item['type'] == 'product':
                try:
                    producto = Producto.objects.get(id=item['id'])
                    cantidad = Decimal(str(item['quantity']))
                    
                    if producto.stock_actual < cantidad:
                        raise Exception(f'Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_actual}')
                    
                    subtotal_item = Decimal(str(item['subtotal']))
                    iva_item = subtotal_item * Decimal('0.15')
                    total_item = subtotal_item + iva_item
                    
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad,
                        precio_unitario=Decimal(str(item['unit_price'])),
                        subtotal=subtotal_item,
                        iva_porcentaje=Decimal('15.00'),
                        iva=iva_item,
                        descuento=Decimal('0.00'),
                        total=total_item
                    )
                    
                    producto.stock_actual -= cantidad
                    producto.save()
                    
                except Producto.DoesNotExist:
                    raise Exception(f'Producto ID {item["id"]} no encontrado')
            
            elif item['type'] == 'service':
                try:
                    tipo_servicio = TipoServicio.objects.get(id=item['id'])
                    tecnico = None
                    
                    if item.get('technician_id'):
                        tecnico = Tecnico.objects.get(id=item['technician_id'])
                    
                    subtotal_item = Decimal(str(item['subtotal']))
                    iva_item = subtotal_item * Decimal('0.15')
                    total_item = subtotal_item + iva_item
                    
                    DetalleVenta.objects.create(
                        venta=venta,
                        tipo_servicio=tipo_servicio,
                        tecnico=tecnico,
                        cantidad=Decimal(str(item['quantity'])),
                        precio_unitario=Decimal(str(item['unit_price'])),
                        subtotal=subtotal_item,
                        iva_porcentaje=Decimal('15.00'),
                        iva=iva_item,
                        descuento=Decimal('0.00'),
                        total=total_item,
                        es_servicio=True
                    )
                    
                except (TipoServicio.DoesNotExist, Tecnico.DoesNotExist) as e:
                    raise Exception(f'Servicio o técnico no encontrado: {str(e)}')
        
        # Manejar orden de trabajo si existe
        if data.get('order_id'):
            try:
                orden = OrdenTrabajo.objects.get(id=data['order_id'])
                orden.facturado = True
                orden.venta = venta
                if orden.estado != 'COMPLETADO':
                    orden.estado = 'COMPLETADO'
                    orden.fecha_completado = timezone.now()
                orden.save()
            except OrdenTrabajo.DoesNotExist:
                pass
        
        # Procesar opciones de impresión
        print_result = None
        email_sent = False
        
        print_options = data.get('print_options', {})
        
        if print_options.get('printOption') == 'ticket' and print_options.get('printer'):
            try:
                printer_config = print_options['printer']
                printer_name = printer_config['name']
                printer_type = printer_config['type']
                open_drawer = print_options.get('openDrawer', False)
                
                success, message = TicketThermalService.print_ticket(
                    venta, 
                    printer_name, 
                    printer_type, 
                    open_drawer
                )
                
                print_result = {
                    'success': success,
                    'message': message,
                    'type': 'ticket'
                }
                
            except Exception as e:
                print_result = {
                    'success': False,
                    'message': f'Error al imprimir ticket: {str(e)}',
                    'type': 'ticket'
                }
        
        elif print_options.get('printOption') == 'invoice':
            try:
                # IMPORT LOCAL AQUÍ:
                from .services.factura_service import FacturaService
                
                FacturaService.imprimir_factura(venta)
                print_result = {
                    'success': True,
                    'message': 'Factura enviada a impresora',
                    'type': 'invoice'
                }
            except Exception as e:
                print_result = {
                    'success': False,
                    'message': f'Error al imprimir factura: {str(e)}',
                    'type': 'invoice'
                }
        
        # Enviar email si se solicita y el cliente tiene email
        if print_options.get('sendEmail') and cliente.email:
            try:
                # Aquí puedes implementar el envío de email
                # email_service.send_invoice_email(venta, cliente.email)
                email_sent = True
            except Exception as e:
                print(f"Error enviando email: {e}")
        
        return JsonResponse({
            'success': True,
            'venta_id': venta.id,
            'invoice_number': venta.numero_factura,
            'message': 'Venta procesada correctamente',
            'print_result': print_result,
            'email_sent': email_sent
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
@transaction.atomic
def api_procesar_venta_pos(request):
    """Redireccionar a la nueva función mejorada"""
    return api_procesar_venta_pos_mejorado(request)

@login_required
@require_POST
def imprimir_ticket_venta(request, venta_id):
    """Imprime un ticket térmico de una venta existente"""
    try:
        venta = obtener_venta_por_id_o_numero(venta_id)
        
        data = json.loads(request.body)
        printer_name = data.get('printer_name')
        printer_type = data.get('printer_type', 'GENERIC_80MM')
        open_drawer = data.get('open_drawer', False)
        
        if not printer_name:
            return JsonResponse({
                'success': False,
                'message': 'Nombre de impresora requerido'
            })
        
        success, message = TicketThermalService.print_ticket(
            venta, 
            printer_name, 
            printer_type, 
            open_drawer
        )
        
        return JsonResponse({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error al imprimir ticket: {str(e)}'
        })

@login_required
def preview_ticket(request, venta_id):
    """Muestra una vista previa del ticket en texto plano"""
    try:
        venta = obtener_venta_por_id_o_numero(venta_id)
        printer_type = request.GET.get('type', 'GENERIC_80MM')
        
        content = TicketThermalService.generate_ticket_content(venta, printer_type)
        
        return HttpResponse(content, content_type='text/plain; charset=utf-8')
        
    except Exception as e:
        return HttpResponse(f'Error generando preview: {str(e)}', status=500)

# ========== FUNCIONES ADICIONALES PARA CONFIGURACIÓN ==========

@login_required
def configuracion_impresoras(request):
    """Vista para configurar impresoras del sistema"""
    printers = TicketThermalService.get_available_printers()
    
    context = {
        'active_page': 'configuracion',
        'printers': printers,
        'printer_types': TicketThermalService.THERMAL_PRINTERS
    }
    
    return render(request, 'ventas/configuracion_impresoras.html', context)

@login_required
@require_POST
def guardar_configuracion_impresora(request):
    """Guardar configuración de impresora por defecto"""
    try:
        printer_name = request.POST.get('printer_name')
        printer_type = request.POST.get('printer_type')
        auto_open_drawer = request.POST.get('auto_open_drawer') == 'on'
        
        # Guardar en configuración del usuario o sistema
        # Aquí puedes implementar la lógica para guardar las preferencias
        
        messages.success(request, 'Configuración de impresora guardada correctamente')
        return redirect('ventas:configuracion_impresoras')
        
    except Exception as e:
        messages.error(request, f'Error al guardar configuración: {str(e)}')
        return redirect('ventas:configuracion_impresoras')

# ========== OTRAS FUNCIONES ==========

@login_required
def importar_orden_trabajo(request, orden_id):
    """Importa una orden de trabajo completa al punto de venta"""
    try:
        orden = get_object_or_404(OrdenTrabajo, pk=orden_id)
        
        if orden.estado != 'PENDIENTE':
            return JsonResponse({
                'success': False, 
                'mensaje': 'Solo se pueden facturar órdenes pendientes'
            })
        
        if orden.facturado:
            return JsonResponse({
                'success': False, 
                'mensaje': 'Esta orden ya ha sido facturada'
            })
        
        orden_data = {
            'orden_trabajo_id': orden.id,
            'numero_orden': orden.numero_orden,
            'cliente': {
                'id': orden.cliente.id,
                'nombre': f"{orden.cliente.nombres} {orden.cliente.apellidos}".strip(),
                'identificacion': orden.cliente.identificacion
            },
            'moto': {
                'placa': orden.moto_placa,
                'marca': orden.moto_marca,
                'modelo': orden.moto_modelo
            },
            'servicios': [],
            'repuestos': [],
            'totales': {
                'mano_obra': float(orden.precio_mano_obra),
                'repuestos': float(orden.precio_repuestos),
                'total': float(orden.precio_total)
            }
        }
        
        for servicio_orden in orden.servicios.all():
            orden_data['servicios'].append({
                'id': servicio_orden.tipo_servicio.id,
                'codigo': servicio_orden.tipo_servicio.codigo,
                'nombre': servicio_orden.tipo_servicio.nombre,
                'precio': float(servicio_orden.precio_total),
                'tecnico_id': servicio_orden.tecnico_asignado.id if servicio_orden.tecnico_asignado else None,
                'tecnico_nombre': servicio_orden.tecnico_asignado.get_nombre_completo() if servicio_orden.tecnico_asignado else None,
                'tiempo_real': float(servicio_orden.tiempo_real or 0),
                'observaciones': servicio_orden.observaciones
            })
        
        for repuesto_orden in orden.repuestos_utilizados.all():
            codigo = repuesto_orden.producto.codigo_unico or repuesto_orden.producto.codigo_barras
            orden_data['repuestos'].append({
                'id': repuesto_orden.producto.id,
                'codigo': codigo,
                'nombre': repuesto_orden.producto.nombre,
                'cantidad': float(repuesto_orden.cantidad),
                'precio_unitario': float(repuesto_orden.precio_unitario),
                'subtotal': float(repuesto_orden.subtotal)
            })
        
        return JsonResponse({
            'success': True,
            'orden_data': orden_data,
            'mensaje': 'Orden cargada correctamente'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'mensaje': f'Error al importar orden: {str(e)}'
        })

@login_required
def generar_cotizacion(request, orden_id):
    """Genera una cotización PDF de una orden de trabajo"""
    orden = get_object_or_404(OrdenTrabajo, pk=orden_id)
    
    if orden.estado == 'CANCELADO':
        messages.error(request, 'No se puede generar cotización de una orden cancelada')
        return redirect('taller:detalle_orden', orden_id=orden.id)
    
    try:
        from taller.services.cotizacion_service import CotizacionService
        
        pdf = CotizacionService.generar_cotizacion_pdf(orden)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        
        filename = f'cotizacion_{orden.numero_orden}_{timezone.now().strftime("%Y%m%d")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except ImportError:
        messages.error(request, 'El servicio de cotización no está disponible')
        return redirect('taller:detalle_orden', orden_id=orden.id)
    except Exception as e:
        messages.error(request, f'Error al generar la cotización: {str(e)}')
        return redirect('taller:detalle_orden', orden_id=orden.id)

# ========== VISTAS DE IMPRESIÓN Y CIERRE ==========

@login_required
def factura_pdf(request):
    """Genera PDF de factura para descarga"""
    identificador = request.GET.get('id')
    if not identificador:
        messages.error(request, 'ID de venta requerido')
        return redirect('ventas:lista_ventas')
    
    try:
        # IMPORT LOCAL AQUÍ:
        from .services.factura_service import FacturaService
        
        import logging
        logger = logging.getLogger(__name__)
        
        venta = obtener_venta_por_id_o_numero(identificador)
        logger.info(f"Generando PDF para venta ID: {venta.id}, Número: {venta.numero_factura}")
        
        # ⭐ USAR EL SERVICIO SIMPLIFICADO
        try:
            pdf_file = FacturaService.generar_pdf(venta)
            
            response = HttpResponse(pdf_file.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="factura_{venta.numero_factura}.pdf"'
            
            logger.info(f"PDF de factura {venta.numero_factura} generado exitosamente")
            return response
            
        except Exception as e:
            logger.error(f"Error generando PDF: {str(e)}")
            messages.error(request, f'Error al generar PDF: {str(e)}')
            return redirect('ventas:detalle_venta', venta_id=venta.id)
        
    except Exception as e:
        logger.error(f"Error general en factura_pdf: {str(e)}", exc_info=True)
        messages.error(request, f'Error al generar PDF: {str(e)}')
        return redirect('ventas:lista_ventas')

@login_required
@require_POST
def imprimir_factura(request):
    """Imprime una factura"""
    identificador = request.GET.get('id')
    if not identificador:
        return JsonResponse({'success': False, 'resultado': 'ID de venta requerido'})
    
    try:
        # IMPORT LOCAL AQUÍ:
        from .services.factura_service import FacturaService
        
        venta = obtener_venta_por_id_o_numero(identificador)
        impresora = request.POST.get('impresora')
        
        success, result = FacturaService.imprimir_factura(venta, impresora)
        
        return JsonResponse({
            'success': success,
            'resultado': result
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'resultado': f'Error: {str(e)}'
        })

@login_required
@require_POST
def imprimir_ticket(request):
    """Imprime un ticket"""
    identificador = request.GET.get('id')
    if not identificador:
        return JsonResponse({'success': False, 'resultado': 'ID de venta requerido'})
    
    try:
        # IMPORT LOCAL AQUÍ:
        from .services.factura_service import FacturaService
        
        venta = obtener_venta_por_id_o_numero(identificador)
        impresora = request.POST.get('impresora')
        
        success, result = FacturaService.imprimir_ticket(venta, impresora)
        
        return JsonResponse({
            'success': success,
            'resultado': result
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'resultado': f'Error: {str(e)}'
        })

@login_required
def lista_cierres(request):
    """Muestra la lista de cierres de caja"""
    cierres = CierreCaja.objects.all().select_related('usuario')
    
    return render(request, 'ventas/lista_cierres.html', {
        'active_page': 'ventas',
        'cierres': cierres
    })

@login_required
def crear_cierre(request):
    """Crea un nuevo cierre de caja"""
    if request.method == 'POST':
        form = CierreCajaForm(request.POST)
        if form.is_valid():
            cierre = form.save(commit=False)
            cierre.usuario = request.user
            cierre.save()
            
            messages.success(request, "Cierre de caja registrado correctamente")
            return redirect('ventas:lista_cierres')
    else:
        form = CierreCajaForm(initial={'fecha': timezone.now().date()})
    
    ventas_dia = Venta.get_ventas_por_dia()
    
    return render(request, 'ventas/cierre_form.html', {
        'active_page': 'ventas',
        'form': form,
        'ventas_dia': ventas_dia
    })

@login_required
def api_dashboard_stats(request):
    """API para obtener estadísticas actualizadas del dashboard"""
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    try:
        # Ventas de hoy
        ventas_hoy = Venta.objects.filter(
            fecha_hora__date=today,
            estado='COMPLETADA'
        )
        
        ventas_ayer = Venta.objects.filter(
            fecha_hora__date=yesterday,
            estado='COMPLETADA'
        )
        
        total_ventas_hoy = ventas_hoy.count()
        total_ventas_ayer = ventas_ayer.count()
        
        ingresos_hoy = ventas_hoy.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        ingresos_ayer = ventas_ayer.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        # Cálculo de crecimiento
        crecimiento_ventas = 0
        if total_ventas_ayer > 0:
            crecimiento_ventas = ((total_ventas_hoy - total_ventas_ayer) / total_ventas_ayer) * 100
        
        crecimiento_ingresos = 0
        if ingresos_ayer > 0:
            crecimiento_ingresos = ((float(ingresos_hoy) - float(ingresos_ayer)) / float(ingresos_ayer)) * 100
        
        # Órdenes pendientes
        ordenes_pendientes = OrdenTrabajo.objects.filter(
            estado='PENDIENTE',
            facturado=False
        ).count()
        
        # Productos bajo stock
        productos_bajo_stock = Producto.objects.filter(
            stock_actual__lte=5,
            activo=True
        ).count()
        
        # Ticket promedio
        ticket_promedio = 0
        if total_ventas_hoy > 0:
            ticket_promedio = float(ingresos_hoy) / total_ventas_hoy
        
        return JsonResponse({
            'success': True,
            'stats': {
                'ventas_hoy': total_ventas_hoy,
                'ingresos_hoy': float(ingresos_hoy),
                'ordenes_pendientes': ordenes_pendientes,
                'productos_bajo_stock': productos_bajo_stock,
                'ticket_promedio': ticket_promedio,
                'crecimiento_ventas': crecimiento_ventas,
                'crecimiento_ingresos': crecimiento_ingresos,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@login_required
def api_todas_ventas(request):
    """API para obtener todas las ventas con filtros"""
    try:
        ventas = Venta.objects.all().select_related('cliente')
        
        # Aplicar filtros
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        estado = request.GET.get('estado')
        
        if fecha_inicio:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                ventas = ventas.filter(fecha_hora__date__gte=fecha_inicio)
            except (ValueError, TypeError):
                pass
        
        if fecha_fin:
            try:
                fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                ventas = ventas.filter(fecha_hora__date__lte=fecha_fin)
            except (ValueError, TypeError):
                pass
        
        if estado:
            ventas = ventas.filter(estado=estado)
        
        # Limitar resultados
        ventas = ventas.order_by('-fecha_hora')[:50]
        
        ventas_data = []
        for venta in ventas:
            cliente_nombre = 'Consumidor Final'
            if venta.cliente.identificacion != '9999999999':
                cliente_nombre = f"{venta.cliente.nombres} {venta.cliente.apellidos}".strip()
            
            ventas_data.append({
                'id': venta.id,
                'numero_factura': venta.numero_factura,
                'cliente_nombre': cliente_nombre,
                'fecha_hora': venta.fecha_hora.strftime('%d/%m/%Y %H:%M'),
                'total': float(venta.total),
                'estado': venta.estado,
                'tipo_pago': venta.get_tipo_pago_display()
            })
        
        return JsonResponse({
            'success': True,
            'ventas': ventas_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@login_required
def api_grafico_ventas(request):
    """API para obtener datos del gráfico de ventas por período"""
    try:
        periodo = request.GET.get('periodo', '7d')
        today = timezone.now().date()
        
        if periodo == '7d':
            dias = 7
            labels = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        elif periodo == '30d':
            dias = 30
            labels = ['Sem 1', 'Sem 2', 'Sem 3', 'Sem 4']
        elif periodo == '90d':
            dias = 90
            labels = ['Mes 1', 'Mes 2', 'Mes 3']
        else:
            dias = 7
            labels = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        
        datos = []
        
        if periodo == '7d':
            # Datos diarios
            for i in range(7):
                fecha = today - timedelta(days=6-i)
                ventas_dia = Venta.objects.filter(
                    fecha_hora__date=fecha,
                    estado='COMPLETADA'
                ).aggregate(
                    total=Sum('total'),
                    cantidad=Count('id')
                )
                
                datos.append({
                    'fecha': fecha.strftime('%Y-%m-%d'),
                    'dia': labels[i],
                    'total': float(ventas_dia['total'] or 0),
                    'cantidad': ventas_dia['cantidad'] or 0
                })
        
        elif periodo == '30d':
            # Datos semanales
            for i in range(4):
                fecha_fin = today - timedelta(days=i*7)
                fecha_inicio = fecha_fin - timedelta(days=6)
                
                ventas_semana = Venta.objects.filter(
                    fecha_hora__date__range=[fecha_inicio, fecha_fin],
                    estado='COMPLETADA'
                ).aggregate(
                    total=Sum('total'),
                    cantidad=Count('id')
                )
                
                datos.append({
                    'fecha': fecha_fin.strftime('%Y-%m-%d'),
                    'periodo': labels[3-i],
                    'total': float(ventas_semana['total'] or 0),
                    'cantidad': ventas_semana['cantidad'] or 0
                })
        
        elif periodo == '90d':
            # Datos mensuales
            for i in range(3):
                fecha_fin = today - timedelta(days=i*30)
                fecha_inicio = fecha_fin - timedelta(days=29)
                
                ventas_mes = Venta.objects.filter(
                    fecha_hora__date__range=[fecha_inicio, fecha_fin],
                    estado='COMPLETADA'
                ).aggregate(
                    total=Sum('total'),
                    cantidad=Count('id')
                )
                
                datos.append({
                    'fecha': fecha_fin.strftime('%Y-%m-%d'),
                    'periodo': labels[2-i],
                    'total': float(ventas_mes['total'] or 0),
                    'cantidad': ventas_mes['cantidad'] or 0
                })
        
        return JsonResponse({
            'success': True,
            'datos': datos,
            'periodo': periodo
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@login_required
def api_productos_top(request):
    """API para obtener productos más vendidos"""
    try:
        periodo_dias = int(request.GET.get('dias', 7))
        fecha_inicio = timezone.now().date() - timedelta(days=periodo_dias)
        
        productos = DetalleVenta.objects.filter(
            venta__fecha_hora__date__gte=fecha_inicio,
            venta__estado='COMPLETADA',
            producto__isnull=False
        ).values(
            'producto__id',
            'producto__nombre',
            'producto__codigo_unico'
        ).annotate(
            total_vendido=Sum('cantidad'),
            ingresos=Sum('total'),
            veces_vendido=Count('venta', distinct=True)
        ).order_by('-total_vendido')[:10]
        
        productos_data = []
        for producto in productos:
            productos_data.append({
                'id': producto['producto__id'],
                'nombre': producto['producto__nombre'],
                'codigo': producto['producto__codigo_unico'],
                'total_vendido': float(producto['total_vendido']),
                'ingresos': float(producto['ingresos']),
                'veces_vendido': producto['veces_vendido']
            })
        
        return JsonResponse({
            'success': True,
            'productos': productos_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@login_required
def api_resumen_mensual(request):
    """API para obtener resumen mensual de ventas"""
    try:
        today = timezone.now().date()
        primer_dia_mes = today.replace(day=1)
        
        # Ventas del mes actual
        ventas_mes = Venta.objects.filter(
            fecha_hora__date__gte=primer_dia_mes,
            estado='COMPLETADA'
        ).aggregate(
            total_ventas=Count('id'),
            total_ingresos=Sum('total'),
            ticket_promedio=Avg('total')
        )
        
        # Ventas del mes anterior para comparación
        if primer_dia_mes.month == 1:
            mes_anterior = primer_dia_mes.replace(year=primer_dia_mes.year-1, month=12)
        else:
            mes_anterior = primer_dia_mes.replace(month=primer_dia_mes.month-1)
        
        ventas_mes_anterior = Venta.objects.filter(
            fecha_hora__date__gte=mes_anterior,
            fecha_hora__date__lt=primer_dia_mes,
            estado='COMPLETADA'
        ).aggregate(
            total_ventas=Count('id'),
            total_ingresos=Sum('total')
        )
        
        # Calcular crecimiento
        crecimiento_ventas = 0
        crecimiento_ingresos = 0
        
        if ventas_mes_anterior['total_ventas']:
            crecimiento_ventas = ((ventas_mes['total_ventas'] - ventas_mes_anterior['total_ventas']) / ventas_mes_anterior['total_ventas']) * 100
        
        if ventas_mes_anterior['total_ingresos']:
            crecimiento_ingresos = ((float(ventas_mes['total_ingresos'] or 0) - float(ventas_mes_anterior['total_ingresos'])) / float(ventas_mes_anterior['total_ingresos'])) * 100
        
        return JsonResponse({
            'success': True,
            'resumen': {
                'total_ventas': ventas_mes['total_ventas'] or 0,
                'total_ingresos': float(ventas_mes['total_ingresos'] or 0),
                'ticket_promedio': float(ventas_mes['ticket_promedio'] or 0),
                'crecimiento_ventas': crecimiento_ventas,
                'crecimiento_ingresos': crecimiento_ingresos,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@login_required
def detalle_venta(request, venta_id):
    """Muestra el detalle de una venta"""
    venta = get_object_or_404(Venta, pk=venta_id)
    detalles = venta.detalleventa_set.all().select_related('producto', 'tipo_servicio')
    
    return render(request, 'ventas/detalle_venta.html', {
        'active_page': 'ventas',
        'venta': venta,
        'detalles': detalles
    })

@login_required
def api_productos_populares(request):
    """API para obtener productos más populares/vendidos"""
    try:
        limit = int(request.GET.get('limit', 12))
        
        # Obtener productos más vendidos en los últimos 30 días
        from datetime import timedelta
        fecha_limite = timezone.now().date() - timedelta(days=30)
        
        productos_populares = DetalleVenta.objects.filter(
            venta__fecha_hora__date__gte=fecha_limite,
            venta__estado='COMPLETADA',
            producto__isnull=False
        ).values(
            'producto__id',
            'producto__codigo_unico',
            'producto__codigo_barras', 
            'producto__nombre',
            'producto__precio_venta',
            'producto__stock_actual',
            'producto__categoria__nombre'
        ).annotate(
            total_vendido=Sum('cantidad')
        ).order_by('-total_vendido')[:limit]
        
        productos_data = []
        for item in productos_populares:
            productos_data.append({
                'id': item['producto__id'],
                'codigo': item['producto__codigo_unico'] or item['producto__codigo_barras'] or '',
                'nombre': item['producto__nombre'],
                'precio': float(item['producto__precio_venta']),
                'stock': float(item['producto__stock_actual']),
                'categoria': item['producto__categoria__nombre'],
                'total_vendido': float(item['total_vendido'])
            })
        
        # Si no hay suficientes productos populares, completar con productos activos
        if len(productos_data) < limit:
            productos_activos = Producto.objects.filter(
                activo=True,
                stock_actual__gt=0
            ).exclude(
                id__in=[p['id'] for p in productos_data]
            ).select_related('categoria')[:limit - len(productos_data)]
            
            for producto in productos_activos:
                productos_data.append({
                    'id': producto.id,
                    'codigo': producto.codigo_unico or producto.codigo_barras or '',
                    'nombre': producto.nombre,
                    'precio': float(producto.precio_venta),
                    'stock': float(producto.stock_actual),
                    'categoria': producto.categoria.nombre if producto.categoria else None,
                    'total_vendido': 0
                })
        
        return JsonResponse({
            'success': True,
            'productos': productos_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': f'Error: {str(e)}',
            'productos': []
        })
@login_required
@require_POST
def marcar_pago_verificado(request, pedido_id):
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)
    pedido.estado_pago = 'PAGADO'
    pedido.save()
    messages.success(request, f'Pago del pedido #{pedido.numero_orden} verificado.')
    return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)
@csrf_exempt
@requiere_token_api
def api_crear_pedido_online(request):
    """
    Crea un pedido online desde la tienda PHP.

    POST /ventas/api/publica/pedidos/crear/
    Authorization: Bearer <token>

    Body JSON:
    {
        "nombres": "Juan",
        "apellidos": "Pérez",
        "cedula": "1234567890",
        "telefono": "0999999999",
        "email": "juan@email.com",
        "tipo_entrega": "RETIRO" | "SERVIENTREGA",
        "direccion_envio": "...",
        "ciudad_envio": "...",
        "provincia_envio": "...",
        "referencia_envio": "...",
        "metodo_pago": "PAYPHONE" | "TRANSFERENCIA" | "CONTRA_ENTREGA",
        "numero_comprobante": "TRF-2025-001",
        "comprobante_base64": "data:image/jpeg;base64,/9j/...",
        "banco_origen": "Banco Pichincha",
        "items": [
            { "producto_id": 1, "cantidad": 2, "precio_unitario": 4.20 }
        ],
        "costo_envio": 5.00,
        "descuento": 0,
        "observaciones": "..."
    }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)

    # ── Validación de campos obligatorios ─────────────────────────
    required = ['nombres', 'apellidos', 'cedula', 'telefono', 'tipo_entrega', 'metodo_pago', 'items']
    for field in required:
        if not data.get(field):
            return JsonResponse({'success': False, 'error': f'Campo requerido: {field}'}, status=400)

    if data['tipo_entrega'] == 'SERVIENTREGA' and not data.get('direccion_envio'):
        return JsonResponse({
            'success': False,
            'error': 'Dirección de envío requerida para Servientrega'
        }, status=400)

    # ── Validación específica para TRANSFERENCIA ───────────────────
    if data['metodo_pago'] == 'TRANSFERENCIA':
        if not data.get('numero_comprobante'):
            return JsonResponse({
                'success': False,
                'error': 'El número de comprobante es requerido para pagos por transferencia'
            }, status=400)

    if not data.get('items'):
        return JsonResponse({'success': False, 'error': 'El pedido no tiene productos'}, status=400)

    # ── Procesar imagen base64 del comprobante ─────────────────────
    comprobante_base64_limpio = ''
    comprobante_content_type = ''

    if data.get('comprobante_base64'):
        raw = data['comprobante_base64'].strip()
        try:
            if ',' in raw and raw.startswith('data:'):
                # Formato completo: "data:image/jpeg;base64,/9j/..."
                header, encoded = raw.split(',', 1)
                content_type = header.split(':')[1].split(';')[0].strip()
            else:
                # Base64 puro sin header
                encoded = raw
                content_type = ''

            # Validar tipo de imagen permitido
            allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
            if content_type and content_type not in allowed_types:
                return JsonResponse({
                    'success': False,
                    'error': f'Tipo de imagen no permitido: {content_type}. Use JPEG, PNG, WEBP o GIF'
                }, status=400)

            # Decodificar para validar
            decoded = base64.b64decode(encoded)

            # Validar tamaño máximo 5MB
            if len(decoded) > 5 * 1024 * 1024:
                return JsonResponse({
                    'success': False,
                    'error': 'La imagen del comprobante no puede superar 5MB'
                }, status=400)

            # Detectar tipo real
            detected = imghdr.what(None, decoded)
            if not detected:
                return JsonResponse({
                    'success': False,
                    'error': 'El archivo enviado no es una imagen válida'
                }, status=400)

            if not content_type:
                content_type = f'image/{detected}'

            comprobante_base64_limpio = encoded
            comprobante_content_type = content_type

        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'comprobante_base64 inválido. Use formato: data:image/jpeg;base64,<datos>'
            }, status=400)

    # ── Verificar stock ───────────────────────────────────────────
    items_procesados = []
    errores_stock = []

    for item in data['items']:
        try:
            producto = Producto.objects.get(id=item['producto_id'], activo=True)
            cantidad = int(item['cantidad'])
            if producto.stock_actual < cantidad:
                errores_stock.append(
                    f"{producto.nombre}: disponible {int(producto.stock_actual)}, solicitado {cantidad}"
                )
            else:
                items_procesados.append({
                    'producto': producto,
                    'cantidad': cantidad,
                    'precio_unitario': Decimal(str(item.get('precio_unitario', producto.precio_venta))),
                })
        except Producto.DoesNotExist:
            errores_stock.append(f"Producto ID {item.get('producto_id')} no encontrado")

    if errores_stock:
        return JsonResponse({
            'success': False,
            'error': 'Stock insuficiente o producto no encontrado',
            'detalle': errores_stock
        }, status=400)

    # ── Calcular totales ──────────────────────────────────────────
    subtotal = sum(i['precio_unitario'] * i['cantidad'] for i in items_procesados)
    costo_envio = Decimal(str(data.get('costo_envio', 0)))
    descuento = Decimal(str(data.get('descuento', 0)))
    total = subtotal + costo_envio - descuento

    # ── Crear pedido en transacción ───────────────────────────────
    try:
        with transaction.atomic():
            pedido = PedidoOnline.objects.create(
                nombres_comprador=data['nombres'],
                apellidos_comprador=data['apellidos'],
                cedula_comprador=data['cedula'],
                telefono_comprador=data['telefono'],
                email_comprador=data.get('email', ''),
                tipo_entrega=data['tipo_entrega'],
                direccion_envio=data.get('direccion_envio', ''),
                ciudad_envio=data.get('ciudad_envio', ''),
                provincia_envio=data.get('provincia_envio', ''),
                referencia_envio=data.get('referencia_envio', ''),
                metodo_pago=data['metodo_pago'],
                # ── Datos de transferencia ────────────────────────
                numero_comprobante=data.get('numero_comprobante', ''),
                banco_origen=data.get('banco_origen', ''),
                comprobante_base64=comprobante_base64_limpio,
                comprobante_content_type=comprobante_content_type,
                # ─────────────────────────────────────────────────
                subtotal=subtotal,
                costo_envio=costo_envio,
                descuento=descuento,
                total=total,
                observaciones=data.get('observaciones', ''),
            )

            for item in items_procesados:
                DetallePedidoOnline.objects.create(
                    pedido=pedido,
                    producto=item['producto'],
                    nombre_producto=item['producto'].nombre,
                    codigo_producto=item['producto'].codigo_unico,
                    cantidad=item['cantidad'],
                    precio_unitario=item['precio_unitario'],
                    subtotal=item['precio_unitario'] * item['cantidad'],
                    total=item['precio_unitario'] * item['cantidad'],
                )
                item['producto'].stock_actual -= item['cantidad']
                item['producto'].save()

        numero_tienda = os.environ.get('WHATSAPP_TIENDA', '593999999999')

        return JsonResponse({
            'success': True,
            'numero_orden': pedido.numero_orden,
            'total': float(pedido.total),
            'estado': pedido.estado,
            'whatsapp_url': pedido.get_whatsapp_url(numero_tienda),
            'mensaje': f'Pedido #{pedido.numero_orden} creado correctamente',
        }, status=201)

    except Exception as e:
        logger.error(f"Error creando pedido online: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Error interno: {str(e)}'}, status=500)

@requiere_token_api
def api_estado_pedido(request, numero_orden):
    """
    Consulta el estado de un pedido.
    GET /ventas/api/publica/pedidos/<numero_orden>/estado/
    """
    try:
        pedido = PedidoOnline.objects.get(numero_orden=numero_orden)
        return JsonResponse({
            'success': True,
            'numero_orden': pedido.numero_orden,
            'estado': pedido.estado,
            'estado_display': pedido.get_estado_display(),
            'estado_pago': pedido.estado_pago,
            'numero_guia': pedido.numero_guia or '',
            'fecha_pedido': pedido.fecha_pedido.strftime('%d/%m/%Y %H:%M'),
        })
    except PedidoOnline.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pedido no encontrado'}, status=404)


# ──────────────────────────────────────────────────────────────────────
#  PANEL ADMIN — gestión de pedidos online
# ──────────────────────────────────────────────────────────────────────

@login_required
def lista_pedidos_online(request):
    """Panel con todos los pedidos online"""
    estado = request.GET.get('estado', '')
    metodo_pago = request.GET.get('metodo_pago', '')
    busqueda = request.GET.get('q', '').strip()

    pedidos = PedidoOnline.objects.all().prefetch_related('detalles')

    if estado:
        pedidos = pedidos.filter(estado=estado)
    if metodo_pago:
        pedidos = pedidos.filter(metodo_pago=metodo_pago)
    if busqueda:
        from django.db.models import Q
        pedidos = pedidos.filter(
            Q(numero_orden__icontains=busqueda) |
            Q(nombres_comprador__icontains=busqueda) |
            Q(apellidos_comprador__icontains=busqueda) |
            Q(cedula_comprador__icontains=busqueda) |
            Q(telefono_comprador__icontains=busqueda)
        )

    pedidos = pedidos.order_by('-fecha_pedido')

    # Estadísticas rápidas
    from django.db.models import Sum, Count
    stats = {
        'pendientes': PedidoOnline.objects.filter(estado='PENDIENTE').count(),
        'confirmados': PedidoOnline.objects.filter(estado='CONFIRMADO').count(),
        'despachados': PedidoOnline.objects.filter(estado='DESPACHADO').count(),
        'entregados_hoy': PedidoOnline.objects.filter(
            estado='ENTREGADO',
            fecha_entrega__date=timezone.now().date()
        ).count(),
        'ingresos_hoy': PedidoOnline.objects.filter(
            estado__in=['CONFIRMADO', 'PREPARANDO', 'DESPACHADO', 'ENTREGADO'],
            fecha_pedido__date=timezone.now().date()
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
    }

    paginator = Paginator(pedidos, 20)
    page = request.GET.get('page', 1)
    pedidos_paginados = paginator.get_page(page)

    return render(request, 'ventas/pedidos_online/lista.html', {
        'active_page': 'ventas',
        'active_sub': 'pedidos_online',
        'pedidos': pedidos_paginados,
        'stats': stats,
        'estado_filtro': estado,
        'metodo_pago_filtro': metodo_pago,
        'busqueda': busqueda,
        'estados': PedidoOnline.ESTADO_CHOICES,
        'metodos_pago': PedidoOnline.METODO_PAGO_CHOICES,
    })


@login_required
def detalle_pedido_online(request, pedido_id):
    """Detalle de un pedido online"""
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)
    detalles = pedido.detalles.select_related('producto')

    # Construir URL de WhatsApp apuntando al número del CLIENTE
    whatsapp_url = None
    if pedido.telefono_comprador:
        import urllib.parse

        # Limpiar el número: dejar solo dígitos
        telefono = ''.join(filter(str.isdigit, pedido.telefono_comprador))

        # Convertir a formato internacional Ecuador
        # 0991234567 (10 dígitos con 0) → 593991234567
        if telefono.startswith('0') and len(telefono) == 10:
            telefono = '593' + telefono[1:]
        # 991234567 (9 dígitos sin 0) → 593991234567
        elif len(telefono) == 9:
            telefono = '593' + telefono
        # Si ya empieza con 593, dejarlo igual

        mensaje = (
            f"Hola {pedido.nombres_comprador}, le contactamos desde *Vpmotos* "
            f"en relación a su pedido *#{pedido.numero_orden}* "
            f"por un total de *${pedido.total:.2f}*. ¿En qué le podemos ayudar?"
        )
        whatsapp_url = f"https://wa.me/{telefono}?text={urllib.parse.quote(mensaje)}"

    return render(request, 'ventas/pedidos_online/detalle.html', {
        'active_page': 'ventas',
        'pedido': pedido,
        'detalles': detalles,
        'whatsapp_url': whatsapp_url,
    })


@login_required
@require_POST
def confirmar_pedido_online(request, pedido_id):
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)
    if pedido.estado == 'PENDIENTE':
        pedido.confirmar()
        messages.success(request, f'Pedido #{pedido.numero_orden} confirmado.')
    else:
        messages.error(request, 'El pedido no está en estado pendiente.')
    return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)


@login_required
@require_POST
def despachar_pedido_online(request, pedido_id):
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)
    numero_guia = request.POST.get('numero_guia', '')
    if pedido.estado in ('CONFIRMADO', 'PREPARANDO'):
        pedido.despachar(numero_guia=numero_guia or None)
        messages.success(request, f'Pedido #{pedido.numero_orden} despachado.')
    else:
        messages.error(request, 'El pedido no está listo para despachar.')
    return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)


@login_required
@require_POST
def entregar_pedido_online(request, pedido_id):
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)
    if pedido.estado == 'DESPACHADO':
        pedido.entregar()
        messages.success(request, f'Pedido #{pedido.numero_orden} marcado como entregado.')
    else:
        messages.error(request, 'El pedido no está despachado.')
    return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)


@login_required
@require_POST
def cancelar_pedido_online(request, pedido_id):
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)
    if pedido.cancelar():
        messages.success(request, f'Pedido #{pedido.numero_orden} cancelado. Stock revertido.')
    else:
        messages.error(request, 'No se puede cancelar este pedido.')
    return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)


@login_required
@require_POST
@transaction.atomic
def procesar_venta_desde_pedido(request, pedido_id):
    """
    Convierte un pedido online en una Venta real del POS.
    Se usa cuando el cliente paga en tienda (RETIRO) o se confirma el pago.
    """
    pedido = get_object_or_404(PedidoOnline, pk=pedido_id)

    if pedido.venta:
        messages.warning(request, 'Este pedido ya tiene una venta asociada.')
        return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)

    if pedido.estado == 'CANCELADO':
        messages.error(request, 'No se puede procesar un pedido cancelado.')
        return redirect('ventas:detalle_pedido_online', pedido_id=pedido.id)

    # Obtener o crear cliente
    cliente = pedido.cliente or Cliente.get_consumidor_final()

    # Mapear método de pago al formato del POS
    tipo_pago_map = {
        'PAYPHONE':       'TARJETA',
        'TRANSFERENCIA':  'TRANSFERENCIA',
        'CONTRA_ENTREGA': 'EFECTIVO',
    }
    tipo_pago = tipo_pago_map.get(pedido.metodo_pago, 'EFECTIVO')

    # Crear venta
    venta = Venta.objects.create(
        cliente=cliente,
        usuario=request.user,
        subtotal=pedido.subtotal,
        iva=Decimal('0.00'),
        descuento=pedido.descuento,
        total=pedido.total,
        tipo_pago=tipo_pago,
        observaciones=f'Pedido online #{pedido.numero_orden}',
    )

    # Crear detalles de venta (el stock ya fue descontado al crear el pedido)
    for detalle in pedido.detalles.all():
        DetalleVenta.objects.create(
            venta=venta,
            producto=detalle.producto,
            cantidad=detalle.cantidad,
            precio_unitario=detalle.precio_unitario,
            subtotal=detalle.subtotal,
            iva_porcentaje=Decimal('0.00'),
            iva=Decimal('0.00'),
            descuento=detalle.descuento,
            total=detalle.total,
        )

    # Vincular pedido con venta
    pedido.venta = venta
    pedido.estado_pago = 'PAGADO'
    if pedido.estado not in ('DESPACHADO', 'ENTREGADO'):
        pedido.estado = 'CONFIRMADO'
        pedido.fecha_confirmacion = timezone.now()
    pedido.save()

    messages.success(request, f'Venta {venta.numero_factura} creada desde pedido #{pedido.numero_orden}.')
    return redirect('ventas:detalle_venta', venta_id=venta.id)
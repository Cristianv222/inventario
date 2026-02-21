from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q, Sum, Count, Case, When, IntegerField, F, Avg, DecimalField
from django.core.paginator import Paginator
from django.template.loader import get_template
from django.db import transaction, connection
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
# Python standard library
from decimal import Decimal
import json
import csv
import barcode
from barcode.writer import ImageWriter
from io import BytesIO, StringIO
import base64
import os
import tempfile
import pandas as pd

# ReportLab para PDFs
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import code128

# Modelos locales
from .models import (
    Producto, 
    CategoriaProducto, 
    Marca, 
    InventarioAjuste, 
    MovimientoInventario,
    TransferenciaInventario,
    DetalleTransferencia,          
)

# Forms locales
from .forms import (
    ProductoForm, 
    CategoriaProductoForm, 
    MarcaForm, 
    InventarioAjusteForm, 
    ProductoSearchForm
)

from .services.transferencias import TransferenciaService

from core.models import Sucursal
from usuarios.models import Usuario
# ========================================
# VISTAS DE PRODUCTOS
# ========================================

@login_required
def lista_productos(request):
    """Vista para listar productos con filtros"""
    form = ProductoSearchForm(request.GET)
    productos = Producto.objects.select_related('categoria', 'marca').all()
    
    # Aplicar filtros
    if form.is_valid():
        # Filtro por texto
        if busqueda := form.cleaned_data.get('busqueda'):
            productos = productos.filter(
                Q(nombre__icontains=busqueda) | 
                Q(codigo_unico__icontains=busqueda) |
                Q(descripcion__icontains=busqueda)
            )
        
        # Filtro por categoría
        if categoria := form.cleaned_data.get('categoria'):
            productos = productos.filter(categoria=categoria)
        
        # Filtro por marca
        if marca := form.cleaned_data.get('marca'):
            productos = productos.filter(marca=marca)
        
        # Filtro por stock bajo
        if form.cleaned_data.get('stock_bajo'):
            productos = productos.filter(stock_actual__lte=F('stock_minimo'))
        
        # Filtro por estado (activo/inactivo)
        activo = form.cleaned_data.get('activo')
        if activo == '1':
            productos = productos.filter(activo=True)
        elif activo == '0':
            productos = productos.filter(activo=False)
    
    # Estadísticas
    estadisticas = {
        'total_productos': Producto.objects.count(),
        'productos_stock_bajo': Producto.objects.filter(
            stock_actual__lte=F('stock_minimo'), activo=True
        ).count(),
        'productos_sin_stock': Producto.objects.filter(stock_actual=0, activo=True).count(),
        'categorias': CategoriaProducto.objects.filter(activa=True).count(),
        'marcas': Marca.objects.filter(activa=True).count(),
    }
    
    # Paginación
    paginator = Paginator(productos, 25)  # 25 productos por página
    page_number = request.GET.get('page')
    productos_page = paginator.get_page(page_number)
    
    return render(request, 'inventario/lista_productos.html', {
        'active_page': 'inventario',
        'productos': productos_page,
        'form': form,
        'estadisticas': estadisticas
    })

@login_required
def buscar_productos_etiquetas(request):
    """API para buscar productos para generar etiquetas"""
    query = request.GET.get('q', '')
    if not query or len(query) < 2:
        return JsonResponse({'products': []})
    
    # Buscar productos que coincidan con la consulta
    productos = Producto.objects.filter(
        Q(nombre__icontains=query) | 
        Q(codigo_unico__icontains=query)
    ).select_related('categoria', 'marca')[:20]
    
    # Formatear resultados
    results = []
    for producto in productos:
        results.append({
            'id': producto.id,
            'nombre': producto.nombre,
            'codigo': producto.codigo_unico,
            'precio': float(producto.precio_venta),
            'categoria': producto.categoria.nombre,
            'marca': producto.marca.nombre,
        })
    
    return JsonResponse({'products': results})

@login_required
def detalle_producto(request, producto_id):
    """Vista para ver detalle de un producto"""
    producto = get_object_or_404(Producto, pk=producto_id)
    
    # Obtener movimientos recientes
    movimientos = MovimientoInventario.objects.filter(producto=producto).order_by('-fecha_hora')[:10]
    ajustes = InventarioAjuste.objects.filter(producto=producto).order_by('-fecha_hora')[:10]
    
    return render(request, 'inventario/detalle_producto.html', {
        'active_page': 'inventario',
        'producto': producto,
        'movimientos': movimientos,
        'ajustes': ajustes
    })

@login_required
def crear_producto(request):
    """Vista para crear un nuevo producto"""
    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f"Producto '{producto.nombre}' creado correctamente")
            return redirect('inventario:detalle_producto', producto_id=producto.id)
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        # Inicializar con código de URL si está presente
        initial = {}
        codigo = request.GET.get('codigo')
        if codigo:
            initial['codigo_unico'] = codigo
        
        form = ProductoForm(initial=initial)
    
    return render(request, 'inventario/producto_form.html', {
        'active_page': 'inventario',
        'form': form,
        'es_nuevo': True
    })

@login_required
def editar_producto(request, producto_id):
    """Vista para editar un producto existente - CORREGIDA"""
    producto = get_object_or_404(Producto, pk=producto_id)
    
    if request.method == 'POST':
        form = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f"Producto '{producto.nombre}' actualizado correctamente")
            return redirect('inventario:detalle_producto', producto_id=producto.id)
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        # ✅ CORRECCIÓN: Pasar la instancia al formulario para que cargue todos los datos
        form = ProductoForm(instance=producto)
    
    return render(request, 'inventario/producto_form.html', {
        'active_page': 'inventario',
        'form': form,
        'producto': producto,
        'es_nuevo': False
    })

@login_required
@require_POST
def activar_desactivar_producto(request, producto_id):
    """Vista para activar/desactivar un producto"""
    producto = get_object_or_404(Producto, pk=producto_id)
    producto.activo = not producto.activo
    producto.save()
    
    estado = "activado" if producto.activo else "desactivado"
    messages.success(request, f"Producto '{producto.nombre}' {estado} correctamente")
    
    return redirect('inventario:lista_productos')

@login_required
def regenerar_codigo_barras(request, producto_id):
    """Vista para regenerar el código de barras de un producto"""
    producto = get_object_or_404(Producto, pk=producto_id)
    resultado = producto.generar_codigo_barras()
    
    if resultado:
        messages.success(request, f"Código de barras para '{producto.nombre}' regenerado correctamente")
    else:
        messages.error(request, f"Error al regenerar código de barras para '{producto.nombre}'")
    
    return redirect('inventario:detalle_producto', producto_id=producto.id)

# ========================================
# VISTAS DE CATEGORÍAS
# ========================================

@login_required
def lista_categorias(request):
    """Vista para listar categorías de productos"""
    categorias = CategoriaProducto.objects.all()
    
    # Agregar conteo de productos y cálculos de ganancia por categoría
    categorias = categorias.annotate(
        num_productos=Count('productos'),
        num_activos=Count(
            Case(
                When(productos__activo=True, then=1),
                output_field=IntegerField()
            )
        ),
        # Calcular promedio de precios
        precio_compra_promedio=Avg(
            'productos__precio_compra',
            filter=Q(productos__activo=True, productos__precio_compra__gt=0)
        ),
        precio_venta_promedio=Avg(
            'productos__precio_venta',
            filter=Q(productos__activo=True, productos__precio_venta__gt=0)
        ),
    )
    
    # Estadísticas generales
    estadisticas = {
        'total_categorias': CategoriaProducto.objects.count(),
        'categorias_activas': CategoriaProducto.objects.filter(activa=True).count(),
        'categorias_inactivas': CategoriaProducto.objects.filter(activa=False).count(),
        # Ganancia promedio general
        'ganancia_promedio_general': Producto.objects.filter(
            activo=True,
            precio_compra__gt=0,
            precio_venta__gt=0
        ).aggregate(
            ganancia=Avg(
                (F('precio_venta') - F('precio_compra')) / F('precio_compra') * 100,
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        )['ganancia'] or 0
    }
    
    return render(request, 'inventario/lista_categorias.html', {
        'active_page': 'inventario',
        'categorias': categorias,
        'estadisticas': estadisticas
    })

@login_required
def crear_categoria(request):
    """Vista para crear una nueva categoría"""
    if request.method == 'POST':
        form = CategoriaProductoForm(request.POST)
        if form.is_valid():
            categoria = form.save()
            messages.success(request, f"Categoría '{categoria.nombre}' creada correctamente")
            return redirect('inventario:lista_categorias')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        form = CategoriaProductoForm()
    
    return render(request, 'inventario/categoria_form.html', {
        'active_page': 'inventario',
        'form': form,
        'es_nueva': True
    })

@login_required
def editar_categoria(request, categoria_id):
    """Vista para editar una categoría"""
    categoria = get_object_or_404(CategoriaProducto, pk=categoria_id)
    
    if request.method == 'POST':
        form = CategoriaProductoForm(request.POST, instance=categoria)
        if form.is_valid():
            categoria = form.save()
            messages.success(request, f"Categoría '{categoria.nombre}' actualizada correctamente")
            return redirect('inventario:lista_categorias')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        form = CategoriaProductoForm(instance=categoria)
    
    return render(request, 'inventario/categoria_form.html', {
        'active_page': 'inventario',
        'form': form,
        'categoria': categoria,
        'es_nueva': False
    })

@login_required
@require_POST
def activar_desactivar_categoria(request, categoria_id):
    """Vista para activar/desactivar una categoría"""
    categoria = get_object_or_404(CategoriaProducto, pk=categoria_id)
    categoria.activa = not categoria.activa
    categoria.save()
    
    estado = "activada" if categoria.activa else "desactivada"
    messages.success(request, f"Categoría '{categoria.nombre}' {estado} correctamente")
    
    return redirect('inventario:lista_categorias')

# ========================================
# VISTAS DE MARCAS
# ========================================

@login_required
def lista_marcas(request):
    """Vista para listar marcas con filtros"""
    # Obtener todas las marcas
    marcas = Marca.objects.all()
    
    # Agregar conteo de productos por marca
    marcas = marcas.annotate(
        num_productos=Count('productos'),
        num_activos=Count(
            Case(
                When(productos__activo=True, then=1),
                output_field=IntegerField()
            )
        )
    )
    
    # Aplicar filtros si es necesario
    filtro_nombre = request.GET.get('nombre', '')
    if filtro_nombre:
        marcas = marcas.filter(nombre__icontains=filtro_nombre)
    
    # Solo mostrar activas/inactivas
    filtro_activas = request.GET.get('activas')
    if filtro_activas == '1':
        marcas = marcas.filter(activa=True)
    elif filtro_activas == '0':
        marcas = marcas.filter(activa=False)
    
    # Estadísticas
    estadisticas = {
        'total_marcas': Marca.objects.count(),
        'marcas_activas': Marca.objects.filter(activa=True).count(),
        'marcas_inactivas': Marca.objects.filter(activa=False).count(),
        'marcas_con_productos': Marca.objects.filter(productos__isnull=False).distinct().count()
    }
    
    # Paginación
    paginator = Paginator(marcas, 25)  # 25 marcas por página
    page_number = request.GET.get('page')
    marcas_page = paginator.get_page(page_number)
    
    return render(request, 'inventario/lista_marcas.html', {
        'active_page': 'inventario',
        'marcas': marcas_page,
        'filtro_nombre': filtro_nombre,
        'filtro_activas': filtro_activas,
        'estadisticas': estadisticas
    })

@login_required
def crear_marca(request):
    """Vista para crear una nueva marca"""
    if request.method == 'POST':
        form = MarcaForm(request.POST)
        if form.is_valid():
            marca = form.save()
            messages.success(request, f"Marca '{marca.nombre}' creada correctamente")
            return redirect('inventario:lista_marcas')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        form = MarcaForm()
    
    return render(request, 'inventario/marca_form.html', {
        'active_page': 'inventario',
        'form': form,
        'es_nueva': True
    })

@login_required
def editar_marca(request, marca_id):
    """Vista para editar una marca"""
    marca = get_object_or_404(Marca, pk=marca_id)
    
    if request.method == 'POST':
        form = MarcaForm(request.POST, instance=marca)
        if form.is_valid():
            marca = form.save()
            messages.success(request, f"Marca '{marca.nombre}' actualizada correctamente")
            return redirect('inventario:lista_marcas')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        form = MarcaForm(instance=marca)
    
    return render(request, 'inventario/marca_form.html', {
        'active_page': 'inventario',
        'form': form,
        'marca': marca,
        'es_nueva': False
    })

@login_required
@require_POST
def activar_desactivar_marca(request, marca_id):
    """Vista para activar/desactivar una marca"""
    marca = get_object_or_404(Marca, pk=marca_id)
    marca.activa = not marca.activa
    marca.save()
    
    estado = "activada" if marca.activa else "desactivada"
    messages.success(request, f"Marca '{marca.nombre}' {estado} correctamente")
    
    return redirect('inventario:lista_marcas')

# ========================================
# VISTAS DE AJUSTES DE INVENTARIO
# ========================================

@login_required
def lista_ajustes(request):
    """Vista para listar ajustes de inventario con filtros"""
    ajustes = InventarioAjuste.objects.select_related('producto', 'usuario').all().order_by('-fecha_hora')
    
    # Aplicar filtros
    producto_id = request.GET.get('producto')
    if producto_id:
        ajustes = ajustes.filter(producto_id=producto_id)
    
    tipo_ajuste = request.GET.get('tipo')
    if tipo_ajuste:
        ajustes = ajustes.filter(tipo_ajuste=tipo_ajuste)
    
    fecha_desde = request.GET.get('fecha_desde')
    if fecha_desde:
        ajustes = ajustes.filter(fecha_hora__date__gte=fecha_desde)
    
    fecha_hasta = request.GET.get('fecha_hasta')
    if fecha_hasta:
        ajustes = ajustes.filter(fecha_hora__date__lte=fecha_hasta)
    
    # Obtener todos los ajustes sin filtros para las estadísticas
    todos_ajustes = InventarioAjuste.objects.all()
    
    # Estadísticas (basadas en todos los ajustes, no filtrados)
    estadisticas = {
        'total_ajustes': todos_ajustes.count(),
        'ajustes_entrada': todos_ajustes.filter(tipo_ajuste='ENTRADA').count(),
        'ajustes_salida': todos_ajustes.filter(tipo_ajuste='SALIDA').count(),
        'ajustes_absolutos': todos_ajustes.filter(tipo_ajuste='AJUSTE').count(),
    }
    
    # Obtener productos para el filtro
    productos_opciones = Producto.objects.filter(activo=True).order_by('nombre')
    
    # Paginación
    paginator = Paginator(ajustes, 25)  # 25 ajustes por página
    page_number = request.GET.get('page')
    ajustes_page = paginator.get_page(page_number)
    
    return render(request, 'inventario/lista_ajustes.html', {
        'active_page': 'inventario',
        'ajustes': ajustes_page,
        'estadisticas': estadisticas,
        'productos_opciones': productos_opciones,
    })

@login_required
def crear_ajuste(request):
    """Vista para crear un nuevo ajuste de inventario"""
    if request.method == 'POST':
        form = InventarioAjusteForm(request.POST)
        if form.is_valid():
            ajuste = form.save(commit=False)
            ajuste.usuario = request.user
            ajuste.save()  # El stock se actualiza en el modelo
            
            messages.success(request, f"Ajuste de inventario para '{ajuste.producto.nombre}' registrado correctamente")
            return redirect('inventario:lista_ajustes')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario")
    else:
        # Precargar producto si viene en la URL
        initial = {}
        producto_id = request.GET.get('producto_id')
        if producto_id:
            try:
                producto = Producto.objects.get(pk=producto_id)
                initial['producto'] = producto
            except Producto.DoesNotExist:
                pass
        
        form = InventarioAjusteForm(initial=initial)
    
    return render(request, 'inventario/ajuste_form.html', {
        'active_page': 'inventario',
        'form': form
    })

# ========================================
# APIS PARA CÁLCULO DE PRECIOS
# ========================================

@login_required
def api_categoria_porcentaje(request):
    """API para obtener el porcentaje de ganancia de una categoría"""
    try:
        categoria_id = request.GET.get('categoria_id')
        
        if not categoria_id:
            return JsonResponse({'success': False, 'message': 'ID de categoría requerido'})
        
        try:
            categoria = CategoriaProducto.objects.get(pk=categoria_id)
            return JsonResponse({
                'success': True,
                'porcentaje_ganancia': float(categoria.porcentaje_ganancia),
                'nombre_categoria': categoria.nombre
            })
        except CategoriaProducto.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Categoría no encontrada'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def calcular_precio_venta(request):
    """API para calcular precio de venta basado en precio de compra y categoría"""
    try:
        # Usar Decimal en lugar de float
        precio_compra_str = request.GET.get('precio_compra', '0')
        precio_compra = Decimal(precio_compra_str)
        categoria_id = request.GET.get('categoria_id')
        
        if not precio_compra or precio_compra <= 0:
            return JsonResponse({'success': False, 'message': 'Precio de compra debe ser mayor a 0'})
        
        if not categoria_id:
            return JsonResponse({'success': False, 'message': 'Categoría requerida'})
        
        try:
            categoria = CategoriaProducto.objects.get(pk=categoria_id)
            
            # Usar Decimal para todos los cálculos
            porcentaje = categoria.porcentaje_ganancia / Decimal('100')
            precio_venta = precio_compra * (Decimal('1') + porcentaje)
            
            return JsonResponse({
                'success': True,
                'precio_venta': float(precio_venta.quantize(Decimal('0.01'))),
                'porcentaje_ganancia': float(categoria.porcentaje_ganancia)
            })
            
        except CategoriaProducto.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Categoría no encontrada'})
            
    except (ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'message': f'Precio de compra inválido: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

# ========================================
# EXPORTAR DATOS
# ========================================

@login_required
def exportar_productos(request):
    """Exportar productos a CSV"""
    # Preparar respuesta CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="productos.csv"'
    
    # Crear el escritor CSV
    writer = csv.writer(response)
    # Escribir cabeceras
    writer.writerow([
        'Código', 'Nombre', 'Categoría', 'Marca', 'Precio Compra', 
        'Precio Venta', 'Stock Actual', 'Stock Mínimo', 'Activo'
    ])
    
    # Escribir datos
    productos = Producto.objects.select_related('categoria', 'marca').all()
    for producto in productos:
        writer.writerow([
            producto.codigo_unico,
            producto.nombre,
            producto.categoria.nombre,
            producto.marca.nombre,
            producto.precio_compra,
            producto.precio_venta,
            producto.stock_actual,
            producto.stock_minimo,
            'Sí' if producto.activo else 'No'
        ])
    
    return response

# ========================================
# GENERACIÓN DE ETIQUETAS
# ========================================

@login_required
def imprimir_etiquetas(request):
    """Vista para generar PDF de etiquetas con códigos de barras"""
    # Obtener categorías y marcas para los filtros
    categorias = CategoriaProducto.objects.filter(activa=True).order_by('nombre')
    marcas = Marca.objects.filter(activa=True).order_by('nombre')
    
    return render(request, 'inventario/imprimir_etiquetas.html', {
        'active_page': 'inventario',
        'categorias': categorias,
        'marcas': marcas
    })

@login_required
def generar_etiquetas_pdf(request):
    """Vista mejorada para generar PDF de etiquetas con reportlab"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'mensaje': 'Método no permitido'})

    try:
        datos = json.loads(request.body)
        productos = datos.get('productos', [])
        config = datos.get('config', {})
        
        # Validar que hay productos
        if not productos:
            return JsonResponse({'success': False, 'mensaje': 'No se han seleccionado productos'})
        
        # Configurar el PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # Obtener configuración
        ancho_etiqueta = float(config.get('ancho', 5)) * cm
        alto_etiqueta = float(config.get('alto', 7)) * cm
        columnas = int(config.get('columnas', 2))
        filas = int(config.get('filas', 5))
        
        # Opciones de contenido
        mostrar_nombre = config.get('mostrar_nombre', True)
        mostrar_codigo = config.get('mostrar_codigo', True)
        mostrar_precio = config.get('mostrar_precio', True)
        mostrar_marca = config.get('mostrar_marca', False)
        mostrar_categoria = config.get('mostrar_categoria', False)
        
        # Calcular márgenes para centrar las etiquetas
        ancho_total = columnas * ancho_etiqueta
        alto_total = filas * alto_etiqueta
        margen_x = (width - ancho_total) / 2
        margen_y = (height - alto_total) / 2
        
        # Dibujar etiquetas
        producto_index = 0
        total_productos = len(productos)
        
        while producto_index < total_productos:
            for row in range(filas):
                for col in range(columnas):
                    if producto_index >= total_productos:
                        break
                    
                    # Datos del producto actual
                    producto = productos[producto_index]
                    
                    # Calcular posición de la etiqueta
                    x = margen_x + (col * ancho_etiqueta)
                    y = height - margen_y - ((row + 1) * alto_etiqueta)
                    
                    # Variables para posicionamiento vertical
                    pos_y = y + alto_etiqueta - 15
                    
                    # Nombre del producto
                    if mostrar_nombre:
                        p.setFont("Helvetica-Bold", 9)
                        # Dividir nombre largo en dos líneas
                        nombre = producto['nombre']
                        if len(nombre) > 25:
                            # Buscar un buen punto de corte
                            medio = len(nombre) // 2
                            espacio = nombre.find(' ', medio)
                            if espacio != -1:
                                linea1 = nombre[:espacio]
                                linea2 = nombre[espacio+1:]
                            else:
                                linea1 = nombre[:25]
                                linea2 = nombre[25:]
                            
                            p.drawCentredString(x + ancho_etiqueta/2, pos_y, linea1)
                            p.drawCentredString(x + ancho_etiqueta/2, pos_y - 12, linea2)
                            pos_y -= 24
                        else:
                            p.drawCentredString(x + ancho_etiqueta/2, pos_y, nombre[:30])
                            pos_y -= 12
                    
                    # Marca y categoría
                    if mostrar_marca or mostrar_categoria:
                        p.setFont("Helvetica", 7)
                        info_texto = ""
                        if mostrar_marca and producto.get('marca'):
                            info_texto += producto['marca']
                        if mostrar_categoria and producto.get('categoria'):
                            if info_texto:
                                info_texto += " - "
                            info_texto += producto['categoria']
                        
                        if info_texto:
                            p.drawCentredString(x + ancho_etiqueta/2, pos_y, info_texto[:40])
                            pos_y -= 10
                    
                    # Código de barras
                    if mostrar_codigo:
                        try:
                            barcode_value = str(producto['codigo'])
                            
                            # Calcular dimensiones del código de barras
                            barcode_width = ancho_etiqueta - 10*mm
                            barcode_height = 15*mm
                            
                            # Crear código de barras
                            barcode_obj = code128.Code128(
                                barcode_value,
                                barWidth=0.4*mm,
                                barHeight=barcode_height
                            )
                            
                            # Dibujar código de barras
                            barcode_obj.drawOn(p, 
                                x + (ancho_etiqueta - barcode_width)/2, 
                                pos_y - barcode_height - 5
                            )
                            
                            # Texto del código debajo del código de barras
                            p.setFont("Helvetica", 6)
                            p.drawCentredString(x + ancho_etiqueta/2, pos_y - barcode_height - 15, barcode_value)
                            pos_y -= barcode_height + 20
                            
                        except Exception as e:
                            # Si falla el código de barras, solo mostrar el texto
                            p.setFont("Helvetica", 8)
                            p.drawCentredString(x + ancho_etiqueta/2, pos_y - 10, f"Código: {producto['codigo']}")
                            pos_y -= 20
                    
                    # Precio
                    if mostrar_precio:
                        p.setFont("Helvetica-Bold", 11)
                        precio_texto = f"${float(producto['precio']):.2f}"
                        p.drawCentredString(x + ancho_etiqueta/2, y + 10, precio_texto)
                    
                    producto_index += 1
                
                if producto_index >= total_productos:
                    break
            
            # Nueva página si quedan productos
            if producto_index < total_productos:
                p.showPage()
        
        # Finalizar PDF
        p.save()
        buffer.seek(0)
        
        # Crear respuesta con PDF
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="etiquetas_productos.pdf"'
        return response

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'mensaje': 'Datos JSON inválidos'})
    except Exception as e:
        return JsonResponse({'success': False, 'mensaje': f'Error al generar PDF: {str(e)}'})

@login_required
def api_buscar_productos_etiquetas(request):
    """API específica para buscar productos para etiquetas"""
    try:
        termino = request.GET.get('q', '').strip()
        categoria_id = request.GET.get('categoria', '')
        marca_id = request.GET.get('marca', '')
        limit = int(request.GET.get('limit', 50))
        
        # Filtrar productos activos
        productos = Producto.objects.filter(activo=True).select_related('categoria', 'marca')
        
        # Aplicar filtros
        if termino:
            productos = productos.filter(
                Q(nombre__icontains=termino) |
                Q(codigo_unico__icontains=termino) |
                Q(descripcion__icontains=termino)
            )
        
        if categoria_id:
            productos = productos.filter(categoria_id=categoria_id)
        
        if marca_id:
            productos = productos.filter(marca_id=marca_id)
        
        # Limitar resultados
        productos = productos[:limit]
        
        # Formatear respuesta
        productos_data = []
        for producto in productos:
            productos_data.append({
                'id': producto.id,
                'nombre': producto.nombre,
                'codigo': producto.codigo_unico,
                'precio': float(producto.precio_venta),
                'categoria': producto.categoria.nombre if producto.categoria else None,
                'marca': producto.marca.nombre if producto.marca else None,
                'stock': producto.stock_actual,
                'activo': producto.activo
            })
        
        return JsonResponse({
            'success': True,
            'productos': productos_data,
            'total': len(productos_data)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'mensaje': f'Error en la búsqueda: {str(e)}'
        })

@login_required
def api_categorias_marcas(request):
    """API para obtener categorías y marcas activas"""
    try:
        categorias = CategoriaProducto.objects.filter(activa=True).values('id', 'nombre').order_by('nombre')
        marcas = Marca.objects.filter(activa=True).values('id', 'nombre').order_by('nombre')
        
        return JsonResponse({
            'success': True,
            'categorias': list(categorias),
            'marcas': list(marcas)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'mensaje': f'Error: {str(e)}'
        })

# ========================================
# APIS PARA EL POS (PRODUCTOS)
# ========================================

@login_required
def api_productos(request):
    """API para obtener lista de productos"""
    try:
        search = request.GET.get('q', '').strip()
        limit = int(request.GET.get('limit', 50))
        
        productos = Producto.objects.filter(activo=True)
        
        if search:
            productos = productos.filter(
                Q(nombre__icontains=search) |
                Q(codigo_unico__icontains=search)
            )
        
        productos = productos.select_related('categoria', 'marca')[:limit]
        
        productos_data = []
        for producto in productos:
            productos_data.append({
                'id': producto.id,
                'codigo': producto.codigo_unico,
                'nombre': producto.nombre,
                'precio': float(producto.precio_venta),
                'stock': float(producto.stock_actual),
                'categoria': producto.categoria.nombre if producto.categoria else None,
                'marca': producto.marca.nombre if producto.marca else None,
                'activo': producto.activo,
                'descripcion': producto.descripcion or ''
            })
        
        return JsonResponse({
            'success': True,
            'productos': productos_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def api_buscar_producto_por_codigo(request):
    """API para buscar producto por código"""
    try:
        codigo = request.GET.get('codigo', '').strip().upper()
        
        if not codigo:
            return JsonResponse({'success': False, 'message': 'Código requerido'})
        
        producto = Producto.objects.filter(
            codigo_unico=codigo,
            activo=True
        ).first()
        
        if producto:
            return JsonResponse({
                'success': True,
                'producto': {
                    'id': producto.id,
                    'codigo': producto.codigo_unico,
                    'nombre': producto.nombre,
                    'precio': float(producto.precio_venta),
                    'stock': float(producto.stock_actual),
                    'categoria': producto.categoria.nombre if producto.categoria else None,
                    'activo': producto.activo
                }
            })
        else:
            return JsonResponse({'success': False, 'message': 'Producto no encontrado'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

# ========================================
# IMPORTACIÓN/EXPORTACIÓN CSV
# ========================================

@login_required
def importar_productos_csv(request):
    """Vista para importar productos desde archivo CSV"""
    if request.method == 'POST':
        # Verificar si se subió un archivo
        if 'archivo_csv' not in request.FILES:
            messages.error(request, 'Por favor selecciona un archivo CSV')
            return redirect('inventario:importar_productos')
        
        archivo_csv = request.FILES['archivo_csv']
        
        # Validar extensión del archivo
        if not archivo_csv.name.endswith('.csv'):
            messages.error(request, 'El archivo debe ser de tipo CSV (.csv)')
            return redirect('inventario:importar_productos')
        
        # Validar tamaño del archivo (máximo 5MB)
        if archivo_csv.size > 5 * 1024 * 1024:
            messages.error(request, 'El archivo es demasiado grande. Máximo 5MB permitido.')
            return redirect('inventario:importar_productos')
        
        try:
            # Leer el archivo CSV
            contenido = archivo_csv.read().decode('utf-8-sig')  # utf-8-sig para manejar BOM
            csv_data = csv.DictReader(contenido.splitlines())
            
            # Validar columnas requeridas
            columnas_requeridas = ['codigo_unico', 'nombre', 'categoria', 'marca', 'precio_compra', 'precio_venta']
            columnas_archivo = [col.strip().lower() for col in csv_data.fieldnames]
            
            for col_requerida in columnas_requeridas:
                if col_requerida.lower() not in columnas_archivo:
                    messages.error(request, f'Columna requerida faltante: {col_requerida}')
                    return redirect('inventario:importar_productos')
            
            # Procesar datos
            productos_creados = 0
            productos_actualizados = 0
            errores = []
            fila_numero = 1
            
            with transaction.atomic():
                for fila in csv_data:
                    fila_numero += 1
                    try:
                        # Limpiar y validar datos
                        codigo_unico = fila.get('codigo_unico', '').strip().upper()
                        nombre = fila.get('nombre', '').strip()
                        categoria_nombre = fila.get('categoria', '').strip()
                        marca_nombre = fila.get('marca', '').strip()
                        
                        # Validaciones básicas
                        if not codigo_unico:
                            errores.append(f"Fila {fila_numero}: Código único es requerido")
                            continue
                        
                        if not nombre:
                            errores.append(f"Fila {fila_numero}: Nombre es requerido")
                            continue
                        
                        # Convertir precios
                        try:
                            precio_compra = Decimal(str(fila.get('precio_compra', '0')).replace(',', '.'))
                            precio_venta = Decimal(str(fila.get('precio_venta', '0')).replace(',', '.'))
                        except (ValueError, TypeError):
                            errores.append(f"Fila {fila_numero}: Precios inválidos")
                            continue
                        
                        if precio_compra < 0 or precio_venta < 0:
                            errores.append(f"Fila {fila_numero}: Los precios no pueden ser negativos")
                            continue
                        
                        # Buscar o crear categoría
                        categoria, created = CategoriaProducto.objects.get_or_create(
                            nombre=categoria_nombre,
                            defaults={'activa': True, 'porcentaje_ganancia': Decimal('25.00')}
                        )
                        
                        # Buscar o crear marca
                        marca, created = Marca.objects.get_or_create(
                            nombre=marca_nombre,
                            defaults={'activa': True}
                        )
                        
                        # Datos opcionales
                        descripcion = fila.get('descripcion', '').strip()
                        stock_actual = max(0, int(float(fila.get('stock_actual', '0') or '0')))
                        stock_minimo = max(0, int(float(fila.get('stock_minimo', '5') or '5')))
                        activo = str(fila.get('activo', 'true')).lower() in ['true', '1', 'si', 'sí', 'yes']
                        
                        # Crear o actualizar producto
                        producto, created = Producto.objects.update_or_create(
                            codigo_unico=codigo_unico,
                            defaults={
                                'nombre': nombre,
                                'descripcion': descripcion,
                                'categoria': categoria,
                                'marca': marca,
                                'precio_compra': precio_compra,
                                'precio_venta': precio_venta,
                                'stock_actual': stock_actual,
                                'stock_minimo': stock_minimo,
                                'activo': activo,
                            }
                        )
                        
                        if created:
                            productos_creados += 1
                        else:
                            productos_actualizados += 1
                            
                    except Exception as e:
                        errores.append(f"Fila {fila_numero}: Error procesando - {str(e)}")
                        continue
            
            # Mostrar resultados
            if productos_creados > 0 or productos_actualizados > 0:
                mensaje = f"Importación completada: {productos_creados} productos creados, {productos_actualizados} actualizados"
                messages.success(request, mensaje)
            
            if errores:
                # Guardar errores en sesión para mostrar en la página
                request.session['errores_importacion'] = errores[:50]  # Limitar a 50 errores
                messages.warning(request, f"Se encontraron {len(errores)} errores. Revisa los detalles.")
            
            return redirect('inventario:importar_productos')
            
        except UnicodeDecodeError:
            messages.error(request, 'Error de codificación. Asegúrate de que el archivo esté en formato UTF-8')
        except Exception as e:
            messages.error(request, f'Error procesando archivo: {str(e)}')
            
        return redirect('inventario:importar_productos')
    
    # GET request - mostrar formulario
    errores_sesion = request.session.get('errores_importacion', [])
    
    # Limpiar errores de la sesión después de mostrarlos
    if 'errores_importacion' in request.session:
        del request.session['errores_importacion']
    
    return render(request, 'inventario/importar_productos.html', {
        'active_page': 'inventario',
        'errores': errores_sesion
    })

@login_required
def exportar_productos_csv(request):
    """Exportar productos a CSV con todas las columnas"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="productos_exportacion.csv"'
    
    # Agregar BOM para Excel
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # Escribir cabeceras
    writer.writerow([
        'codigo_unico',
        'nombre', 
        'descripcion',
        'categoria',
        'marca',
        'precio_compra',
        'precio_venta',
        'stock_actual',
        'stock_minimo',
        'activo',
        'fecha_creacion'
    ])
    
    # Escribir datos de productos
    productos = Producto.objects.select_related('categoria', 'marca').all().order_by('codigo_unico')
    
    for producto in productos:
        writer.writerow([
            producto.codigo_unico,
            producto.nombre,
            producto.descripcion or '',
            producto.categoria.nombre if producto.categoria else '',
            producto.marca.nombre if producto.marca else '',
            float(producto.precio_compra),
            float(producto.precio_venta),
            int(producto.stock_actual),
            int(producto.stock_minimo),
            'true' if producto.activo else 'false',
            producto.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if hasattr(producto, 'fecha_creacion') else ''
        ])
    
    return response

@login_required
def descargar_csv_ejemplo(request):
    """Descargar archivo CSV de ejemplo para importación"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="ejemplo_productos.csv"'
    
    # Agregar BOM para Excel
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # Escribir cabeceras
    writer.writerow([
        'codigo_unico',
        'nombre',
        'descripcion', 
        'categoria',
        'marca',
        'precio_compra',
        'precio_venta',
        'stock_actual',
        'stock_minimo',
        'activo'
    ])
    
    # Escribir datos de ejemplo
    ejemplos = [
        [
            'PROD-001',
            'Producto Ejemplo 1',
            'Descripción del producto ejemplo',
            'Electrónicos',
            'Samsung',
            '100.00',
            '150.00',
            '50',
            '10',
            'true'
        ],
        [
            'PROD-002', 
            'Producto Ejemplo 2',
            'Otro producto de ejemplo',
            'Hogar',
            'LG',
            '75.50',
            '120.00',
            '25',
            '5',
            'true'
        ],
        [
            'PROD-003',
            'Producto Ejemplo 3',
            '',
            'Ropa',
            'Nike',
            '45.00',
            '89.99',
            '100',
            '20',
            'false'
        ]
    ]
    
    for ejemplo in ejemplos:
        writer.writerow(ejemplo)
    
    return response

@login_required
def validar_csv_ajax(request):
    """API para validar archivo CSV antes de importar"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'mensaje': 'Método no permitido'})
    
    if 'archivo_csv' not in request.FILES:
        return JsonResponse({'success': False, 'mensaje': 'No se recibió archivo'})
    
    archivo_csv = request.FILES['archivo_csv']
    
    try:
        # Validar extensión
        if not archivo_csv.name.endswith('.csv'):
            return JsonResponse({'success': False, 'mensaje': 'El archivo debe ser CSV'})
        
        # Leer contenido
        contenido = archivo_csv.read().decode('utf-8-sig')
        archivo_csv.seek(0)  # Resetear para uso posterior
        
        csv_data = csv.DictReader(contenido.splitlines())
        
        # Validar columnas
        columnas_requeridas = ['codigo_unico', 'nombre', 'categoria', 'marca', 'precio_compra', 'precio_venta']
        columnas_archivo = [col.strip().lower() for col in csv_data.fieldnames if col]
        
        columnas_faltantes = []
        for col in columnas_requeridas:
            if col.lower() not in columnas_archivo:
                columnas_faltantes.append(col)
        
        if columnas_faltantes:
            return JsonResponse({
                'success': False, 
                'mensaje': f'Columnas faltantes: {", ".join(columnas_faltantes)}'
            })
        
        # Contar filas
        filas = list(csv_data)
        total_filas = len(filas)
        
        # Validar algunas filas de muestra
        errores_muestra = []
        for i, fila in enumerate(filas[:5]):  # Solo las primeras 5 filas
            if not fila.get('codigo_unico', '').strip():
                errores_muestra.append(f"Fila {i+2}: Código único vacío")
            if not fila.get('nombre', '').strip():
                errores_muestra.append(f"Fila {i+2}: Nombre vacío")
        
        return JsonResponse({
            'success': True,
            'mensaje': 'Archivo válido',
            'total_filas': total_filas,
            'columnas': list(csv_data.fieldnames),
            'errores_muestra': errores_muestra
        })
        
    except UnicodeDecodeError:
        return JsonResponse({'success': False, 'mensaje': 'Error de codificación UTF-8'})
    except Exception as e:
        return JsonResponse({'success': False, 'mensaje': f'Error: {str(e)}'})

@login_required
def limpiar_errores_sesion(request):
    """Limpiar errores de importación de la sesión"""
    if 'errores_importacion' in request.session:
        del request.session['errores_importacion']
    
    return JsonResponse({'success': True})

# ========================================
# FUNCIONES AUXILIARES PARA CSV
# ========================================

def validar_fila_producto(fila, numero_fila):
    """Validar una fila del CSV y retornar errores"""
    errores = []
    
    # Validar código único
    codigo = fila.get('codigo_unico', '').strip()
    if not codigo:
        errores.append(f"Fila {numero_fila}: Código único es requerido")
    elif len(codigo) > 50:
        errores.append(f"Fila {numero_fila}: Código único muy largo (máx 50 caracteres)")
    
    # Validar nombre
    nombre = fila.get('nombre', '').strip()
    if not nombre:
        errores.append(f"Fila {numero_fila}: Nombre es requerido")
    elif len(nombre) > 200:
        errores.append(f"Fila {numero_fila}: Nombre muy largo (máx 200 caracteres)")
    
    # Validar precios
    try:
        precio_compra = float(fila.get('precio_compra', '0'))
        if precio_compra < 0:
            errores.append(f"Fila {numero_fila}: Precio de compra no puede ser negativo")
    except (ValueError, TypeError):
        errores.append(f"Fila {numero_fila}: Precio de compra inválido")
    
    try:
        precio_venta = float(fila.get('precio_venta', '0'))
        if precio_venta < 0:
            errores.append(f"Fila {numero_fila}: Precio de venta no puede ser negativo")
    except (ValueError, TypeError):
        errores.append(f"Fila {numero_fila}: Precio de venta inválido")
    
    # Validar stock
    try:
        stock_actual = int(float(fila.get('stock_actual', '0')))
        if stock_actual < 0:
            errores.append(f"Fila {numero_fila}: Stock actual no puede ser negativo")
    except (ValueError, TypeError):
        errores.append(f"Fila {numero_fila}: Stock actual inválido")
    
    return errores

def procesar_lote_productos(filas_csv, tamaño_lote=100):
    """Procesar productos en lotes para mejor rendimiento"""
    total_filas = len(filas_csv)
    productos_procesados = 0
    errores_globales = []
    
    for i in range(0, total_filas, tamaño_lote):
        lote = filas_csv[i:i + tamaño_lote]
        
        try:
            with transaction.atomic():
                for j, fila in enumerate(lote):
                    numero_fila = i + j + 2  # +2 porque empezamos en fila 2 (después del header)
                    
                    # Validar fila
                    errores_fila = validar_fila_producto(fila, numero_fila)
                    if errores_fila:
                        errores_globales.extend(errores_fila)
                        continue
                    
                    # Procesar producto
                    # ... lógica de creación/actualización ...
                    productos_procesados += 1
                    
        except Exception as e:
            errores_globales.append(f"Error en lote {i//tamaño_lote + 1}: {str(e)}")
    
    return productos_procesados, errores_globales

@login_required
def transferencias_lista(request):
    """Vista para listar transferencias"""
    # Obtener sucursal del usuario
    sucursal_usuario = request.user.sucursal
    es_admin = request.user.puede_ver_todas_sucursales or request.user.is_superuser
    
    # Cambiar a schema PUBLIC para acceder a transferencias
    from django_tenants.utils import schema_context
    
    with schema_context('principal'):
        # Filtrar transferencias según permisos
        if es_admin:
            # Admin ve todas
            transferencias = TransferenciaInventario.objects.all()
        elif sucursal_usuario:
            # Usuario ve solo las de su sucursal (enviadas o recibidas)
            transferencias = TransferenciaInventario.objects.filter(
                Q(sucursal_origen=sucursal_usuario) | 
                Q(sucursal_destino=sucursal_usuario)
            )
        else:
            # Usuario sin sucursal no ve nada
            transferencias = TransferenciaInventario.objects.none()
        
        # Aplicar filtros
        estado_filtro = request.GET.get('estado')
        if estado_filtro:
            transferencias = transferencias.filter(estado=estado_filtro)
        
        tipo_filtro = request.GET.get('tipo')
        if tipo_filtro == 'enviadas' and sucursal_usuario:
            transferencias = transferencias.filter(sucursal_origen=sucursal_usuario)
        elif tipo_filtro == 'recibidas' and sucursal_usuario:
            transferencias = transferencias.filter(sucursal_destino=sucursal_usuario)
        
        # Búsqueda por número de guía
        busqueda = request.GET.get('busqueda')
        if busqueda:
            transferencias = transferencias.filter(
                Q(numero_guia__icontains=busqueda) |
                Q(observaciones_envio__icontains=busqueda)
            )
        
        # Ordenar y paginar
        transferencias = transferencias.select_related(
            'sucursal_origen',
            'sucursal_destino',
            'usuario_envia',
            'usuario_recibe'
        ).order_by('-fecha_envio')
        
        # Estadísticas
        estadisticas = {
            'total': transferencias.count(),
            'pendientes': transferencias.filter(estado='PENDIENTE').count(),
            'en_transito': transferencias.filter(estado='EN_TRANSITO').count(),
            'recibidas': transferencias.filter(estado='RECIBIDA').count(),
            'canceladas': transferencias.filter(estado='CANCELADA').count(),
        }
        
        # Paginación
        paginator = Paginator(transferencias, 20)
        page_number = request.GET.get('page')
        transferencias_page = paginator.get_page(page_number)
        
        # ✅ AGREGAR: Obtener sucursales disponibles para el modal
        if es_admin:
            sucursales_origen = list(Sucursal.objects.filter(activa=True))
            sucursales_destino = list(Sucursal.objects.filter(activa=True))
        else:
            sucursales_origen = [sucursal_usuario] if sucursal_usuario else []
            sucursales_destino = list(Sucursal.objects.filter(activa=True).exclude(
                id=sucursal_usuario.id if sucursal_usuario else None
            ))
    
    return render(request, 'inventario/transferencias/lista.html', {
        'active_page': 'inventario',
        'transferencias': transferencias_page,
        'estadisticas': estadisticas,
        'es_admin': es_admin,
        # ✅ AGREGAR: Pasar sucursales al contexto
        'sucursales_origen': sucursales_origen,
        'sucursales_destino': sucursales_destino,
    })


@login_required
def transferencia_crear(request):
    """Vista para crear una nueva transferencia"""
    sucursal_usuario = request.user.sucursal
    
    # Validar que el usuario tenga sucursal asignada
    if not sucursal_usuario and not request.user.puede_ver_todas_sucursales:
        messages.error(request, "No tienes una sucursal asignada. Contacta al administrador.")
        return redirect('inventario:transferencias_lista')
    
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            data = json.loads(request.body)
            
            sucursal_destino_id = data.get('sucursal_destino')
            productos = data.get('productos', [])
            observaciones = data.get('observaciones', '')
            
            # Validaciones
            if not sucursal_destino_id:
                return JsonResponse({
                    'success': False,
                    'mensaje': 'Debe seleccionar una sucursal destino'
                })
            
            if not productos:
                return JsonResponse({
                    'success': False,
                    'mensaje': 'Debe agregar al menos un producto'
                })
            
            # Obtener sucursales en schema public
            from django_tenants.utils import schema_context
            
            with schema_context('principal'):
                # Sucursal origen
                if request.user.puede_ver_todas_sucursales:
                    # Admin puede seleccionar origen
                    sucursal_origen_id = data.get('sucursal_origen')
                    if not sucursal_origen_id:
                        return JsonResponse({
                            'success': False,
                            'mensaje': 'Debe seleccionar una sucursal origen'
                        })
                    sucursal_origen = Sucursal.objects.get(id=sucursal_origen_id)
                else:
                    sucursal_origen = sucursal_usuario
                
                sucursal_destino = Sucursal.objects.get(id=sucursal_destino_id)
                
                # Crear transferencia usando el service
                transferencia = TransferenciaService.crear_transferencia(
                    sucursal_origen=sucursal_origen,
                    sucursal_destino=sucursal_destino,
                    usuario=request.user,
                    productos=productos,
                    observaciones=observaciones
                )
            
            return JsonResponse({
                'success': True,
                'mensaje': f'Transferencia #{transferencia.numero_guia} creada correctamente',
                'transferencia_id': transferencia.id,
                'numero_guia': transferencia.numero_guia
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'mensaje': f'Error al crear transferencia: {str(e)}'
            })
    
    # GET - Mostrar formulario
    # IMPORTANTE: Forzar schema public para obtener sucursales
    from django_tenants.utils import schema_context
    
    with schema_context('principal'):
        # Obtener sucursales disponibles
        if request.user.puede_ver_todas_sucursales:
            sucursales_origen = list(Sucursal.objects.filter(activa=True))
            sucursales_destino = list(Sucursal.objects.filter(activa=True))
        else:
            sucursales_origen = [sucursal_usuario] if sucursal_usuario else []
            sucursales_destino = list(Sucursal.objects.filter(activa=True).exclude(
                id=sucursal_usuario.id if sucursal_usuario else None
            ))
    
    return render(request, 'inventario/transferencias/crear.html', {
        'active_page': 'inventario',
        'sucursales_origen': sucursales_origen,
        'sucursales_destino': sucursales_destino,
        'es_admin': request.user.puede_ver_todas_sucursales,
    })


@login_required
def transferencia_detalle(request, transferencia_id):
    """Vista para ver detalle de una transferencia"""
    from django_tenants.utils import schema_context
    
    with schema_context('principal'):
        transferencia = get_object_or_404(
            TransferenciaInventario.objects.select_related(
                'sucursal_origen',
                'sucursal_destino',
                'usuario_envia',
                'usuario_recibe'
            ).prefetch_related('detalles'),
            id=transferencia_id
        )
        
        # Verificar permisos
        sucursal_usuario = request.user.sucursal
        es_admin = request.user.puede_ver_todas_sucursales or request.user.is_superuser
        
        if not es_admin and sucursal_usuario:
            # Verificar que el usuario tenga acceso a esta transferencia
            if transferencia.sucursal_origen.id != sucursal_usuario.id and \
               transferencia.sucursal_destino.id != sucursal_usuario.id:
                messages.error(request, "No tienes permiso para ver esta transferencia")
                return redirect('inventario:transferencias_lista')
        
        # Determinar permisos de acciones
        puede_recibir = (
            transferencia.puede_ser_recibida() and
            sucursal_usuario and
            transferencia.sucursal_destino.id == sucursal_usuario.id
        ) or es_admin
        
        puede_cancelar = (
            transferencia.puede_ser_cancelada() and
            sucursal_usuario and
            transferencia.sucursal_origen.id == sucursal_usuario.id
        ) or es_admin
    
    return render(request, 'inventario/transferencias/detalle.html', {
        'active_page': 'inventario',
        'transferencia': transferencia,
        'puede_recibir': puede_recibir,
        'puede_cancelar': puede_cancelar,
    })


@login_required
def transferencia_recibir(request, transferencia_id):
    """Vista para recibir una transferencia"""
    from django_tenants.utils import schema_context
    
    with schema_context('principal'):
        transferencia = get_object_or_404(
            TransferenciaInventario.objects.select_related(
                'sucursal_origen',
                'sucursal_destino'
            ).prefetch_related('detalles'),
            id=transferencia_id
        )
        
        # Verificar permisos
        sucursal_usuario = request.user.sucursal
        es_admin = request.user.puede_ver_todas_sucursales or request.user.is_superuser
        
        if not es_admin:
            if not sucursal_usuario or transferencia.sucursal_destino.id != sucursal_usuario.id:
                messages.error(request, "No tienes permiso para recibir esta transferencia")
                return redirect('inventario:transferencias_lista')
        
        if not transferencia.puede_ser_recibida():
            messages.error(request, f"La transferencia está en estado {transferencia.estado} y no puede ser recibida")
            return redirect('inventario:transferencia_detalle', transferencia_id=transferencia_id)
        
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                productos_recibidos = data.get('productos', [])
                observaciones = data.get('observaciones', '')
                
                if not productos_recibidos:
                    return JsonResponse({
                        'success': False,
                        'mensaje': 'Debe especificar las cantidades recibidas'
                    })
                
                # Recibir transferencia usando el service
                transferencia = TransferenciaService.recibir_transferencia(
                    transferencia_id=transferencia_id,
                    usuario=request.user,
                    productos_recibidos=productos_recibidos,
                    observaciones=observaciones
                )
                
                return JsonResponse({
                    'success': True,
                    'mensaje': f'Transferencia #{transferencia.numero_guia} recibida correctamente'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'mensaje': f'Error al recibir transferencia: {str(e)}'
                })
        
        # GET - Mostrar formulario
        detalles = transferencia.detalles.all()
    
    return render(request, 'inventario/transferencias/recibir.html', {
        'active_page': 'inventario',
        'transferencia': transferencia,
        'detalles': detalles,
    })


@login_required
def transferencia_cancelar(request, transferencia_id):
    """Vista para cancelar una transferencia"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'mensaje': 'Método no permitido'
        })
    
    try:
        data = json.loads(request.body)
        motivo = data.get('motivo', '')
        
        if not motivo:
            return JsonResponse({
                'success': False,
                'mensaje': 'Debe especificar un motivo de cancelación'
            })
        
        from django_tenants.utils import schema_context
        
        with schema_context('principal'):
            # Cancelar usando el service
            transferencia = TransferenciaService.cancelar_transferencia(
                transferencia_id=transferencia_id,
                usuario=request.user,
                motivo=motivo
            )
        
        return JsonResponse({
            'success': True,
            'mensaje': f'Transferencia #{transferencia.numero_guia} cancelada correctamente'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'mensaje': f'Error al cancelar transferencia: {str(e)}'
        })


# ========================================
# APIS AUXILIARES
# ========================================

@login_required
def api_buscar_productos_transferencia(request):
    """API para buscar productos en la sucursal origen"""
    try:
        sucursal_id = request.GET.get('sucursal_id')
        termino = request.GET.get('q', '').strip()
        
        if not sucursal_id:
            return JsonResponse({
                'success': False,
                'mensaje': 'Sucursal requerida'
            })
        
        from django_tenants.utils import schema_context
        
        with schema_context('principal'):
            # Obtener sucursal
            sucursal = Sucursal.objects.get(id=sucursal_id)
        
        # Cambiar al schema de la sucursal
        with schema_context(sucursal.schema_name):
            # Buscar productos
            productos = Producto.objects.filter(activo=True, stock_actual__gt=0)
            
            if termino:
                productos = productos.filter(
                    Q(nombre__icontains=termino) |
                    Q(codigo_unico__icontains=termino)
                )
            
            productos = productos.select_related('categoria', 'marca')[:20]
            
            # Formatear resultados
            productos_data = []
            for producto in productos:
                productos_data.append({
                    'id': producto.id,
                    'codigo': producto.codigo_unico,
                    'nombre': producto.nombre,
                    'stock': float(producto.stock_actual),
                    'precio_venta': float(producto.precio_venta),
                    'categoria': producto.categoria.nombre if producto.categoria else '',
                    'marca': producto.marca.nombre if producto.marca else '',
                })
        
        return JsonResponse({
            'success': True,
            'productos': productos_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'mensaje': f'Error: {str(e)}'
        })


@login_required
def api_validar_stock(request):
    """API para validar stock disponible"""
    try:
        data = json.loads(request.body)
        sucursal_id = data.get('sucursal_id')
        productos = data.get('productos', [])
        
        from django_tenants.utils import schema_context
        
        with schema_context('principal'):
            sucursal = Sucursal.objects.get(id=sucursal_id)
            
            # Validar usando el service
            es_valido, errores = TransferenciaService.validar_stock_disponible(
                sucursal, 
                productos
            )
        
        return JsonResponse({
            'success': es_valido,
            'errores': errores if not es_valido else []
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'mensaje': f'Error: {str(e)}'
        })

from functools import wraps
from django.http import JsonResponse

def requiere_token_api(view_func):
    """Decorador para proteger endpoints de API con token"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '').strip()
        
        if not token:
            return JsonResponse({
                'success': False,
                'mensaje': 'Token de autenticación requerido'
            }, status=401)
        
        # Validar contra el token configurado en settings
        from django.conf import settings
        token_valido = getattr(settings, 'API_TOKEN', None)
        
        if token_valido and token != token_valido:
            return JsonResponse({
                'success': False,
                'mensaje': 'Token inválido'
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    return wrapper
@login_required
def api_transferencia_detalles(request, transferencia_id):
    """API para obtener detalles de una transferencia"""
    from django_tenants.utils import schema_context
    
    with schema_context('principal'):
        transferencia = get_object_or_404(
            TransferenciaInventario.objects.prefetch_related('detalles'),
            id=transferencia_id
        )
        
        detalles_data = []
        for detalle in transferencia.detalles.all():
            detalles_data.append({
                'producto_id': detalle.producto_id if hasattr(detalle, 'producto_id') else None,
                'producto_codigo': detalle.producto_codigo,
                'producto_nombre': detalle.producto_nombre,
                'cantidad_enviada': float(detalle.cantidad_enviada),
                'cantidad_recibida': float(detalle.cantidad_recibida) if detalle.cantidad_recibida else 0,
            })
    
    return JsonResponse({
        'success': True,
        'detalles': detalles_data
    })

def api_publica_productos(request):
    from django.conf import settings
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8001').rstrip('/')
    
    productos = Producto.objects.filter(activo=True).select_related('categoria', 'marca')
    
    def get_imagen_url(campo):
        try:
            if campo and campo.name:
                return f"{site_url}{campo.url}"
        except Exception:
            pass
        return None

    data = []
    for p in productos:
        data.append({
            'id': p.id,
            'codigo': p.codigo_unico,
            'nombre': p.nombre,
            'descripcion': p.descripcion,
            'precio': float(p.precio_final),
            'stock': p.stock_actual,
            'categoria': p.categoria.nombre if p.categoria else '',
            'marca': p.marca.nombre if p.marca else '',
            'imagen_url': get_imagen_url(getattr(p, 'imagen', None)),
            'imagen_2_url': get_imagen_url(getattr(p, 'imagen_2', None)),
            'imagen_3_url': get_imagen_url(getattr(p, 'imagen_3', None)),
        })
    
    return JsonResponse({'success': True, 'productos': data})
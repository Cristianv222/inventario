from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Sum, Avg, F
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from usuarios.decorators import admin_requerido
from datetime import datetime, timedelta
import json
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_POST

# IMPORTANTE: Si encuentras errores de "column does not exist", ejecuta:
# python manage.py makemigrations taller
# python manage.py migrate taller
# Esto sincronizará los modelos con la base de datos

from .models import (
    Tecnico, EspecialidadTecnica, CategoriaServicio, TipoServicio,
    OrdenTrabajo, ServicioOrden, RepuestoOrden,
    SeguimientoOrden, EvaluacionServicio
)
from .service.cotizacion_service import CotizacionService
from .forms import (
    TipoServicioForm, OrdenTrabajoForm, ServicioOrdenForm,
    RepuestoOrdenForm, EvaluacionServicioForm,
    BusquedaOrdenForm, ServicioOrdenFormSet, RepuestoOrdenFormSet
)
from clientes.models import Cliente, Moto
from inventario.models import Producto

class AdminRequeridoMixin(LoginRequiredMixin):
    """Solo administradores (is_staff / is_superuser). La gestión de técnicos
    (crear/editar) vive en Admin > Técnicos."""
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'Solo un administrador puede ver esta sección.')
            return redirect('taller:dashboard')
        return super().dispatch(request, *args, **kwargs)


# ================== HELPERS ==================

def safe_get_field(obj, field_name, default=None):
    """Obtiene un campo de forma segura, retornando un valor por defecto si no existe"""
    try:
        return getattr(obj, field_name, default)
    except Exception:
        return default

def get_orden_moto_info(orden):
    """Obtiene información de la moto de forma segura"""
    moto_info = {
        'marca': '',
        'modelo': '',
        'placa': '',
        'año': ''
    }
    
    # Intentar obtener de campos directos primero
    for field in ['moto_marca', 'moto_modelo', 'moto_placa', 'moto_año']:
        value = safe_get_field(orden, field)
        if value:
            key = field.replace('moto_', '')
            moto_info[key] = value
    
    # Si no hay campos directos, intentar con relación moto
    if not any(moto_info.values()) and hasattr(orden, 'moto'):
        moto = safe_get_field(orden, 'moto')
        if moto:
            moto_info['marca'] = safe_get_field(moto, 'marca', '')
            moto_info['modelo'] = safe_get_field(moto, 'modelo', '')
            moto_info['placa'] = safe_get_field(moto, 'placa', '')
            moto_info['año'] = safe_get_field(moto, 'año', '')
    
    return moto_info

def check_database_fields():
    """Verifica si los campos del modelo existen en la base de datos"""
    try:
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Verificar campos de OrdenTrabajo
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'taller_ordentrabajo'
            """)
            columns = [col[0] for col in cursor.fetchall()]
            
            # Campos esperados que podrían causar problemas
            expected_fields = ['moto_marca', 'moto_modelo', 'moto_placa', 'moto_año', 'moto_id']
            missing_fields = [field for field in expected_fields if field not in columns]
            
            if missing_fields:
                print(f"ADVERTENCIA: Campos faltantes en taller_ordentrabajo: {missing_fields}")
                print("Ejecuta: python manage.py makemigrations taller && python manage.py migrate taller")
                
            return not bool(missing_fields)
    except Exception as e:
        print(f"No se pudo verificar los campos de la base de datos: {e}")
        return True  # Asumir que está bien para no bloquear la aplicación

# ================== DASHBOARD PRINCIPAL ==================

@login_required
def dashboard_taller(request):
    """Dashboard principal del taller"""
    # Verificar campos de base de datos (solo en DEBUG)
    from django.conf import settings
    if settings.DEBUG:
        check_database_fields()
    
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    
    # Estadísticas generales
    ordenes_pendientes = OrdenTrabajo.objects.filter(estado__in=['PENDIENTE', 'EN_PROCESO']).count()
    ordenes_hoy = OrdenTrabajo.objects.filter(fecha_ingreso__date=hoy).count()
    
    # Estadísticas del mes
    ordenes_mes = OrdenTrabajo.objects.filter(fecha_ingreso__gte=inicio_mes)
    facturacion_mes = ordenes_mes.filter(estado='ENTREGADO').aggregate(
        total=Sum('precio_total')
    )['total'] or 0
    
    # Órdenes recientes - CORRECCIÓN: Removido 'moto' de select_related
    try:
        ordenes_recientes = OrdenTrabajo.objects.select_related(
            'cliente', 'tecnico_principal'
        ).order_by('-fecha_ingreso')[:10]
    except Exception as e:
        # Si hay error con campos que no existen, obtener órdenes sin select_related
        ordenes_recientes = OrdenTrabajo.objects.all().order_by('-fecha_ingreso')[:10]
    
    # Técnicos activos
    tecnicos_activos = Tecnico.objects.filter(estado='ACTIVO').count()
    
    # Servicios más solicitados (este mes)
    servicios_populares = ServicioOrden.objects.filter(
        orden__fecha_ingreso__gte=inicio_mes
    ).values(
        'tipo_servicio__nombre'
    ).annotate(
        cantidad=Count('id')
    ).order_by('-cantidad')[:5]
    
    # Evaluaciones promedio
    evaluacion_promedio = EvaluacionServicio.objects.filter(
        fecha_evaluacion__gte=inicio_mes
    ).aggregate(
        promedio=Avg('calificacion_general')
    )['promedio'] or 0
    
    context = {
        'ordenes_pendientes': ordenes_pendientes,
        'ordenes_hoy': ordenes_hoy,
        'ordenes_mes': ordenes_mes.count(),
        'facturacion_mes': facturacion_mes,
        'ordenes_recientes': ordenes_recientes,
        'tecnicos_activos': tecnicos_activos,
        'servicios_populares': servicios_populares,
        'evaluacion_promedio': round(evaluacion_promedio, 1),
        'hoy': hoy,
        # Helper para obtener info de moto en templates
        'get_orden_moto_info': get_orden_moto_info,
    }
    
    return render(request, 'taller/dashboard.html', context)

# ================== TÉCNICOS ==================

class TecnicoListView(AdminRequeridoMixin, ListView):
    model = Tecnico
    template_name = 'taller/tecnico_list.html'
    context_object_name = 'tecnicos'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Tecnico.objects.prefetch_related('especialidades').order_by('nombres')
        busqueda = self.request.GET.get('busqueda')
        estado = self.request.GET.get('estado')
        
        if busqueda:
            queryset = queryset.filter(
                Q(nombres__icontains=busqueda) |
                Q(apellidos__icontains=busqueda) |
                Q(codigo__icontains=busqueda) |
                Q(identificacion__icontains=busqueda)
            )
        
        if estado:
            queryset = queryset.filter(estado=estado)
            
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'taller'
        context['busqueda'] = self.request.GET.get('busqueda', '')
        context['estado_filtro'] = self.request.GET.get('estado', '')
        context['estados'] = Tecnico.ESTADO_CHOICES
        return context

class TecnicoDetailView(AdminRequeridoMixin, DetailView):
    model = Tecnico
    template_name = 'taller/tecnico_detail.html'
    context_object_name = 'tecnico'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tecnico = self.object
        hoy = timezone.localdate()
        inicio_mes = hoy.replace(day=1)
        
        # Estadísticas del técnico
        context['ordenes_activas'] = tecnico.get_ordenes_activas()
        context['stats_mes'] = tecnico.get_servicios_mes()
        
        # Historial de órdenes recientes - CORRECCIÓN: Removido 'moto'
        context['ordenes_recientes'] = OrdenTrabajo.objects.filter(
            tecnico_principal=tecnico
        ).select_related('cliente').order_by('-fecha_ingreso')[:10]

        # Historial financiero completo (comisiones pagadas, adelantos, inventario a cuenta)
        deudas = _deudas_pendientes(tecnico)
        pagos = list(tecnico.pagos.all()[:50])
        todos_pagos = tecnico.pagos.all()
        context['hist_pagos'] = pagos
        context['hist_adelantos'] = tecnico.adelantos.select_related('pago')[:50]
        context['hist_consumos'] = tecnico.consumos.select_related('producto')[:50]
        context['hist_deuda_adelantos'] = deudas['adelantos_saldo']
        context['hist_deuda_consumos'] = deudas['consumos_saldo']
        context['hist_deuda_total'] = deudas['total']
        context['hist_total_pagado'] = todos_pagos.aggregate(s=Sum('monto_pagado'))['s'] or Decimal('0')
        context['hist_total_comision'] = todos_pagos.aggregate(s=Sum('comision_bruta'))['s'] or Decimal('0')
        context['hist_total_descontado'] = (
            (todos_pagos.aggregate(s=Sum('adelantos_descontados'))['s'] or Decimal('0')) +
            (todos_pagos.aggregate(s=Sum('consumos_descontados'))['s'] or Decimal('0'))
        )
        return context

# ================== TIPOS DE SERVICIO ==================

class TipoServicioListView(LoginRequiredMixin, ListView):
    model = TipoServicio
    template_name = 'taller/tipo_servicio_list.html'
    context_object_name = 'tipos_servicio'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = TipoServicio.objects.select_related('categoria', 'requiere_especialidad')
        busqueda = self.request.GET.get('busqueda')
        categoria = self.request.GET.get('categoria')
        activo = self.request.GET.get('activo')
        
        if busqueda:
            queryset = queryset.filter(
                Q(nombre__icontains=busqueda) |
                Q(codigo__icontains=busqueda)
            )
        
        if categoria:
            queryset = queryset.filter(categoria_id=categoria)
            
        if activo:
            queryset = queryset.filter(activo=activo == 'true')
            
        return queryset.order_by('categoria__nombre', 'nombre')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias'] = CategoriaServicio.objects.filter(activa=True)
        context['busqueda'] = self.request.GET.get('busqueda', '')
        context['categoria_filtro'] = self.request.GET.get('categoria', '')
        return context

class TipoServicioCreateView(LoginRequiredMixin, CreateView):
    model = TipoServicio
    form_class = TipoServicioForm
    template_name = 'taller/tipo_servicio_form.html'
    success_url = reverse_lazy('taller:tipo_servicio_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Tipo de servicio creado exitosamente.')
        return super().form_valid(form)

class TipoServicioUpdateView(LoginRequiredMixin, UpdateView):
    model = TipoServicio
    form_class = TipoServicioForm
    template_name = 'taller/tipo_servicio_form.html'
    success_url = reverse_lazy('taller:tipo_servicio_list')

# ================== ÓRDENES DE TRABAJO ==================

class OrdenTrabajoListView(LoginRequiredMixin, ListView):
    model = OrdenTrabajo
    template_name = 'taller/orden_list.html'
    context_object_name = 'ordenes'
    paginate_by = 25
    
    def get_queryset(self):
        # CORRECCIÓN: Removido 'moto' de select_related
        try:
            queryset = OrdenTrabajo.objects.select_related(
                'cliente', 'tecnico_principal'
            ).prefetch_related('servicios__tipo_servicio')
        except Exception as e:
            # Fallback sin select_related si hay problemas
            queryset = OrdenTrabajo.objects.all()
        
        # Aplicar filtros del formulario de búsqueda
        form = BusquedaOrdenForm(self.request.GET)
        if form.is_valid():
            busqueda = form.cleaned_data.get('busqueda')
            estado = form.cleaned_data.get('estado')
            tecnico = form.cleaned_data.get('tecnico')
            fecha_desde = form.cleaned_data.get('fecha_desde')
            fecha_hasta = form.cleaned_data.get('fecha_hasta')
            
            if busqueda:
                # Filtros básicos que deberían funcionar siempre
                filters = Q(numero_orden__icontains=busqueda)
                
                # Intentar agregar filtros de cliente si existen
                try:
                    filters |= Q(cliente__nombres__icontains=busqueda)
                    filters |= Q(cliente__apellidos__icontains=busqueda)
                except Exception:
                    pass
                
                # Intentar agregar filtro de placa si existe el campo
                try:
                    filters |= Q(moto_placa__icontains=busqueda)
                except Exception:
                    pass
                
                queryset = queryset.filter(filters)
            
            if estado:
                queryset = queryset.filter(estado=estado)
                
            if tecnico:
                queryset = queryset.filter(tecnico_principal=tecnico)
                
            if fecha_desde:
                queryset = queryset.filter(fecha_ingreso__date__gte=fecha_desde)
                
            if fecha_hasta:
                queryset = queryset.filter(fecha_ingreso__date__lte=fecha_hasta)
        
        return queryset.order_by('-fecha_ingreso')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_busqueda'] = BusquedaOrdenForm(self.request.GET)
        
        # Estadísticas rápidas
        context['total_ordenes'] = self.get_queryset().count()
        context['pendientes'] = self.get_queryset().filter(estado='PENDIENTE').count()
        context['en_proceso'] = self.get_queryset().filter(estado='EN_PROCESO').count()
        
        return context

class OrdenTrabajoDetailView(LoginRequiredMixin, DetailView):
    model = OrdenTrabajo
    template_name = 'taller/orden_detail.html'
    context_object_name = 'orden'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orden = self.object
        
        context['servicios'] = orden.servicios.select_related('tipo_servicio', 'tecnico_asignado')
        context['repuestos'] = orden.repuestos_utilizados.select_related('producto')
        context['seguimientos'] = orden.seguimientos.select_related('usuario')[:10]
        
        # Agregar información de la moto de forma segura
        context['moto_info'] = get_orden_moto_info(orden)
        
        # Verificar si hay evaluación
        try:
            context['evaluacion'] = orden.evaluacion
        except EvaluacionServicio.DoesNotExist:
            context['evaluacion'] = None
            
        return context

class OrdenTrabajoCreateView(LoginRequiredMixin, CreateView):
    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = 'taller/orden_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.request.POST:
            context['servicios_formset'] = ServicioOrdenFormSet(
                self.request.POST,
                instance=self.object,
                prefix='servicios'
            )
            context['repuestos_formset'] = RepuestoOrdenFormSet(
                self.request.POST,
                instance=self.object,
                prefix='repuestos'
            )
        else:
            context['servicios_formset'] = ServicioOrdenFormSet(
                instance=self.object,
                prefix='servicios'
            )
            context['repuestos_formset'] = RepuestoOrdenFormSet(
                instance=self.object,
                prefix='repuestos'
            )
        
        # Agregar datos para los templates de JavaScript
        context['servicios_disponibles'] = TipoServicio.objects.filter(
            activo=True
        ).select_related('categoria')
        
        context['tecnicos_disponibles'] = Tecnico.objects.filter(
            estado='ACTIVO', 
            activo=True
        )
        
        return context
    
    @transaction.atomic
    def form_valid(self, form):
        # DEBUG: Agregar al inicio
        print("=" * 50)
        print("FORM_VALID LLAMADO - OrdenTrabajoCreateView")
        print("Datos del formulario principal:")
        for field, value in form.cleaned_data.items():
            print(f"  {field}: {value}")
        print("=" * 50)
        
        context = self.get_context_data()
        servicios_formset = context['servicios_formset']
        repuestos_formset = context['repuestos_formset']
        
        # DEBUG: Validar formsets
        servicios_valido = servicios_formset.is_valid()
        repuestos_valido = repuestos_formset.is_valid()
        
        print(f"Servicios formset válido: {servicios_valido}")
        print(f"Repuestos formset válido: {repuestos_valido}")
        
        if not servicios_valido:
            print("ERRORES EN SERVICIOS FORMSET:")
            for i, errors in enumerate(servicios_formset.errors):
                if errors:
                    print(f"  Formulario {i}: {errors}")
            print(f"  Non-form errors: {servicios_formset.non_form_errors()}")
            print("=" * 50)
        
        if not repuestos_valido:
            print("ERRORES EN REPUESTOS FORMSET:")
            for i, errors in enumerate(repuestos_formset.errors):
                if errors:
                    print(f"  Formulario {i}: {errors}")
            print(f"  Non-form errors: {repuestos_formset.non_form_errors()}")
            print("=" * 50)
        
        # Validar formsets
        if servicios_formset.is_valid() and repuestos_formset.is_valid():
            print("✓ TODOS LOS FORMSETS VÁLIDOS - Guardando orden...")
            # Asignar usuario de creación
            form.instance.usuario_creacion = self.request.user
            # Guardar la orden primero
            self.object = form.save()
            
            # Luego guardar los formsets
            servicios_formset.instance = self.object
            servicios_formset.save()
            
            repuestos_formset.instance = self.object
            repuestos_formset.save()
            
            # Crear seguimiento inicial
            SeguimientoOrden.objects.create(
                orden=self.object,
                usuario=self.request.user,
                estado_nuevo='PENDIENTE',
                observaciones='Orden creada'
            )
            
            print(f"✓ Orden creada exitosamente: #{self.object.numero_orden}")
            print("=" * 50)
            
            messages.success(
                self.request, 
                f'Orden #{self.object.numero_orden} creada exitosamente.'
            )
            
            # Determinar la acción
            action = self.request.POST.get('action', 'save')
            if action == 'save_and_new':
                return redirect('taller:orden_create')
            else:
                return redirect(self.get_success_url())
        else:
            print("✗ FORMSETS INVÁLIDOS - Llamando form_invalid")
            print("=" * 50)
            # Si hay errores en los formsets, mostrarlos
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        print("=" * 50)
        print("FORMULARIO INVÁLIDO - ORDEN DE TRABAJO")
        print("Errores del formulario:")
        for field, errors in form.errors.items():
            print(f"  {field}: {errors}")
        print("=" * 50)
        print("Datos POST recibidos:")
        for field, value in self.request.POST.items():
            print(f"  {field}: {value}")
        print("=" * 50)
        
        # También revisar formsets
        context = self.get_context_data()
        servicios_formset = context['servicios_formset']
        repuestos_formset = context['repuestos_formset']
        
        if not servicios_formset.is_valid():
            print("ERRORES EN FORMSET DE SERVICIOS:")
            print(servicios_formset.errors)
            print("=" * 50)
        
        if not repuestos_formset.is_valid():
            print("ERRORES EN FORMSET DE REPUESTOS:")
            print(repuestos_formset.errors)
            print("=" * 50)
        
        messages.error(
            self.request,
            'Por favor corrija los errores en el formulario.'
        )
        return super().form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('taller:orden_detail', kwargs={'pk': self.object.pk})
class OrdenTrabajoUpdateView(LoginRequiredMixin, UpdateView):
    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = 'taller/orden_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Verificar que la orden no esté completada antes de permitir edición"""
        orden = self.get_object()
        
        # Si la orden está completada, redirigir al detalle
        if orden.estado in ['COMPLETADO', 'ENTREGADO']:
            messages.warning(
                request, 
                f'No se puede editar la orden #{orden.numero_orden} porque ya está {orden.get_estado_display()}. Solo puedes verla.'
            )
            return redirect('taller:orden_detail', pk=orden.pk)
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.request.POST:
            context['servicios_formset'] = ServicioOrdenFormSet(
                self.request.POST,
                instance=self.object,
                prefix='servicios'
            )
            context['repuestos_formset'] = RepuestoOrdenFormSet(
                self.request.POST,
                instance=self.object,
                prefix='repuestos'
            )
        else:
            context['servicios_formset'] = ServicioOrdenFormSet(
                instance=self.object,
                prefix='servicios'
            )
            context['repuestos_formset'] = RepuestoOrdenFormSet(
                instance=self.object,
                prefix='repuestos'
            )
        
        # Agregar datos para los templates
        context['servicios_disponibles'] = TipoServicio.objects.filter(
            activo=True
        ).select_related('categoria')
        
        context['tecnicos_disponibles'] = Tecnico.objects.filter(
            estado='ACTIVO',
            activo=True
        )
        
        # ✅ Indicar que es edición
        context['es_edicion'] = True
        
        # ✅ Datos existentes para JavaScript
        context['servicios_existentes_json'] = self._get_servicios_existentes_json()
        context['repuestos_existentes_json'] = self._get_repuestos_existentes_json()
        
        return context
    
    # ✅ NUEVO MÉTODO - Obtener servicios existentes en JSON
    def _get_servicios_existentes_json(self):
        """Obtiene datos completos de servicios existentes para JavaScript"""
        import json
        servicios_data = []
        for servicio_orden in self.object.servicios.all():
            servicios_data.append({
                'servicioOrdenId': servicio_orden.id,
                'id': servicio_orden.tipo_servicio.id,
                'name': servicio_orden.nombre_servicio_personalizado or servicio_orden.tipo_servicio.nombre,
                'code': servicio_orden.tipo_servicio.codigo,
                'price': float(servicio_orden.precio_servicio),
                'es_personalizable': servicio_orden.tipo_servicio.es_personalizable,
                'incluye_iva': bool(servicio_orden.aplica_iva),
                'technician_id': servicio_orden.tecnico_asignado.id if servicio_orden.tecnico_asignado else None,
                'technician_name': servicio_orden.tecnico_asignado.get_nombre_completo() if servicio_orden.tecnico_asignado else None,
                'quantity': 1,
                'isExisting': True
            })
        
        return json.dumps(servicios_data)
    
    def _get_repuestos_existentes_json(self):
        """Obtiene datos completos de repuestos existentes para JavaScript"""
        import json
        repuestos_data = []
        
        for repuesto_orden in self.object.repuestos_utilizados.all():
            # Intentar obtener código del producto de forma segura
            producto_codigo = ''
            try:
                producto_codigo = repuesto_orden.producto.codigo
            except AttributeError:
                try:
                    producto_codigo = repuesto_orden.producto.codigo_unico
                except AttributeError:
                    producto_codigo = f'PROD-{repuesto_orden.producto.id}'
            
            repuestos_data.append({
                'repuestoOrdenId': repuesto_orden.id,  # ✅ CORREGIDO: era 'repuestosOrdenId'
                'id': repuesto_orden.producto.id,
                'name': repuesto_orden.nombre_personalizado or repuesto_orden.producto.nombre,
                'code': producto_codigo,
                'price': float(repuesto_orden.precio_unitario),
                'quantity': float(repuesto_orden.cantidad),
                'stock': float(repuesto_orden.producto.stock_actual),
                'isExisting': True,
                'es_editable': repuesto_orden.producto.es_editable
            })
        
        return json.dumps(repuestos_data)
    
    @transaction.atomic
    def form_valid(self, form):
        # Verificar nuevamente que no esté completada
        if self.object.estado in ['COMPLETADO', 'ENTREGADO']:
            messages.error(
                self.request,
                'No se puede editar una orden completada o entregada.'
            )
            return redirect('taller:orden_detail', pk=self.object.pk)
        
        context = self.get_context_data()
        servicios_formset = context['servicios_formset']
        repuestos_formset = context['repuestos_formset']
        
        # ✅ AGREGAR DEBUG
        print("=" * 80)
        print("FORM_VALID - OrdenTrabajoUpdateView")
        print(f"Formulario principal válido: {form.is_valid()}")
        print(f"Servicios formset válido: {servicios_formset.is_valid()}")
        print(f"Repuestos formset válido: {repuestos_formset.is_valid()}")
        
        if not servicios_formset.is_valid():
            print("ERRORES EN SERVICIOS FORMSET:")
            for i, form_errors in enumerate(servicios_formset.errors):
                if form_errors:
                    print(f"  Formulario {i}: {form_errors}")
            print("Non-form errors:", servicios_formset.non_form_errors())
        
        if not repuestos_formset.is_valid():
            print("ERRORES EN REPUESTOS FORMSET:")
            for i, errors in enumerate(repuestos_formset.errors):
                if errors:
                    print(f"  Formulario {i}: {errors}")
            print("Non-form errors:", repuestos_formset.non_form_errors())
        
        print("=" * 80)
        
        if servicios_formset.is_valid() and repuestos_formset.is_valid():
            estado_anterior = OrdenTrabajo.objects.get(pk=self.object.pk).estado
            self.object = form.save()
            servicios_formset.save()
            repuestos_formset.save()
            
            # Si cambió el estado, crear seguimiento
            if estado_anterior != self.object.estado:
                SeguimientoOrden.objects.create(
                    orden=self.object,
                    usuario=self.request.user,
                    estado_anterior=estado_anterior,
                    estado_nuevo=self.object.estado,
                    observaciones=f'Estado cambiado de {estado_anterior} a {self.object.estado}'
                )
            
            messages.success(
                self.request,
                f'Orden #{self.object.numero_orden} actualizada exitosamente.'
            )
            
            return redirect(self.get_success_url())
        else:
            return self.form_invalid(form)
    
    # ✅ AGREGAR ESTE MÉTODO
    def form_invalid(self, form):
        print("=" * 80)
        print("FORM_INVALID - OrdenTrabajoUpdateView")
        print("Errores del formulario principal:")
        for field, errors in form.errors.items():
            print(f"  {field}: {errors}")
        print("=" * 80)
        
        messages.error(
            self.request,
            'Error al actualizar la orden. Revisa los campos marcados.'
        )
        return super().form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('taller:orden_detail', kwargs={'pk': self.object.pk})

@login_required
@require_POST
def cambiar_estado_orden(request, pk):
    """Cambiar estado de una orden de trabajo"""
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    nuevo_estado = request.POST.get('estado')
    observaciones = request.POST.get('observaciones', '')
    
    if nuevo_estado in dict(OrdenTrabajo.ESTADO_CHOICES):
        estado_anterior = orden.estado
        orden.estado = nuevo_estado
        orden.save()
        
        # Crear seguimiento
        SeguimientoOrden.objects.create(
            orden=orden,
            usuario=request.user,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            observaciones=observaciones
        )
        
        messages.success(request, f'Estado cambiado a {nuevo_estado}')
    else:
        messages.error(request, 'Estado inválido')
    
    return redirect('taller:orden_detail', pk=pk)

# ================== EVALUACIONES ==================

class EvaluacionServicioCreateView(LoginRequiredMixin, CreateView):
    model = EvaluacionServicio
    form_class = EvaluacionServicioForm
    template_name = 'taller/evaluacion_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orden_pk = self.kwargs.get('orden_pk')
        context['orden'] = get_object_or_404(OrdenTrabajo, pk=orden_pk)
        return context
    
    def form_valid(self, form):
        orden_pk = self.kwargs.get('orden_pk')
        orden = get_object_or_404(OrdenTrabajo, pk=orden_pk)
        
        # Verificar que la orden esté entregada y no tenga evaluación
        if orden.estado != 'ENTREGADO':
            messages.error(self.request, 'Solo se pueden evaluar órdenes entregadas.')
            return redirect('taller:orden_detail', pk=orden.pk)
        
        if hasattr(orden, 'evaluacion'):
            messages.error(self.request, 'Esta orden ya tiene una evaluación.')
            return redirect('taller:orden_detail', pk=orden.pk)
        
        form.instance.orden = orden
        messages.success(self.request, 'Evaluación guardada exitosamente.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('taller:orden_detail', kwargs={'pk': self.object.orden.pk})

# ================== REPORTES ==================

@login_required
def reporte_tecnicos(request):
    """Reporte de desempeño de técnicos"""
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    
    if not fecha_desde:
        fecha_desde = timezone.localdate().replace(day=1)
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = timezone.localdate()
    else:
        fecha_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
    
    # Obtener técnicos con sus estadísticas
    tecnicos = []
    tecnicos_activos = 0
    total_servicios = 0
    total_ordenes = 0
    total_ingresos = 0
    
    for tecnico in Tecnico.objects.filter(estado='ACTIVO'):
        tecnicos_activos += 1
        
        # Órdenes del técnico en el período
        ordenes = OrdenTrabajo.objects.filter(
            tecnico_principal=tecnico,
            fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
        )
        
        # Servicios del técnico
        servicios = ServicioOrden.objects.filter(
            tecnico_asignado=tecnico,
            orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
        )
        
        servicios_count = servicios.count()
        ordenes_count = ordenes.count()
        
        # Total facturado
        ingresos = ordenes.filter(estado='COMPLETADO').aggregate(
            total=Sum('precio_total')
        )['total'] or 0
        
        # Evaluaciones
        evaluaciones = EvaluacionServicio.objects.filter(
            orden__tecnico_principal=tecnico,
            fecha_evaluacion__date__range=[fecha_desde, fecha_hasta]
        )
        
        promedio_calificacion = evaluaciones.aggregate(
            promedio=Avg('calificacion_tecnico')
        )['promedio']
        
        # Agregar estadísticas al técnico
        tecnico.servicios_count = servicios_count
        tecnico.ordenes_count = ordenes_count
        tecnico.total_ingresos = ingresos
        tecnico.promedio_calificacion = promedio_calificacion
        
        tecnicos.append(tecnico)
        
        # Totales generales
        total_servicios += servicios_count
        total_ordenes += ordenes_count
        total_ingresos += ingresos
    
    # Calcular promedio diario
    dias = (fecha_hasta - fecha_desde).days + 1
    promedio_diario = total_servicios / dias if dias > 0 else 0
    
    # Top servicios más realizados - CORREGIDO AQUÍ
    top_servicios = TipoServicio.objects.filter(
        servicioorden__orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
    ).annotate(
        total_realizados=Count('servicioorden')
    ).order_by('-total_realizados')[:10]
    
    # Técnico del mes (el que más servicios realizó)
    tecnico_del_mes = None
    if tecnicos:
        tecnico_del_mes = max(tecnicos, key=lambda t: t.servicios_count)
    
    context = {
        'tecnicos': tecnicos,
        'total_tecnicos': Tecnico.objects.count(),
        'tecnicos_activos': tecnicos_activos,
        'total_servicios': total_servicios,
        'total_ordenes': total_ordenes,
        'total_ingresos': total_ingresos,
        'promedio_diario': promedio_diario,
        'top_servicios': top_servicios,
        'tecnico_del_mes': tecnico_del_mes,
        'fecha_inicio': fecha_desde,
        'fecha_fin': fecha_hasta,
        'tecnicos_stats': tecnicos,  # Por compatibilidad
    }
    
    return render(request, 'taller/reporte_tecnicos.html', context)

@login_required
def reporte_servicios(request):
    """Reporte de servicios más solicitados"""
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    categoria_id = request.GET.get('categoria')
    
    if not fecha_desde:
        fecha_desde = timezone.localdate().replace(day=1)
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = timezone.localdate()
    else:
        fecha_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
    
    # Filtrar servicios por período
    servicios_ordenes = ServicioOrden.objects.filter(
        orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
    )
    
    # Filtrar por categoría si se especifica
    if categoria_id:
        servicios_ordenes = servicios_ordenes.filter(
            tipo_servicio__categoria_id=categoria_id
        )
    
    # Estadísticas generales
    total_servicios = servicios_ordenes.count()
    total_ingresos = servicios_ordenes.aggregate(
        total=Sum('precio_total')
    )['total'] or 0
    
    # Tiempo promedio
    tiempo_promedio = servicios_ordenes.filter(
        tiempo_real__isnull=False
    ).aggregate(
        promedio=Avg('tiempo_real')
    )['promedio'] or 0
    
    # Calificación promedio
    evaluaciones = EvaluacionServicio.objects.filter(
        orden__servicios__in=servicios_ordenes,
        fecha_evaluacion__date__range=[fecha_desde, fecha_hasta]
    ).distinct()
    
    calificacion_promedio = evaluaciones.aggregate(
        promedio=Avg('calificacion_general')
    )['promedio'] or 0
    
    # Servicios por categoría - CORREGIDO AQUÍ
    servicios_por_categoria = {}
    categorias = CategoriaServicio.objects.filter(activa=True)
    
    for categoria in categorias:
        servicios = TipoServicio.objects.filter(
            categoria=categoria,
            servicioorden__orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
        ).annotate(
            total_realizados=Count('servicioorden'),
            total_generado=Sum('servicioorden__precio_total')
        ).distinct()
        
        if servicios.exists():
            servicios_por_categoria[categoria.nombre] = servicios
    
    # Servicios sin categoría - CORREGIDO AQUÍ
    servicios_sin_cat = TipoServicio.objects.filter(
        categoria__isnull=True,
        servicioorden__orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
    ).annotate(
        total_realizados=Count('servicioorden'),
        total_generado=Sum('servicioorden__precio_total')
    ).distinct()
    
    if servicios_sin_cat.exists():
        servicios_por_categoria['Sin Categoría'] = servicios_sin_cat
    
    # Top 10 servicios más solicitados - CORREGIDO AQUÍ
    top_servicios = TipoServicio.objects.filter(
        servicioorden__orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
    ).annotate(
        total_realizados=Count('servicioorden'),
        total_generado=Sum('servicioorden__precio_total')
    ).order_by('-total_realizados')[:10]
    
    # Distribución por categoría para gráfico
    distribucion_categorias = {}
    for cat_nombre, servicios in servicios_por_categoria.items():
        total_cat = sum(s.total_realizados for s in servicios)
        distribucion_categorias[cat_nombre] = {
            'cantidad': total_cat,
            'porcentaje': (total_cat / total_servicios * 100) if total_servicios > 0 else 0
        }
    
    # Lista plana de todos los servicios
    servicios = []
    for servicios_cat in servicios_por_categoria.values():
        servicios.extend(list(servicios_cat))
    
    context = {
        'servicios': servicios,
        'servicios_por_categoria': servicios_por_categoria,
        'categorias': categorias,
        'categoria_id': categoria_id,
        'total_servicios': total_servicios,
        'total_ingresos': total_ingresos,
        'tiempo_promedio': tiempo_promedio,
        'calificacion_promedio': calificacion_promedio,
        'top_servicios': top_servicios,
        'distribucion_categorias': distribucion_categorias,
        'fecha_inicio': fecha_desde,
        'fecha_fin': fecha_hasta,
        'servicios_stats': servicios,  # Por compatibilidad
    }
    
    return render(request, 'taller/reporte_servicios.html', context)

# ================== AJAX VIEWS ==================

@login_required
def ajax_motos_por_cliente(request):
    """Obtener motos de un cliente específico"""
    cliente_id = request.GET.get('cliente_id')
    motos = Moto.objects.filter(cliente_id=cliente_id).values('id', 'placa', 'marca', 'modelo')
    return JsonResponse(list(motos), safe=False)

@login_required
def ajax_precio_servicio(request):
    """Obtener precio de un tipo de servicio"""
    servicio_id = request.GET.get('servicio_id')
    try:
        servicio = TipoServicio.objects.get(id=servicio_id)
        data = {
            'precio_base': float(servicio.precio_base),
            'precio_mano_obra': float(servicio.precio_mano_obra),
            'tiempo_estimado': float(servicio.tiempo_estimado_horas),
            'precio_total': float(servicio.get_precio_total())
        }
        return JsonResponse(data)
    except TipoServicio.DoesNotExist:
        return JsonResponse({'error': 'Servicio no encontrado'}, status=404)

@login_required
def ajax_precio_producto(request):
    """Obtener precio de un producto"""
    producto_id = request.GET.get('producto_id')
    try:
        producto = Producto.objects.get(id=producto_id)
        data = {
            'precio_venta': float(producto.precio_venta),
            'stock_disponible': float(producto.stock_actual)
        }
        return JsonResponse(data)
    except Producto.DoesNotExist:
        return JsonResponse({'error': 'Producto no encontrado'}, status=404)

# ================== ESPECIALIDADES Y CATEGORÍAS ==================

class EspecialidadTecnicaListView(LoginRequiredMixin, ListView):
    model = EspecialidadTecnica
    template_name = 'taller/especialidad_list.html'
    context_object_name = 'especialidades'

class CategoriaServicioListView(LoginRequiredMixin, ListView):
    model = CategoriaServicio
    template_name = 'taller/categoria_list.html'
    context_object_name = 'categorias'

# ================== FUNCIONES ADICIONALES ==================

@login_required
@require_POST
def toggle_estado_servicio(request, pk):
    """Cambiar estado activo/inactivo de un tipo de servicio"""
    try:
        servicio = get_object_or_404(TipoServicio, pk=pk)
        servicio.activo = not servicio.activo
        servicio.save()
        
        estado = "activado" if servicio.activo else "desactivado"
        messages.success(request, f'Servicio "{servicio.nombre}" {estado} exitosamente.')
        
        return JsonResponse({
            'success': True,
            'activo': servicio.activo,
            'message': f'Servicio {estado}'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error al cambiar estado: {str(e)}'
        }, status=400)

@login_required
def duplicar_servicio(request, pk):
    """Duplicar un tipo de servicio existente"""
    servicio_original = get_object_or_404(TipoServicio, pk=pk)
    
    # Crear copia del servicio
    servicio_duplicado = TipoServicio.objects.get(pk=pk)
    servicio_duplicado.pk = None
    servicio_duplicado.codigo = f"{servicio_original.codigo}_COPIA"
    servicio_duplicado.nombre = f"{servicio_original.nombre} (Copia)"
    servicio_duplicado.activo = False  # Crear inactivo para revisión
    servicio_duplicado.save()
    
    # Copiar especialidades requeridas si las tiene
    if servicio_original.requiere_especialidad:
        servicio_duplicado.requiere_especialidad = servicio_original.requiere_especialidad
        servicio_duplicado.save()
    
    messages.success(request, f'Servicio duplicado como "{servicio_duplicado.nombre}"')
    return redirect('taller:tipo_servicio_update', pk=servicio_duplicado.pk)

@login_required
def historial_ventas_servicio(request, pk):
    """Ver historial de ventas de un tipo de servicio"""
    servicio = get_object_or_404(TipoServicio, pk=pk)
    
    # Filtros de fecha
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    
    if not fecha_desde:
        fecha_desde = timezone.localdate() - timedelta(days=90)  # Últimos 3 meses
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = timezone.localdate()
    else:
        fecha_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
    
    # Obtener servicios realizados
    servicios_realizados = ServicioOrden.objects.filter(
        tipo_servicio=servicio,
        orden__fecha_ingreso__date__range=[fecha_desde, fecha_hasta]
    ).select_related(
        'orden__cliente', 'tecnico_asignado'
    ).order_by('-orden__fecha_ingreso')
    
    # Estadísticas
    total_servicios = servicios_realizados.count()
    total_facturado = servicios_realizados.aggregate(
        total=Sum('precio_total')
    )['total'] or 0
    
    tiempo_promedio = servicios_realizados.filter(
        tiempo_real__isnull=False
    ).aggregate(
        promedio=Avg('tiempo_real')
    )['promedio'] or 0
    
    # Servicios por mes (para gráfico)
    servicios_por_mes = servicios_realizados.extra(
        select={'mes': 'EXTRACT(month FROM fecha_ingreso)', 
                'año': 'EXTRACT(year FROM fecha_ingreso)'}
    ).values('mes', 'año').annotate(
        cantidad=Count('id'),
        total_mes=Sum('precio_total')
    ).order_by('año', 'mes')
    
    context = {
        'servicio': servicio,
        'servicios_realizados': servicios_realizados,
        'total_servicios': total_servicios,
        'total_facturado': total_facturado,
        'tiempo_promedio': tiempo_promedio,
        'servicios_por_mes': servicios_por_mes,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
    }
    
    return render(request, 'taller/historial_ventas_servicio.html', context)

@login_required
def exportar_orden_a_pos(request, pk):
    """Exportar orden al sistema POS para facturación"""
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    
    if orden.estado != 'COMPLETADO':
        messages.error(request, 'Solo se pueden exportar órdenes completadas.')
        return redirect('taller:orden_detail', pk=pk)
    
    try:
        # Aquí irían los datos para exportar al POS
        # Por ahora simulamos la exportación
        datos_pos = {
            'numero_orden': orden.numero_orden,
            'cliente': {
                'nombre': f"{orden.cliente.nombres} {orden.cliente.apellidos}",  # CORREGIDO
                'identificacion': orden.cliente.identificacion,
                'telefono': orden.cliente.telefono,
                'email': orden.cliente.email,
            },
            'servicios': [],
            'repuestos': [],
            'total': float(orden.precio_total)
        }
        
        # Agregar servicios
        for servicio in orden.servicios.all():
            datos_pos['servicios'].append({
                'codigo': servicio.tipo_servicio.codigo,
                'nombre': servicio.tipo_servicio.nombre,
                'cantidad': 1,
                'precio_unitario': float(servicio.precio_total),
                'total': float(servicio.precio_total)
            })
        
        # Agregar repuestos
        for repuesto in orden.repuestos_utilizados.all():
            datos_pos['repuestos'].append({
                'codigo': repuesto.producto.codigo,
                'nombre': repuesto.producto.nombre,
                'cantidad': float(repuesto.cantidad),
                'precio_unitario': float(repuesto.precio_unitario),
                'total': float(repuesto.subtotal)
            })
        
        # Marcar como exportado (agregar campo si no existe)
        # orden.exportado_pos = True
        # orden.fecha_exportacion = timezone.now()
        # orden.save()
        
        messages.success(request, 'Orden exportada al POS exitosamente.')
        
        # Retornar JSON para AJAX o redirigir
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Orden exportada exitosamente',
                'datos': datos_pos
            })
        
    except Exception as e:
        messages.error(request, f'Error al exportar orden: {str(e)}')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)
    
    return redirect('taller:orden_detail', pk=pk)

@login_required
def generar_cotizacion_pdf(request, pk):
    """Generar cotización en PDF utilizando el servicio de cotización"""
    from django.template.loader import render_to_string
    import logging
    
    logger = logging.getLogger(__name__)
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    filename = f"cotizacion_{orden.numero_orden or orden.id}.pdf"
    
    try:
        # Usar el servicio para generar el PDF real
        pdf_content = CotizacionService.generar_cotizacion_pdf(orden)
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        logger.warning(f"Error generando PDF de cotización para la orden {pk} ({str(e)}), enviando HTML descargable")
        # Si falla el servicio, intentamos renderizar HTML como fallback pero forzando descarga
        context = {
            'orden': orden,
            'servicios': orden.servicios.all(),
            'repuestos': orden.repuestos_utilizados.all(),
            'error': str(e),
            'empresa': {
                'nombre': 'VPMOTOS',
                'direccion': 'Dirección de la empresa',
                'telefono': 'Teléfono',
                'email': 'email@vpmotos.com'
            }
        }
        html_content = render_to_string('taller/cotizacion_pdf.html', context)
        response = HttpResponse(html_content, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{filename.replace(".pdf", ".html")}"'
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar cotización: {str(e)}')
        return redirect('taller:orden_detail', pk=pk)

@login_required
def generar_orden_pdf(request, pk):
    """Generar Orden de Trabajo en PDF con el logo oficial"""
    import os
    import base64
    from django.conf import settings
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    import logging

    logger = logging.getLogger(__name__)
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    filename = f"orden_trabajo_{orden.numero_orden or orden.id}.pdf"
    
    try:
        # Cargar logo de forma segura en Base64 para WeasyPrint/HTML
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'logo_vp.png')
        logo_base64 = ""
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                logo_base64 = f"data:image/png;base64,{encoded_string}"
        
        # Preparar data de la orden
        cotizacion_data = orden.generar_cotizacion_data()
        
        context = {
            'orden': orden,
            'servicios': cotizacion_data['servicios'],
            'repuestos': cotizacion_data['repuestos'],
            'totales': cotizacion_data['totales'],
            'logo_base64': logo_base64,
            'empresa': {
                'nombre': 'VPMOTOS',
                'direccion': 'Dirección de la empresa',
                'telefono': 'Teléfono',
                'email': 'email@vpmotos.com'
            }
        }
        
        html_content = render_to_string('taller/orden_pdf.html', context)
        
        try:
            from weasyprint import HTML, CSS
            
            # En WeasyPrint 65+, FontConfiguration es opcional para uso básico
            # Si se necesita específicamente, está en weasyprint.text.fonts
            css = CSS(string='''
                @page {
                    size: A4;
                    margin: 1cm;
                    @top-center { content: "ORDEN DE TRABAJO - VPMOTOS"; font-size: 10px; color: #666; }
                    @bottom-center { content: "Página " counter(page) " de " counter(pages); font-size: 10px; color: #666; }
                }
            ''')
            
            html_doc = HTML(string=html_content, base_url=request.build_absolute_uri('/'))
            pdf = html_doc.write_pdf(stylesheets=[css])
            
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except (ImportError, Exception) as e:
            logger.warning(f"WeasyPrint falló o no está instalado ({str(e)}), enviando HTML descargable")
            # Fallback: Enviar el HTML pero forzando la descarga para que no se pierda la utilidad
            response = HttpResponse(html_content, content_type='text/html')
            # Usamos extensión .html para que el usuario pueda abrirlo en el navegador tras descargar
            response['Content-Disposition'] = f'attachment; filename="{filename.replace(".pdf", ".html")}"'
            return response
            
    except Exception as e:
        logger.exception(f"Error crítico generando documento para la orden {pk}")
        messages.error(request, f'No se pudo generar el documento: {str(e)}')
        return redirect('taller:orden_detail', pk=pk)

@login_required
def ajax_servicios_disponibles(request):
    """AJAX: Obtener servicios disponibles filtrados"""
    categoria_id = request.GET.get('categoria_id')
    busqueda = request.GET.get('busqueda', '')
    
    try:
        servicios = TipoServicio.objects.filter(activo=True)
        
        if categoria_id:
            servicios = servicios.filter(categoria_id=categoria_id)
        
        if busqueda:
            servicios = servicios.filter(
                Q(nombre__icontains=busqueda) |
                Q(codigo__icontains=busqueda)
            )
        
        # Sin límite: el catálogo de servicios es chico y el formulario de la orden filtra
        # en el navegador; con [:50] los servicios más allá de los primeros 50 no aparecían.
        servicios = servicios.select_related('categoria', 'requiere_especialidad').order_by('categoria__nombre', 'nombre')
        
        datos = []
        for servicio in servicios:
            datos.append({
                'id': servicio.id,
                'codigo': servicio.codigo,
                'nombre': servicio.nombre,
                'categoria': servicio.categoria.nombre if servicio.categoria else '',
                'precio': float(servicio.precio),  # ✅ Usar 'precio' en lugar de 'precio_total'
                'tiempo_estimado': float(servicio.tiempo_estimado_horas) if servicio.tiempo_estimado_horas else 0,
                'requiere_especialidad': servicio.requiere_especialidad.nombre if servicio.requiere_especialidad else None,
                'es_personalizable': servicio.es_personalizable,
                'incluye_iva': bool(servicio.incluye_iva)
            })
        
        # ✅ FORMATO CORRECTO
        return JsonResponse({
            'success': True,
            'servicios': datos
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@login_required
def ajax_datos_servicio_pos(request):
    """AJAX: Obtener datos de servicio para integración con POS"""
    servicio_id = request.GET.get('servicio_id')
    
    try:
        servicio = TipoServicio.objects.get(id=servicio_id, activo=True)
        
        datos = {
            'id': servicio.id,
            'codigo': servicio.codigo,
            'nombre': servicio.nombre,
            'descripcion': servicio.descripcion,
            'categoria': {
                'id': servicio.categoria.id if servicio.categoria else None,
                'nombre': servicio.categoria.nombre if servicio.categoria else ''
            },
            'precios': {
                'base': float(servicio.precio_base),
                'mano_obra': float(servicio.precio_mano_obra),
                'total': float(servicio.get_precio_total())
            },
            'tiempo_estimado': float(servicio.tiempo_estimado_horas),
            'activo': servicio.activo,
            'requiere_especialidad': {
                'requerida': servicio.requiere_especialidad is not None,
                'especialidad': servicio.requiere_especialidad.nombre if servicio.requiere_especialidad else None
            }
        }
        
        return JsonResponse(datos)
        
    except TipoServicio.DoesNotExist:
        return JsonResponse({
            'error': 'Servicio no encontrado'
        }, status=404)

# Vista AJAX para buscar clientes
@login_required
def buscar_cliente_ajax(request):
    """
    Vista AJAX para buscar clientes por identificación o nombre
    """
    query = request.GET.get('q', '').strip()
    
    if len(query) < 3:
        return JsonResponse([], safe=False)
    
    # Buscar clientes por identificación, nombres o apellidos
    clientes = Cliente.objects.filter(
        Q(identificacion__icontains=query) |
        Q(nombres__icontains=query) |
        Q(apellidos__icontains=query)
    )[:10]  # Limitar a 10 resultados
    
    data = []
    for cliente in clientes:
        data.append({
            'id': cliente.id,
            'identificacion': cliente.identificacion,
            'nombres': cliente.nombres,
            'apellidos': cliente.apellidos,
            'telefono': cliente.telefono or '',
            'email': cliente.email or '',
            'direccion': cliente.direccion or '',
            'text': f"{cliente.nombres} {cliente.apellidos} - {cliente.identificacion}"
        })
    
    return JsonResponse(data, safe=False)

# Vista AJAX para obtener precios de servicios
@login_required
def obtener_precio_servicio_ajax(request, pk):
    """
    Vista AJAX para obtener los precios de un servicio
    """
    try:
        servicio = TipoServicio.objects.get(pk=pk)
        data = {
            'precio_base': float(servicio.precio_base),
            'precio_mano_obra': float(servicio.precio_mano_obra),
            'tiempo_estimado': float(servicio.tiempo_estimado_horas),
            'incluye_iva': servicio.incluye_iva
        }
        return JsonResponse(data)
    except TipoServicio.DoesNotExist:
        return JsonResponse({'error': 'Servicio no encontrado'}, status=404)

# Vista AJAX para buscar productos
@login_required
def buscar_producto_ajax(request):
    """
    Vista AJAX para buscar productos/repuestos
    """
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    # Buscar productos por código único, nombre o descripción.
    # (No se excluye stock 0: en una orden/cotización puede pedirse un repuesto
    #  que esté agotado; el frontend muestra el stock disponible.)
    productos = Producto.objects.filter(
        Q(codigo_unico__icontains=query) |
        Q(nombre__icontains=query) |
        Q(descripcion__icontains=query)
    ).filter(activo=True)[:15]

    data = []
    for producto in productos:
        data.append({
            'id': producto.id,
            'codigo': producto.codigo_unico,
            'nombre': producto.nombre,
            'descripcion': producto.descripcion or '',
            'precio_venta': float(producto.precio_venta),
            'stock_actual': float(producto.stock_actual),
            'text': f"{producto.codigo_unico} - {producto.nombre} (Stock: {producto.stock_actual})"
        })
    
    return JsonResponse(data, safe=False)

# ================== APIs PARA INTEGRACIÓN POS ==================

@login_required
def api_tecnicos(request):
    """API para obtener lista de técnicos"""
    try:
        tecnicos = Tecnico.objects.filter(activo=True)
        
        tecnicos_data = []
        for tecnico in tecnicos:
            # Verificar disponibilidad
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
            servicios_data.append({
                'id': servicio.id,
                'codigo': servicio.codigo,
                'nombre': servicio.nombre,
                'descripcion': servicio.descripcion or '',
                'precio': float(servicio.precio),  # ✅ Usar 'precio' en lugar de campos separados
                'categoria': servicio.categoria.nombre if servicio.categoria else None,
                'tiempo_estimado': float(servicio.tiempo_estimado_horas or 0)
            })
        
        return JsonResponse({
            'success': True,
            'servicios': servicios_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def api_ordenes_completadas(request):
    """API para obtener órdenes completadas pendientes de facturar"""
    try:
        search = request.GET.get('q', '').strip()
        
        # CORRECCIÓN: Verificar si existe el campo 'facturado' y 'moto'
        try:
            ordenes = OrdenTrabajo.objects.filter(
                estado='COMPLETADO'
            ).select_related('cliente', 'tecnico_principal')
            
            # Verificar si existe el campo facturado
            if hasattr(OrdenTrabajo, 'facturado'):
                ordenes = ordenes.filter(facturado=False)
                
        except Exception as e:
            # Si hay problemas con campos, obtener todas las órdenes completadas
            ordenes = OrdenTrabajo.objects.filter(estado='COMPLETADO')
        
        if search:
            # CORRECCIÓN: Usar Q en lugar de models.Q
            filters = Q(numero_orden__icontains=search)
            
            # Intentar agregar filtros adicionales si existen los campos
            try:
                filters |= Q(cliente__nombres__icontains=search)
                filters |= Q(cliente__apellidos__icontains=search)
            except Exception:
                pass
            
            # Intentar filtro de placa si existe
            try:
                if hasattr(OrdenTrabajo, 'moto_placa'):
                    filters |= Q(moto_placa__icontains=search)
                elif hasattr(OrdenTrabajo, 'moto'):
                    filters |= Q(moto__placa__icontains=search)
            except Exception:
                pass
            
            ordenes = ordenes.filter(filters)
        
        ordenes = ordenes.order_by('-fecha_ingreso')[:20]
        
        ordenes_data = []
        for orden in ordenes:
            # Obtener información de la moto de forma segura
            moto_info = get_orden_moto_info(orden)
            vehiculo = f"{moto_info['marca']} {moto_info['modelo']}" if moto_info['marca'] else "N/A"
            placa = moto_info['placa'] or "N/A"
            
            ordenes_data.append({
                'id': orden.id,
                'numero_orden': orden.numero_orden,
                'cliente_nombre': f"{orden.cliente.nombres} {orden.cliente.apellidos}",
                'vehiculo': vehiculo,
                'placa': placa,
                'precio_total': float(orden.precio_total),
                'fecha_completado': orden.fecha_finalizacion.strftime('%d/%m/%Y %H:%M') if hasattr(orden, 'fecha_finalizacion') and orden.fecha_finalizacion else '',
                'tecnico_principal': orden.tecnico_principal.get_nombre_completo() if orden.tecnico_principal else ''
            })
        
        return JsonResponse({
            'success': True,
            'ordenes': ordenes_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def api_orden_datos_pos(request, orden_id):
    """API para obtener datos completos de una orden para el POS"""
    try:
        orden = get_object_or_404(OrdenTrabajo, pk=orden_id)
        
        if orden.estado != 'COMPLETADO':
            return JsonResponse({
                'success': False, 
                'message': 'Solo se pueden facturar órdenes completadas'
            })
        
        # Verificar si existe el campo facturado
        if hasattr(orden, 'facturado') and orden.facturado:
            return JsonResponse({
                'success': False, 
                'message': 'Esta orden ya ha sido facturada'
            })
        
        # Obtener servicios
        servicios = []
        for servicio_orden in orden.servicios.all():
            servicios.append({
                'id': servicio_orden.tipo_servicio.id,
                'codigo': servicio_orden.tipo_servicio.codigo,
                'nombre': servicio_orden.tipo_servicio.nombre,
                'precio_total': float(servicio_orden.precio_total),
                'tecnico_id': servicio_orden.tecnico_asignado.id if servicio_orden.tecnico_asignado else None,
                'tecnico_nombre': servicio_orden.tecnico_asignado.get_nombre_completo() if servicio_orden.tecnico_asignado else None,
                'categoria': servicio_orden.tipo_servicio.categoria.nombre if servicio_orden.tipo_servicio.categoria else None
            })
        
        # Obtener repuestos
        repuestos = []
        for repuesto_orden in orden.repuestos_utilizados.all():
            # Verificar si existe el campo codigo_unico
            codigo = getattr(repuesto_orden.producto, 'codigo', None) or getattr(repuesto_orden.producto, 'codigo_unico', None) or 'N/A'
            
            repuestos.append({
                'id': repuesto_orden.producto.id,
                'codigo': codigo,
                'nombre': repuesto_orden.producto.nombre,
                'cantidad': float(repuesto_orden.cantidad),
                'precio_unitario': float(repuesto_orden.precio_unitario),
                'stock_disponible': float(repuesto_orden.producto.stock_actual),
                'categoria': repuesto_orden.producto.categoria.nombre if hasattr(repuesto_orden.producto, 'categoria') and repuesto_orden.producto.categoria else None
            })
        
        # Obtener información de la moto de forma segura
        moto_info = get_orden_moto_info(orden)
        vehiculo = f"{moto_info['marca']} {moto_info['modelo']} - {moto_info['placa']}" if moto_info['marca'] else "N/A"
        
        orden_data = {
            'id': orden.id,
            'numero_orden': orden.numero_orden,
            'cliente': {
                'id': orden.cliente.id,
                'nombre_completo': f"{orden.cliente.nombres} {orden.cliente.apellidos}",
                'identificacion': orden.cliente.identificacion
            },
            'vehiculo': vehiculo,
            'tecnico_principal': orden.tecnico_principal.get_nombre_completo() if orden.tecnico_principal else None,
            'fecha_completado': orden.fecha_finalizacion.strftime('%d/%m/%Y %H:%M') if hasattr(orden, 'fecha_finalizacion') and orden.fecha_finalizacion else '',
            'servicios': servicios,
            'repuestos': repuestos,
            'precio_total': float(orden.precio_total)
        }
        
        return JsonResponse({
            'success': True,
            'orden': orden_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
# Agregar esta función al final de taller/views.py
# ANTES de los comentarios largos

@login_required
@require_POST
def crear_categoria_ajax(request):
    """Vista AJAX para crear categoría de servicio"""
    try:
        # Obtener datos del formulario
        nombre = request.POST.get('nombre', '').strip()
        codigo = request.POST.get('codigo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        color = request.POST.get('color', '#007bff')
        requiere_diagnostico = request.POST.get('requiere_diagnostico') == 'on'
        tiempo_estimado = request.POST.get('tiempo_estimado_horas', '').strip()
        
        # Validaciones básicas
        if not nombre:
            return JsonResponse({
                'success': False,
                'message': 'El nombre de la categoría es requerido.'
            })
        
        if not codigo:
            return JsonResponse({
                'success': False,
                'message': 'El código de la categoría es requerido.'
            })
        
        # Verificar si ya existe el código
        if CategoriaServicio.objects.filter(codigo=codigo).exists():
            return JsonResponse({
                'success': False,
                'message': f'Ya existe una categoría con el código "{codigo}".'
            })
        
        # Verificar si ya existe el nombre
        if CategoriaServicio.objects.filter(nombre=nombre).exists():
            return JsonResponse({
                'success': False,
                'message': f'Ya existe una categoría con el nombre "{nombre}".'
            })
        
        # Convertir tiempo estimado
        tiempo_estimado_decimal = None
        if tiempo_estimado:
            try:
                tiempo_estimado_decimal = Decimal(tiempo_estimado)
                if tiempo_estimado_decimal < 0:
                    raise ValueError("El tiempo no puede ser negativo")
            except (ValueError, InvalidOperation):
                return JsonResponse({
                    'success': False,
                    'message': 'El tiempo estimado debe ser un número válido.'
                })
        
        # Crear la categoría
        categoria = CategoriaServicio.objects.create(
            nombre=nombre,
            codigo=codigo,
            descripcion=descripcion or None,
            color=color,
            requiere_diagnostico=requiere_diagnostico,
            tiempo_estimado_horas=tiempo_estimado_decimal,
            activa=True
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Categoría creada exitosamente.',
            'categoria': {
                'id': categoria.id,
                'nombre': categoria.nombre,
                'codigo': categoria.codigo,
                'color': categoria.color,
                'descripcion': categoria.descripcion or '',
                'activa': categoria.activa
            }
        })
        
    except Exception as e:
        print(f"Error al crear categoría: {e}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        })


# ============================================================================
# PANEL DEL TÉCNICO (Rendimiento semanal, liquidación, órdenes y POS)
# ============================================================================
@login_required
def panel_tecnico(request, seccion='calculadora'):
    """Panel personal del técnico: sus trabajos de la semana (Lunes a Sábado),
    servicios realizados en Órdenes de taller y en POS (mecánica rápida),
    filtros interactivos por día y panel de liquidación de comisión según
    lo configurado en el panel del administrador.

    Soporta múltiples pantallas/templates especializados:
    - 'calculadora': Resumen general y calculadora interactiva unificada.
    - 'ordenes': Detalle exclusivo de órdenes de taller con ID de venta.
    - 'pos': Detalle exclusivo de servicios en POS con ID de venta.
    - 'cuenta': Historial de comisiones, pagos y adelantos.
    - 'perfil': Datos personales y foto de perfil.
    """
    tecnico = getattr(request.user, 'tecnico', None)
    if tecnico is None and (request.user.is_staff or request.user.is_superuser):
        tid = request.GET.get('tecnico_id')
        if tid:
            tecnico = Tecnico.objects.filter(pk=tid).first()

    if tecnico is None:
        return render(request, 'taller/panel_tecnico/base_panel.html', {'sin_tecnico': True})

    from ventas.models import DetalleVenta
    from .models import AdelantoTecnico, PagoTecnico
    hoy = timezone.localdate()

    # Determinar la semana de referencia (Lunes a Sábado)
    # Permite navegar con ?fecha=YYYY-MM-DD o ?semana=YYYY-MM-DD
    ref_str = request.GET.get('fecha') or request.GET.get('semana')
    if ref_str:
        try:
            fecha_ref = datetime.strptime(ref_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_ref = hoy
    else:
        fecha_ref = hoy

    # Lunes de la semana seleccionada
    inicio = fecha_ref - timedelta(days=fecha_ref.weekday())
    # Sábado de la semana (Lunes a Sábado = 6 días laborales)
    fin = inicio + timedelta(days=5)

    semana_anterior = inicio - timedelta(days=7)
    semana_siguiente = inicio + timedelta(days=7)
    es_semana_actual = (inicio == (hoy - timedelta(days=hoy.weekday())))

    # Filtro opcional por día específico (Lunes, Martes, etc.)
    dia = None
    dia_str = request.GET.get('dia')
    if dia_str:
        try:
            dia = datetime.strptime(dia_str, '%Y-%m-%d').date()
        except ValueError:
            dia = None

    factor = _factor_comision(tecnico)
    gana_comision = getattr(tecnico, 'gana_comision', True)
    if not gana_comision:
        porcentaje_cfg = Decimal('0')
    else:
        porcentaje_cfg = tecnico.porcentaje_comision if (tecnico.porcentaje_comision and tecnico.porcentaje_comision > 0) else Decimal('50')

    # -------------------------------------------------------------------------
    # 1. SERVICIOS DE ÓRDENES DE TRABAJO (Taller)
    # -------------------------------------------------------------------------
    # Buscamos órdenes completadas, entregadas o facturadas donde el técnico
    # sea técnico principal o tenga asignados servicios individuales,
    # cuya fecha de finalización o facturación pertenezca a la semana [inicio, fin].
    ordenes_sem = OrdenTrabajo.objects.filter(
        Q(tecnico_principal=tecnico) | Q(servicios__tecnico_asignado=tecnico)
    ).filter(
        Q(estado__in=['COMPLETADO', 'ENTREGADO']) | Q(facturado=True) | Q(venta__isnull=False)
    ).filter(
        Q(fecha_completado__date__gte=inicio, fecha_completado__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__fecha_hora__date__gte=inicio, venta__fecha_hora__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__date__gte=inicio, fecha_entrega__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__isnull=True, fecha_ingreso__date__gte=inicio, fecha_ingreso__date__lte=fin)
    ).distinct().select_related('cliente', 'venta', 'tecnico_principal').prefetch_related(
        'servicios__tipo_servicio', 'servicios__tecnico_asignado'
    )

    lista_ordenes_semana = []
    ordenes_venta_ids = set()

    for orden in ordenes_sem:
        if orden.venta_id:
            ordenes_venta_ids.add(orden.venta_id)

        fecha_orden = orden.fecha_completado or (orden.venta.fecha_hora if orden.venta else None) or orden.fecha_entrega or orden.fecha_ingreso
        fecha_orden_date = timezone.localtime(fecha_orden).date() if fecha_orden else inicio

        servicios_orden_tec = [
            s for s in orden.servicios.all()
            if (s.tecnico_asignado_id == tecnico.id) or (s.tecnico_asignado_id is None and orden.tecnico_principal_id == tecnico.id)
        ]

        cliente_str = orden.cliente.get_nombre_completo() if orden.cliente else '—'
        vehiculo_str = f"{orden.moto_marca or ''} {orden.moto_modelo or ''}".strip()
        if orden.moto_placa:
            vehiculo_str = f"{vehiculo_str} ({orden.moto_placa})" if vehiculo_str else orden.moto_placa
        if not vehiculo_str:
            vehiculo_str = '—'

        if servicios_orden_tec:
            for s in servicios_orden_tec:
                val = s.precio_servicio or Decimal('0')
                com = val * factor
                lista_ordenes_semana.append({
                    'id': f"ORD-{orden.id}-{s.id}",
                    'tipo': 'ORDEN',
                    'tipo_label': 'Orden de Taller',
                    'orden_id': orden.id,
                    'venta_id': orden.venta_id,
                    'numero': orden.numero_orden,
                    'factura': orden.venta.numero_factura if orden.venta else None,
                    'fecha': fecha_orden,
                    'fecha_date': fecha_orden_date,
                    'cliente': cliente_str,
                    'vehiculo': vehiculo_str,
                    'servicio': s.nombre_servicio_personalizado or (s.tipo_servicio.nombre if s.tipo_servicio else 'Servicio de Taller'),
                    'valor': val,
                    'comision': com,
                    'liquidada': orden.comision_liquidada,
                    'estado_orden': orden.get_estado_display(),
                    'facturado': orden.facturado or (orden.venta is not None),
                })
        elif orden.tecnico_principal_id == tecnico.id and (orden.precio_mano_obra and orden.precio_mano_obra > 0):
            val = orden.precio_mano_obra
            com = val * factor
            lista_ordenes_semana.append({
                'id': f"ORD-{orden.id}",
                'tipo': 'ORDEN',
                'tipo_label': 'Orden de Taller',
                'orden_id': orden.id,
                'venta_id': orden.venta_id,
                'numero': orden.numero_orden,
                'factura': orden.venta.numero_factura if orden.venta else None,
                'fecha': fecha_orden,
                'fecha_date': fecha_orden_date,
                'cliente': cliente_str,
                'vehiculo': vehiculo_str,
                'servicio': f"Mano de obra - {orden.motivo_ingreso[:60]}" if orden.motivo_ingreso else f"Mano de obra Orden #{orden.numero_orden}",
                'valor': val,
                'comision': com,
                'liquidada': orden.comision_liquidada,
                'estado_orden': orden.get_estado_display(),
                'facturado': orden.facturado or (orden.venta is not None),
            })

    # -------------------------------------------------------------------------
    # 2. SERVICIOS DE POS (Mecánica Rápida)
    # -------------------------------------------------------------------------
    serv_pos_sem = DetalleVenta.objects.filter(
        tecnico=tecnico,
        es_servicio=True,
        venta__estado='COMPLETADA',
        venta__fecha_hora__date__gte=inicio,
        venta__fecha_hora__date__lte=fin,
    ).select_related('venta', 'venta__cliente', 'tipo_servicio')

    # Excluimos ventas que ya pertenezcan a órdenes de taller para no duplicar
    if ordenes_venta_ids:
        serv_pos_sem = serv_pos_sem.exclude(venta_id__in=ordenes_venta_ids)

    lista_pos_semana = []
    for d in serv_pos_sem:
        fecha_pos = d.venta.fecha_hora
        fecha_pos_date = timezone.localtime(fecha_pos).date() if fecha_pos else inicio
        val = _base_comision_detalle(d)
        com = val * factor
        lista_pos_semana.append({
            'id': f"POS-{d.id}",
            'tipo': 'POS',
            'tipo_label': 'Mecánica Rápida (POS)',
            'orden_id': None,
            'venta_id': d.venta_id,
            'detalle_id': d.id,
            'numero': d.venta.numero_factura or f"POS #{d.venta_id}",
            'factura': d.venta.numero_factura,
            'fecha': fecha_pos,
            'fecha_date': fecha_pos_date,
            'cliente': d.venta.cliente.get_nombre_completo() if d.venta.cliente else 'Consumidor Final',
            'vehiculo': '—',
            'servicio': d.nombre_personalizado or (d.tipo_servicio.nombre if d.tipo_servicio else 'Servicio Rápido POS'),
            'valor': val,
            'comision': com,
            'liquidada': d.comision_liquidada,
            'estado_orden': 'Completada',
            'facturado': True,
        })

    # Todos los trabajos de la semana ordenados por fecha desc
    todos_trabajos_semana = sorted(
        lista_ordenes_semana + lista_pos_semana,
        key=lambda x: x['fecha'],
        reverse=True
    )

    # -------------------------------------------------------------------------
    # 3. DESGLOSE DIARIO (LUNES A SÁBADO = 6 DÍAS)
    # -------------------------------------------------------------------------
    dias_nombres = [
        ('Lun', 'Lunes'),
        ('Mar', 'Martes'),
        ('Mié', 'Miércoles'),
        ('Jue', 'Jueves'),
        ('Vie', 'Viernes'),
        ('Sáb', 'Sábado'),
    ]

    por_dia = []
    max_dia_total = 0
    for i, (abbrev, nombre_completo) in enumerate(dias_nombres):
        dd = inicio + timedelta(days=i)
        trabajos_este_dia = [t for t in todos_trabajos_semana if t['fecha_date'] == dd]
        tot_servicios = len(trabajos_este_dia)
        val_dia = sum((t['valor'] for t in trabajos_este_dia), Decimal('0'))
        com_dia = sum((t['comision'] for t in trabajos_este_dia), Decimal('0'))
        tot_ordenes = sum(1 for t in trabajos_este_dia if t['tipo'] == 'ORDEN')
        tot_pos = sum(1 for t in trabajos_este_dia if t['tipo'] == 'POS')

        por_dia.append({
            'label': abbrev,
            'nombre': nombre_completo,
            'fecha': dd,
            'total': tot_servicios,
            'valor': val_dia,
            'comision': com_dia,
            'ordenes': tot_ordenes,
            'pos': tot_pos,
            'es_hoy': (dd == hoy),
            'activo': (dia == dd),
        })
        if tot_servicios > max_dia_total:
            max_dia_total = tot_servicios

    for x in por_dia:
        x['pct'] = int((x['total'] / max_dia_total) * 100) if max_dia_total else 0

    # -------------------------------------------------------------------------
    # 4. FILTRADO POR DÍA
    # -------------------------------------------------------------------------
    if dia:
        trabajos_filtrados = [t for t in todos_trabajos_semana if t['fecha_date'] == dia]
        dia_info = next((d for d in por_dia if d['fecha'] == dia), None)
    else:
        trabajos_filtrados = todos_trabajos_semana
        dia_info = None

    lista_ordenes_vista = [t for t in trabajos_filtrados if t['tipo'] == 'ORDEN']
    lista_pos_vista = [t for t in trabajos_filtrados if t['tipo'] == 'POS']

    # -------------------------------------------------------------------------
    # 5. TOTALES Y LIQUIDACIÓN DE LA SEMANA (Lunes a Sábado)
    # -------------------------------------------------------------------------
    total_servicios_semana = len(todos_trabajos_semana)
    base_ordenes_semana = sum((t['valor'] for t in lista_ordenes_semana), Decimal('0'))
    comision_ordenes_semana = sum((t['comision'] for t in lista_ordenes_semana), Decimal('0'))

    base_pos_semana = sum((t['valor'] for t in lista_pos_semana), Decimal('0'))
    comision_pos_semana = sum((t['comision'] for t in lista_pos_semana), Decimal('0'))

    valor_neto_total_semana = base_ordenes_semana + base_pos_semana
    comision_total_semana = comision_ordenes_semana + comision_pos_semana

    # Deudas pendientes (adelantos + productos tomados a cuenta). El administrador
    # decide cuánto se descuenta (parcial o total) al liquidar la semana.
    deudas = _deudas_pendientes(tecnico)
    total_adelantos_semana = deudas['total']
    neto_semana = max(Decimal('0'), comision_total_semana - total_adelantos_semana)

    resumen_semana = {
        'total_servicios': total_servicios_semana,
        'total_ordenes': len(lista_ordenes_semana),
        'total_pos': len(lista_pos_semana),
        'base_ordenes': base_ordenes_semana,
        'comision_ordenes': comision_ordenes_semana,
        'base_pos': base_pos_semana,
        'comision_pos': comision_pos_semana,
        'valor_neto_total': valor_neto_total_semana,
        'comision_total': comision_total_semana,
        'adelantos_semana': total_adelantos_semana,
        'deuda_adelantos': deudas['adelantos_saldo'],
        'deuda_consumos': deudas['consumos_saldo'],
        'neto_a_pagar': neto_semana,
        'porcentaje_comision': porcentaje_cfg,
        'gana_comision': gana_comision,
        # Vista actual (día o semana):
        'servicios_vista': len(trabajos_filtrados),
        'valor_vista': sum((t['valor'] for t in trabajos_filtrados), Decimal('0')),
        'comision_vista': sum((t['comision'] for t in trabajos_filtrados), Decimal('0')),
        'ordenes_vista_count': len(lista_ordenes_vista),
        'pos_vista_count': len(lista_pos_vista),
    }

    cuenta_historica = _resumen_cuenta_tecnico(tecnico)

    seccion = request.GET.get('seccion') or seccion or 'calculadora'
    template_map = {
        'calculadora': 'taller/panel_tecnico/calculadora.html',
        'ordenes': 'taller/panel_tecnico/ordenes.html',
        'pos': 'taller/panel_tecnico/pos.html',
        'cuenta': 'taller/panel_tecnico/cuenta.html',
        'perfil': 'taller/panel_tecnico/perfil.html',
        'rendimiento': 'taller/panel_tecnico/rendimiento.html',
    }
    template_name = template_map.get(seccion, 'taller/panel_tecnico/calculadora.html')

    ranking = None
    periodo_rank = 'semana'
    if seccion == 'rendimiento':
        if request.GET.get('periodo') == 'mes':
            periodo_rank = 'mes'
            ranking = ranking_rango('mes', fecha_ref, yo=tecnico)
        else:
            ranking = _ranking_tecnicos(inicio, fin, dia=dia if (dia and inicio <= dia <= fin) else None, yo=tecnico)
            ranking['etiqueta'] = None

    return render(request, template_name, {
        'seccion': seccion,
        'ranking': ranking,
        'periodo_rank': periodo_rank,
        'tecnico': tecnico,
        'resumen_semana': resumen_semana,
        'por_dia': por_dia,
        'trabajos_filtrados': trabajos_filtrados,
        'lista_ordenes': lista_ordenes_vista,
        'lista_pos': lista_pos_vista,
        'inicio': inicio,
        'fin': fin,
        'hoy': hoy,
        'dia': dia,
        'dia_info': dia_info,
        'semana_anterior': semana_anterior,
        'semana_siguiente': semana_siguiente,
        'es_semana_actual': es_semana_actual,
        'cuenta': cuenta_historica,
        'pagos_recientes': tecnico.pagos.all()[:15],
        'adelantos_recientes': tecnico.adelantos.all()[:15],
        'consumos_recientes': tecnico.consumos.select_related('producto').filter(anulado=False)[:15],
        'gana_comision': gana_comision,
        'gana_salario': getattr(tecnico, 'gana_salario', False),
        'salario_info': _info_salario(tecnico, hoy) if getattr(tecnico, 'gana_salario', False) else None,
        'es_preview_admin': getattr(request.user, 'tecnico', None) is None,
    })


# ============================================================================
def _base_comision_detalle(d):
    """Valor de un servicio cobrado en POS sobre el que se paga la comisión: SIN IVA.
    El IVA no es ingreso del taller (se paga al SRI), así que no genera comisión."""
    total = d.total if d.total is not None else (d.subtotal or Decimal('0'))
    return max(Decimal('0'), (total or Decimal('0')) - (d.iva or Decimal('0')))


def _servicios_pendientes_tecnico(tecnico):
    """Líneas de SERVICIO (solo el servicio, no repuestos) cobradas en POS,
    del técnico, en ventas completadas y aún no liquidadas para comisión."""
    from ventas.models import DetalleVenta
    return DetalleVenta.objects.filter(
        tecnico=tecnico, es_servicio=True,
        venta__estado='COMPLETADA', comision_liquidada=False,
    )


def _ventas_de_ordenes(venta_ids):
    """Subconjunto de venta_ids que corresponden a una Orden de Trabajo."""
    if not venta_ids:
        return set()
    return set(OrdenTrabajo.objects.filter(
        venta_id__in=venta_ids).values_list('venta_id', flat=True))


def _factor_comision(tecnico):
    """Fracción de comisión del técnico (porcentaje configurable).

    Si no gana comisión -> 0. Si el porcentaje no está configurado, usa 50%
    (equivalente al ÷2 histórico) para no romper técnicos existentes.
    """
    if not getattr(tecnico, 'gana_comision', True):
        return Decimal('0')
    pct = tecnico.porcentaje_comision or Decimal('50')
    return pct / Decimal('100')


def _deudas_pendientes(tecnico, lock=False):
    """Deudas del técnico por descontar: adelantos de efectivo + productos del
    inventario tomados a cuenta. Cada una con su saldo (permite cobros parciales)."""
    from .models import AdelantoTecnico, ConsumoTecnico
    qa = AdelantoTecnico.objects.filter(tecnico=tecnico, liquidado=False).order_by('fecha')
    qc = ConsumoTecnico.objects.filter(tecnico=tecnico, liquidado=False, anulado=False).order_by('fecha')
    if lock:
        qa = qa.select_for_update()
        qc = qc.select_for_update()
    adel = list(qa)
    cons = list(qc.select_related('producto'))
    s_adel = sum((x.saldo for x in adel), Decimal('0'))
    s_cons = sum((x.saldo for x in cons), Decimal('0'))
    return {
        'adelantos': adel, 'consumos': cons,
        'adelantos_saldo': s_adel, 'consumos_saldo': s_cons,
        'total': s_adel + s_cons,
    }


def _resolver_descuento(data, deuda, bruto):
    """Determina cuánto y qué deudas se descuentan al liquidar.

    modo_descuento:
      - 'seleccion' : el admin marcó adelantos y/o productos concretos (adelanto_ids / consumo_ids);
                      si además manda monto_descuento, solo se descuenta ese monto (cobro parcial).
      - 'total' / 'parcial' / 'ninguno': comportamiento anterior sobre toda la deuda.
    Devuelve (descuento, ids_adelantos, ids_consumos, error_response)."""
    modo = (data.get('modo_descuento') or 'total').strip().lower()
    ids_a = ids_c = None
    if modo == 'seleccion':
        ids_a = {int(x) for x in (data.get('adelanto_ids') or []) if str(x).isdigit()}
        ids_c = {int(x) for x in (data.get('consumo_ids') or []) if str(x).isdigit()}
        disponible = (sum((a.saldo for a in deuda['adelantos'] if a.pk in ids_a), Decimal('0')) +
                      sum((c.saldo for c in deuda['consumos'] if c.pk in ids_c), Decimal('0')))
    else:
        disponible = deuda['total']
    tope = min(disponible, bruto)

    raw = data.get('monto_descuento')
    quiere_parcial = modo == 'parcial' or (modo == 'seleccion' and raw not in (None, ''))
    if modo == 'ninguno':
        descuento = Decimal('0')
    elif quiere_parcial:
        try:
            descuento = Decimal(str(raw or '0'))
        except (InvalidOperation, ValueError):
            descuento = Decimal('-1')
        if descuento < 0:
            return None, None, None, JsonResponse({'success': False, 'message': 'El monto a descontar no es válido.'}, status=400)
        if descuento > tope:
            return None, None, None, JsonResponse({
                'success': False,
                'message': f'Lo máximo que se puede descontar es ${tope:.2f} (seleccionado ${disponible:.2f}, a pagar ${bruto:.2f}).'
            }, status=400)
    else:
        descuento = tope   # todo lo seleccionado, sin pasar de lo que se le paga
    return descuento.quantize(Decimal('0.01')), ids_a, ids_c, None


def _aplicar_descuento_deudas(tecnico, monto, pago, ids_adelantos=None, ids_consumos=None):
    """Descuenta `monto` de las deudas, de la más antigua a la más nueva.
    Devuelve (aplicado_a_adelantos, aplicado_a_consumos)."""
    d = _deudas_pendientes(tecnico, lock=True)
    items = ([('A', x) for x in d['adelantos'] if ids_adelantos is None or x.pk in ids_adelantos] +
             [('C', x) for x in d['consumos'] if ids_consumos is None or x.pk in ids_consumos])
    items.sort(key=lambda t: t[1].fecha)
    restante = monto
    ap_a = Decimal('0')
    ap_c = Decimal('0')
    for tipo, obj in items:
        if restante <= 0:
            break
        aplicar = min(obj.saldo, restante)
        if aplicar <= 0:
            continue
        obj.abonado = (obj.abonado or Decimal('0')) + aplicar
        obj.pago = pago
        if obj.saldo <= 0:
            obj.liquidado = True
        obj.save(update_fields=['abonado', 'pago', 'liquidado'])
        restante -= aplicar
        if tipo == 'A':
            ap_a += aplicar
        else:
            ap_c += aplicar
    return ap_a, ap_c


from .ranking import _ranking_tecnicos, ranking_rango  # noqa: E402


def pantalla_publica(request, token):
    """Monitor del taller (pantalla completa). Sin login: se protege con un token
    en la URL. Solo muestra servicios realizados, nunca dinero."""
    from .ranking import token_valido, payload_publico
    from django.http import Http404
    if not token_valido(token):
        raise Http404()
    resp = render(request, 'taller/pantalla_publica.html', {'token': token, 'payload': payload_publico()})
    resp['Cache-Control'] = 'no-store'
    return resp


def pantalla_publica_datos(request, token):
    """Respaldo por HTTP del monitor (si el WebSocket no está disponible)."""
    from .ranking import token_valido, payload_publico
    from django.http import Http404
    if not token_valido(token):
        raise Http404()
    per = request.GET.get('periodo')
    try:
        fecha = datetime.strptime(request.GET.get('fecha') or '', '%Y-%m-%d').date()
    except ValueError:
        fecha = None
    resp = JsonResponse(payload_publico(periodo=per, fecha=fecha))
    resp['Cache-Control'] = 'no-store'
    return resp


@admin_requerido
def rendimiento_tecnicos(request):
    """Ranking de rendimiento de los técnicos activos por semana (lun–sáb), día o mes.
    Solo administradores."""
    hoy = timezone.localdate()
    try:
        ref = datetime.strptime(request.GET.get('fecha') or '', '%Y-%m-%d').date()
    except ValueError:
        ref = hoy
    periodo = 'mes' if request.GET.get('periodo') == 'mes' else 'semana'
    if periodo == 'mes':
        rank = ranking_rango('mes', ref)
        rank['dia'] = None
        return render(request, 'taller/rendimiento_tecnicos.html', {
            'rank': rank, 'periodo': 'mes', 'etiqueta': rank['etiqueta'],
            'inicio': rank['inicio'], 'fin': rank['fin'], 'dia': None, 'hoy': hoy,
            'anterior': rank['anterior'], 'siguiente': rank['siguiente'],
            'es_actual': rank['es_actual'], 'dias': [],
        })
    inicio = ref - timedelta(days=ref.weekday())
    fin = inicio + timedelta(days=5)
    try:
        dia = datetime.strptime(request.GET.get('dia') or '', '%Y-%m-%d').date()
        if not (inicio <= dia <= fin):
            dia = None
    except ValueError:
        dia = None
    rank = _ranking_tecnicos(inicio, fin, dia=dia)
    return render(request, 'taller/rendimiento_tecnicos.html', {
        'rank': rank, 'periodo': 'semana',
        'etiqueta': f'Semana {inicio:%d/%m} al {fin:%d/%m/%Y} (lunes a sábado)',
        'inicio': inicio, 'fin': fin, 'dia': dia, 'hoy': hoy,
        'anterior': inicio - timedelta(days=7), 'siguiente': inicio + timedelta(days=7),
        'es_actual': inicio == hoy - timedelta(days=hoy.weekday()),
        'dias': [inicio + timedelta(days=i) for i in range(6)],
    })


def _periodo_salario(tecnico, ref):
    """Periodo de salario (inicio, fin) que contiene la fecha `ref`, según la
    periodicidad del técnico: SEMANAL (lun–sáb), QUINCENAL (1–15 / 16–fin) o MENSUAL."""
    import calendar
    per = tecnico.periodicidad_salario or 'MENSUAL'
    if per == 'SEMANAL':
        ini = ref - timedelta(days=ref.weekday())
        return ini, ini + timedelta(days=5)
    ultimo = calendar.monthrange(ref.year, ref.month)[1]
    if per == 'QUINCENAL':
        if ref.day <= 15:
            return ref.replace(day=1), ref.replace(day=15)
        return ref.replace(day=16), ref.replace(day=ultimo)
    return ref.replace(day=1), ref.replace(day=ultimo)


def _info_salario(tecnico, ref):
    """Estado del salario del técnico en el periodo de `ref` (para admin y panel)."""
    from .models import PagoTecnico
    hoy = timezone.localdate()
    ini, fin = _periodo_salario(tecnico, ref)
    ini_hoy, _fin_hoy = _periodo_salario(tecnico, hoy)
    paso = 2 if (tecnico.periodicidad_salario == 'SEMANAL') else 1
    ant, _ = _periodo_salario(tecnico, ini - timedelta(days=1))
    sig, _ = _periodo_salario(tecnico, fin + timedelta(days=paso))
    pago = PagoTecnico.objects.filter(
        tecnico=tecnico, tipo='SALARIO', semana_inicio=ini, semana_fin=fin).first()
    return {
        'inicio': ini, 'fin': fin,
        'salario': tecnico.salario_base or Decimal('0'),
        'periodicidad': tecnico.get_periodicidad_salario_display() if tecnico.periodicidad_salario else 'Mensual',
        'pago': pago, 'pagado': pago is not None,
        'anterior': ant, 'siguiente': sig,
        'es_actual': ini == ini_hoy,
    }


def _resumen_cuenta_tecnico(tecnico):
    """Comisión pendiente acumulada = valor de los servicios cobrados en POS
    y órdenes de trabajo completadas/facturadas no liquidadas.
    Descuenta adelantos para el neto a pagar."""
    from .models import AdelantoTecnico
    pend = _servicios_pendientes_tecnico(tecnico)
    vids = list(pend.values_list('venta_id', flat=True).distinct())
    ord_vids = _ventas_de_ordenes(vids)

    en_orden = pend.filter(venta_id__in=ord_vids)
    en_pos = pend.exclude(venta_id__in=ord_vids)
    base_ord = en_orden.aggregate(s=Sum(F('total') - F('iva')))['s'] or Decimal('0')
    base_pos = en_pos.aggregate(s=Sum(F('total') - F('iva')))['s'] or Decimal('0')

    # Órdenes de taller completadas o facturadas donde el técnico es principal y aún no liquidadas
    ordenes_pend = OrdenTrabajo.objects.filter(
        tecnico_principal=tecnico,
        comision_liquidada=False,
    ).filter(
        Q(estado__in=['COMPLETADO', 'ENTREGADO']) | Q(facturado=True)
    ).exclude(venta_id__in=vids)
    base_ord_extra = ordenes_pend.aggregate(s=Sum('precio_mano_obra'))['s'] or Decimal('0')
    base_ord += base_ord_extra

    factor = _factor_comision(tecnico)
    com_ord = base_ord * factor
    com_pos = base_pos * factor
    comision_pendiente = com_ord + com_pos

    total_adel = _deudas_pendientes(tecnico)['total']

    return {
        'comision_pendiente': comision_pendiente,
        'comision_ordenes': com_ord,
        'comision_pos': com_pos,
        'base_ordenes': base_ord,
        'base_pos': base_pos,
        'servicios_ordenes': en_orden.count() + ordenes_pend.count(),
        'servicios_pos': en_pos.count(),
        'servicios_pendientes': pend.count() + ordenes_pend.count(),
        'adelantos_pendientes': total_adel,
        'neto_a_pagar': comision_pendiente - total_adel,
    }


@admin_requerido
def cuenta_tecnico(request, pk):
    """Página (admin) para gestionar liquidaciones semanales de un técnico."""
    from datetime import date as date_obj
    from ventas.models import DetalleVenta
    tecnico = get_object_or_404(Tecnico, pk=pk)

    # Semana a visualizar (parámetro ?fecha=YYYY-MM-DD → lunes de esa semana)
    hoy = date_obj.today()
    fecha_str = request.GET.get('fecha')
    if fecha_str:
        try:
            fecha_ref = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_ref = hoy
    else:
        fecha_ref = hoy

    inicio = fecha_ref - timedelta(days=fecha_ref.weekday())     # Lunes
    fin    = inicio + timedelta(days=5)                           # Sábado
    semana_anterior  = inicio - timedelta(weeks=1)
    semana_siguiente = inicio + timedelta(weeks=1)
    es_semana_actual = (inicio == (hoy - timedelta(days=hoy.weekday())))

    # Factor y porcentaje de comisión del técnico
    factor = _factor_comision(tecnico)
    gana_comision = getattr(tecnico, 'gana_comision', True)
    if not gana_comision:
        porcentaje_cfg = Decimal('0')
    else:
        porcentaje_cfg = tecnico.porcentaje_comision if (tecnico.porcentaje_comision and tecnico.porcentaje_comision > 0) else Decimal('50')

    # ---- Servicios de ÓRDENES de esta semana ----
    ordenes_sem = OrdenTrabajo.objects.filter(
        Q(tecnico_principal=tecnico) | Q(servicios__tecnico_asignado=tecnico)
    ).filter(
        Q(estado__in=['COMPLETADO', 'ENTREGADO']) | Q(facturado=True) | Q(venta__isnull=False)
    ).filter(
        Q(fecha_completado__date__gte=inicio, fecha_completado__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__fecha_hora__date__gte=inicio, venta__fecha_hora__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__date__gte=inicio, fecha_entrega__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__isnull=True, fecha_ingreso__date__gte=inicio, fecha_ingreso__date__lte=fin)
    ).distinct().select_related('cliente', 'venta', 'tecnico_principal').prefetch_related(
        'servicios__tipo_servicio',
    )

    ordenes_venta_ids = set()
    lista_ordenes = []
    for orden in ordenes_sem:
        if orden.venta_id:
            ordenes_venta_ids.add(orden.venta_id)
        fecha_orden = orden.fecha_completado or (orden.venta.fecha_hora if orden.venta else None) or orden.fecha_entrega or orden.fecha_ingreso
        cliente_str = orden.cliente.get_nombre_completo() if orden.cliente else '—'
        vehiculo_str = f"{orden.moto_marca or ''} {orden.moto_modelo or ''}".strip()
        if orden.moto_placa:
            vehiculo_str = f"{vehiculo_str} ({orden.moto_placa})" if vehiculo_str else orden.moto_placa
        servicios_tec = [s for s in orden.servicios.all()
            if (s.tecnico_asignado_id == tecnico.id) or (s.tecnico_asignado_id is None and orden.tecnico_principal_id == tecnico.id)]

        if servicios_tec:
            for s in servicios_tec:
                val = s.precio_servicio or Decimal('0')
                lista_ordenes.append({
                    'tipo': 'ORDEN', 'venta_id': orden.venta_id, 'numero': orden.numero_orden,
                    'fecha': fecha_orden, 'cliente': cliente_str, 'vehiculo': vehiculo_str,
                    'servicio': s.nombre_servicio_personalizado or (s.tipo_servicio.nombre if s.tipo_servicio else 'Servicio de Taller'),
                    'valor': val, 'comision': val * factor,
                    'liquidada': orden.comision_liquidada, 'estado_orden': orden.get_estado_display(),
                })
        elif orden.tecnico_principal_id == tecnico.id and (orden.precio_mano_obra and orden.precio_mano_obra > 0):
            val = orden.precio_mano_obra
            lista_ordenes.append({
                'tipo': 'ORDEN', 'venta_id': orden.venta_id, 'numero': orden.numero_orden,
                'fecha': fecha_orden, 'cliente': cliente_str, 'vehiculo': vehiculo_str,
                'servicio': f"Mano de obra - {orden.motivo_ingreso[:50]}" if orden.motivo_ingreso else f"Mano de obra Orden #{orden.numero_orden}",
                'valor': val, 'comision': val * factor,
                'liquidada': orden.comision_liquidada, 'estado_orden': orden.get_estado_display(),
            })

    # ---- Servicios de POS de esta semana ----
    serv_pos = DetalleVenta.objects.filter(
        tecnico=tecnico, es_servicio=True,
        venta__estado='COMPLETADA',
        venta__fecha_hora__date__gte=inicio,
        venta__fecha_hora__date__lte=fin,
    ).select_related('venta', 'venta__cliente', 'tipo_servicio')
    if ordenes_venta_ids:
        serv_pos = serv_pos.exclude(venta_id__in=ordenes_venta_ids)

    lista_pos = []
    for d in serv_pos:
        val = _base_comision_detalle(d)
        lista_pos.append({
            'tipo': 'POS', 'venta_id': d.venta_id,
            'numero': d.venta.numero_factura or f"POS #{d.venta_id}",
            'fecha': d.venta.fecha_hora,
            'cliente': d.venta.cliente.get_nombre_completo() if d.venta.cliente else 'Consumidor Final',
            'servicio': d.nombre_personalizado or (d.tipo_servicio.nombre if d.tipo_servicio else 'Servicio Rápido POS'),
            'valor': val, 'comision': val * factor,
            'liquidada': d.comision_liquidada,
        })

    todos = sorted(lista_ordenes + lista_pos, key=lambda x: (x['fecha'] or inicio), reverse=True)

    # Totales de la semana
    base_ord = sum((t['valor'] for t in lista_ordenes), Decimal('0'))
    com_ord  = sum((t['comision'] for t in lista_ordenes), Decimal('0'))
    base_pos = sum((t['valor'] for t in lista_pos), Decimal('0'))
    com_pos  = sum((t['comision'] for t in lista_pos), Decimal('0'))
    neto_total = base_ord + base_pos
    com_total  = com_ord + com_pos

    # Deudas pendientes del técnico (adelantos + inventario a cuenta)
    deudas = _deudas_pendientes(tecnico)
    total_adelantos_sem = deudas['total']
    descuento_max = min(deudas['total'], com_total)
    neto_a_pagar = max(Decimal('0'), com_total - descuento_max)

    # ¿Ya tiene liquidación para esta semana?
    from .models import PagoTecnico
    liquidacion_existente = PagoTecnico.objects.filter(
        tecnico=tecnico, semana_inicio=inicio, semana_fin=fin, tipo='COMISION'
    ).first()

    # Historial de liquidaciones previas
    historial_pagos = tecnico.pagos.all()[:30]
    # Adelantos generales recientes
    adelantos_all = tecnico.adelantos.select_related('pago').all()[:20]

    resumen_semana = {
        'inicio': inicio, 'fin': fin,
        'total_ordenes': len(lista_ordenes),
        'total_pos': len(lista_pos),
        'total_servicios': len(todos),
        'base_ordenes': base_ord, 'comision_ordenes': com_ord,
        'base_pos': base_pos, 'comision_pos': com_pos,
        'neto_total': neto_total, 'comision_total': com_total,
        'adelantos_semana': total_adelantos_sem,
        'deuda_adelantos': deudas['adelantos_saldo'],
        'deuda_consumos': deudas['consumos_saldo'],
        'descuento_max': descuento_max,
        'neto_a_pagar': neto_a_pagar,
        'porcentaje': porcentaje_cfg,
        'ya_liquidada': liquidacion_existente is not None,
        'liquidacion': liquidacion_existente,
    }

    # Salario fijo (si el técnico gana salario): periodo elegido con ?periodo=YYYY-MM-DD
    salario_info = None
    if getattr(tecnico, 'gana_salario', False):
        ref_s = hoy
        per_str = request.GET.get('periodo')
        if per_str:
            try:
                ref_s = datetime.strptime(per_str, '%Y-%m-%d').date()
            except ValueError:
                ref_s = hoy
        salario_info = _info_salario(tecnico, ref_s)
        salario_info['descuento_max'] = min(deudas['total'], salario_info['salario'])
        salario_info['neto'] = salario_info['salario'] - salario_info['descuento_max']

    return render(request, 'taller/cuenta_tecnico.html', {
        'tecnico': tecnico,
        'gana_comision': getattr(tecnico, 'gana_comision', True),
        'gana_salario': getattr(tecnico, 'gana_salario', False),
        'salario_info': salario_info,
        'deuda_total': deudas['total'],
        'deudas_adelantos_lista': deudas['adelantos'],
        'deudas_consumos_lista': deudas['consumos'],
        'resumen_semana': resumen_semana,
        'trabajos': todos,
        'historial_pagos': historial_pagos,
        'adelantos': adelantos_all,
        'consumos': tecnico.consumos.select_related('producto').all()[:30],
        'inicio': inicio, 'fin': fin,
        'semana_anterior': semana_anterior,
        'semana_siguiente': semana_siguiente,
        'es_semana_actual': es_semana_actual,
        'hoy': hoy,
    })


@admin_requerido
def registrar_adelanto(request, pk):
    """Registra un adelanto / dinero entregado al técnico (admin)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    tecnico = get_object_or_404(Tecnico, pk=pk)
    from .models import AdelantoTecnico
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = request.POST
    try:
        monto = Decimal(str(data.get('monto', '0')))
    except (InvalidOperation, ValueError):
        monto = Decimal('0')
    if monto <= 0:
        return JsonResponse({'success': False, 'message': 'El monto debe ser mayor a 0.'}, status=400)
    AdelantoTecnico.objects.create(
        tecnico=tecnico, monto=monto,
        descripcion=(data.get('descripcion') or '').strip(),
        usuario_registro=request.user if request.user.is_authenticated else None,
    )
    return JsonResponse({'success': True, 'message': f'Adelanto de ${monto} registrado.'})


@admin_requerido
def registrar_consumo(request, pk):
    """Anota un producto del inventario que el técnico se lleva a cuenta.
    Descuenta stock y queda como deuda del técnico."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    tecnico = get_object_or_404(Tecnico, pk=pk)
    from .models import ConsumoTecnico
    from inventario.models import MovimientoInventario
    from django.db.models import F
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = request.POST
    try:
        cantidad = Decimal(str(data.get('cantidad') or '0'))
    except (InvalidOperation, ValueError):
        cantidad = Decimal('0')
    if cantidad <= 0:
        return JsonResponse({'success': False, 'message': 'La cantidad debe ser mayor a 0.'}, status=400)

    with transaction.atomic():
        producto = Producto.objects.select_for_update().filter(pk=data.get('producto_id'), activo=True).first()
        if not producto:
            return JsonResponse({'success': False, 'message': 'Producto no encontrado o inactivo.'}, status=400)
        if producto.stock_actual < cantidad:
            return JsonResponse({
                'success': False,
                'message': f'Stock insuficiente de "{producto.nombre}": hay {producto.stock_actual}.'
            }, status=400)
        try:
            precio = Decimal(str(data.get('precio_unitario') or producto.precio_venta))
        except (InvalidOperation, ValueError):
            precio = producto.precio_venta
        if precio < 0:
            return JsonResponse({'success': False, 'message': 'El precio no es válido.'}, status=400)
        total = (cantidad * precio).quantize(Decimal('0.01'))
        usuario = request.user if request.user.is_authenticated else None

        consumo = ConsumoTecnico.objects.create(
            tecnico=tecnico, producto=producto, cantidad=cantidad,
            precio_unitario=precio, total=total,
            descripcion=(data.get('descripcion') or '').strip(),
            usuario_registro=usuario,
        )
        stock_ant = producto.stock_actual
        # update() para no disparar la señal de "ajuste automático": el movimiento se registra aquí
        Producto.objects.filter(pk=producto.pk).update(stock_actual=F('stock_actual') - cantidad)
        MovimientoInventario.objects.create(
            producto=producto, usuario=usuario, tipo_movimiento='SALIDA',
            cantidad=cantidad, stock_anterior=stock_ant, stock_nuevo=stock_ant - cantidad,
            precio_unitario=precio,
            motivo=f'Consumo a cuenta del técnico {tecnico.get_nombre_completo()}',
            referencia=f'CONSUMO-TEC-{consumo.pk}',
        )
    return JsonResponse({'success': True, 'message': f'{producto.nombre} x{cantidad} anotado a {tecnico.nombres} (${total}).'})


@admin_requerido
def anular_consumo(request, pk):
    """Anula un consumo aún no cobrado y devuelve el producto al stock."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    from .models import ConsumoTecnico
    from inventario.models import MovimientoInventario
    from django.db.models import F
    with transaction.atomic():
        c = ConsumoTecnico.objects.select_for_update().select_related('producto', 'tecnico').filter(pk=pk).first()
        if not c:
            return JsonResponse({'success': False, 'message': 'Consumo no encontrado.'}, status=404)
        if c.anulado:
            return JsonResponse({'success': False, 'message': 'Este consumo ya está anulado.'}, status=400)
        if c.abonado > 0 or c.liquidado:
            return JsonResponse({'success': False, 'message': 'No se puede anular: ya fue descontado (total o parcialmente) en un pago.'}, status=400)
        prod = Producto.objects.select_for_update().get(pk=c.producto_id)
        stock_ant = prod.stock_actual
        Producto.objects.filter(pk=prod.pk).update(stock_actual=F('stock_actual') + c.cantidad)
        MovimientoInventario.objects.create(
            producto=prod, usuario=request.user if request.user.is_authenticated else None,
            tipo_movimiento='ENTRADA', cantidad=c.cantidad,
            stock_anterior=stock_ant, stock_nuevo=stock_ant + c.cantidad,
            precio_unitario=c.precio_unitario,
            motivo=f'Anulación de consumo a cuenta de {c.tecnico.get_nombre_completo()}',
            referencia=f'CONSUMO-TEC-{c.pk}-ANULADO',
        )
        c.anulado = True
        c.save(update_fields=['anulado'])
    return JsonResponse({'success': True, 'message': 'Consumo anulado y producto devuelto al inventario.'})


@admin_requerido
def pagar_salario(request, pk):
    """Liquida el salario fijo de un periodo (semanal, quincenal o mensual).
    Igual que la comisión, permite descontar deudas (adelantos / inventario) total o parcial."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    tecnico = get_object_or_404(Tecnico, pk=pk)
    from .models import PagoTecnico
    if not getattr(tecnico, 'gana_salario', False) or not tecnico.salario_base or tecnico.salario_base <= 0:
        return JsonResponse({'success': False, 'message': 'Este técnico no tiene un salario configurado.'}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = request.POST
    try:
        ref = datetime.strptime((data.get('periodo') or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        ref = timezone.localdate()
    ini, fin = _periodo_salario(tecnico, ref)
    salario = tecnico.salario_base

    with transaction.atomic():
        if PagoTecnico.objects.filter(tecnico=tecnico, tipo='SALARIO', semana_inicio=ini, semana_fin=fin).exists():
            return JsonResponse({'success': False, 'message': f'El salario del periodo {ini:%d/%m} – {fin:%d/%m/%Y} ya fue pagado.'}, status=400)

        deuda = _deudas_pendientes(tecnico, lock=True)
        descuento, ids_a, ids_c, err = _resolver_descuento(data, deuda, salario)
        if err:
            return err

        pago = PagoTecnico.objects.create(
            tecnico=tecnico, tipo='SALARIO',
            semana_inicio=ini, semana_fin=fin,
            comision_bruta=0, salario_bruto=salario,
            adelantos_descontados=0, consumos_descontados=0,
            monto_pagado=salario, num_trabajos=0,
            porcentaje_comision=0,
            descripcion=(data.get('descripcion') or f'Salario {tecnico.get_periodicidad_salario_display()} {ini:%d/%m} – {fin:%d/%m/%Y}').strip(),
            usuario_registro=request.user if request.user.is_authenticated else None,
        )
        ap_adel, ap_cons = _aplicar_descuento_deudas(tecnico, descuento, pago, ids_a, ids_c) if descuento > 0 else (Decimal('0'), Decimal('0'))
        neto = salario - ap_adel - ap_cons
        pago.adelantos_descontados = ap_adel
        pago.consumos_descontados = ap_cons
        pago.monto_pagado = neto
        pago.save(update_fields=['adelantos_descontados', 'consumos_descontados', 'monto_pagado'])
        deuda_restante = deuda['total'] - ap_adel - ap_cons

    return JsonResponse({
        'success': True,
        'message': f'Salario {ini:%d/%m} – {fin:%d/%m/%Y} pagado. Salario ${salario:.2f} · Descuento deudas −${ap_adel + ap_cons:.2f} · Neto a entregar ${neto:.2f}.'
                   + (f' Deuda pendiente: ${deuda_restante:.2f}.' if deuda_restante > 0 else ''),
    })


@admin_requerido
def pagar_comision(request, pk):
    """Liquida la comisión de una semana específica (Lunes–Sábado) del técnico."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    tecnico = get_object_or_404(Tecnico, pk=pk)
    from .models import PagoTecnico, AdelantoTecnico
    from datetime import date as date_obj
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = request.POST

    # Recibir la semana a liquidar
    semana_str = (data.get('semana_inicio') or '').strip()
    if semana_str:
        try:
            inicio = datetime.strptime(semana_str, '%Y-%m-%d').date()
        except ValueError:
            hoy = date_obj.today()
            inicio = hoy - timedelta(days=hoy.weekday())
    else:
        hoy = date_obj.today()
        inicio = hoy - timedelta(days=hoy.weekday())
    fin = inicio + timedelta(days=5)

    # Verificar si ya existe liquidación para esta semana
    if PagoTecnico.objects.filter(tecnico=tecnico, semana_inicio=inicio, semana_fin=fin, tipo='COMISION').exists():
        return JsonResponse({'success': False, 'message': f'Esta semana ({inicio:%d/%m} – {fin:%d/%m}) ya fue liquidada.'}, status=400)

    factor = _factor_comision(tecnico)
    gana = getattr(tecnico, 'gana_comision', True)
    porcentaje_cfg = Decimal('0')
    if gana:
        pct = tecnico.porcentaje_comision if (tecnico.porcentaje_comision and tecnico.porcentaje_comision > 0) else Decimal('50')
        porcentaje_cfg = pct

    from ventas.models import DetalleVenta as DV
    with transaction.atomic():
        # Órdenes de taller de esta semana
        # PostgreSQL no permite FOR UPDATE junto con DISTINCT/joins: primero se obtienen
        # los ids y luego se bloquean esas filas por pk.
        ids_ordenes = list(OrdenTrabajo.objects.filter(
            Q(tecnico_principal=tecnico) | Q(servicios__tecnico_asignado=tecnico)
        ).filter(
            Q(estado__in=['COMPLETADO', 'ENTREGADO']) | Q(facturado=True) | Q(venta__isnull=False)
        ).filter(
            Q(fecha_completado__date__gte=inicio, fecha_completado__date__lte=fin) |
            Q(fecha_completado__isnull=True, venta__fecha_hora__date__gte=inicio, venta__fecha_hora__date__lte=fin) |
            Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__date__gte=inicio, fecha_entrega__date__lte=fin) |
            Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__isnull=True, fecha_ingreso__date__gte=inicio, fecha_ingreso__date__lte=fin)
        ).values_list('pk', flat=True).distinct())
        ordenes_sem = OrdenTrabajo.objects.select_for_update().filter(pk__in=ids_ordenes)
        ordenes_venta_ids = list(ordenes_sem.values_list('venta_id', flat=True))

        base_ordenes = Decimal('0')
        for orden in ordenes_sem:
            servicios_tec = [s for s in orden.servicios.all()
                if (s.tecnico_asignado_id == tecnico.id) or (s.tecnico_asignado_id is None and orden.tecnico_principal_id == tecnico.id)]
            if servicios_tec:
                base_ordenes += sum((s.precio_servicio or Decimal('0') for s in servicios_tec), Decimal('0'))
            elif orden.tecnico_principal_id == tecnico.id and orden.precio_mano_obra:
                base_ordenes += orden.precio_mano_obra

        # Servicios POS de esta semana
        pos_sem = DV.objects.select_for_update().filter(
            tecnico=tecnico, es_servicio=True,
            venta__estado='COMPLETADA',
            venta__fecha_hora__date__gte=inicio,
            venta__fecha_hora__date__lte=fin,
        )
        if ordenes_venta_ids:
            pos_sem = pos_sem.exclude(venta_id__in=ordenes_venta_ids)
        base_pos = pos_sem.aggregate(s=Sum(F('total') - F('iva')))['s'] or Decimal('0')

        base_total = base_ordenes + base_pos
        comision = base_total * factor
        num_trabajos = ordenes_sem.count() + pos_sem.count()

        if num_trabajos == 0:
            return JsonResponse({'success': False, 'message': 'No hay servicios pendientes de liquidar en esta semana.'}, status=400)

        # Deudas (adelantos + inventario a cuenta): el admin elige cuánto descontar
        deuda = _deudas_pendientes(tecnico, lock=True)
        descuento, ids_a, ids_c, err = _resolver_descuento(data, deuda, comision)
        if err:
            return err

        pago = PagoTecnico.objects.create(
            tecnico=tecnico,
            semana_inicio=inicio,
            semana_fin=fin,
            comision_bruta=comision,
            adelantos_descontados=0,
            consumos_descontados=0,
            monto_pagado=comision,
            num_trabajos=num_trabajos,
            porcentaje_comision=porcentaje_cfg,
            descripcion=(data.get('descripcion') or f'Semana {inicio:%d/%m} – {fin:%d/%m/%Y}').strip(),
            usuario_registro=request.user if request.user.is_authenticated else None,
        )
        ap_adel, ap_cons = _aplicar_descuento_deudas(tecnico, descuento, pago, ids_a, ids_c) if descuento > 0 else (Decimal('0'), Decimal('0'))
        total_adel = ap_adel + ap_cons
        neto = comision - total_adel
        pago.adelantos_descontados = ap_adel
        pago.consumos_descontados = ap_cons
        pago.monto_pagado = neto
        pago.save(update_fields=['adelantos_descontados', 'consumos_descontados', 'monto_pagado'])

        # Marcar servicios como liquidados
        ordenes_sem.update(comision_liquidada=True, pago_comision=pago)
        pos_sem.update(comision_liquidada=True, pago_comision=pago)
        deuda_restante = deuda['total'] - total_adel

    return JsonResponse({
        'success': True,
        'message': f'Semana {inicio:%d/%m} – {fin:%d/%m/%Y} liquidada. '
                   f'Comisión ${comision:.2f} · Descuento deudas −${total_adel:.2f} · Neto a entregar ${neto:.2f}.'
                   + (f' Deuda pendiente: ${deuda_restante:.2f}.' if deuda_restante > 0 else ''),
        'neto': str(neto), 'comision': str(comision), 'adelantos': str(total_adel),
        'deuda_restante': str(deuda_restante),
        'semana': f'{inicio:%d/%m/%Y} – {fin:%d/%m/%Y}',
    })


@login_required
def perfil_tecnico(request):
    """El técnico actualiza sus datos de contacto y su foto de perfil."""
    tecnico = getattr(request.user, 'tecnico', None)
    if tecnico is None:
        return JsonResponse({'success': False, 'message': 'Tu usuario no es un técnico.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    tecnico.telefono = (request.POST.get('telefono') or '').strip() or None
    tecnico.email = (request.POST.get('email') or '').strip() or None
    tecnico.direccion = (request.POST.get('direccion') or '').strip() or None
    if request.FILES.get('foto'):
        tecnico.foto = request.FILES['foto']
    tecnico.save()

    return JsonResponse({
        'success': True,
        'message': 'Perfil actualizado correctamente.',
        'foto_url': tecnico.foto.url if tecnico.foto else '',
    })

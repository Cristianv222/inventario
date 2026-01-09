from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
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
from .forms import (
    TecnicoForm, TipoServicioForm, OrdenTrabajoForm, ServicioOrdenForm,
    RepuestoOrdenForm, EvaluacionServicioForm,
    BusquedaOrdenForm, ServicioOrdenFormSet, RepuestoOrdenFormSet
)
from clientes.models import Cliente, Moto
from inventario.models import Producto

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
    
    hoy = timezone.now().date()
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

class TecnicoListView(LoginRequiredMixin, ListView):
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

class TecnicoDetailView(LoginRequiredMixin, DetailView):
    model = Tecnico
    template_name = 'taller/tecnico_detail.html'
    context_object_name = 'tecnico'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tecnico = self.object
        hoy = timezone.now().date()
        inicio_mes = hoy.replace(day=1)
        
        # Estadísticas del técnico
        context['ordenes_activas'] = tecnico.get_ordenes_activas()
        context['stats_mes'] = tecnico.get_servicios_mes()
        
        # Historial de órdenes recientes - CORRECCIÓN: Removido 'moto'
        context['ordenes_recientes'] = OrdenTrabajo.objects.filter(
            tecnico_principal=tecnico
        ).select_related('cliente').order_by('-fecha_ingreso')[:10]
        
        return context

class TecnicoCreateView(LoginRequiredMixin, CreateView):
    model = Tecnico
    form_class = TecnicoForm
    template_name = 'taller/tecnico_form.html'
    success_url = reverse_lazy('taller:tecnico_list')
    
    def form_valid(self, form):
        # Debugging
        print("=" * 50)
        print("FORMULARIO VÁLIDO - Guardando técnico...")
        print(f"Datos: {form.cleaned_data}")
        
        try:
            response = super().form_valid(form)
            print(f"Técnico guardado: ID={self.object.id}, Código={self.object.codigo}")
            
            messages.success(
                self.request, 
                f'Técnico {self.object.get_nombre_completo()} creado exitosamente.'
            )
            
            # Verificar si es "Guardar y Nuevo"
            if self.request.POST.get('action') == 'save_and_new':
                return redirect('taller:tecnico_create')
            
            return response
            
        except Exception as e:
            print(f"ERROR al guardar: {e}")
            import traceback
            traceback.print_exc()
            messages.error(self.request, f'Error al guardar: {str(e)}')
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        # AGREGAR ESTOS PRINTS
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

class TecnicoUpdateView(LoginRequiredMixin, UpdateView):
    model = Tecnico
    form_class = TecnicoForm
    template_name = 'taller/tecnico_form.html'
    success_url = reverse_lazy('taller:tecnico_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Técnico actualizado exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al actualizar el técnico. Revisa los campos marcados.')
        return super().form_invalid(form)

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
        
        # AGREGAR ESTA LÍNEA - Indicar que es edición
        context['es_edicion'] = True
        
        return context
    
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
        fecha_desde = timezone.now().date().replace(day=1)
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = timezone.now().date()
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
        fecha_desde = timezone.now().date().replace(day=1)
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = timezone.now().date()
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
        fecha_desde = timezone.now().date() - timedelta(days=90)  # Últimos 3 meses
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = timezone.now().date()
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
    """Generar cotización en PDF"""
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    
    try:
        # Aquí irías la lógica para generar PDF
        # Por ahora simulamos con HTML que se puede imprimir
        
        context = {
            'orden': orden,
            'servicios': orden.servicios.all(),
            'repuestos': orden.repuestos_utilizados.all(),
            'empresa': {
                'nombre': 'VPMOTOS',
                'direccion': 'Dirección de la empresa',
                'telefono': 'Teléfono',
                'email': 'email@vpmotos.com'
            }
        }
        
        if request.GET.get('format') == 'pdf':
            # Aquí podrías usar ReportLab o WeasyPrint para generar PDF real
            # Por ahora devolvemos HTML
            response = HttpResponse(content_type='text/html')
            response['Content-Disposition'] = f'inline; filename="cotizacion_{orden.numero_orden}.html"'
        else:
            response = render(request, 'taller/cotizacion_pdf.html', context)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar cotización: {str(e)}')
        return redirect('taller:orden_detail', pk=pk)

@login_required
def ajax_servicios_disponibles(request):
    """AJAX: Obtener servicios disponibles filtrados"""
    categoria_id = request.GET.get('categoria_id')
    busqueda = request.GET.get('busqueda', '')
    
    servicios = TipoServicio.objects.filter(activo=True)
    
    if categoria_id:
        servicios = servicios.filter(categoria_id=categoria_id)
    
    if busqueda:
        servicios = servicios.filter(
            Q(nombre__icontains=busqueda) |
            Q(codigo__icontains=busqueda)
        )
    
    datos = []
    for servicio in servicios[:20]:  # Limitar resultados
        datos.append({
            'id': servicio.id,
            'codigo': servicio.codigo,
            'nombre': servicio.nombre,
            'categoria': servicio.categoria.nombre if servicio.categoria else '',
            'precio_base': float(servicio.precio_base),
            'precio_mano_obra': float(servicio.precio_mano_obra),
            'precio_total': float(servicio.get_precio_total()),
            'tiempo_estimado': float(servicio.tiempo_estimado_horas),
            'requiere_especialidad': servicio.requiere_especialidad.nombre if servicio.requiere_especialidad else None
        })
    
    return JsonResponse(datos, safe=False)

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
    
    # Buscar productos por código, nombre o descripción
    productos = Producto.objects.filter(
        Q(codigo__icontains=query) |
        Q(nombre__icontains=query) |
        Q(descripcion__icontains=query)
    ).filter(
        activo=True,
        stock_actual__gt=0  # Solo productos con stock
    )[:10]
    
    data = []
    for producto in productos:
        data.append({
            'id': producto.id,
            'codigo': producto.codigo,
            'nombre': producto.nombre,
            'descripcion': producto.descripcion or '',
            'precio_venta': float(producto.precio_venta),
            'stock_actual': producto.stock_actual,
            'text': f"{producto.codigo} - {producto.nombre} (Stock: {producto.stock_actual})"
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
            precio_total = servicio.precio_base + (servicio.precio_mano_obra or 0)
            
            servicios_data.append({
                'id': servicio.id,
                'codigo': servicio.codigo,
                'nombre': servicio.nombre,
                'descripcion': servicio.descripcion or '',
                'precio_base': float(servicio.precio_base),
                'precio_mano_obra': float(servicio.precio_mano_obra or 0),
                'precio_total': float(precio_total),
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
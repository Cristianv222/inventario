# apps/hardware_integration/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View
)
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Sum

from .models import (
    Impresora, PlantillaImpresion, ConfiguracionCodigoBarras,
    GavetaDinero, RegistroImpresion, EscanerCodigoBarras
)
from .forms import (
    ImpresoraForm, PlantillaImpresionForm, ConfiguracionCodigoBarrasForm,
    GavetaDineroForm, EscanerCodigoBarrasForm, TestImpresionForm
)
from .printers.printer_service import PrinterService
from .printers.ticket_printer import TicketPrinter
from .printers.label_printer import LabelPrinter

from .printers.cash_drawer_service import CashDrawerService

# Importar mixins requeridos
from django.contrib.auth.mixins import LoginRequiredMixin


# ============================================================================
# DASHBOARD DE HARDWARE
# ============================================================================

class HardwareDashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard principal del módulo de hardware"""
    template_name = 'hardware/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Estadísticas de impresoras
        context['total_impresoras'] = Impresora.objects.count()
        context['impresoras_activas'] = Impresora.objects.filter(estado='ACTIVA').count()
        context['impresoras_error'] = Impresora.objects.filter(estado='ERROR').count()
        
        # Estadísticas de dispositivos
        context['total_gavetas'] = GavetaDinero.objects.filter(activa=True).count()
        context['total_escaners'] = EscanerCodigoBarras.objects.filter(activo=True).count()
        context['total_plantillas'] = PlantillaImpresion.objects.filter(activa=True).count()
        
        # Impresoras por tipo
        context['impresoras_por_tipo'] = Impresora.objects.values(
            'tipo_impresora'
        ).annotate(
            cantidad=Count('id')
        ).order_by('tipo_impresora')
        
        # Últimas impresiones
        context['ultimas_impresiones'] = RegistroImpresion.objects.select_related(
            'impresora', 'venta', 'usuario'
        ).order_by('-fecha_impresion')[:10]
        
        # Impresiones de hoy
        hoy = timezone.now().date()
        context['impresiones_hoy'] = RegistroImpresion.objects.filter(
            fecha_impresion__date=hoy
        ).count()
        
        # Impresoras que necesitan mantenimiento (más de 10,000 impresiones)
        context['impresoras_mantenimiento'] = Impresora.objects.filter(
            contador_impresiones__gte=10000
        ).order_by('-contador_impresiones')[:5]
        
        # Errores recientes
        context['errores_recientes'] = RegistroImpresion.objects.filter(
            estado='ERROR'
        ).select_related('impresora').order_by('-fecha_impresion')[:5]

        # Lista completa de impresoras para la tabla
        context['total_impresoras_list'] = Impresora.objects.all()
        
        return context


# ============================================================================
# VISTAS DE IMPRESORAS
# ============================================================================

class ImpresoraListView(LoginRequiredMixin, ListView):
    """Lista de impresoras"""
    model = Impresora
    template_name = 'hardware/impresora_list.html'
    context_object_name = 'impresoras'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtros
        tipo = self.request.GET.get('tipo')
        estado = self.request.GET.get('estado')
        ubicacion = self.request.GET.get('ubicacion')
        
        if tipo:
            queryset = queryset.filter(tipo_impresora=tipo)
        if estado:
            queryset = queryset.filter(estado=estado)
        if ubicacion:
            queryset = queryset.filter(ubicacion__icontains=ubicacion)
        
        return queryset.order_by('ubicacion', 'nombre')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Ubicaciones únicas para filtro
        context['ubicaciones'] = Impresora.objects.values_list(
            'ubicacion', flat=True
        ).distinct().order_by('ubicacion')
        
        # Filtros actuales
        context['tipo_selected'] = self.request.GET.get('tipo', '')
        context['estado_selected'] = self.request.GET.get('estado', '')
        context['ubicacion_selected'] = self.request.GET.get('ubicacion', '')
        
        return context


class ImpresoraCreateView(LoginRequiredMixin, CreateView):
    """Crear nueva impresora"""
    model = Impresora
    form_class = ImpresoraForm
    template_name = 'hardware/impresora_form.html'
    success_url = reverse_lazy('hardware_integration:impresora_list')
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f"Impresora '{form.instance.nombre}' creada exitosamente."
        )
        return super().form_valid(form)


class ImpresoraDetailView(LoginRequiredMixin, DetailView):
    """Detalle de impresora con estadísticas"""
    model = Impresora
    template_name = 'hardware/impresora_detail.html'
    context_object_name = 'impresora'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        impresora = self.get_object()
        
        # Estadísticas de impresión
        context['total_impresiones'] = impresora.contador_impresiones
        
        # Impresiones por tipo
        context['impresiones_por_tipo'] = RegistroImpresion.objects.filter(
            impresora=impresora
        ).values('tipo_documento').annotate(
            cantidad=Count('id')
        ).order_by('tipo_documento')
        
        # Últimas impresiones
        context['ultimas_impresiones'] = RegistroImpresion.objects.filter(
            impresora=impresora
        ).order_by('-fecha_impresion')[:20]
        
        # Errores recientes
        context['errores'] = RegistroImpresion.objects.filter(
            impresora=impresora,
            estado='ERROR'
        ).order_by('-fecha_impresion')[:10]
        
        # Plantillas asociadas
        context['plantillas'] = impresora.plantillas.filter(activa=True)
        
        # Gavetas conectadas
        context['gavetas'] = impresora.gavetas.filter(activa=True)
        
        return context


class ImpresoraUpdateView(LoginRequiredMixin, UpdateView):
    """Editar impresora"""
    model = Impresora
    form_class = ImpresoraForm
    template_name = 'hardware/impresora_form.html'
    
    def get_success_url(self):
        return reverse('hardware_integration:impresora_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f"Impresora '{form.instance.nombre}' actualizada exitosamente."
        )
        return super().form_valid(form)


class ImpresoraDeleteView(LoginRequiredMixin, DeleteView):
    """Eliminar impresora"""
    model = Impresora
    template_name = 'hardware/impresora_confirm_delete.html'
    success_url = reverse_lazy('hardware_integration:impresora_list')
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # Verificar si tiene impresiones
        if self.object.impresiones.exists():
            messages.error(
                request,
                f"No se puede eliminar la impresora '{self.object.nombre}' porque tiene registros de impresión."
            )
            return redirect('hardware_integration:impresora_detail', pk=self.object.pk)
        
        messages.success(request, f"Impresora '{self.object.nombre}' eliminada exitosamente.")
        return super().delete(request, *args, **kwargs)


# ============================================================================
# PRUEBAS DE IMPRESORA
# ============================================================================

class TestConexionView(LoginRequiredMixin, View):
    """Probar conexión con impresora"""
    
    def post(self, request, pk):
        impresora = get_object_or_404(Impresora, pk=pk)
        
        success, mensaje = PrinterService.test_connection(impresora)
        
        if success:
            impresora.estado = 'ACTIVA'
            impresora.save(update_fields=['estado'])
            messages.success(request, f"Conexión exitosa: {mensaje}")
        else:
            impresora.estado = 'ERROR'
            impresora.save(update_fields=['estado'])
            messages.error(request, f"Error de conexión: {mensaje}")
        
        return redirect('hardware_integration:impresora_detail', pk=pk)


class TestPaginaPruebaView(LoginRequiredMixin, View):
    """Imprimir página de prueba"""
    
    def get(self, request, pk):
        impresora = get_object_or_404(Impresora, pk=pk)
        return render(request, 'hardware/test_impresion_form.html', {
            'impresora': impresora,
            'form': TestImpresionForm()
        })
    
    def post(self, request, pk):
        impresora = get_object_or_404(Impresora, pk=pk)
        form = TestImpresionForm(request.POST)
        
        if form.is_valid():
            tipo_prueba = form.cleaned_data['tipo_prueba']
            
            if tipo_prueba == 'PAGINA':
                success = PrinterService.print_test_page(impresora)
                if success:
                    messages.success(request, "Página de prueba impresa exitosamente.")
                else:
                    messages.error(request, "Error al imprimir página de prueba.")
            
            elif tipo_prueba == 'TICKET':
                # Crear venta de prueba
                from ventas.models import Venta
                venta_prueba = Venta.objects.filter(estado='COMPLETADA').first()
                if venta_prueba:
                    success = TicketPrinter.imprimir_ticket(venta_prueba, impresora)
                    if success:
                        messages.success(request, "Ticket de prueba impreso exitosamente.")
                    else:
                        messages.error(request, "Error al imprimir ticket de prueba.")
                else:
                    messages.error(request, "No hay ventas para usar como prueba.")
            
            elif tipo_prueba == 'ETIQUETA':
                # Usar primer producto como prueba
                from inventario.models import Producto
                producto_prueba = Producto.objects.filter(activo=True).first()
                if producto_prueba:
                    success = LabelPrinter.imprimir_etiqueta_producto(
                        producto_prueba, 1, impresora
                    )
                    if success:
                        messages.success(request, "Etiqueta de prueba impresa exitosamente.")
                    else:
                        messages.error(request, "Error al imprimir etiqueta de prueba.")
                else:
                    messages.error(request, "No hay productos para usar como prueba.")
        
        return redirect('hardware_integration:impresora_detail', pk=pk)


class MantenimientoImpresoraView(LoginRequiredMixin, View):
    """Registrar mantenimiento de impresora"""
    
    def post(self, request, pk):
        impresora = get_object_or_404(Impresora, pk=pk)
        
        # Resetear contador y registrar mantenimiento
        impresora.contador_impresiones = 0
        impresora.fecha_ultimo_mantenimiento = timezone.now()
        impresora.estado = 'ACTIVA'
        impresora.save()
        
        messages.success(
            request,
            f"Mantenimiento registrado para '{impresora.nombre}'. Contador reiniciado."
        )
        
        return redirect('hardware_integration:impresora_detail', pk=pk)


# ============================================================================
# VISTAS DE PLANTILLAS DE IMPRESIÓN
# ============================================================================

class PlantillaListView(LoginRequiredMixin, ListView):
    """Lista de plantillas de impresión"""
    model = PlantillaImpresion
    template_name = 'hardware/plantilla_list.html'
    context_object_name = 'plantillas'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtros
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo_documento=tipo)
        
        return queryset.order_by('tipo_documento', 'nombre')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tipo_selected'] = self.request.GET.get('tipo', '')
        return context


class PlantillaCreateView(LoginRequiredMixin, CreateView):
    """Crear plantilla de impresión"""
    model = PlantillaImpresion
    form_class = PlantillaImpresionForm
    template_name = 'hardware/plantilla_form.html'
    success_url = reverse_lazy('hardware_integration:plantilla_list')
    
    def form_valid(self, form):
        # Si es predeterminada, quitar el flag de otras
        if form.instance.es_predeterminada:
            PlantillaImpresion.objects.filter(
                tipo_documento=form.instance.tipo_documento,
                es_predeterminada=True
            ).update(es_predeterminada=False)
        
        messages.success(
            self.request,
            f"Plantilla '{form.instance.nombre}' creada exitosamente."
        )
        return super().form_valid(form)


class PlantillaDetailView(LoginRequiredMixin, DetailView):
    """Detalle de plantilla con vista previa"""
    model = PlantillaImpresion
    template_name = 'hardware/plantilla_detail.html'
    context_object_name = 'plantilla'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plantilla = self.get_object()
        
        # Variables de ejemplo para vista previa
        context['variables_ejemplo'] = {
            'empresa_nombre': 'CommerceBox',
            'empresa_ruc': '1234567890001',
            'numero_venta': 'VNT-2025-00001',
            'fecha': timezone.now().strftime('%d/%m/%Y %H:%M'),
            'cliente_nombre': 'Juan Pérez',
            'total': '125.50'
        }
        
        return context


class PlantillaUpdateView(LoginRequiredMixin, UpdateView):
    """Editar plantilla"""
    model = PlantillaImpresion
    form_class = PlantillaImpresionForm
    template_name = 'hardware/plantilla_form.html'
    
    def get_success_url(self):
        return reverse('hardware_integration:plantilla_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        # Si es predeterminada, quitar el flag de otras
        if form.instance.es_predeterminada:
            PlantillaImpresion.objects.filter(
                tipo_documento=form.instance.tipo_documento,
                es_predeterminada=True
            ).exclude(pk=form.instance.pk).update(es_predeterminada=False)
        
        messages.success(
            self.request,
            f"Plantilla '{form.instance.nombre}' actualizada exitosamente."
        )
        return super().form_valid(form)


class PlantillaDeleteView(LoginRequiredMixin, DeleteView):
    """Eliminar plantilla"""
    model = PlantillaImpresion
    template_name = 'hardware/plantilla_confirm_delete.html'
    success_url = reverse_lazy('hardware_integration:plantilla_list')


# ============================================================================
# VISTAS DE CONFIGURACIÓN DE CÓDIGOS DE BARRAS
# ============================================================================

class ConfigCodigoBarrasListView(LoginRequiredMixin, ListView):
    """Lista de configuraciones de códigos de barras"""
    model = ConfiguracionCodigoBarras
    template_name = 'hardware/config_codigo_list.html'
    context_object_name = 'configuraciones'
    
    def get_queryset(self):
        return ConfiguracionCodigoBarras.objects.filter(activa=True)


class ConfigCodigoBarrasCreateView(LoginRequiredMixin, CreateView):
    """Crear configuración de código de barras"""
    model = ConfiguracionCodigoBarras
    form_class = ConfiguracionCodigoBarrasForm
    template_name = 'hardware/config_codigo_form.html'
    success_url = reverse_lazy('hardware_integration:config_codigo_list')
    
    def form_valid(self, form):
        # Si es predeterminada, quitar el flag de otras
        if form.instance.es_predeterminada:
            ConfiguracionCodigoBarras.objects.filter(
                es_predeterminada=True
            ).update(es_predeterminada=False)
        
        messages.success(
            self.request,
            f"Configuración '{form.instance.nombre}' creada exitosamente."
        )
        return super().form_valid(form)


class ConfigCodigoBarrasDetailView(LoginRequiredMixin, DetailView):
    """Detalle de configuración con vista previa"""
    model = ConfiguracionCodigoBarras
    template_name = 'hardware/config_codigo_detail.html'
    context_object_name = 'configuracion'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_object()
        
        # Generar código de ejemplo
        context['codigo_ejemplo'] = f"{config.prefijo}12345{config.sufijo}"
        
        return context


class ConfigCodigoBarrasUpdateView(LoginRequiredMixin, UpdateView):
    """Editar configuración"""
    model = ConfiguracionCodigoBarras
    form_class = ConfiguracionCodigoBarrasForm
    template_name = 'hardware/config_codigo_form.html'
    
    def get_success_url(self):
        return reverse('hardware_integration:config_codigo_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        # Si es predeterminada, quitar el flag de otras
        if form.instance.es_predeterminada:
            ConfiguracionCodigoBarras.objects.filter(
                es_predeterminada=True
            ).exclude(pk=form.instance.pk).update(es_predeterminada=False)
        
        messages.success(
            self.request,
            f"Configuración '{form.instance.nombre}' actualizada exitosamente."
        )
        return super().form_valid(form)


# ============================================================================
# VISTAS DE GAVETAS DE DINERO
# ============================================================================

class GavetaDineroListView(LoginRequiredMixin, ListView):
    """Lista de gavetas de dinero"""
    model = GavetaDinero
    template_name = 'hardware/gaveta_list.html'
    context_object_name = 'gavetas'
    
    def get_queryset(self):
        return GavetaDinero.objects.select_related('impresora')


class GavetaDineroCreateView(LoginRequiredMixin, CreateView):
    """Crear gaveta de dinero"""
    model = GavetaDinero
    form_class = GavetaDineroForm
    template_name = 'hardware/gaveta_form.html'
    success_url = reverse_lazy('hardware_integration:gaveta_list')
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f"Gaveta '{form.instance.nombre}' creada exitosamente."
        )
        return super().form_valid(form)


class GavetaDineroDetailView(LoginRequiredMixin, DetailView):
    """Detalle de gaveta"""
    model = GavetaDinero
    template_name = 'hardware/gaveta_detail.html'
    context_object_name = 'gaveta'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        gaveta = self.get_object()
        
        # Estadísticas
        context['total_aperturas'] = gaveta.contador_aperturas
        
        return context


class GavetaDineroUpdateView(LoginRequiredMixin, UpdateView):
    """Editar gaveta"""
    model = GavetaDinero
    form_class = GavetaDineroForm
    template_name = 'hardware/gaveta_form.html'
    
    def get_success_url(self):
        return reverse('hardware_integration:gaveta_detail', kwargs={'pk': self.object.pk})


class AbrirGavetaView(LoginRequiredMixin, View):
    """Abrir gaveta de dinero"""
    
    def get(self, request, pk=None):
        """Versión para AJAX/Pruebas"""
        # Si no hay PK, tomar la primera gaveta activa para el test
        if pk is None:
            gaveta = GavetaDinero.objects.filter(activa=True).first()
            if not gaveta:
                return JsonResponse({'success': False, 'message': 'No hay gavetas configuradas'})
        else:
            gaveta = get_object_or_404(GavetaDinero, pk=pk)
            
        if CashDrawerService.abrir_gaveta(gaveta, request.user):
            return JsonResponse({'success': True, 'message': 'Gaveta abierta'})
        return JsonResponse({'success': False, 'message': 'Error al abrir gaveta'})

    def post(self, request, pk):
        gaveta = get_object_or_404(GavetaDinero, pk=pk)
        
        # Verificar si requiere autorización
        if gaveta.requiere_autorizacion:
            # Verificar permisos especiales
            if not request.user.has_perm('hardware_integration.abrir_gaveta_manual'):
                messages.error(request, "No tienes autorización para abrir la gaveta manualmente.")
                return redirect('hardware_integration:gaveta_detail', pk=pk)
        
        # Intentar abrir
        if CashDrawerService.abrir_gaveta(gaveta, request.user):
            messages.success(request, f"Gaveta '{gaveta.nombre}' abierta exitosamente.")
        else:
            messages.error(request, "Error al abrir la gaveta.")
        
        return redirect('hardware_integration:gaveta_detail', pk=pk)


# ============================================================================
# VISTAS DE ESCÁNER
# ============================================================================

class EscanerListView(LoginRequiredMixin, ListView):
    """Lista de escáneres"""
    model = EscanerCodigoBarras
    template_name = 'hardware/escaner_list.html'
    context_object_name = 'escaners'
    
    def get_queryset(self):
        return EscanerCodigoBarras.objects.filter(activo=True)


class EscanerCreateView(LoginRequiredMixin, CreateView):
    """Crear escáner"""
    model = EscanerCodigoBarras
    form_class = EscanerCodigoBarrasForm
    template_name = 'hardware/escaner_form.html'
    success_url = reverse_lazy('hardware_integration:escaner_list')
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f"Escáner '{form.instance.nombre}' creado exitosamente."
        )
        return super().form_valid(form)


class EscanerDetailView(LoginRequiredMixin, DetailView):
    """Detalle de escáner"""
    model = EscanerCodigoBarras
    template_name = 'hardware/escaner_detail.html'
    context_object_name = 'escaner'


class EscanerUpdateView(LoginRequiredMixin, UpdateView):
    """Editar escáner"""
    model = EscanerCodigoBarras
    form_class = EscanerCodigoBarrasForm
    template_name = 'hardware/escaner_form.html'
    
    def get_success_url(self):
        return reverse('hardware_integration:escaner_detail', kwargs={'pk': self.object.pk})


# ============================================================================
# VISTAS DE REGISTRO DE IMPRESIONES
# ============================================================================

class RegistroImpresionListView(LoginRequiredMixin, ListView):
    """Lista de registros de impresión"""
    model = RegistroImpresion
    template_name = 'hardware/registro_impresion_list.html'
    context_object_name = 'registros'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'impresora', 'venta', 'producto', 'usuario'
        )
        
        # Filtros
        impresora_id = self.request.GET.get('impresora')
        tipo = self.request.GET.get('tipo')
        estado = self.request.GET.get('estado')
        fecha = self.request.GET.get('fecha')
        
        if impresora_id:
            queryset = queryset.filter(impresora_id=impresora_id)
        if tipo:
            queryset = queryset.filter(tipo_documento=tipo)
        if estado:
            queryset = queryset.filter(estado=estado)
        if fecha:
            queryset = queryset.filter(fecha_impresion__date=fecha)
        
        return queryset.order_by('-fecha_impresion')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Impresoras para filtro
        context['impresoras'] = Impresora.objects.all()
        
        # Filtros actuales
        context['impresora_selected'] = self.request.GET.get('impresora', '')
        context['tipo_selected'] = self.request.GET.get('tipo', '')
        context['estado_selected'] = self.request.GET.get('estado', '')
        context['fecha_selected'] = self.request.GET.get('fecha', '')
        
        return context


# ============================================================================
# APIs JSON
# ============================================================================

class ImpresoraStatusAPIView(View):
    """API para obtener estado de impresoras"""
    
    def get(self, request):
        impresoras = Impresora.objects.all()
        
        data = []
        for imp in impresoras:
            data.append({
                'id': str(imp.id),
                'nombre': imp.nombre,
                'tipo': imp.tipo_impresora,
                'estado': imp.estado,
                'ubicacion': imp.ubicacion,
                'conexion': imp.get_connection_info(),
                'contador': imp.contador_impresiones,
                'ancho_etiqueta': imp.ancho_etiqueta,
                'alto_etiqueta': imp.alto_etiqueta
            })
        
        return JsonResponse({'impresoras': data})


class ImprimirEtiquetaAPIView(View):
    """API para imprimir etiquetas"""
    
    def post(self, request):
        from inventario.models import Producto
        
        producto_id = request.POST.get('producto_id')
        cantidad = int(request.POST.get('cantidad', 1))
        impresora_id = request.POST.get('impresora_id')
        
        try:
            producto = Producto.objects.get(pk=producto_id)
            
            impresora = None
            if impresora_id:
                impresora = Impresora.objects.get(pk=impresora_id)
            
            if LabelPrinter.imprimir_etiqueta_producto(producto, cantidad, impresora):
                return JsonResponse({
                    'success': True,
                    'message': f'{cantidad} etiqueta(s) impresa(s) exitosamente'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Error al imprimir etiquetas'
                })
        
        except Producto.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Producto no encontrado'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })


class GenerarCodigoBarrasAPIView(View):
    """API para generar siguiente código de barras"""
    
    def get(self, request):
        config_id = request.GET.get('config_id')
        
        try:
            if config_id:
                config = ConfiguracionCodigoBarras.objects.get(pk=config_id)
            else:
                config = ConfiguracionCodigoBarras.objects.filter(
                    es_predeterminada=True,
                    activa=True
                ).first()
            
            if config:
                codigo = config.generar_siguiente_codigo()
                return JsonResponse({
                    'success': True,
                    'codigo': codigo
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No hay configuración de códigos disponible'
                })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

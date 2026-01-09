from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import (
    EspecialidadTecnica, CategoriaServicio, Tecnico, 
    TipoServicio, OrdenTrabajo, ServicioOrden, 
    RepuestoOrden, CitaTaller, EvaluacionServicio
)
from clientes.models import Cliente
from inventario.models import Producto


class EspecialidadTecnicaForm(forms.ModelForm):
    """Formulario para especialidades técnicas"""
    class Meta:
        model = EspecialidadTecnica
        fields = ['nombre', 'descripcion', 'activa']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CategoriaServicioForm(forms.ModelForm):
    """Formulario para categorías de servicios"""
    class Meta:
        model = CategoriaServicio
        fields = ['nombre', 'codigo', 'descripcion', 'color', 
                 'activa', 'requiere_diagnostico', 'tiempo_estimado_horas']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requiere_diagnostico': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tiempo_estimado_horas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
        }


class TecnicoForm(forms.ModelForm):
    """Formulario para técnicos"""
    class Meta:
        model = Tecnico
        fields = [
            'codigo', 'nombres', 'apellidos', 'identificacion', 
            'tipo_identificacion', 'telefono', 'celular', 'email', 
            'direccion', 'fecha_ingreso', 'estado', 'especialidades',
            'porcentaje_comision', 'salario_base', 'foto', 'observaciones'
        ]
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control'}),
            'identificacion': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_identificacion': forms.Select(attrs={'class': 'form-select'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'especialidades': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'porcentaje_comision': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'salario_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'foto': forms.FileInput(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class TipoServicioForm(forms.ModelForm):
    """Formulario para tipos de servicios"""
    class Meta:
        model = TipoServicio
        fields = [
            'categoria',
            'nombre',
            'codigo',
            'descripcion',
            'precio',
            'activo',
            'tiempo_estimado_horas',
            'requiere_repuestos',
            'requiere_especialidad',
            'nivel_dificultad'
        ]
        
        labels = {
            'categoria': 'Categoría',
            'nombre': 'Nombre del Servicio',
            'codigo': 'Código',
            'descripcion': 'Descripción',
            'precio': 'Precio del Servicio',
            'activo': 'Activo',
            'tiempo_estimado_horas': 'Tiempo Estimado (horas)',
            'requiere_repuestos': 'Requiere Repuestos',
            'requiere_especialidad': 'Requiere Especialidad',
            'nivel_dificultad': 'Nivel de Dificultad'
        }
        
        widgets = {
            'categoria': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Cambio de Aceite'
            }),
            'codigo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: SERV-001'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción del servicio...'
            }),
            'precio': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 25.00',
                'step': '0.01',
                'min': '0'
            }),
            'tiempo_estimado_horas': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 1.5',
                'step': '0.25',
                'min': '0'
            }),
            'requiere_repuestos': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'requiere_especialidad': forms.Select(attrs={
                'class': 'form-select'
            }),
            'nivel_dificultad': forms.Select(attrs={
                'class': 'form-select'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        
        help_texts = {
            'precio': 'Precio total del servicio sin IVA',
            'codigo': 'Código único para identificar el servicio',
            'tiempo_estimado_horas': 'Tiempo aproximado que toma realizar el servicio',
            'requiere_repuestos': 'Marcar si el servicio normalmente requiere repuestos',
        }


class OrdenTrabajoForm(forms.ModelForm):
    """Formulario para órdenes de trabajo"""
    cliente_identificacion = forms.CharField(
        label="Identificación Cliente",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Ingrese cédula o RUC'
        })
    )
    
    class Meta:
        model = OrdenTrabajo
        fields = [
            'cliente', 'moto_marca', 'moto_modelo', 'moto_cilindraje',
            'moto_color', 'moto_placa', 'tecnico_principal', 'tecnicos_apoyo',
            'fecha_prometida', 'motivo_ingreso', 'diagnostico_inicial',
            'estado', 'prioridad', 'kilometraje_entrada', 'nivel_combustible',
            'anticipo', 'observaciones_cliente'
        ]
        widgets = {
            'cliente': forms.HiddenInput(),
            'moto_marca': forms.TextInput(attrs={'class': 'form-control'}),
            'moto_modelo': forms.TextInput(attrs={'class': 'form-control'}),
            'moto_cilindraje': forms.TextInput(attrs={'class': 'form-control'}),
            'moto_color': forms.TextInput(attrs={'class': 'form-control'}),
            'moto_placa': forms.TextInput(attrs={'class': 'form-control'}),
            'tecnico_principal': forms.Select(attrs={'class': 'form-select'}),
            'tecnicos_apoyo': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'fecha_prometida': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'motivo_ingreso': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'diagnostico_inicial': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'kilometraje_entrada': forms.NumberInput(attrs={'class': 'form-control'}),
            'nivel_combustible': forms.Select(attrs={'class': 'form-select'}),
            'anticipo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'observaciones_cliente': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo técnicos activos
        self.fields['tecnico_principal'].queryset = Tecnico.objects.filter(
            estado='ACTIVO', activo=True
        )
        self.fields['tecnicos_apoyo'].queryset = Tecnico.objects.filter(
            estado='ACTIVO', activo=True
        )
        
        # Si estamos editando una orden existente, prellenar la identificación del cliente
        if self.instance and self.instance.pk and self.instance.cliente:
            self.fields['cliente_identificacion'].initial = self.instance.cliente.identificacion
    
    def clean(self):
        """
        Validación personalizada del formulario.
        Si se proporciona una identificación de cliente pero no un ID de cliente,
        intenta encontrar el cliente por su identificación.
        """
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        cliente_identificacion = cleaned_data.get('cliente_identificacion')
        
        # Si no hay cliente pero sí identificación, buscar el cliente
        if not cliente and cliente_identificacion:
            try:
                # Buscar cliente por identificación
                cliente = Cliente.objects.get(identificacion=cliente_identificacion)
                cleaned_data['cliente'] = cliente
            except Cliente.DoesNotExist:
                raise forms.ValidationError({
                    'cliente_identificacion': 'No se encontró un cliente con esa identificación.'
                })
            except Cliente.MultipleObjectsReturned:
                raise forms.ValidationError({
                    'cliente_identificacion': 'Se encontraron múltiples clientes con esa identificación.'
                })
        
        # Si hay cliente, actualizar el campo de identificación
        if cliente and not cliente_identificacion:
            cleaned_data['cliente_identificacion'] = cliente.identificacion
        
        # Validar que se haya proporcionado un cliente
        if not cleaned_data.get('cliente'):
            raise forms.ValidationError({
                'cliente': 'Debe seleccionar un cliente para la orden.'
            })
        
        return cleaned_data
    
    def save(self, commit=True):
        """
        Guardar la orden asegurándose de que el cliente esté correctamente asignado.
        """
        orden = super().save(commit=False)
        
        # Asegurarse de que el cliente esté asignado
        if self.cleaned_data.get('cliente'):
            orden.cliente = self.cleaned_data['cliente']
        
        if commit:
            orden.save()
            self.save_m2m()  # Guardar relaciones many-to-many (tecnicos_apoyo)
        
        return orden


# ============================================
# ✅ CORREGIDO: ServicioOrdenForm
# ============================================
class ServicioOrdenForm(forms.ModelForm):
    """Formulario para servicios en órdenes"""
    class Meta:
        model = ServicioOrden
        fields = [
            'tipo_servicio',
            'tecnico_asignado',
            'precio_servicio',  # ✅ CORREGIDO - nombre real del campo en el modelo
            'observaciones'
        ]
        
        labels = {
            'tipo_servicio': 'Servicio',
            'tecnico_asignado': 'Técnico Asignado',
            'precio_servicio': 'Precio Total',
            'observaciones': 'Observaciones'
        }
        
        widgets = {
            'tipo_servicio': forms.Select(attrs={
                'class': 'form-select servicio-select',
                'data-precio-url': '/taller/ajax/precio-servicio/'
            }),
            'tecnico_asignado': forms.Select(attrs={
                'class': 'form-select'
            }),
            'precio_servicio': forms.NumberInput(attrs={  # ✅ CORREGIDO
                'class': 'form-control precio-servicio',
                'step': '0.01',
                'min': '0',
                'readonly': 'readonly'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Observaciones adicionales...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtrar solo servicios activos
        self.fields['tipo_servicio'].queryset = TipoServicio.objects.filter(activo=True)
        
        # Filtrar solo técnicos activos
        self.fields['tecnico_asignado'].queryset = Tecnico.objects.filter(
            estado='ACTIVO', activo=True
        )
        
        # ✅ Hacer campos opcionales
        self.fields['tecnico_asignado'].required = False
        self.fields['precio_servicio'].required = False  # ✅ CORREGIDO
        self.fields['observaciones'].required = False


# ============================================
# ✅ CORREGIDO: RepuestoOrdenForm
# ============================================
class RepuestoOrdenForm(forms.ModelForm):
    """Formulario para repuestos en órdenes"""
    class Meta:
        model = RepuestoOrden
        fields = [
            'producto',
            'cantidad',
            'precio_unitario',
            'observaciones'
        ]
        
        labels = {
            'producto': 'Producto/Repuesto',
            'cantidad': 'Cantidad',
            'precio_unitario': 'Precio Unitario',
            'observaciones': 'Observaciones'
        }
        
        widgets = {
            'producto': forms.Select(attrs={
                'class': 'form-select producto-select',
                'data-precio-url': '/taller/ajax/precio-producto/'
            }),
            'cantidad': forms.NumberInput(attrs={
                'class': 'form-control cantidad-input',
                'min': '0.01',
                'step': '0.01',
                'value': '1'
            }),
            'precio_unitario': forms.NumberInput(attrs={
                'class': 'form-control precio-unitario',
                'step': '0.01',
                'min': '0',
                'readonly': 'readonly'
            }),
            'observaciones': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Observaciones...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtrar solo productos activos con stock
        self.fields['producto'].queryset = Producto.objects.filter(
            activo=True,
            stock_actual__gt=0
        )
        
        # ✅ Hacer campos opcionales
        self.fields['precio_unitario'].required = False
        self.fields['observaciones'].required = False


# ============================================
# ✅ FORMSETS CORREGIDOS
# ============================================
ServicioOrdenFormSet = inlineformset_factory(
    OrdenTrabajo,
    ServicioOrden,
    form=ServicioOrdenForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
    max_num=20
)

RepuestoOrdenFormSet = inlineformset_factory(
    OrdenTrabajo,
    RepuestoOrden,
    form=RepuestoOrdenForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
    max_num=50
)


class CitaTallerForm(forms.ModelForm):
    """Formulario para citas del taller"""
    class Meta:
        model = CitaTaller
        fields = [
            'cliente', 'moto_descripcion', 'tecnico_preferido',
            'fecha_hora', 'duracion_estimada', 'motivo', 'observaciones'
        ]
        widgets = {
            'cliente': forms.Select(attrs={'class': 'form-select'}),
            'moto_descripcion': forms.TextInput(attrs={'class': 'form-control'}),
            'tecnico_preferido': forms.Select(attrs={'class': 'form-select'}),
            'fecha_hora': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'duracion_estimada': forms.NumberInput(attrs={'class': 'form-control', 'min': '15', 'step': '15'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo técnicos activos
        self.fields['tecnico_preferido'].queryset = Tecnico.objects.filter(
            estado='ACTIVO', activo=True
        )


class EvaluacionServicioForm(forms.ModelForm):
    """Formulario para evaluaciones de servicio"""
    class Meta:
        model = EvaluacionServicio
        fields = [
            'calificacion_general', 'calificacion_tecnico',
            'calificacion_tiempo', 'calificacion_precio',
            'comentarios', 'recomendaria'
        ]
        widgets = {
            'calificacion_general': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'calificacion_tecnico': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'calificacion_tiempo': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'calificacion_precio': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'recomendaria': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BusquedaOrdenForm(forms.Form):
    """Formulario para buscar órdenes de trabajo"""
    busqueda = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por número de orden, cliente o placa...'
        })
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los estados')] + list(OrdenTrabajo.ESTADO_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    tecnico = forms.ModelChoiceField(
        queryset=Tecnico.objects.filter(estado='ACTIVO', activo=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='Todos los técnicos'
    )
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
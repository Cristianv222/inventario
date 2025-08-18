from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import datetime
from .models import GastoDiario, CierreDiario, TipoMovimiento


class FiltroFechasForm(forms.Form):
    """Form base para filtros de fechas"""
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Fecha desde'
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Fecha hasta'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)
        
        if not self.data:
            self.fields['fecha_desde'].initial = primer_dia_mes
            self.fields['fecha_hasta'].initial = hoy


class GastoDiarioForm(forms.ModelForm):
    """Form para registrar gastos diarios"""
    
    class Meta:
        model = GastoDiario
        fields = [
            'fecha', 'categoria', 'concepto', 'descripcion', 'monto',
            'proveedor', 'numero_factura', 'archivo_factura'
        ]
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'concepto': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descripción breve del gasto'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Detalles adicionales (opcional)'
            }),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'proveedor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre del proveedor (opcional)'
            }),
            'numero_factura': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de factura o documento'
            }),
            'archivo_factura': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['fecha'].initial = timezone.now().date()


class CierreDiarioForm(forms.ModelForm):
    """Form para cerrar caja diaria"""
    
    class Meta:
        model = CierreDiario
        fields = ['efectivo_contado', 'observaciones']
        widgets = {
            'efectivo_contado': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Efectivo contado físicamente'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Observaciones del cierre de caja (opcional)'
            })
        }


class ReporteVentasForm(FiltroFechasForm):
    """Form para generar reportes de ventas"""
    AGRUPACION_CHOICES = [
        ('dia', 'Por Día'),
        ('semana', 'Por Semana'),
        ('mes', 'Por Mes'),
    ]
    
    TIPO_REPORTE_CHOICES = [
        ('general', 'Reporte General'),
        ('productos', 'Solo Productos'),
        ('servicios', 'Solo Servicios'),
        ('metodos_pago', 'Por Método de Pago'),
    ]
    
    agrupacion = forms.ChoiceField(
        choices=AGRUPACION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='dia'
    )
    
    tipo_reporte = forms.ChoiceField(
        choices=TIPO_REPORTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='general'
    )


class FiltroGastosForm(FiltroFechasForm):
    """Form para filtrar gastos"""
    CATEGORIA_CHOICES = [
        ('', 'Todas las categorías'),
        ('oficina', 'Oficina'),
        ('mantenimiento', 'Mantenimiento'),
        ('servicios', 'Servicios'),
        ('inventario', 'Inventario'),
        ('marketing', 'Marketing'),
        ('personal', 'Personal'),
        ('transporte', 'Transporte'),
        ('otros', 'Otros'),
    ]
    
    APROBADO_CHOICES = [
        ('', 'Todos'),
        ('True', 'Aprobados'),
        ('False', 'Pendientes'),
    ]
    
    categoria = forms.ChoiceField(
        choices=CATEGORIA_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    aprobado = forms.ChoiceField(
        choices=APROBADO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    proveedor = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por proveedor'
        })
    )


class FiltroMovimientosForm(FiltroFechasForm):
    """Form para filtrar movimientos de caja"""
    ES_INGRESO_CHOICES = [
        ('', 'Todos'),
        ('True', 'Ingresos'),
        ('False', 'Egresos'),
    ]
    
    es_ingreso = forms.ChoiceField(
        choices=ES_INGRESO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    busqueda = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar en concepto o descripción'
        })
    )


class ComparativoVentasForm(forms.Form):
    """Form para comparativo de ventas entre períodos"""
    PERIODO_CHOICES = [
        ('dia', 'Día'),
        ('semana', 'Semana'),
        ('mes', 'Mes'),
        ('trimestre', 'Trimestre'),
        ('año', 'Año'),
    ]
    
    COMPARAR_CHOICES = [
        ('anterior', 'Período Anterior'),
        ('mismo_año_anterior', 'Mismo Período Año Anterior'),
        ('personalizado', 'Período Personalizado'),
    ]
    
    periodo_actual = forms.ChoiceField(
        choices=PERIODO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='mes'
    )
    
    fecha_actual = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=datetime.date.today
    )
    
    comparar_con = forms.ChoiceField(
        choices=COMPARAR_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='anterior'
    )
    
    fecha_comparacion = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        comparar_con = cleaned_data.get('comparar_con')
        fecha_comparacion = cleaned_data.get('fecha_comparacion')
        
        if comparar_con == 'personalizado' and not fecha_comparacion:
            raise ValidationError('Debe seleccionar una fecha para la comparación personalizada')
        
        return cleaned_data


class ExportarReporteForm(forms.Form):
    """Form para exportar reportes"""
    FORMATO_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    ]
    
    TIPO_REPORTE_CHOICES = [
        ('ventas', 'Reporte de Ventas'),
        ('gastos', 'Reporte de Gastos'),
        ('caja', 'Reporte de Caja'),
        ('productos', 'Reporte de Productos'),
        ('servicios', 'Reporte de Servicios'),
    ]
    
    tipo_reporte = forms.ChoiceField(
        choices=TIPO_REPORTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    formato = forms.ChoiceField(
        choices=FORMATO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='pdf'
    )
    
    fecha_desde = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    fecha_hasta = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    incluir_graficos = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        initial=True
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)
        
        if not self.data:
            self.fields['fecha_desde'].initial = primer_dia_mes
            self.fields['fecha_hasta'].initial = hoy
    
    def clean(self):
        cleaned_data = super().clean()
        fecha_desde = cleaned_data.get('fecha_desde')
        fecha_hasta = cleaned_data.get('fecha_hasta')
        
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            raise ValidationError('La fecha desde no puede ser mayor que la fecha hasta')
        
        return cleaned_data
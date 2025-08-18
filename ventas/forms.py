from django import forms
from django.forms import inlineformset_factory
from .models import Venta, DetalleVenta, CierreCaja
from clientes.models import Cliente
from inventario.models import Producto


class VentaForm(forms.ModelForm):
    """Formulario para la creación y edición de ventas"""
    cliente_identificacion = forms.CharField(
        label="Identificación Cliente",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula / RUC'})
    )
    
    cliente_nombre = forms.CharField(
        label="Nombre Cliente",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Consumidor Final', 'readonly': 'readonly'})
    )
    
    consumidor_final = forms.BooleanField(
        label="Consumidor Final",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    class Meta:
        model = Venta
        fields = ['tipo_pago', 'observaciones', 'datos_pago']
        widgets = {
            'tipo_pago': forms.Select(attrs={'class': 'form-select'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'datos_pago': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hacer tipo_pago obligatorio
        self.fields['tipo_pago'].required = True
        
        # Si es edición y hay cliente, mostrar datos
        if self.instance.pk and self.instance.cliente:
            self.fields['cliente_identificacion'].initial = self.instance.cliente.identificacion
            self.fields['cliente_nombre'].initial = f"{self.instance.cliente.nombres} {self.instance.cliente.apellidos}"
            self.fields['consumidor_final'].initial = self.instance.cliente.identificacion == '9999999999'
    
    def clean(self):
        cleaned_data = super().clean()
        consumidor_final = cleaned_data.get('consumidor_final')
        cliente_identificacion = cleaned_data.get('cliente_identificacion')
        
        if not consumidor_final and not cliente_identificacion:
            self.add_error('cliente_identificacion', "Debe ingresar la identificación del cliente")
        
        return cleaned_data

class DetalleVentaForm(forms.ModelForm):
    """Formulario para detalles de venta"""
    producto_codigo = forms.CharField(
        label="Código",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    producto_nombre = forms.CharField(
        label="Producto",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
    )
    
    class Meta:
        model = DetalleVenta
        fields = ['cantidad', 'precio_unitario', 'descuento', 'observaciones']
        widgets = {
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'step': '1'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'descuento': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'observaciones': forms.TextInput(attrs={'class': 'form-control'}),
        }

# Formset para detalles de venta
DetalleVentaFormSet = inlineformset_factory(
    Venta, DetalleVenta, 
    form=DetalleVentaForm, 
    extra=1, can_delete=True
)

class CierreCajaForm(forms.ModelForm):
    """Formulario para cierre de caja"""
    class Meta:
        model = CierreCaja
        fields = ['fecha', 'observaciones']
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Verificar si ya existe un cierre para la fecha seleccionada
        if 'fecha' in self.data:
            fecha = self.data.get('fecha')
            if fecha and CierreCaja.objects.filter(fecha=fecha).exists():
                self.add_error('fecha', "Ya existe un cierre de caja para esta fecha")

class AgregarProductoForm(forms.Form):
    """Formulario para agregar productos a una venta"""
    codigo = forms.CharField(
        label="Código",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Código del producto'})
    )
    
    cantidad = forms.IntegerField(
        label="Cantidad",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )
    
    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo')
        try:
            producto = Producto.objects.get(codigo_unico=codigo)
            return codigo
        except Producto.DoesNotExist:
            raise forms.ValidationError("Producto no encontrado")
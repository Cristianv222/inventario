from django import forms
from .models import Producto, CategoriaProducto, Marca, InventarioAjuste

class ProductoForm(forms.ModelForm):
    """Formulario para crear y editar productos"""
    
    class Meta:
        model = Producto
        fields = [
            'categoria', 'marca', 'codigo_unico', 'nombre', 'descripcion',
            'precio_compra', 'precio_venta', 'stock_actual', 'stock_minimo',
            'incluye_iva', 'activo', 'ubicacion_almacen'
        ]
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'marca': forms.Select(attrs={'class': 'form-select'}),
            'codigo_unico': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'precio_compra': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'precio_venta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'stock_actual': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'stock_minimo': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'incluye_iva': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ubicacion_almacen': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def clean_codigo_unico(self):
        codigo = self.cleaned_data.get('codigo_unico')
        if not codigo:
            return codigo
        
        # Verificar si ya existe un producto con este código (excepto para ediciones)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            qs = Producto.objects.filter(codigo_unico=codigo).exclude(pk=instance.pk)
        else:
            qs = Producto.objects.filter(codigo_unico=codigo)
        
        if qs.exists():
            raise forms.ValidationError("Ya existe un producto con este código")
        return codigo
    
    def clean(self):
        cleaned_data = super().clean()
        precio_compra = cleaned_data.get('precio_compra')
        precio_venta = cleaned_data.get('precio_venta')
        
        if precio_compra and precio_venta and precio_venta < precio_compra:
            self.add_error('precio_venta', "El precio de venta no puede ser menor al precio de compra")
        
        return cleaned_data

class CategoriaProductoForm(forms.ModelForm):
    """Formulario para crear y editar categorías de productos"""
    
    class Meta:
        model = CategoriaProducto
        fields = ['nombre', 'codigo', 'descripcion', 'porcentaje_ganancia', 'activa', 'categoria_padre']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'porcentaje_ganancia': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'categoria_padre': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Excluir la categoría actual y sus hijos para evitar ciclos
        if self.instance.pk:
            descendientes = self.get_descendientes(self.instance)
            self.fields['categoria_padre'].queryset = CategoriaProducto.objects.exclude(
                pk__in=[self.instance.pk] + list(descendientes)
            )
    
    def get_descendientes(self, categoria):
        """Obtiene los IDs de todas las categorías descendientes"""
        descendientes = []
        for hijo in categoria.subcategorias.all():
            descendientes.append(hijo.pk)
            descendientes.extend(self.get_descendientes(hijo))
        return descendientes

class MarcaForm(forms.ModelForm):
    """Formulario para crear y editar marcas"""
    
    class Meta:
        model = Marca
        fields = ['nombre', 'descripcion', 'activa']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class InventarioAjusteForm(forms.ModelForm):
    """Formulario para ajustes de inventario"""
    
    class Meta:
        model = InventarioAjuste
        fields = ['producto', 'tipo_ajuste', 'cantidad', 'motivo']
        widgets = {
            'producto': forms.Select(attrs={'class': 'form-select'}),
            'tipo_ajuste': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo productos activos
        self.fields['producto'].queryset = Producto.objects.filter(activo=True)

class ProductoSearchForm(forms.Form):
    """Formulario para búsqueda de productos"""
    
    busqueda = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por nombre, código o descripción'
        })
    )
    
    categoria = forms.ModelChoiceField(
        queryset=CategoriaProducto.objects.filter(activa=True),
        required=False,
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    marca = forms.ModelChoiceField(
        queryset=Marca.objects.filter(activa=True),
        required=False,
        empty_label="Todas las marcas",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    stock_bajo = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    activo = forms.ChoiceField(
        choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
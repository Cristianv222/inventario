from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
import re

from .models import (
    Cliente, Moto, ConfiguracionPuntos, CanjeoPuntos, 
    HistorialCliente, MovimientoPuntos
)

class ClienteForm(forms.ModelForm):
    """Formulario para crear/editar clientes"""
    
    class Meta:
        model = Cliente
        fields = [
            'nombres', 'apellidos', 'identificacion', 'tipo_identificacion',
            'direccion', 'telefono', 'celular', 'email', 'fecha_nacimiento',
            'profesion', 'referido_por', 'descuento_preferencial', 
            'observaciones', 'activo'
        ]
        
        widgets = {
            'nombres': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ingrese los nombres',
                'required': True
            }),
            'apellidos': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ingrese los apellidos',
                'required': True
            }),
            'identificacion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 1234567890 o 1234567890001',
                'required': True,
                'maxlength': 20
            }),
            'tipo_identificacion': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'direccion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Dirección completa'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 02-234-5678'
            }),
            'celular': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 0987654321'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'cliente@email.com'
            }),
            'fecha_nacimiento': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'profesion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Profesión u ocupación'
            }),
            'referido_por': forms.Select(attrs={
                'class': 'form-select'
            }),
            'descuento_preferencial': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 100,
                'step': 0.01,
                'placeholder': '0.00'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones adicionales'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtrar clientes activos para referidos
        self.fields['referido_por'].queryset = Cliente.objects.filter(
            activo=True
        ).exclude(identificacion='9999999999')
        self.fields['referido_por'].empty_label = "-- Seleccionar cliente --"
        
        # Si es edición, excluir el cliente actual de los referidos
        if self.instance and self.instance.pk:
            self.fields['referido_por'].queryset = self.fields['referido_por'].queryset.exclude(
                pk=self.instance.pk
            )
    
    def clean_identificacion(self):
        """Valida el número de identificación"""
        # ✅ Corregido: manejo seguro de None
        identificacion = self.cleaned_data.get('identificacion') or ''
        identificacion = identificacion.strip() if identificacion else ''
        tipo_identificacion = self.cleaned_data.get('tipo_identificacion')
        
        if not identificacion:
            raise ValidationError('La identificación es requerida')
        
        # Validaciones específicas por tipo
        if tipo_identificacion == 'CEDULA':
            if not self._validar_cedula(identificacion):
                raise ValidationError('Número de cédula inválido')
        elif tipo_identificacion == 'RUC':
            if not self._validar_ruc(identificacion):
                raise ValidationError('Número de RUC inválido')
        elif tipo_identificacion == 'PASAPORTE':
            if len(identificacion) < 6:
                raise ValidationError('El pasaporte debe tener al menos 6 caracteres')
        
        # Verificar unicidad (excepto para el mismo cliente en edición)
        queryset = Cliente.objects.filter(identificacion=identificacion)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise ValidationError('Ya existe un cliente con esta identificación')
        
        return identificacion
    
    def clean_email(self):
        """Valida el email del cliente"""
        # ✅ Corregido: manejo seguro de None
        email = self.cleaned_data.get('email') or ''
        email = email.strip() if email else ''
        
        if email:
            # Verificar unicidad del email
            queryset = Cliente.objects.filter(email=email)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise ValidationError('Ya existe un cliente con este email')
        
        return email or None
    
    def clean_fecha_nacimiento(self):
        """Valida la fecha de nacimiento"""
        fecha_nacimiento = self.cleaned_data.get('fecha_nacimiento')
        
        if fecha_nacimiento:
            if fecha_nacimiento > date.today():
                raise ValidationError('La fecha de nacimiento no puede ser futura')
            
            # Verificar edad mínima (ej: 16 años)
            edad = (date.today() - fecha_nacimiento).days // 365
            if edad < 16:
                raise ValidationError('El cliente debe ser mayor de 16 años')
        
        return fecha_nacimiento
    
    def clean_descuento_preferencial(self):
        """Valida el descuento preferencial"""
        descuento = self.cleaned_data.get('descuento_preferencial', 0)
        
        if descuento is None:
            descuento = 0
            
        if descuento < 0 or descuento > 100:
            raise ValidationError('El descuento debe estar entre 0 y 100%')
        
        return descuento
    
    def _validar_cedula(self, cedula):
        """Valida cédula ecuatoriana"""
        if len(cedula) != 10:
            return False
        
        if not cedula.isdigit():
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
    
    def _validar_ruc(self, ruc):
        """Valida RUC ecuatoriano"""
        if len(ruc) == 13:
            # RUC de persona natural (cédula + 001)
            if ruc.endswith('001'):
                return self._validar_cedula(ruc[:10])
        elif len(ruc) == 13:
            # RUC de empresa
            tercero = int(ruc[2])
            if tercero >= 6 and tercero <= 9:
                # Validación específica para RUC de empresa
                return True
        
        return False

class MotoForm(forms.ModelForm):
    """Formulario para crear/editar motos"""
    
    class Meta:
        model = Moto
        fields = [
            'placa', 'marca', 'modelo', 'año', 'color',
            'numero_chasis', 'numero_motor', 'cilindraje',
            'tipo', 'kilometraje', 'fecha_ultima_revision',
            'descripcion', 'estado'
        ]
        
        widgets = {
            'placa': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: ABC-1234',
                'required': True,
                'style': 'text-transform: uppercase;'
            }),
            'marca': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'modelo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Modelo de la moto',
                'required': True
            }),
            'año': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1990,
                'max': date.today().year + 1,
                'placeholder': str(date.today().year)
            }),
            'color': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Color principal'
            }),
            'numero_chasis': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de chasis'
            }),
            'numero_motor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de motor'
            }),
            'cilindraje': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 150cc'
            }),
            'tipo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Scooter, Deportiva, Naked'
            }),
            'kilometraje': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Kilometraje actual'
            }),
            'fecha_ultima_revision': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción adicional'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-select'
            }, choices=[
                ('Activo', 'Activo'),
                ('Inactivo', 'Inactivo'),
                ('En reparación', 'En reparación'),
                ('Vendido', 'Vendido')
            ])
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Cargar marcas desde el modelo de inventario
        try:
            from inventario.models import Marca
            self.fields['marca'].queryset = Marca.objects.filter(activo=True)
        except ImportError:
            pass
    
    def clean_placa(self):
        """Valida la placa de la moto"""
        # ✅ Corregido: manejo seguro de None
        placa = self.cleaned_data.get('placa') or ''
        placa = placa.strip().upper() if placa else ''
        
        if not placa:
            raise ValidationError('La placa es requerida')
        
        # Validar formato de placa ecuatoriana
        patron_placa = r'^[A-Z]{2,3}-\d{3,4}$'
        if not re.match(patron_placa, placa):
            raise ValidationError('Formato de placa inválido. Use formato: ABC-1234')
        
        # Verificar unicidad
        queryset = Moto.objects.filter(placa=placa)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise ValidationError('Ya existe una moto registrada con esta placa')
        
        return placa
    
    def clean_año(self):
        """Valida el año de la moto"""
        año = self.cleaned_data.get('año')
        
        if año:
            if año < 1990:
                raise ValidationError('El año no puede ser menor a 1990')
            
            if año > date.today().year + 1:
                raise ValidationError('El año no puede ser mayor al próximo año')
        
        return año

class HistorialClienteForm(forms.ModelForm):
    """Formulario para agregar entradas al historial del cliente"""
    
    class Meta:
        model = HistorialCliente
        fields = ['tipo', 'descripcion', 'importante']
        
        widgets = {
            'tipo': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Descripción detallada de la interacción',
                'required': True
            }),
            'importante': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def clean_descripcion(self):
        """Valida la descripción"""
        # ✅ Corregido: manejo seguro de None
        descripcion = self.cleaned_data.get('descripcion') or ''
        descripcion = descripcion.strip() if descripcion else ''
        
        if len(descripcion) < 10:
            raise ValidationError('La descripción debe tener al menos 10 caracteres')
        
        return descripcion

class CanjeoPuntosForm(forms.ModelForm):
    """Formulario para canjear puntos"""
    
    class Meta:
        model = CanjeoPuntos
        fields = [
            'tipo_premio', 'descripcion_premio', 'puntos_utilizados',
            'valor_equivalente', 'fecha_vencimiento', 'observaciones'
        ]
        
        widgets = {
            'tipo_premio': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'descripcion_premio': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descripción del premio',
                'required': True
            }),
            'puntos_utilizados': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'required': True
            }),
            'valor_equivalente': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'step': 0.01,
                'placeholder': '0.00'
            }),
            'fecha_vencimiento': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones adicionales'
            })
        }
    
    def clean_puntos_utilizados(self):
        """Valida los puntos a utilizar"""
        puntos = self.cleaned_data.get('puntos_utilizados', 0)
        
        if puntos is None or puntos <= 0:
            raise ValidationError('Debe ingresar una cantidad válida de puntos')
        
        return puntos
    
    def clean_fecha_vencimiento(self):
        """Valida la fecha de vencimiento"""
        fecha_vencimiento = self.cleaned_data.get('fecha_vencimiento')
        
        if fecha_vencimiento and fecha_vencimiento <= date.today():
            raise ValidationError('La fecha de vencimiento debe ser futura')
        
        return fecha_vencimiento

class ConfiguracionPuntosForm(forms.ModelForm):
    """Formulario para configurar el sistema de puntos"""
    
    class Meta:
        model = ConfiguracionPuntos
        fields = [
            'nombre', 'regla', 'valor', 'activo',
            'fecha_inicio', 'fecha_fin', 'descripcion'
        ]
        
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la configuración',
                'required': True
            }),
            'regla': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': 0.01,
                'min': 0,
                'required': True
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'fecha_inicio': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'fecha_fin': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción de la configuración'
            })
        }
    
    def clean(self):
        """Validaciones generales"""
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        
        if fecha_inicio and fecha_fin:
            if fecha_fin <= fecha_inicio:
                raise ValidationError('La fecha fin debe ser posterior a la fecha inicio')
        
        return cleaned_data

class BusquedaClienteForm(forms.Form):
    """Formulario para búsqueda avanzada de clientes"""
    
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por nombre, cédula, teléfono...'
        })
    )
    
    tipo_identificacion = forms.ChoiceField(
        choices=[('', 'Todos')] + Cliente.TIPO_IDENTIFICACION_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    activo = forms.ChoiceField(
        choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')],
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    con_puntos = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    fecha_registro_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    fecha_registro_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
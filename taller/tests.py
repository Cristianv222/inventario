from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import OrdenTrabajo, TipoServicio, CategoriaServicio, Tecnico, EspecialidadTecnica
from .forms import OrdenTrabajoForm, ServicioOrdenFormSet, RepuestoOrdenFormSet
from clientes.models import Cliente

User = get_user_model()


class OrdenTrabajoFormTest(TestCase):
    """Pruebas para el formulario de órdenes de trabajo"""
    
    def setUp(self):
        # Crear usuario de prueba
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Crear cliente de prueba
        self.cliente = Cliente.objects.create(
            identificacion='1234567890',
            nombres='Juan',
            apellidos='Pérez',
            telefono='0999999999',
            email='juan@example.com',
            direccion='Calle Principal 123'
        )
        
        # Crear especialidad técnica
        self.especialidad = EspecialidadTecnica.objects.create(
            nombre='Mecánica General',
            descripcion='Especialidad en mecánica general'
        )
        
        # Crear técnico de prueba
        self.tecnico = Tecnico.objects.create(
            codigo='TEC001',
            identificacion='0987654321',
            nombres='Carlos',
            apellidos='Técnico',
            estado='ACTIVO',
            activo=True
        )
        self.tecnico.especialidades.add(self.especialidad)
        
        # Crear categoría y tipo de servicio
        self.categoria = CategoriaServicio.objects.create(
            nombre='Mantenimiento',
            codigo='MANT'
        )
        
        self.tipo_servicio = TipoServicio.objects.create(
            categoria=self.categoria,
            nombre='Cambio de aceite',
            codigo='CA001',
            precio_base=15.00,
            precio_mano_obra=10.00,
            tiempo_estimado_horas=1.0
        )
    
    def test_crear_orden_con_cliente_existente(self):
        """Test crear orden con cliente existente usando ID"""
        form_data = {
            'cliente': self.cliente.id,
            'cliente_identificacion': self.cliente.identificacion,
            'moto_marca': 'Honda',
            'moto_modelo': 'CBR 150',
            'moto_placa': 'ABC-123',
            'tecnico_principal': self.tecnico.id,
            'motivo_ingreso': 'Mantenimiento preventivo',
            'prioridad': 'NORMAL',
            'estado': 'PENDIENTE',
            # Formsets vacíos
            'servicios-TOTAL_FORMS': '0',
            'servicios-INITIAL_FORMS': '0',
            'servicios-MIN_NUM_FORMS': '0',
            'servicios-MAX_NUM_FORMS': '1000',
            'repuestos-TOTAL_FORMS': '0',
            'repuestos-INITIAL_FORMS': '0',
            'repuestos-MIN_NUM_FORMS': '0',
            'repuestos-MAX_NUM_FORMS': '1000',
        }
        
        form = OrdenTrabajoForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Errores del formulario: {form.errors}")
        
        orden = form.save()
        self.assertEqual(orden.cliente, self.cliente)
        self.assertEqual(orden.cliente.nombres, 'Juan')
        self.assertEqual(orden.cliente.apellidos, 'Pérez')
        self.assertEqual(orden.cliente.identificacion, '1234567890')
        self.assertEqual(orden.cliente.email, 'juan@example.com')
        self.assertEqual(orden.cliente.direccion, 'Calle Principal 123')
        self.assertEqual(orden.cliente.telefono, '0999999999')
    
    def test_crear_orden_buscando_cliente_por_identificacion(self):
        """Test crear orden buscando cliente solo por identificación"""
        form_data = {
            # No incluimos el ID del cliente, solo la identificación
            'cliente_identificacion': '1234567890',
            'moto_marca': 'Yamaha',
            'moto_modelo': 'FZ 150',
            'moto_placa': 'XYZ-789',
            'tecnico_principal': self.tecnico.id,
            'motivo_ingreso': 'Cambio de aceite',
            'prioridad': 'NORMAL',
            'estado': 'PENDIENTE',
        }
        
        form = OrdenTrabajoForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Errores del formulario: {form.errors}")
        
        # El método clean debe encontrar y asignar el cliente
        self.assertEqual(form.cleaned_data['cliente'], self.cliente)
        
        orden = form.save()
        self.assertEqual(orden.cliente, self.cliente)
        self.assertEqual(orden.cliente.identificacion, '1234567890')
    
    def test_error_cliente_no_encontrado(self):
        """Test error cuando no se encuentra el cliente"""
        form_data = {
            'cliente_identificacion': '9999999999',  # Identificación no existente
            'moto_marca': 'Suzuki',
            'moto_modelo': 'GN 125',
            'moto_placa': 'DEF-456',
            'tecnico_principal': self.tecnico.id,
            'motivo_ingreso': 'Revisión general',
            'prioridad': 'NORMAL',
            'estado': 'PENDIENTE',
        }
        
        form = OrdenTrabajoForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('cliente_identificacion', form.errors)
        self.assertIn('No se encontró un cliente', str(form.errors['cliente_identificacion']))
    
    def test_vista_crear_orden(self):
        """Test vista de creación de orden"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('taller:orden_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Test POST
        form_data = {
            'cliente': self.cliente.id,
            'cliente_identificacion': self.cliente.identificacion,
            'moto_marca': 'Honda',
            'moto_modelo': 'Wave 110',
            'moto_placa': 'GHI-789',
            'tecnico_principal': self.tecnico.id,
            'motivo_ingreso': 'Mantenimiento 5000km',
            'prioridad': 'NORMAL',
            'estado': 'PENDIENTE',
            'action': 'save',
            # Formsets
            'servicios-TOTAL_FORMS': '1',
            'servicios-INITIAL_FORMS': '0',
            'servicios-MIN_NUM_FORMS': '0',
            'servicios-MAX_NUM_FORMS': '1000',
            'servicios-0-tipo_servicio': self.tipo_servicio.id,
            'servicios-0-tecnico_asignado': self.tecnico.id,
            'servicios-0-precio_base': '15.00',
            'servicios-0-precio_mano_obra': '10.00',
            'servicios-0-tiempo_estimado': '1.0',
            'repuestos-TOTAL_FORMS': '0',
            'repuestos-INITIAL_FORMS': '0',
            'repuestos-MIN_NUM_FORMS': '0',
            'repuestos-MAX_NUM_FORMS': '1000',
        }
        
        response = self.client.post(url, data=form_data)
        
        # Verificar que se creó la orden
        orden = OrdenTrabajo.objects.filter(moto_placa='GHI-789').first()
        self.assertIsNotNone(orden)
        self.assertEqual(orden.cliente, self.cliente)
        self.assertEqual(orden.servicios.count(), 1)
    
    def test_buscar_cliente_ajax(self):
        """Test búsqueda AJAX de clientes"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('taller:buscar_cliente_ajax')
        
        # Buscar por identificación
        response = self.client.get(url, {'q': '1234'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['identificacion'], '1234567890')
        
        # Buscar por nombre
        response = self.client.get(url, {'q': 'Juan'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['nombres'], 'Juan')
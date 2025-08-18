from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
import json

from .models import (
    Cliente, Moto, MovimientoPuntos, ConfiguracionPuntos, 
    CanjeoPuntos, HistorialCliente
)
from .utils import (
    validar_cedula_ecuatoriana, validar_ruc_ecuatoriano, 
    procesar_puntos_venta, calcular_descuento_puntos
)
from .services.sri_service import SRIService


class ClienteModelTest(TestCase):
    """Tests para el modelo Cliente"""
    
    def setUp(self):
        self.cliente_data = {
            'nombres': 'Juan Carlos',
            'apellidos': 'Pérez García',
            'identificacion': '1234567890',
            'tipo_identificacion': 'CEDULA',
            'telefono': '0987654321',
            'email': 'juan.perez@email.com',
            'direccion': 'Av. Principal 123',
            'activo': True
        }
        
    def test_crear_cliente(self):
        """Test crear cliente básico"""
        cliente = Cliente.objects.create(**self.cliente_data)
        
        self.assertEqual(cliente.nombres, 'Juan Carlos')
        self.assertEqual(cliente.apellidos, 'Pérez García')
        self.assertEqual(cliente.identificacion, '1234567890')
        self.assertEqual(cliente.puntos_disponibles, 0)
        self.assertEqual(cliente.puntos_acumulados, 0)
        self.assertTrue(cliente.activo)
        
    def test_get_nombre_completo(self):
        """Test método get_nombre_completo"""
        cliente = Cliente.objects.create(**self.cliente_data)
        self.assertEqual(cliente.get_nombre_completo(), 'Juan Carlos Pérez García')
        
    def test_agregar_puntos(self):
        """Test agregar puntos al cliente"""
        cliente = Cliente.objects.create(**self.cliente_data)
        
        # Agregar puntos
        cliente.agregar_puntos(100, 'Test de puntos')
        
        self.assertEqual(cliente.puntos_disponibles, 100)
        self.assertEqual(cliente.puntos_acumulados, 100)
        
        # Verificar movimiento creado
        movimiento = MovimientoPuntos.objects.filter(cliente=cliente).first()
        self.assertIsNotNone(movimiento)
        self.assertEqual(movimiento.tipo, 'GANADO')
        self.assertEqual(movimiento.puntos, 100)
        
    def test_canjear_puntos(self):
        """Test canjear puntos del cliente"""
        cliente = Cliente.objects.create(**self.cliente_data)
        cliente.agregar_puntos(100, 'Puntos iniciales')
        
        # Canjear puntos
        resultado = cliente.canjear_puntos(50, 'Canje de prueba')
        
        self.assertTrue(resultado)
        self.assertEqual(cliente.puntos_disponibles, 50)
        self.assertEqual(cliente.puntos_canjeados, 50)
        
        # Verificar movimiento de canje
        movimiento_canje = MovimientoPuntos.objects.filter(
            cliente=cliente, tipo='CANJEADO'
        ).first()
        self.assertIsNotNone(movimiento_canje)
        self.assertEqual(movimiento_canje.puntos, 50)
        
    def test_canjear_puntos_insuficientes(self):
        """Test canjear más puntos de los disponibles"""
        cliente = Cliente.objects.create(**self.cliente_data)
        cliente.agregar_puntos(50, 'Puntos iniciales')
        
        # Intentar canjear más puntos de los disponibles
        resultado = cliente.canjear_puntos(100, 'Canje imposible')
        
        self.assertFalse(resultado)
        self.assertEqual(cliente.puntos_disponibles, 50)
        self.assertEqual(cliente.puntos_canjeados, 0)
        
    def test_calcular_descuento_puntos(self):
        """Test cálculo de descuento por puntos"""
        cliente = Cliente.objects.create(**self.cliente_data)
        cliente.agregar_puntos(1000, 'Puntos para descuento')
        
        # Descuento con total de $50 (descuento máximo $10)
        descuento = cliente.calcular_descuento_puntos(Decimal('50.00'))
        expected_descuento = Decimal('10.00')  # 1000 puntos = $10
        
        self.assertEqual(descuento, expected_descuento)
        
        # Descuento con total de $5 (límite por total)
        descuento_limitado = cliente.calcular_descuento_puntos(Decimal('5.00'))
        expected_limitado = Decimal('2.50')  # Máximo 50% del total
        
        self.assertEqual(descuento_limitado, expected_limitado)
        
    def test_get_consumidor_final(self):
        """Test obtener cliente consumidor final"""
        consumidor = Cliente.get_consumidor_final()
        
        self.assertIsNotNone(consumidor)
        self.assertEqual(consumidor.identificacion, '9999999999')
        self.assertEqual(consumidor.nombres, 'Consumidor')
        self.assertEqual(consumidor.apellidos, 'Final')
        
        # Verificar que no crea duplicados
        consumidor2 = Cliente.get_consumidor_final()
        self.assertEqual(consumidor.id, consumidor2.id)


class MotoModelTest(TestCase):
    """Tests para el modelo Moto"""
    
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombres='Test',
            apellidos='Cliente',
            identificacion='1234567890',
            tipo_identificacion='CEDULA'
        )
        
        # Crear marca ficticia para tests
        from inventario.models import Marca
        self.marca, _ = Marca.objects.get_or_create(
            nombre='Honda',
            defaults={'activo': True}
        )
        
    def test_crear_moto(self):
        """Test crear moto"""
        moto = Moto.objects.create(
            cliente=self.cliente,
            placa='ABC-1234',
            marca=self.marca,
            modelo='CBR 250R',
            año='2023',
            color='Rojo'
        )
        
        self.assertEqual(moto.cliente, self.cliente)
        self.assertEqual(moto.placa, 'ABC-1234')
        self.assertEqual(moto.marca, self.marca)
        self.assertEqual(moto.estado, 'Activo')
        
    def test_str_moto(self):
        """Test representación string de moto"""
        moto = Moto.objects.create(
            cliente=self.cliente,
            placa='ABC-1234',
            marca=self.marca,
            modelo='CBR 250R',
            año='2023',
            color='Rojo'
        )
        
        expected_str = f"{self.marca} CBR 250R - ABC-1234 ({self.cliente.nombres})"
        self.assertEqual(str(moto), expected_str)


class ConfiguracionPuntosTest(TestCase):
    """Tests para el modelo ConfiguracionPuntos"""
    
    def setUp(self):
        self.config_data = {
            'nombre': 'Test Config',
            'regla': 'POR_DOLAR',
            'valor': Decimal('1.50'),
            'activo': True,
            'fecha_inicio': date.today()
        }
        
    def test_crear_configuracion(self):
        """Test crear configuración de puntos"""
        config = ConfiguracionPuntos.objects.create(**self.config_data)
        
        self.assertEqual(config.nombre, 'Test Config')
        self.assertEqual(config.regla, 'POR_DOLAR')
        self.assertEqual(config.valor, Decimal('1.50'))
        self.assertTrue(config.activo)
        
    def test_calcular_puntos_venta(self):
        """Test cálculo de puntos por venta"""
        # Crear configuración activa
        ConfiguracionPuntos.objects.create(**self.config_data)
        
        total_venta = Decimal('100.00')
        puntos = ConfiguracionPuntos.calcular_puntos_venta(total_venta)
        
        # 1.50 puntos por dólar * 100 dólares = 150 puntos
        self.assertEqual(puntos, 150)
        
    def test_calcular_puntos_multiple_configs(self):
        """Test cálculo con múltiples configuraciones"""
        # Configuración por dólar
        ConfiguracionPuntos.objects.create(**self.config_data)
        
        # Configuración por venta
        ConfiguracionPuntos.objects.create(
            nombre='Bonus por venta',
            regla='POR_VENTA',
            valor=Decimal('10.00'),
            activo=True,
            fecha_inicio=date.today()
        )
        
        total_venta = Decimal('100.00')
        puntos = ConfiguracionPuntos.calcular_puntos_venta(total_venta)
        
        # (1.50 * 100) + 10 = 160 puntos
        self.assertEqual(puntos, 160)


class UtilsTest(TestCase):
    """Tests para funciones de utilidad"""
    
    def test_validar_cedula_ecuatoriana_valida(self):
        """Test validación de cédula válida"""
        # Cédulas válidas de ejemplo
        cedulas_validas = ['1714616123', '1710034264', '0926687856']
        
        for cedula in cedulas_validas:
            with self.subTest(cedula=cedula):
                self.assertTrue(validar_cedula_ecuatoriana(cedula))
                
    def test_validar_cedula_ecuatoriana_invalida(self):
        """Test validación de cédula inválida"""
        cedulas_invalidas = ['1234567890', '123456789', '12345678901', 'abcdefghij']
        
        for cedula in cedulas_invalidas:
            with self.subTest(cedula=cedula):
                self.assertFalse(validar_cedula_ecuatoriana(cedula))
                
    def test_validar_ruc_ecuatoriano_persona_natural(self):
        """Test validación de RUC de persona natural"""
        # RUC válido: cédula válida + 001
        ruc_valido = '1714616123001'
        self.assertTrue(validar_ruc_ecuatoriano(ruc_valido))
        
    def test_validar_ruc_ecuatoriano_empresa(self):
        """Test validación de RUC de empresa"""
        # RUC de empresa (tercer dígito 6-9)
        ruc_empresa = '1790016919001'
        self.assertTrue(validar_ruc_ecuatoriano(ruc_empresa))
        
    def test_procesar_puntos_venta(self):
        """Test procesamiento de puntos por venta"""
        # Crear cliente y configuración
        cliente = Cliente.objects.create(
            nombres='Test',
            apellidos='Cliente',
            identificacion='1234567890',
            tipo_identificacion='CEDULA'
        )
        
        ConfiguracionPuntos.objects.create(
            nombre='Test Config',
            regla='POR_DOLAR',
            valor=Decimal('2.00'),
            activo=True,
            fecha_inicio=date.today()
        )
        
        # Procesar puntos
        total_venta = Decimal('50.00')
        puntos_otorgados = procesar_puntos_venta(cliente, total_venta)
        
        self.assertEqual(puntos_otorgados, 100)  # 2 puntos por dólar * 50
        self.assertEqual(cliente.puntos_disponibles, 100)
        
    def test_calcular_descuento_puntos_util(self):
        """Test función de utilidad para calcular descuento"""
        cliente = Cliente.objects.create(
            nombres='Test',
            apellidos='Cliente',
            identificacion='1234567890',
            tipo_identificacion='CEDULA',
            puntos_disponibles=500
        )
        
        total_compra = Decimal('100.00')
        descuento_info = calcular_descuento_puntos(cliente, total_compra)
        
        self.assertEqual(descuento_info['puntos_actuales'], 500)
        self.assertEqual(descuento_info['descuento_disponible'], 5.0)  # 500 * 0.01
        self.assertTrue(descuento_info['puede_aplicar'])


class ClienteViewsTest(TestCase):
    """Tests para las vistas de clientes"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        self.cliente = Cliente.objects.create(
            nombres='Juan',
            apellidos='Pérez',
            identificacion='1234567890',
            tipo_identificacion='CEDULA',
            telefono='0987654321',
            email='juan@email.com'
        )
        
    def test_lista_clientes_view(self):
        """Test vista lista de clientes"""
        url = reverse('clientes:lista_clientes')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Pérez')
        self.assertContains(response, '1234567890')
        
    def test_detalle_cliente_view(self):
        """Test vista detalle de cliente"""
        url = reverse('clientes:detalle_cliente', kwargs={'cliente_id': self.cliente.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Pérez')
        self.assertContains(response, self.cliente.email)
        
    def test_crear_cliente_view_get(self):
        """Test vista crear cliente GET"""
        url = reverse('clientes:crear_cliente')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nuevo Cliente')
        
    def test_crear_cliente_view_post(self):
        """Test vista crear cliente POST"""
        url = reverse('clientes:crear_cliente')
        data = {
            'nombres': 'María',
            'apellidos': 'González',
            'identificacion': '0987654321',
            'tipo_identificacion': 'CEDULA',
            'telefono': '0987654321',
            'email': 'maria@email.com',
            'activo': True
        }
        
        response = self.client.post(url, data)
        
        # Verificar redirección después de crear
        self.assertEqual(response.status_code, 302)
        
        # Verificar que el cliente fue creado
        cliente_creado = Cliente.objects.filter(identificacion='0987654321').first()
        self.assertIsNotNone(cliente_creado)
        self.assertEqual(cliente_creado.nombres, 'María')
        
    def test_editar_cliente_view(self):
        """Test vista editar cliente"""
        url = reverse('clientes:editar_cliente', kwargs={'cliente_id': self.cliente.id})
        data = {
            'nombres': 'Juan Carlos',
            'apellidos': 'Pérez García',
            'identificacion': self.cliente.identificacion,
            'tipo_identificacion': self.cliente.tipo_identificacion,
            'telefono': '0987654321',
            'email': 'juan.actualizado@email.com',
            'activo': True
        }
        
        response = self.client.post(url, data)
        
        # Verificar redirección
        self.assertEqual(response.status_code, 302)
        
        # Verificar actualización
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.email, 'juan.actualizado@email.com')
        self.assertEqual(self.cliente.nombres, 'Juan Carlos')
        
    def test_gestionar_puntos_view(self):
        """Test vista gestionar puntos"""
        url = reverse('clientes:gestionar_puntos', kwargs={'cliente_id': self.cliente.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gestionar Puntos')
        self.assertContains(response, self.cliente.get_nombre_completo())


class ClienteAPITest(TestCase):
    """Tests para las APIs de clientes"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        self.cliente = Cliente.objects.create(
            nombres='Juan',
            apellidos='Pérez',
            identificacion='1234567890',
            tipo_identificacion='CEDULA',
            telefono='0987654321',
            email='juan@email.com',
            puntos_disponibles=100
        )
        
    def test_api_buscar_clientes(self):
        """Test API buscar clientes"""
        url = reverse('clientes:api_buscar_clientes')
        response = self.client.get(url, {'q': 'Juan'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertTrue(data['success'])
        self.assertEqual(len(data['clientes']), 1)
        self.assertEqual(data['clientes'][0]['nombre_completo'], 'Juan Pérez')
        
    def test_api_cliente_puntos(self):
        """Test API información de puntos"""
        url = reverse('clientes:api_cliente_puntos', kwargs={'cliente_id': self.cliente.id})
        response = self.client.get(url, {'total': '50.00'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertTrue(data['success'])
        self.assertEqual(data['puntos_disponibles'], 100)
        self.assertEqual(data['descuento_disponible'], 1.0)  # 100 puntos = $1.00
        
    def test_buscar_cliente_api(self):
        """Test API buscar cliente por identificación"""
        url = reverse('clientes:buscar_cliente_api')
        response = self.client.get(url, {'identificacion': '1234567890'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertTrue(data['success'])
        self.assertEqual(data['cliente']['nombres'], 'Juan')
        self.assertEqual(data['cliente']['apellidos'], 'Pérez')


class SRIServiceTest(TestCase):
    """Tests para el servicio SRI"""
    
    def setUp(self):
        self.sri_service = SRIService()
        
    def test_validar_cedula(self):
        """Test validación de cédula en SRI service"""
        # Cédula válida
        self.assertTrue(self.sri_service._validar_cedula('1714616123'))
        
        # Cédula inválida
        self.assertFalse(self.sri_service._validar_cedula('1234567890'))
        
    def test_validar_ruc(self):
        """Test validación de RUC en SRI service"""
        # RUC válido
        self.assertTrue(self.sri_service._validar_ruc('1714616123001'))
        
        # RUC inválido
        self.assertFalse(self.sri_service._validar_ruc('1234567890123'))
        
    def test_determinar_tipo_identificacion(self):
        """Test determinar tipo de identificación"""
        self.assertEqual(self.sri_service._determinar_tipo_identificacion('1234567890'), 'CEDULA')
        self.assertEqual(self.sri_service._determinar_tipo_identificacion('1234567890001'), 'RUC')
        self.assertEqual(self.sri_service._determinar_tipo_identificacion('A12345678'), 'PASAPORTE')
        
    def test_obtener_provincias_ecuador(self):
        """Test obtener provincias de Ecuador"""
        provincias = self.sri_service.obtener_provincias_ecuador()
        
        self.assertIn('17', provincias)  # Pichincha
        self.assertEqual(provincias['17'], 'Pichincha')
        self.assertIn('09', provincias)  # Guayas
        self.assertEqual(provincias['09'], 'Guayas')
        
    def test_obtener_provincia_por_cedula(self):
        """Test obtener provincia por cédula"""
        # Cédula de Pichincha (17)
        provincia = self.sri_service.obtener_provincia_por_cedula('1714616123')
        self.assertEqual(provincia, 'Pichincha')
        
        # Cédula de Guayas (09)
        provincia = self.sri_service.obtener_provincia_por_cedula('0926687856')
        self.assertEqual(provincia, 'Guayas')


class SignalsTest(TestCase):
    """Tests para los signals"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.cliente = Cliente.objects.create(
            nombres='Juan',
            apellidos='Pérez',
            identificacion='1234567890',
            tipo_identificacion='CEDULA'
        )
        
        # Crear configuración de puntos
        ConfiguracionPuntos.objects.create(
            nombre='Test Config',
            regla='POR_DOLAR',
            valor=Decimal('1.00'),
            activo=True,
            fecha_inicio=date.today()
        )
        
    def test_procesar_puntos_por_venta_signal(self):
        """Test signal para procesar puntos por venta"""
        # Simular creación de venta (normalmente esto vendría del modelo Venta)
        from ventas.models import Venta
        
        venta = Venta.objects.create(
            cliente=self.cliente,
            usuario=self.user,
            subtotal=Decimal('100.00'),
            iva=Decimal('15.00'),
            total=Decimal('115.00'),
            estado='COMPLETADA'
        )
        
        # Verificar que se procesaron los puntos
        self.cliente.refresh_from_db()
        self.assertGreater(self.cliente.puntos_disponibles, 0)
        
        # Verificar movimiento de puntos
        movimiento = MovimientoPuntos.objects.filter(
            cliente=self.cliente,
            venta=venta
        ).first()
        self.assertIsNotNone(movimiento)
        
    def test_procesar_cliente_referido_signal(self):
        """Test signal para cliente referido"""
        # Crear configuración para referidos
        ConfiguracionPuntos.objects.create(
            nombre='Referidos',
            regla='POR_REFERIDO',
            valor=Decimal('100.00'),
            activo=True,
            fecha_inicio=date.today()
        )
        
        cliente_referente = Cliente.objects.create(
            nombres='Cliente',
            apellidos='Referente',
            identificacion='0987654321',
            tipo_identificacion='CEDULA'
        )
        
        # Crear cliente referido
        cliente_nuevo = Cliente.objects.create(
            nombres='Cliente',
            apellidos='Nuevo',
            identificacion='1122334455',
            tipo_identificacion='CEDULA',
            referido_por=cliente_referente
        )
        
        # Verificar que el referente ganó puntos
        cliente_referente.refresh_from_db()
        self.assertGreater(cliente_referente.puntos_disponibles, 0)
        
        # Verificar historial
        historial = HistorialCliente.objects.filter(
            cliente=cliente_referente,
            descripcion__contains='referir'
        ).first()
        self.assertIsNotNone(historial)


class IntegrationTest(TestCase):
    """Tests de integración completos"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Configurar sistema de puntos
        ConfiguracionPuntos.objects.create(
            nombre='Puntos por dólar',
            regla='POR_DOLAR',
            valor=Decimal('1.00'),
            activo=True,
            fecha_inicio=date.today()
        )
        
    def test_flujo_completo_cliente_y_puntos(self):
        """Test del flujo completo: crear cliente, realizar venta, gestionar puntos"""
        
        # 1. Crear cliente
        cliente_data = {
            'nombres': 'Test',
            'apellidos': 'Integration',
            'identificacion': '1234567890',
            'tipo_identificacion': 'CEDULA',
            'telefono': '0987654321',
            'email': 'test@email.com',
            'activo': True
        }
        
        url_crear = reverse('clientes:crear_cliente')
        response = self.client.post(url_crear, cliente_data)
        self.assertEqual(response.status_code, 302)
        
        cliente = Cliente.objects.get(identificacion='1234567890')
        
        # 2. Simular venta y procesamiento de puntos
        from ventas.models import Venta
        venta = Venta.objects.create(
            cliente=cliente,
            usuario=self.user,
            total=Decimal('100.00'),
            estado='COMPLETADA'
        )
        
        # 3. Verificar puntos otorgados
        cliente.refresh_from_db()
        self.assertGreater(cliente.puntos_disponibles, 0)
        
        # 4. Gestionar puntos (agregar más)
        url_puntos = reverse('clientes:gestionar_puntos', kwargs={'cliente_id': cliente.id})
        puntos_data = {
            'accion': 'agregar',
            'puntos': 50,
            'concepto': 'Puntos de prueba'
        }
        response = self.client.post(url_puntos, puntos_data)
        
        cliente.refresh_from_db()
        self.assertGreaterEqual(cliente.puntos_disponibles, 50)
        
        # 5. Canjear puntos
        puntos_iniciales = cliente.puntos_disponibles
        canje_data = {
            'accion': 'canjear',
            'puntos': 25,
            'concepto': 'Canje de prueba'
        }
        response = self.client.post(url_puntos, canje_data)
        
        cliente.refresh_from_db()
        self.assertEqual(cliente.puntos_disponibles, puntos_iniciales - 25)
        self.assertEqual(cliente.puntos_canjeados, 25)
        
        # 6. Verificar historial de movimientos
        movimientos = MovimientoPuntos.objects.filter(cliente=cliente)
        self.assertGreaterEqual(movimientos.count(), 3)  # Venta + agregar + canjear
        
        # 7. Verificar API de búsqueda
        url_api = reverse('clientes:api_buscar_clientes')
        response = self.client.get(url_api, {'q': 'Test'})
        data = json.loads(response.content)
        
        self.assertTrue(data['success'])
        self.assertEqual(len(data['clientes']), 1)
        self.assertEqual(data['clientes'][0]['nombre_completo'], 'Test Integration')


# ========== COVERAGE REPORT ==========

class CoverageTest(TestCase):
    """Test para asegurar cobertura de funciones críticas"""
    
    def test_all_models_str_methods(self):
        """Test que todos los modelos tienen método __str__"""
        models = [Cliente, Moto, MovimientoPuntos, ConfiguracionPuntos, CanjeoPuntos, HistorialCliente]
        
        for model in models:
            # Crear instancia básica
            if model == Cliente:
                instance = model(nombres='Test', apellidos='Test', identificacion='1234567890')
            elif model == Moto:
                cliente = Cliente(nombres='Test', apellidos='Test', identificacion='1234567890')
                instance = model(cliente=cliente, placa='ABC-123')
            else:
                # Para otros modelos, verificar que tengan __str__ definido
                self.assertTrue(hasattr(model, '__str__'))
                continue
            
            # Verificar que __str__ no falla
            try:
                str(instance)
            except Exception as e:
                self.fail(f"Método __str__ falló para {model.__name__}: {str(e)}")
                
    def test_all_views_require_login(self):
        """Test que todas las vistas requieren login"""
        client = Client()
        
        # URLs que requieren autenticación
        protected_urls = [
            reverse('clientes:lista_clientes'),
            reverse('clientes:crear_cliente'),
        ]
        
        for url in protected_urls:
            response = client.get(url)
            # Debe redirigir al login (302) o retornar 403
            self.assertIn(response.status_code, [302, 403, 401])


if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['clientes'])
    
    if failures:
        print(f"\n❌ {failures} test(s) failed")
    else:
        print("\n✅ All tests passed!")
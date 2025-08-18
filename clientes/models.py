from django.db import models
from django.conf import settings  # ← Agregado para AUTH_USER_MODEL
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal

class Cliente(models.Model):
    """Clientes del negocio"""
    TIPO_IDENTIFICACION_CHOICES = [
        ('CEDULA', 'Cédula'),
        ('RUC', 'RUC'),
        ('PASAPORTE', 'Pasaporte'),
    ]
    
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    identificacion = models.CharField(max_length=20, unique=True)
    tipo_identificacion = models.CharField(max_length=20, choices=TIPO_IDENTIFICACION_CHOICES)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    celular = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=100, blank=True, null=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True, null=True)
    
    # ========== SISTEMA DE PUNTOS ==========
    puntos_disponibles = models.PositiveIntegerField(default=0, help_text="Puntos disponibles para canjear")
    puntos_acumulados = models.PositiveIntegerField(default=0, help_text="Total de puntos acumulados históricamente")
    puntos_canjeados = models.PositiveIntegerField(default=0, help_text="Total de puntos canjeados")
    
    # ========== DATOS ADICIONALES ==========
    profesion = models.CharField(max_length=100, blank=True, null=True)
    referido_por = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, 
                                   related_name='referidos')
    descuento_preferencial = models.DecimalField(max_digits=5, decimal_places=2, default=0.00,
                                                help_text="Descuento preferencial en porcentaje")
    
    class Meta:
        verbose_name = _('Cliente')
        verbose_name_plural = _('Clientes')
        ordering = ['-fecha_registro']
    
    def __str__(self):
        return f"{self.nombres} {self.apellidos} ({self.identificacion})"
    
    def get_nombre_completo(self):
        """Retorna el nombre completo del cliente"""
        return f"{self.nombres} {self.apellidos}".strip()
    
    def agregar_puntos(self, puntos, concepto="Compra", venta=None):
        """Agrega puntos al cliente"""
        if puntos > 0:
            self.puntos_disponibles += puntos
            self.puntos_acumulados += puntos
            self.save()
            
            # Registrar el movimiento
            MovimientoPuntos.objects.create(
                cliente=self,
                tipo='GANADO',
                puntos=puntos,
                concepto=concepto,
                venta=venta
            )
    
    def canjear_puntos(self, puntos, concepto="Canje de puntos"):
        """Canjea puntos del cliente"""
        if puntos <= self.puntos_disponibles:
            self.puntos_disponibles -= puntos
            self.puntos_canjeados += puntos
            self.save()
            
            # Registrar el movimiento
            MovimientoPuntos.objects.create(
                cliente=self,
                tipo='CANJEADO',
                puntos=puntos,
                concepto=concepto
            )
            return True
        return False
    
    def calcular_descuento_puntos(self, total_compra):
        """Calcula el descuento disponible por puntos"""
        # 1 punto = $0.01 de descuento
        descuento_max = self.puntos_disponibles * Decimal('0.01')
        # Máximo 50% de descuento
        descuento_limite = total_compra * Decimal('0.50')
        return min(descuento_max, descuento_limite)
    
    @classmethod
    def get_consumidor_final(cls):
        """Obtiene o crea el cliente 'Consumidor Final'"""
        consumidor, created = cls.objects.get_or_create(
            identificacion='9999999999',
            defaults={
                'nombres': 'Consumidor',
                'apellidos': 'Final',
                'tipo_identificacion': 'CEDULA',
                'direccion': '-',
                'activo': True
            }
        )
        return consumidor

class MovimientoPuntos(models.Model):
    """Historial de movimientos de puntos"""
    TIPO_MOVIMIENTO_CHOICES = [
        ('GANADO', 'Puntos Ganados'),
        ('CANJEADO', 'Puntos Canjeados'),
        ('AJUSTE', 'Ajuste Manual'),
        ('VENCIDO', 'Puntos Vencidos'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='movimientos_puntos')
    tipo = models.CharField(max_length=20, choices=TIPO_MOVIMIENTO_CHOICES)
    puntos = models.PositiveIntegerField()
    concepto = models.CharField(max_length=200)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)  # ← Corregido
    venta = models.ForeignKey('ventas.Venta', on_delete=models.SET_NULL, blank=True, null=True)
    
    class Meta:
        verbose_name = _('Movimiento de Puntos')
        verbose_name_plural = _('Movimientos de Puntos')
        ordering = ['-fecha']
    
    def __str__(self):
        return f"{self.cliente.get_nombre_completo()} - {self.tipo} - {self.puntos} puntos"

class ConfiguracionPuntos(models.Model):
    """Configuración del sistema de puntos"""
    REGLA_CHOICES = [
        ('POR_DOLAR', 'Puntos por dólar gastado'),
        ('POR_VENTA', 'Puntos por venta realizada'),
        ('POR_REFERIDO', 'Puntos por cliente referido'),
    ]
    
    nombre = models.CharField(max_length=100)
    regla = models.CharField(max_length=20, choices=REGLA_CHOICES)
    valor = models.DecimalField(max_digits=10, decimal_places=2, 
                               help_text="Cantidad de puntos o multiplicador")
    activo = models.BooleanField(default=True)
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = _('Configuración de Puntos')
        verbose_name_plural = _('Configuraciones de Puntos')
    
    def __str__(self):
        return f"{self.nombre} - {self.get_regla_display()}"
    
    @classmethod
    def calcular_puntos_venta(cls, total_venta):
        """Calcula los puntos a otorgar por una venta"""
        configuraciones = cls.objects.filter(
            activo=True,
            fecha_inicio__lte=timezone.now().date()
        ).filter(
            models.Q(fecha_fin__isnull=True) | 
            models.Q(fecha_fin__gte=timezone.now().date())
        )
        
        total_puntos = 0
        
        for config in configuraciones:
            if config.regla == 'POR_DOLAR':
                # Ejemplo: 1 punto por cada $1 gastado
                total_puntos += int(total_venta * config.valor)
            elif config.regla == 'POR_VENTA':
                # Ejemplo: 10 puntos por venta
                total_puntos += int(config.valor)
        
        return total_puntos

class CanjeoPuntos(models.Model):
    """Registro de canjes de puntos por premios/servicios"""
    TIPO_PREMIO_CHOICES = [
        ('DESCUENTO', 'Descuento en compra'),
        ('SERVICIO_GRATIS', 'Servicio gratuito'),
        ('PRODUCTO_GRATIS', 'Producto gratuito'),
        ('OTRO', 'Otro premio'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='canjes')
    tipo_premio = models.CharField(max_length=20, choices=TIPO_PREMIO_CHOICES)
    descripcion_premio = models.CharField(max_length=200)
    puntos_utilizados = models.PositiveIntegerField()
    valor_equivalente = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fecha_canje = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField(blank=True, null=True)
    utilizado = models.BooleanField(default=False)
    fecha_utilizacion = models.DateTimeField(blank=True, null=True)
    venta_utilizacion = models.ForeignKey('ventas.Venta', on_delete=models.SET_NULL, 
                                        blank=True, null=True, related_name='canjes_utilizados')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)  # ← Corregido
    observaciones = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = _('Canje de Puntos')
        verbose_name_plural = _('Canjes de Puntos')
        ordering = ['-fecha_canje']
    
    def __str__(self):
        return f"{self.cliente.get_nombre_completo()} - {self.descripcion_premio}"
    
    def marcar_como_utilizado(self, venta=None):
        """Marca el canje como utilizado"""
        self.utilizado = True
        self.fecha_utilizacion = timezone.now()
        self.venta_utilizacion = venta
        self.save()

class Moto(models.Model):
    """Motos de los clientes"""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='motos')
    placa = models.CharField(max_length=20, unique=True)
    marca = models.ForeignKey('inventario.Marca', on_delete=models.CASCADE)
    modelo = models.CharField(max_length=100)
    año = models.CharField(max_length=4)
    color = models.CharField(max_length=50)
    numero_chasis = models.CharField(max_length=50, blank=True, null=True)
    numero_motor = models.CharField(max_length=50, blank=True, null=True)
    cilindraje = models.CharField(max_length=20, blank=True, null=True)
    tipo = models.CharField(max_length=50, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, default='Activo')
    kilometraje = models.PositiveIntegerField(blank=True, null=True, help_text="Kilometraje actual")
    fecha_ultima_revision = models.DateField(blank=True, null=True)
    
    class Meta:
        verbose_name = _('Moto')
        verbose_name_plural = _('Motos')
        ordering = ['-fecha_registro']
    
    def __str__(self):
        return f"{self.marca} {self.modelo} - {self.placa} ({self.cliente.nombres})"
    
    def get_ordenes_trabajo(self):
        """Retorna las órdenes de trabajo de esta moto"""
        return self.ordenes_trabajo.all().order_by('-fecha_ingreso')
    
    def get_ultimo_mantenimiento(self):
        """Retorna la fecha del último mantenimiento"""
        ultima_orden = self.ordenes_trabajo.filter(
            estado='COMPLETADO'
        ).order_by('-fecha_completado').first()
        
        if ultima_orden:
            return ultima_orden.fecha_completado
        return None

class HistorialCliente(models.Model):
    """Historial de interacciones con el cliente"""
    TIPO_INTERACCION_CHOICES = [
        ('VENTA', 'Venta realizada'),
        ('SERVICIO', 'Servicio prestado'),
        ('LLAMADA', 'Llamada telefónica'),
        ('EMAIL', 'Email enviado'),
        ('WHATSAPP', 'Mensaje WhatsApp'),
        ('VISITA', 'Visita al taller'),
        ('RECLAMO', 'Reclamo o queja'),
        ('FELICITACION', 'Felicitación'),
        ('OTRO', 'Otro tipo'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='historial')
    tipo = models.CharField(max_length=20, choices=TIPO_INTERACCION_CHOICES)
    descripcion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)  # ← Corregido
    venta = models.ForeignKey('ventas.Venta', on_delete=models.SET_NULL, blank=True, null=True)
    orden_trabajo = models.ForeignKey('taller.OrdenTrabajo', on_delete=models.SET_NULL, 
                                    blank=True, null=True)
    importante = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = _('Historial de Cliente')
        verbose_name_plural = _('Historiales de Clientes')
        ordering = ['-fecha']
    
    def __str__(self):
        return f"{self.cliente.get_nombre_completo()} - {self.get_tipo_display()}"
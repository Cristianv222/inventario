from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum, Avg, Count, Q
from decimal import Decimal
from datetime import timedelta
import uuid

# ================== MODELOS DE CONFIGURACIÓN ==================

class EspecialidadTecnica(models.Model):
    """Especialidades técnicas que pueden tener los técnicos"""
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    activa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = _('Especialidad Técnica')
        verbose_name_plural = _('Especialidades Técnicas')
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre


class CategoriaServicio(models.Model):
    """Categorías de servicios técnicos"""
    nombre = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(max_length=20, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    color = models.CharField(
        max_length=7, 
        default='#007bff', 
        help_text="Color en formato hexadecimal"
    )
    activa = models.BooleanField(default=True)
    requiere_diagnostico = models.BooleanField(default=False)
    tiempo_estimado_horas = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        blank=True, 
        null=True
    )
    
    class Meta:
        verbose_name = _('Categoría de Servicio')
        verbose_name_plural = _('Categorías de Servicios')
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre
    
    def get_servicios_activos(self):
        """Obtener servicios activos de esta categoría"""
        return self.tipos_servicio.filter(activo=True)


# ================== MODELOS DE PERSONAL ==================

class Tecnico(models.Model):
    """Técnicos que trabajan en el taller"""
    TIPO_IDENTIFICACION_CHOICES = [
        ('CEDULA', 'Cédula'),
        ('RUC', 'RUC'),
        ('PASAPORTE', 'Pasaporte'),
    ]
    
    ESTADO_CHOICES = [
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
        ('VACACIONES', 'En Vacaciones'),
        ('LICENCIA', 'En Licencia'),
    ]
    
    # Información básica
    codigo = models.CharField(
        max_length=20, 
        unique=True, 
        help_text="Código único del técnico"
    )
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    identificacion = models.CharField(max_length=20, unique=True)
    tipo_identificacion = models.CharField(
        max_length=20, 
        choices=TIPO_IDENTIFICACION_CHOICES,
        default='CEDULA'
    )
    
    # Información de contacto
    telefono = models.CharField(max_length=20, blank=True, null=True)
    celular = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=100, blank=True, null=True)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    
    # Información laboral
    fecha_ingreso = models.DateField()
    fecha_salida = models.DateField(blank=True, null=True)
    estado = models.CharField(
        max_length=20, 
        choices=ESTADO_CHOICES, 
        default='ACTIVO'
    )
    especialidades = models.ManyToManyField(
        EspecialidadTecnica, 
        blank=True,
        related_name='tecnicos'
    )
    porcentaje_comision = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0, 
        help_text="Porcentaje de comisión por servicios"
    )
    salario_base = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True
    )
    
    # Otros campos
    foto = models.ImageField(upload_to='tecnicos/', blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    usuario = models.OneToOneField(
        'usuarios.Usuario', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    activo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = _('Técnico')
        verbose_name_plural = _('Técnicos')
        ordering = ['nombres', 'apellidos']
    
    def __str__(self):
        return f"{self.get_nombre_completo()} ({self.codigo})"
    
    def save(self, *args, **kwargs):
        if not self.codigo:
            # Generar código único
            self.codigo = self._generar_codigo_unico()
        super().save(*args, **kwargs)
    
    def _generar_codigo_unico(self):
        """Generar código único para el técnico"""
        while True:
            codigo = f"TEC-{uuid.uuid4().hex[:6].upper()}"
            if not Tecnico.objects.filter(codigo=codigo).exists():
                return codigo
    
    def get_nombre_completo(self):
        """Obtener nombre completo del técnico"""
        return f"{self.nombres} {self.apellidos}"
    
    def get_ordenes_activas(self):
        """Obtiene las órdenes de trabajo activas del técnico"""
        return self.ordenes_asignadas.filter(
            estado__in=['PENDIENTE', 'EN_PROCESO', 'ESPERANDO_REPUESTOS']
        ).count()
    
    def get_estadisticas_mes(self, mes=None, año=None):
        """Obtiene estadísticas completas del técnico por mes"""
        if not mes:
            mes = timezone.now().month
        if not año:
            año = timezone.now().year
        
        # Órdenes del mes
        ordenes = self.ordenes_asignadas.filter(
            fecha_ingreso__month=mes,
            fecha_ingreso__year=año
        )
        
        # Estadísticas
        stats = {
            'total_ordenes': ordenes.count(),
            'ordenes_completadas': ordenes.filter(estado='COMPLETADO').count(),
            'ordenes_entregadas': ordenes.filter(estado='ENTREGADO').count(),
            'total_facturado': ordenes.filter(
                estado__in=['COMPLETADO', 'ENTREGADO']
            ).aggregate(total=Sum('precio_total'))['total'] or 0,
            'promedio_evaluacion': 0,
            'total_servicios': 0,
            'comision_estimada': 0
        }
        
        # Calcular promedio de evaluaciones
        evaluaciones = EvaluacionServicio.objects.filter(
            orden__in=ordenes,
            calificacion_tecnico__isnull=False
        )
        if evaluaciones.exists():
            stats['promedio_evaluacion'] = evaluaciones.aggregate(
                promedio=Avg('calificacion_tecnico')
            )['promedio'] or 0
        
        # Total de servicios realizados
        stats['total_servicios'] = ServicioOrden.objects.filter(
            orden__in=ordenes,
            tecnico_asignado=self
        ).count()
        
        # Comisión estimada
        if self.porcentaje_comision > 0:
            stats['comision_estimada'] = stats['total_facturado'] * (self.porcentaje_comision / 100)
        
        return stats
    
    def get_servicios_mes(self):
        """Alias para get_estadisticas_mes sin parámetros"""
        return self.get_estadisticas_mes()
    
    @property
    def esta_disponible(self):
        """Verificar si el técnico está disponible"""
        return self.estado == 'ACTIVO' and self.activo


# ================== MODELOS DE SERVICIOS ==================

class TipoServicio(models.Model):
    """Tipos de servicios ofrecidos en el taller"""
    NIVEL_DIFICULTAD_CHOICES = [
        ('BASICO', 'Básico'),
        ('INTERMEDIO', 'Intermedio'),
        ('AVANZADO', 'Avanzado'),
        ('EXPERTO', 'Experto'),
    ]
    
    # Información básica
    categoria = models.ForeignKey(
        CategoriaServicio, 
        on_delete=models.CASCADE, 
        related_name='tipos_servicio'
    )
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    
    # ✅ CAMBIO 1: Solo un campo de precio
    precio = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Precio total del servicio (sin IVA)"
    )
    
    # ❌ ELIMINAR ESTOS CAMPOS:
    # precio_base = models.DecimalField(...)
    # precio_mano_obra = models.DecimalField(...)
    # incluye_iva = models.BooleanField(...)  # Los servicios NO tienen IVA
    
    # Configuración
    activo = models.BooleanField(default=True)
    tiempo_estimado_horas = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        help_text="Tiempo estimado en horas"
    )
    requiere_repuestos = models.BooleanField(default=False)
    requiere_especialidad = models.ForeignKey(
        EspecialidadTecnica, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    nivel_dificultad = models.CharField(
        max_length=20, 
        choices=NIVEL_DIFICULTAD_CHOICES, 
        default='BASICO'
    )
    
    # Metadata
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Tipo de Servicio')
        verbose_name_plural = _('Tipos de Servicios')
        ordering = ['categoria__nombre', 'nombre']
    
    def __str__(self):
        return f"{self.categoria.nombre} - {self.nombre}"
    
    # ✅ CAMBIO 2: Simplificar método
    def get_precio_total(self):
        """Retorna el precio del servicio"""
        return self.precio
    
    # ❌ ELIMINAR ESTE MÉTODO:
    # def get_precio_con_iva(self):
    #     ...
    
    def puede_realizar_tecnico(self, tecnico):
        """Verifica si un técnico puede realizar este servicio"""
        if not self.requiere_especialidad:
            return True
        return self.requiere_especialidad in tecnico.especialidades.all()
    
    def get_tecnicos_calificados(self):
        """Obtiene técnicos calificados para este servicio"""
        if not self.requiere_especialidad:
            return Tecnico.objects.filter(estado='ACTIVO', activo=True)
        return Tecnico.objects.filter(
            estado='ACTIVO',
            activo=True,
            especialidades=self.requiere_especialidad
        )


# ================== MODELO PRINCIPAL: ORDEN DE TRABAJO ==================

class OrdenTrabajo(models.Model):
    """Órdenes de trabajo del taller"""
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En Proceso'),
        ('ESPERANDO_REPUESTOS', 'Esperando Repuestos'),
        ('ESPERANDO_APROBACION', 'Esperando Aprobación'),
        ('COMPLETADO', 'Completado'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    PRIORIDAD_CHOICES = [
        ('BAJA', 'Baja'),
        ('NORMAL', 'Normal'),
        ('ALTA', 'Alta'),
        ('URGENTE', 'Urgente'),
    ]
    
    NIVEL_COMBUSTIBLE_CHOICES = [
        ('VACIO', 'Vacío'),
        ('1/4', '1/4 de tanque'),
        ('1/2', '1/2 tanque'),
        ('3/4', '3/4 de tanque'),
        ('LLENO', 'Lleno'),
    ]
    
    # Información básica
    numero_orden = models.CharField(max_length=20, unique=True)
    cliente = models.ForeignKey(
        'clientes.Cliente', 
        on_delete=models.PROTECT, 
        related_name='ordenes_trabajo'
    )
    
    # Información de la motocicleta (como texto)
    moto_marca = models.CharField(max_length=100, verbose_name="Marca")
    moto_modelo = models.CharField(max_length=100, verbose_name="Modelo")
    moto_cilindraje = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Cilindraje"
    )
    moto_color = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Color"
    )
    moto_placa = models.CharField(max_length=20, verbose_name="Placa")
    moto_año = models.CharField(
        max_length=4,
        blank=True,
        null=True,
        verbose_name="Año"
    )
    
    # Asignación de técnicos
    tecnico_principal = models.ForeignKey(
        Tecnico, 
        on_delete=models.PROTECT, 
        related_name='ordenes_asignadas'
    )
    tecnicos_apoyo = models.ManyToManyField(
        Tecnico, 
        blank=True, 
        related_name='ordenes_apoyo'
    )
    
    # Fechas importantes
    fecha_ingreso = models.DateTimeField(auto_now_add=True)
    fecha_prometida = models.DateTimeField(blank=True, null=True)
    fecha_completado = models.DateTimeField(blank=True, null=True)
    fecha_entrega = models.DateTimeField(blank=True, null=True)
    
    # Detalles del servicio
    motivo_ingreso = models.TextField(
        help_text="Motivo por el que ingresa la moto"
    )
    diagnostico_inicial = models.TextField(blank=True, null=True)
    diagnostico_final = models.TextField(blank=True, null=True)
    trabajo_realizado = models.TextField(blank=True, null=True)
    observaciones_tecnico = models.TextField(blank=True, null=True)
    observaciones_cliente = models.TextField(blank=True, null=True)
    
    # Estado y prioridad
    estado = models.CharField(
        max_length=25, 
        choices=ESTADO_CHOICES, 
        default='PENDIENTE'
    )
    prioridad = models.CharField(
        max_length=20, 
        choices=PRIORIDAD_CHOICES, 
        default='NORMAL'
    )
    
    # Información técnica
    kilometraje_entrada = models.PositiveIntegerField(blank=True, null=True)
    kilometraje_salida = models.PositiveIntegerField(blank=True, null=True)
    nivel_combustible = models.CharField(
        max_length=20, 
        choices=NIVEL_COMBUSTIBLE_CHOICES, 
        blank=True, 
        null=True
    )
    
    # Precios y facturación
    precio_mano_obra = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    precio_repuestos = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    precio_total = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    anticipo = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    saldo_pendiente = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    
    # Control
    usuario_creacion = models.ForeignKey(
        'usuarios.Usuario', 
        on_delete=models.PROTECT, 
        related_name='ordenes_creadas'
    )
    facturado = models.BooleanField(default=False)
    venta = models.ForeignKey(
        'ventas.Venta', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    
    # Metadata
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Orden de Trabajo')
        verbose_name_plural = _('Órdenes de Trabajo')
        ordering = ['-fecha_ingreso']
        indexes = [
            models.Index(fields=['numero_orden']),
            models.Index(fields=['estado']),
            models.Index(fields=['fecha_ingreso']),
            models.Index(fields=['cliente']),
        ]
    
    def __str__(self):
        return f"{self.numero_orden} - {self.moto_placa} ({self.cliente.nombres})"
    
    def save(self, *args, **kwargs):
        # Generar número de orden si no existe
        if not self.numero_orden:
            self.numero_orden = self._generar_numero_orden()
        
        # Calcular saldo pendiente
        self.saldo_pendiente = self.precio_total - self.anticipo
        
        # Actualizar fechas según estado
        if self.estado == 'COMPLETADO' and not self.fecha_completado:
            self.fecha_completado = timezone.now()
        
        if self.estado == 'ENTREGADO' and not self.fecha_entrega:
            self.fecha_entrega = timezone.now()
        
        super().save(*args, **kwargs)
    
    def _generar_numero_orden(self):
        """Generar número de orden único"""
        año = timezone.now().year
        mes = timezone.now().month
        
        # Obtener el último número del mes
        ultima_orden = OrdenTrabajo.objects.filter(
            fecha_ingreso__year=año,
            fecha_ingreso__month=mes
        ).order_by('-numero_orden').first()
        
        if ultima_orden and ultima_orden.numero_orden.startswith(f"OT-{año}{mes:02d}"):
            # Extraer el número secuencial
            try:
                ultimo_numero = int(ultima_orden.numero_orden.split('-')[-1])
                siguiente_numero = ultimo_numero + 1
            except ValueError:
                siguiente_numero = 1
        else:
            siguiente_numero = 1
        
        return f"OT-{año}{mes:02d}-{siguiente_numero:04d}"
    
    def get_tiempo_transcurrido(self):
        """Obtiene el tiempo transcurrido desde el ingreso"""
        if self.fecha_completado:
            return self.fecha_completado - self.fecha_ingreso
        return timezone.now() - self.fecha_ingreso
    
    def get_dias_transcurridos(self):
        """Obtiene los días transcurridos"""
        tiempo = self.get_tiempo_transcurrido()
        return tiempo.days
    
    def actualizar_precios(self):
        """Actualiza los precios basado en servicios y repuestos"""
        # Calcular total de servicios
        servicios_total = self.servicios.aggregate(
            total=Sum('precio_servicio')
        )['total'] or Decimal('0.00')
        
        # Calcular total de repuestos
        repuestos_total = self.repuestos_utilizados.aggregate(
            total=Sum('subtotal')
        )['total'] or Decimal('0.00')
        
        # Actualizar precios
        self.precio_mano_obra = servicios_total
        self.precio_repuestos = repuestos_total
        self.precio_total = self.precio_mano_obra + self.precio_repuestos
        self.saldo_pendiente = self.precio_total - self.anticipo
        
        self.save(update_fields=[
            'precio_mano_obra', 'precio_repuestos', 
            'precio_total', 'saldo_pendiente'
        ])

    def puede_completarse(self):
        """Verifica si la orden puede marcarse como completada"""
        return (
            self.estado in ['PENDIENTE', 'EN_PROCESO'] and
            self.servicios.exists()
        )
    
    def puede_entregarse(self):
        """Verifica si la orden puede entregarse"""
        return (
            self.estado == 'COMPLETADO' and
            self.saldo_pendiente <= 0
        )
    
    def marcar_completada(self, usuario=None):
        """Marca la orden como completada"""
        if self.puede_completarse():
            self.estado = 'COMPLETADO'
            self.fecha_completado = timezone.now()
            self.save()
            
            # Crear seguimiento
            if usuario:
                SeguimientoOrden.objects.create(
                    orden=self,
                    usuario=usuario,
                    estado_anterior=self.estado,
                    estado_nuevo='COMPLETADO',
                    observaciones='Orden marcada como completada'
                )
            return True
        return False
    
    def marcar_entregada(self, usuario=None):
        """Marca la orden como entregada"""
        if self.puede_entregarse():
            self.estado = 'ENTREGADO'
            self.fecha_entrega = timezone.now()
            self.save()
            
            # Crear seguimiento
            if usuario:
                SeguimientoOrden.objects.create(
                    orden=self,
                    usuario=usuario,
                    estado_anterior='COMPLETADO',
                    estado_nuevo='ENTREGADO',
                    observaciones='Orden entregada al cliente'
                )
            return True
        return False
    
    def get_resumen_moto(self):
        """Obtiene un resumen de la información de la moto"""
        partes = [self.moto_marca, self.moto_modelo]
        if self.moto_cilindraje:
            partes.append(self.moto_cilindraje)
        return ' '.join(partes)
    
    def get_color_prioridad(self):
        """Retorna el color según la prioridad"""
        colores = {
            'BAJA': '#28a745',      # Verde
            'NORMAL': '#17a2b8',    # Azul
            'ALTA': '#ffc107',      # Amarillo
            'URGENTE': '#dc3545',   # Rojo
        }
        return colores.get(self.prioridad, '#6c757d')
    
    def get_porcentaje_completado(self):
        """Calcula el porcentaje de servicios completados"""
        total_servicios = self.servicios.count()
        if total_servicios == 0:
            return 0
        
        servicios_completados = self.servicios.filter(completado=True).count()
        return int((servicios_completados / total_servicios) * 100)


# ================== MODELOS RELACIONADOS CON ORDENES ==================

class ServicioOrden(models.Model):
    """Servicios específicos incluidos en una orden de trabajo"""
    orden = models.ForeignKey(
        OrdenTrabajo, 
        on_delete=models.CASCADE, 
        related_name='servicios'
    )
    tipo_servicio = models.ForeignKey(
        TipoServicio, 
        on_delete=models.PROTECT
    )
    tecnico_asignado = models.ForeignKey(
        Tecnico, 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True
    )
    
    # ✅ CAMBIO 3: Solo un campo de precio
    precio_servicio = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Precio del servicio en esta orden"
    )
    
    # ❌ ELIMINAR ESTOS CAMPOS:
    # precio_base = models.DecimalField(...)
    # precio_mano_obra = models.DecimalField(...)
    # precio_total = models.DecimalField(...)
    
    # Control de tiempo
    tiempo_estimado = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        help_text="Tiempo estimado en horas"
    )
    tiempo_real = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        blank=True, 
        null=True, 
        help_text="Tiempo real empleado"
    )
    fecha_inicio = models.DateTimeField(blank=True, null=True)
    fecha_fin = models.DateTimeField(blank=True, null=True)
    
    # Estado del servicio
    completado = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, null=True)
    requiere_aprobacion = models.BooleanField(default=False)
    aprobado_cliente = models.BooleanField(default=True)
    
    # Metadata
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Servicio de Orden')
        verbose_name_plural = _('Servicios de Orden')
        ordering = ['tipo_servicio__nombre']
    
    def __str__(self):
        return f"{self.orden.numero_orden} - {self.tipo_servicio.nombre}"
    
    # ✅ CAMBIO 4: Simplificar método save
    def save(self, *args, **kwargs):
        # Establecer precio por defecto si no está definido
        if not self.precio_servicio:
            self.precio_servicio = self.tipo_servicio.precio
        
        if not self.tiempo_estimado:
            self.tiempo_estimado = self.tipo_servicio.tiempo_estimado_horas
        
        # Si no hay técnico asignado, usar el principal
        if not self.tecnico_asignado:
            self.tecnico_asignado = self.orden.tecnico_principal
        
        super().save(*args, **kwargs)
        
        # Actualizar precios de la orden
        self.orden.actualizar_precios()
    
    def iniciar_servicio(self):
        """Marca el inicio del servicio"""
        if not self.fecha_inicio:
            self.fecha_inicio = timezone.now()
            self.save()
            return True
        return False
    
    def finalizar_servicio(self):
        """Marca el fin del servicio"""
        if self.fecha_inicio and not self.fecha_fin:
            self.fecha_fin = timezone.now()
            self.completado = True
            
            # Calcular tiempo real
            tiempo_transcurrido = self.fecha_fin - self.fecha_inicio
            self.tiempo_real = Decimal(tiempo_transcurrido.total_seconds() / 3600)
            
            self.save()
            return True
        return False


class RepuestoOrden(models.Model):
    """Repuestos utilizados en una orden de trabajo"""
    orden = models.ForeignKey(
        OrdenTrabajo, 
        on_delete=models.CASCADE, 
        related_name='repuestos_utilizados'
    )
    producto = models.ForeignKey(
        'inventario.Producto', 
        on_delete=models.PROTECT
    )
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    servicio_asociado = models.ForeignKey(
        ServicioOrden, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    observaciones = models.TextField(blank=True, null=True)
    
    # Metadata
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Repuesto de Orden')
        verbose_name_plural = _('Repuestos de Orden')
        ordering = ['producto__nombre']
    
    def __str__(self):
        return f"{self.orden.numero_orden} - {self.producto.nombre} x{self.cantidad}"
    
    def save(self, *args, **kwargs):
        # Calcular subtotal
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)
        
        # Actualizar precios de la orden
        self.orden.actualizar_precios()
    
    def get_subtotal_con_iva(self):
        """Calcula el subtotal con IVA"""
        return self.subtotal * Decimal('1.15')  # 15% IVA


class SeguimientoOrden(models.Model):
    """Seguimiento de cambios en las órdenes de trabajo"""
    orden = models.ForeignKey(
        OrdenTrabajo, 
        on_delete=models.CASCADE, 
        related_name='seguimientos'
    )
    usuario = models.ForeignKey(
        'usuarios.Usuario', 
        on_delete=models.PROTECT
    )
    fecha_hora = models.DateTimeField(auto_now_add=True)
    estado_anterior = models.CharField(
        max_length=25, 
        choices=OrdenTrabajo.ESTADO_CHOICES, 
        blank=True, 
        null=True
    )
    estado_nuevo = models.CharField(
        max_length=25, 
        choices=OrdenTrabajo.ESTADO_CHOICES
    )
    observaciones = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = _('Seguimiento de Orden')
        verbose_name_plural = _('Seguimientos de Órdenes')
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.orden.numero_orden} - {self.estado_nuevo} ({self.fecha_hora.strftime('%d/%m/%Y %H:%M')})"


# ================== MODELOS DE CITAS Y EVALUACIONES ==================

class CitaTaller(models.Model):
    """Citas programadas para el taller"""
    ESTADO_CHOICES = [
        ('PROGRAMADA', 'Programada'),
        ('CONFIRMADA', 'Confirmada'),
        ('EN_CURSO', 'En Curso'),
        ('COMPLETADA', 'Completada'),
        ('CANCELADA', 'Cancelada'),
        ('NO_ASISTIO', 'No Asistió'),
    ]
    
    cliente = models.ForeignKey(
        'clientes.Cliente', 
        on_delete=models.CASCADE, 
        related_name='citas_taller'
    )
    moto_descripcion = models.CharField(
        max_length=200,
        blank=True,  # CORREGIDO: Permitir valores en blanco
        null=True,   # CORREGIDO: Permitir valores nulos
        help_text="Marca, modelo y placa de la moto"
    )
    tecnico_preferido = models.ForeignKey(
        Tecnico, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    
    fecha_hora = models.DateTimeField()
    duracion_estimada = models.PositiveIntegerField(
        default=60, 
        help_text="Duración estimada en minutos"
    )
    
    motivo = models.TextField(help_text="Motivo de la cita")
    observaciones = models.TextField(blank=True, null=True)
    
    estado = models.CharField(
        max_length=20, 
        choices=ESTADO_CHOICES, 
        default='PROGRAMADA'
    )
    
    # Recordatorios
    recordatorio_enviado = models.BooleanField(default=False)
    fecha_recordatorio = models.DateTimeField(blank=True, null=True)
    
    # Control
    usuario_creacion = models.ForeignKey(
        'usuarios.Usuario', 
        on_delete=models.PROTECT
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    orden_trabajo = models.OneToOneField(
        OrdenTrabajo, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    
    class Meta:
        verbose_name = _('Cita de Taller')
        verbose_name_plural = _('Citas de Taller')
        ordering = ['fecha_hora']
    
    def __str__(self):
        return f"{self.cliente.nombres} - {self.fecha_hora.strftime('%d/%m/%Y %H:%M')}"
    
    def puede_crear_orden(self):
        """Verifica si se puede crear una orden de trabajo desde esta cita"""
        return (
            self.estado in ['CONFIRMADA', 'EN_CURSO'] and 
            not self.orden_trabajo
        )
    
    def esta_proxima(self):
        """Verifica si la cita está próxima (dentro de 24 horas)"""
        ahora = timezone.now()
        return (
            self.fecha_hora > ahora and 
            self.fecha_hora <= ahora + timedelta(hours=24)
        )
    
    def enviar_recordatorio(self):
        """Marca que se envió el recordatorio"""
        self.recordatorio_enviado = True
        self.fecha_recordatorio = timezone.now()
        self.save()


class EvaluacionServicio(models.Model):
    """Evaluaciones de servicio por parte de los clientes"""
    orden = models.OneToOneField(
        OrdenTrabajo, 
        on_delete=models.CASCADE, 
        related_name='evaluacion'
    )
    
    # Calificaciones
    calificacion_general = models.PositiveIntegerField(
        choices=[(i, i) for i in range(1, 6)], 
        help_text="Calificación de 1 a 5"
    )
    calificacion_tecnico = models.PositiveIntegerField(
        choices=[(i, i) for i in range(1, 6)], 
        blank=True, 
        null=True
    )
    calificacion_tiempo = models.PositiveIntegerField(
        choices=[(i, i) for i in range(1, 6)], 
        blank=True, 
        null=True
    )
    calificacion_precio = models.PositiveIntegerField(
        choices=[(i, i) for i in range(1, 6)], 
        blank=True, 
        null=True
    )
    
    comentarios = models.TextField(blank=True, null=True)
    recomendaria = models.BooleanField(default=True)
    
    fecha_evaluacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('Evaluación de Servicio')
        verbose_name_plural = _('Evaluaciones de Servicio')
        ordering = ['-fecha_evaluacion']
    
    def __str__(self):
        return f"{self.orden.numero_orden} - {self.calificacion_general} estrellas"
    
    def get_promedio_calificacion(self):
        """Calcula el promedio de todas las calificaciones"""
        calificaciones = [self.calificacion_general]
        
        if self.calificacion_tecnico:
            calificaciones.append(self.calificacion_tecnico)
        if self.calificacion_tiempo:
            calificaciones.append(self.calificacion_tiempo)
        if self.calificacion_precio:
            calificaciones.append(self.calificacion_precio)
        
        return sum(calificaciones) / len(calificaciones)
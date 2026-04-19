from django.db import models
from django.core.validators import FileExtensionValidator
from django.conf import settings
from cryptography.fernet import Fernet
import hashlib
import uuid
import base64

class SRIConfig(models.Model):
    """Configuración global para la facturación electrónica SRI Ecuador"""
    AMBIENTE_CHOICES = [
        (1, 'Pruebas'),
        (2, 'Producción'),
    ]
    EMISION_CHOICES = [
        (1, 'Emisión Normal'),
    ]

    ambiente = models.IntegerField(choices=AMBIENTE_CHOICES, default=1)
    tipo_emision = models.IntegerField(choices=EMISION_CHOICES, default=1)
    
    # Datos de la Empresa (matriz)
    ruc = models.CharField(max_length=13, help_text="RUC de la empresa (13 dígitos)")
    razon_social = models.CharField(max_length=300)
    nombre_comercial = models.CharField(max_length=300, blank=True, null=True)
    direccion_matriz = models.TextField()
    obligado_contabilidad = models.BooleanField(default=True)
    
    # Configuración de resolución (si aplica)
    contribuyente_especial = models.CharField(max_length=20, blank=True, null=True)
    agente_retencion = models.CharField(max_length=20, blank=True, null=True)
    regimen_microempresas = models.BooleanField(default=False)
    regimen_rimpe = models.BooleanField(default=False)

    # URLs Web Services SRI
    wsdl_recepcion_pruebas = models.URLField(
        default="https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl",
        help_text="URL WSDL Recepción (Pruebas)"
    )
    wsdl_autorizacion_pruebas = models.URLField(
        default="https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl",
        help_text="URL WSDL Autorización (Pruebas)"
    )
    wsdl_recepcion_produccion = models.URLField(
        default="https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl",
        help_text="URL WSDL Recepción (Producción)"
    )
    wsdl_autorizacion_produccion = models.URLField(
        default="https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl",
        help_text="URL WSDL Autorización (Producción)"
    )

    class Meta:
        verbose_name = "Configuración SRI"
        verbose_name_plural = "Configuraciones SRI"

    def __str__(self):
        return f"Configuración SRI - {self.get_ambiente_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1  # Singleton
        super().save(*args, **kwargs)

class PuntoEmision(models.Model):
    """Configuración de establecimientos y puntos de emisión"""
    establecimiento = models.CharField(max_length=3, help_text="Ej: 001")
    punto_emision = models.CharField(max_length=3, help_text="Ej: 001")
    direccion_establecimiento = models.TextField()
    ultimo_secuencial = models.IntegerField(default=0, help_text="El próximo comprobante será este número + 1")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Punto de Emisión"
        verbose_name_plural = "Puntos de Emisión"
        unique_together = ['establecimiento', 'punto_emision']

    def __str__(self):
        return f"{self.establecimiento}-{self.punto_emision}"

class CertificadoDigital(models.Model):
    """Almacenamiento de la firma electrónica (.p12)"""
    archivo = models.FileField(
        upload_to='sri/certificados/',
        validators=[FileExtensionValidator(allowed_extensions=['p12'])]
    )
    password_encrypted = models.CharField(max_length=500, verbose_name="Password (Encriptado)")
    
    # Metadata extraída del certificado
    nombre_titular = models.CharField(max_length=300, null=True, blank=True)
    ruc_titular = models.CharField(max_length=13, null=True, blank=True)
    emisor = models.CharField(max_length=300, null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    
    activo = models.BooleanField(default=True)
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Certificado Digital"
        verbose_name_plural = "Certificados Digitales"

    def __str__(self):
        return f"Certificado - {self.fecha_carga.strftime('%Y-%m-%d')}"

    def _get_cipher(self):
        # Derivamos una llave de 32 bytes (256 bits) para Fernet usando el SECRET_KEY de Django
        h = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(h)
        return Fernet(key)

    def set_password(self, raw_password):
        """Encripta y guarda la contraseña"""
        cipher = self._get_cipher()
        encrypted = cipher.encrypt(raw_password.encode())
        self.password_encrypted = base64.b64encode(encrypted).decode()

    def get_password(self):
        """Desencripta y retorna la contraseña en texto plano"""
        try:
            cipher = self._get_cipher()
            encrypted = base64.b64decode(self.password_encrypted.encode())
            return cipher.decrypt(encrypted).decode()
        except Exception as e:
            return None

class ComprobanteElectronico(models.Model):
    """Registro de cada comprobante electrónico generado y enviado"""
    ESTADO_CHOICES = [
        ('CREADO', 'Creado (Pendiente Firma)'),
        ('FIRMADO', 'Firmado (Pendiente Envío)'),
        ('RECIBIDO', 'Recibido por SRI'),
        ('DEVUELTO', 'Devuelto por SRI (Error)'),
        ('AUTORIZADO', 'Autorizado'),
        ('RECHAZADO', 'Rechazado'),
        ('ERROR', 'Error Interno'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venta = models.OneToOneField(
        'ventas.Venta',
        on_delete=models.CASCADE,
        related_name='comprobante_electronico'
    )
    punto_emision = models.ForeignKey(PuntoEmision, on_delete=models.PROTECT, null=True, blank=True)
    
    tipo_comprobante = models.CharField(max_length=2, default='01', help_text="01=Factura, 04=Nota de Crédito, etc.")
    clave_acceso = models.CharField(max_length=49, unique=True, null=True, blank=True)
    numero_autorizacion = models.CharField(max_length=49, null=True, blank=True)
    fecha_autorizacion = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='CREADO')
    ambiente = models.IntegerField(choices=SRIConfig.AMBIENTE_CHOICES, default=1)
    
    # Archivos y Datos XML
    xml_generado = models.TextField(null=True, blank=True)
    xml_firmado = models.TextField(null=True, blank=True)
    xml_autorizado = models.TextField(null=True, blank=True)
    pdf_ride = models.FileField(upload_to='sri/rides/', null=True, blank=True)
    
    # Tracking
    mensajes_error = models.TextField(null=True, blank=True)
    
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Comprobante Electrónico"
        verbose_name_plural = "Comprobantes Electrónicos"
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.tipo_comprobante} - {self.venta.numero_factura} ({self.estado})"

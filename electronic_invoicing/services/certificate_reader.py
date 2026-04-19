import logging
import re
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from cryptography import x509

logger = logging.getLogger(__name__)

class CertificateReaderSRI:
    """
    Servicio robusto para extraer metadata de certificados electrónicos (.p12) 
    compatible con múltiples entidades certificadoras de Ecuador.
    """

    # OIDs comunes en certificados de Ecuador
    OID_RUC_SECURITY_DATA = "1.3.6.1.4.1.37442.2.1.1"
    OID_CEDULA_SECURITY_DATA = "1.3.6.1.4.1.37442.2.1.2"
    OID_UID = "0.9.2342.19200300.100.1.1"

    @staticmethod
    def extraer_metadata(p12_content, password):
        """
        Extrae la información relevante de un archivo PKCS12 con búsqueda multi-campo.
        """
        try:
            # 1. Cargar el archivo P12
            _, cert, _ = pkcs12.load_key_and_certificates(
                p12_content, 
                password.encode()
            )

            if not cert:
                raise ValueError("No se encontró un certificado válido.")

            # 2. Extraer Atributos del Sujeto
            subject = cert.subject
            
            # --- NOMBRE DEL TITULAR ---
            nombre_titular = None
            cn_attr = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if cn_attr:
                nombre_titular = cn_attr[0].value
            
            # --- RUC (Búsqueda Multi-Campo) ---
            ruc_titular = None
            
            # Intento 1: OID Estándar Serial Number (2.5.4.5)
            serial_attr = subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
            if serial_attr:
                ruc_titular = serial_attr[0].value
            
            # Intento 2: UID (Común en ANF y Banco Central)
            if not ruc_titular:
                uid_attr = subject.get_attributes_for_oid(x509.ObjectIdentifier(CertificateReaderSRI.OID_UID))
                if uid_attr:
                    ruc_titular = uid_attr[0].value
            
            # Intento 3: OID específico de Security Data
            if not ruc_titular:
                sd_ruc_attr = subject.get_attributes_for_oid(x509.ObjectIdentifier(CertificateReaderSRI.OID_RUC_SECURITY_DATA))
                if sd_ruc_attr:
                    ruc_titular = sd_ruc_attr[0].value

            # --- SANITIZACIÓN DEL RUC ---
            if ruc_titular:
                # Algunas entidades ponen "RUC:" o "IDG:" como prefijo
                ruc_titular = re.sub(r'[^0-9]', '', str(ruc_titular))
                # El RUC debe ser de 13 dígitos. Si tiene más (e.g. Cédula + algo), truncamos o validamos.
                if len(ruc_titular) > 13:
                    ruc_titular = ruc_titular[:13]

            # --- EMISOR ---
            issuer = cert.issuer
            issuer_cn = issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
            emisor = issuer_cn[0].value if issuer_cn else "Entidad Certificadora"

            # --- FECHA DE VENCIMIENTO ---
            try:
                fecha_vencimiento = cert.not_valid_after_utc.date()
            except AttributeError:
                fecha_vencimiento = cert.not_valid_after.date()

            logger.info(f"Metadata extraída: {nombre_titular} (RUC: {ruc_titular})")

            return {
                'nombre_titular': nombre_titular or "Desconocido",
                'ruc_titular': ruc_titular,
                'emisor': emisor,
                'fecha_vencimiento': fecha_vencimiento
            }

        except Exception as e:
            logger.error(f"Error al leer el certificado: {str(e)}")
            raise ValueError(f"Falla de lectura (Posible clave incorrecta o formato no soportado): {str(e)}")

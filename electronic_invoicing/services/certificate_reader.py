import logging
import re
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from cryptography import x509

logger = logging.getLogger(__name__)


class CertificateReaderSRI:
    """
    Extrae metadata de certificados electrónicos (.p12) de Ecuador,
    distinguiendo correctamente certificados de EMPRESA (persona jurídica)
    de los de persona natural.

    En un certificado de empresa, el SUJETO contiene DOS identidades:
      - El representante legal (CN / givenName / surname / cédula).
      - La empresa (organizationName + organizationIdentifier con el RUC).
    El comprobante electrónico debe emitirse con el RUC y la razón social de
    la EMPRESA, no con los datos de la persona.
    """

    # OIDs estándar X.509
    OID_ORG_NAME = "2.5.4.10"          # organizationName  -> Razón social (empresa)
    OID_ORG_IDENTIFIER = "2.5.4.97"    # organizationIdentifier -> RUC empresa (p.ej. VATEC-1793...)
    OID_SERIAL_NUMBER = "2.5.4.5"      # serialNumber -> cédula/RUC del titular
    OID_TITLE = "2.5.4.12"             # title -> cargo (GERENTE GENERAL, etc.)
    OID_GIVEN_NAME = "2.5.4.42"
    OID_SURNAME = "2.5.4.4"

    # OIDs propietarios comunes en Ecuador
    OID_UID = "0.9.2342.19200300.100.1.1"
    OID_RUC_SECURITY_DATA = "1.3.6.1.4.1.37442.2.1.1"
    OID_CEDULA_SECURITY_DATA = "1.3.6.1.4.1.37442.2.1.2"
    # UANATACA (SubjectAlternativeName OtherName)
    OID_UANATACA_RUC_EMPRESA = "1.3.6.1.4.1.47286.102.3.11"
    OID_UANATACA_RAZON_SOCIAL = "1.3.6.1.4.1.47286.102.3.10"

    @staticmethod
    def _solo_digitos(valor):
        return re.sub(r'[^0-9]', '', str(valor or ''))

    @staticmethod
    def _primer_valor(subject, oid_dotted):
        try:
            attrs = subject.get_attributes_for_oid(x509.ObjectIdentifier(oid_dotted))
            return attrs[0].value if attrs else None
        except Exception:
            return None

    @staticmethod
    def _san_othername(cert, oid_dotted):
        """Lee un OtherName del SubjectAlternativeName (DER UTF8String) por OID."""
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            for g in san:
                if isinstance(g, x509.OtherName) and g.type_id.dotted_string == oid_dotted:
                    raw = g.value
                    # OtherName viene como TLV DER; UTF8String = tag 0x0c.
                    if isinstance(raw, (bytes, bytearray)) and len(raw) >= 2 and raw[0] == 0x0c:
                        return raw[2:].decode('utf-8', errors='ignore')
                    if isinstance(raw, (bytes, bytearray)):
                        return raw.decode('utf-8', errors='ignore')
                    return str(raw)
        except Exception:
            pass
        return None

    @classmethod
    def extraer_metadata(cls, p12_content, password):
        """
        Devuelve:
          ruc_titular    -> RUC a usar para emitir (EMPRESA si es jurídica, 13 díg.)
          razon_social   -> Razón social de la empresa (o nombre de la persona)
          nombre_titular -> Igual que razon_social (compat. hacia atrás)
          representante  -> Nombre del representante legal (persona)
          es_empresa     -> bool
          emisor, fecha_vencimiento
        """
        try:
            _, cert, _ = pkcs12.load_key_and_certificates(p12_content, password.encode())
            if not cert:
                raise ValueError("No se encontró un certificado válido.")

            subject = cert.subject

            # --- Datos de la persona (representante / titular natural) ---
            cn = cls._primer_valor(subject, "2.5.4.3")
            given = cls._primer_valor(subject, cls.OID_GIVEN_NAME)
            surname = cls._primer_valor(subject, cls.OID_SURNAME)
            representante = cn or (f"{given} {surname}".strip() if (given or surname) else None)
            cargo = cls._primer_valor(subject, cls.OID_TITLE)
            # Cédula del representante (serialNumber: p.ej. 'IDCEC-1716516750')
            cedula = cls._solo_digitos(cls._primer_valor(subject, cls.OID_SERIAL_NUMBER))
            if len(cedula) > 10:
                cedula = cedula[:10]

            # --- ¿Es un certificado de EMPRESA? (tiene organizationName) ---
            org_name = cls._primer_valor(subject, cls.OID_ORG_NAME)
            org_name_san = cls._san_othername(cert, cls.OID_UANATACA_RAZON_SOCIAL)
            razon_social_empresa = org_name or org_name_san

            # --- RUC de la EMPRESA ---
            ruc_empresa = None
            # 1) organizationIdentifier estándar (p.ej. 'VATEC-1793242935001')
            org_id = cls._primer_valor(subject, cls.OID_ORG_IDENTIFIER)
            if org_id:
                d = cls._solo_digitos(org_id)
                if len(d) >= 13:
                    ruc_empresa = d[-13:]
            # 2) SAN propietario UANATACA
            if not ruc_empresa:
                d = cls._solo_digitos(cls._san_othername(cert, cls.OID_UANATACA_RUC_EMPRESA))
                if len(d) >= 13:
                    ruc_empresa = d[-13:]
            # 3) OID Security Data
            if not ruc_empresa:
                d = cls._solo_digitos(cls._primer_valor(subject, cls.OID_RUC_SECURITY_DATA))
                if len(d) >= 13:
                    ruc_empresa = d[-13:]

            # --- RUC/identificación del titular natural (fallback) ---
            ruc_persona = None
            for oid in (cls.OID_SERIAL_NUMBER, cls.OID_UID, cls.OID_RUC_SECURITY_DATA):
                d = cls._solo_digitos(cls._primer_valor(subject, oid))
                if d:
                    if len(d) == 10:        # cédula -> RUC persona natural
                        ruc_persona = d + '001'
                    elif len(d) >= 13:
                        ruc_persona = d[-13:]
                    else:
                        ruc_persona = d
                    break

            es_empresa = bool(razon_social_empresa and ruc_empresa)

            if es_empresa:
                ruc_titular = ruc_empresa
                razon_social = razon_social_empresa
            else:
                ruc_titular = ruc_persona
                razon_social = representante or "Desconocido"

            # --- Emisor y vencimiento ---
            issuer_cn = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
            emisor = issuer_cn[0].value if issuer_cn else "Entidad Certificadora"
            try:
                fecha_vencimiento = cert.not_valid_after_utc.date()
            except AttributeError:
                fecha_vencimiento = cert.not_valid_after.date()

            logger.info(
                "Cert leído: %s (empresa=%s, RUC=%s, rep=%s)",
                razon_social, es_empresa, ruc_titular, representante,
            )

            return {
                'ruc_titular': ruc_titular,
                'razon_social': razon_social,
                'nombre_titular': razon_social,   # compat. hacia atrás
                'representante': representante,
                'cargo': cargo,
                'cedula': cedula or None,
                'es_empresa': es_empresa,
                'emisor': emisor,
                'fecha_vencimiento': fecha_vencimiento,
            }

        except Exception as e:
            logger.error(f"Error al leer el certificado: {str(e)}")
            raise ValueError(
                f"Falla de lectura (Posible clave incorrecta o formato no soportado): {str(e)}"
            )

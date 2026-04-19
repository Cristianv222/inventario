import copy
import logging
import uuid
import base64
import hashlib
from datetime import datetime, timezone
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding

logger = logging.getLogger(__name__)


class SignatureServiceSRI:
    """
    Firma XAdES-BES compatible con SRI Ecuador.

    Correcciones aplicadas:
    1. IssuerSerial incluye OID 2.5.4.97 (ORGANIZATIONIDENTIFIER) necesario
       para certificados UANATACA — sin él el SRI dice "certificado no válido".
    2. Digest del comprobante calculado DESPUÉS de root.append(signature),
       sobre una copia sin el nodo <Signature>, para que los namespaces
       propagados por lxml ya estén presentes (igual que en la verificación SRI).
    3. C14N inclusivo (REC-xml-c14n-20010315) en todos los nodos — consistente
       con el CanonicalizationMethod declarado en SignedInfo.
    """

    def __init__(self, certificado_obj):
        self.certificado_obj = certificado_obj

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _canonicalize(self, element) -> bytes:
        """C14N inclusivo sin comentarios (coincide con REC-xml-c14n-20010315)."""
        return etree.tostring(element, method="c14n", exclusive=False, with_comments=False)

    def _sha256_base64(self, data: bytes) -> str:
        return base64.b64encode(hashlib.sha256(data).digest()).decode()

    def _build_issuer_string(self, name) -> str:
        """
        Construye el DN del emisor en el orden y formato que el SRI espera.
        Incluye OID 2.5.4.97 (organizationIdentifier) requerido por UANATACA.
        El orden sigue la secuencia del certificado (no invertido como rfc4514).
        """
        # Mapa OID → etiqueta legible
        oid_labels = {
            "2.5.4.3":               "CN",
            "2.5.4.4":               "SN",
            "2.5.4.5":               "SERIALNUMBER",
            "2.5.4.6":               "C",
            "2.5.4.7":               "L",
            "2.5.4.8":               "ST",
            "2.5.4.9":               "STREET",
            "2.5.4.10":              "O",
            "2.5.4.11":              "OU",
            "2.5.4.97":              "2.5.4.97",   # organizationIdentifier — clave para UANATACA
            "1.2.840.113549.1.9.1":  "E",
        }
        parts = []
        for rdn in name.rdns:
            for attr in rdn:
                oid_str = attr.oid.dotted_string
                label   = oid_labels.get(oid_str)
                if label is None:
                    continue  # omitir OIDs desconocidos
                parts.append(f"{label}={attr.value}")
        return ", ".join(parts)

    # ── Firma principal ───────────────────────────────────────────────────────

    def firmar_xml(self, xml_content: bytes) -> bytes:
        try:
            # 1. Cargar certificado .p12
            if not self.certificado_obj or not hasattr(self.certificado_obj, 'archivo'):
                raise ValueError("Objeto de certificado inválido.")
            p12_content = self.certificado_obj.archivo.read()
            password    = self.certificado_obj.get_password()
            if not password:
                raise ValueError("No se pudo recuperar la contraseña del certificado.")

            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                p12_content, password.encode()
            )

            # 2. Parsear XML
            parser = etree.XMLParser(remove_blank_text=True)
            root   = etree.fromstring(xml_content, parser)
            root.set("id", "comprobante")   # asegurar atributo id en minúscula

            # 3. IDs y constantes
            sig_id          = f"Signature{uuid.uuid4().hex[:8]}"
            key_info_id     = f"KeyInfo{uuid.uuid4().hex[:8]}"
            signed_props_id = f"SignedProperties{uuid.uuid4().hex[:8]}"
            cert_b64        = base64.b64encode(certificate.public_bytes(Encoding.DER)).decode()
            signing_time    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            NS_DS    = "http://www.w3.org/2000/09/xmldsig#"
            NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"
            ns_map   = {"ds": NS_DS, "xades": NS_XADES}

            # 4. Construir estructura <Signature> ─────────────────────────────
            signature = etree.Element(f"{{{NS_DS}}}Signature", nsmap=ns_map)
            signature.set("Id", sig_id)

            # SignedInfo
            signed_info = etree.SubElement(signature, f"{{{NS_DS}}}SignedInfo")
            etree.SubElement(
                signed_info, f"{{{NS_DS}}}CanonicalizationMethod",
                Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
            )
            etree.SubElement(
                signed_info, f"{{{NS_DS}}}SignatureMethod",
                Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
            )

            # Ref 1 — comprobante (digest se llena en paso 6)
            ref_comp = etree.SubElement(signed_info, f"{{{NS_DS}}}Reference",
                                        URI="#comprobante")
            transforms = etree.SubElement(ref_comp, f"{{{NS_DS}}}Transforms")
            etree.SubElement(
                transforms, f"{{{NS_DS}}}Transform",
                Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"
            )
            etree.SubElement(ref_comp, f"{{{NS_DS}}}DigestMethod",
                             Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            digest_comp_elem = etree.SubElement(ref_comp, f"{{{NS_DS}}}DigestValue")
            digest_comp_elem.text = "PLACEHOLDER"

            # Ref 2 — KeyInfo (digest se llena después de construir KeyInfo)
            ref_ki = etree.SubElement(signed_info, f"{{{NS_DS}}}Reference",
                                      URI=f"#{key_info_id}")
            etree.SubElement(ref_ki, f"{{{NS_DS}}}DigestMethod",
                             Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            digest_ki_elem = etree.SubElement(ref_ki, f"{{{NS_DS}}}DigestValue")

            # Ref 3 — SignedProperties (digest se llena después)
            ref_sp = etree.SubElement(
                signed_info, f"{{{NS_DS}}}Reference",
                Type="http://uri.etsi.org/01903#SignedProperties",
                URI=f"#{signed_props_id}"
            )
            etree.SubElement(ref_sp, f"{{{NS_DS}}}DigestMethod",
                             Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            digest_sp_elem = etree.SubElement(ref_sp, f"{{{NS_DS}}}DigestValue")

            # SignatureValue — placeholder
            sig_value_elem = etree.SubElement(signature, f"{{{NS_DS}}}SignatureValue")

            # KeyInfo
            key_info  = etree.SubElement(signature, f"{{{NS_DS}}}KeyInfo")
            key_info.set("Id", key_info_id)
            x509_data = etree.SubElement(key_info, f"{{{NS_DS}}}X509Data")
            etree.SubElement(x509_data, f"{{{NS_DS}}}X509Certificate").text = cert_b64
            # Digest KeyInfo ya está completo
            digest_ki_elem.text = self._sha256_base64(self._canonicalize(key_info))

            # XAdES Object
            ds_object  = etree.SubElement(signature, f"{{{NS_DS}}}Object")
            qualifying = etree.SubElement(
                ds_object, f"{{{NS_XADES}}}QualifyingProperties",
                Target=f"#{sig_id}"
            )
            signed_props = etree.SubElement(
                qualifying, f"{{{NS_XADES}}}SignedProperties"
            )
            signed_props.set("Id", signed_props_id)

            sig_sig_props = etree.SubElement(
                signed_props, f"{{{NS_XADES}}}SignedSignatureProperties"
            )
            etree.SubElement(sig_sig_props, f"{{{NS_XADES}}}SigningTime").text = signing_time

            signing_cert_node = etree.SubElement(
                sig_sig_props, f"{{{NS_XADES}}}SigningCertificate"
            )
            cert_node   = etree.SubElement(signing_cert_node, f"{{{NS_XADES}}}Cert")
            cert_digest = etree.SubElement(cert_node, f"{{{NS_XADES}}}CertDigest")
            etree.SubElement(cert_digest, f"{{{NS_DS}}}DigestMethod",
                             Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            etree.SubElement(cert_digest, f"{{{NS_DS}}}DigestValue").text = \
                self._sha256_base64(certificate.public_bytes(Encoding.DER))

            issuer_serial = etree.SubElement(cert_node, f"{{{NS_XADES}}}IssuerSerial")
            # ✅ FIX CRÍTICO: incluir 2.5.4.97 (ORGANIZATIONIDENTIFIER) para UANATACA
            etree.SubElement(issuer_serial, f"{{{NS_DS}}}X509IssuerName").text = \
                self._build_issuer_string(certificate.issuer)
            etree.SubElement(issuer_serial, f"{{{NS_DS}}}X509SerialNumber").text = \
                str(certificate.serial_number)

            # Digest SignedProperties ya está completo
            digest_sp_elem.text = self._sha256_base64(self._canonicalize(signed_props))

            # 5. Insertar firma en el árbol
            root.append(signature)

            # 6. ✅ FIX CRÍTICO: calcular digest del comprobante DESPUÉS del append
            # Copia profunda sin <Signature> = equivale al transform enveloped-signature
            # Los namespaces propagados por lxml ya están presentes → digest correcto
            root_copy = copy.deepcopy(root)
            sig_node  = root_copy.find(f"{{{NS_DS}}}Signature")
            if sig_node is not None:
                root_copy.remove(sig_node)
            digest_comp_elem.text = self._sha256_base64(self._canonicalize(root_copy))

            # 7. Firmar SignedInfo con el digest correcto ya puesto
            signed_info_node = root.find(f"{{{NS_DS}}}Signature/{{{NS_DS}}}SignedInfo")
            signed_info_c14n = self._canonicalize(signed_info_node)
            raw_sig = private_key.sign(
                signed_info_c14n,
                asymmetric_padding.PKCS1v15(),
                hashes.SHA256()
            )
            sig_value_elem.text = base64.b64encode(raw_sig).decode()

            # 8. Serializar
            result = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                    pretty_print=False)
            return result

        except Exception as e:
            logger.error(f"Fallo en firma XAdES-BES manual: {str(e)}")
            raise
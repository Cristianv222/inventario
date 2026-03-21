# apps/hardware_integration/printers/ticket_printer.py
import logging
from django.conf import settings
from django.utils import timezone as tz

logger = logging.getLogger(__name__)

ANCHO = 48  # igual que printer_service.py que funciona bien


def get_sucursal():
    try:
        from core.models import Sucursal
        return Sucursal.objects.filter(es_principal=True).first() or Sucursal.objects.first()
    except Exception as e:
        logger.warning(f"No se pudo obtener sucursal: {e}")
        return None


def get_config():
    class Config:
        def __init__(self, s):
            vs = getattr(settings, "VPMOTOS_SETTINGS", {})
            if s:
                self.nombre = s.nombre_comercial or s.nombre or "EMPRESA"
                self.ruc    = s.ruc or ""
                self.ciudad = f"{s.ciudad}, {s.provincia}" if s.ciudad else ""
                self.tel    = s.telefono or s.celular or ""
            else:
                self.nombre = vs.get("COMPANY_NAME", "EMPRESA")
                self.ruc    = vs.get("COMPANY_TAX_ID", "")
                self.ciudad = ""
                self.tel    = vs.get("COMPANY_PHONE", "")
            self.S   = "$"
            self.D   = 2
            self.iva = vs.get("IVA_PERCENTAGE", 15.0)
    return Config(get_sucursal())


def centrar(texto, ancho=ANCHO):
    texto = str(texto)[:ancho]
    pad = (ancho - len(texto)) // 2
    return (" " * pad + texto + "\n").encode("utf-8")


def izquierda(texto):
    return (str(texto) + "\n").encode("utf-8")


def fila(izq, der, ancho=ANCHO):
    izq = str(izq)
    der = str(der)
    espacio = ancho - len(izq) - len(der)
    if espacio < 1: espacio = 1
    return (izq + " " * espacio + der + "\n").encode("utf-8")


def sep(char="=", ancho=ANCHO):
    return (char * ancho + "\n").encode("utf-8")


# Comandos ESC/POS
ESC       = b"\x1B"
BOLD_ON   = b"\x1B\x21\x08"
BOLD_OFF  = b"\x1B\x21\x00"
BIG_ON    = b"\x1B\x21\x38"
BIG_OFF   = b"\x1B\x21\x00"
CENTER    = b"\x1B\x61\x01"
LEFT      = b"\x1B\x61\x00"
CUT       = b"\x1D\x56\x41\x03"
FEED      = b"\n\n\n\n"


class TicketPrinter:

    @staticmethod
    def generar_comandos_ticket(venta, impresora_obj):
        try:
            cfg = get_config()
            S = cfg.S
            D = cfg.D
            c = b""

            # ENCABEZADO
            c += CENTER
            c += BOLD_ON
            c += centrar(cfg.nombre)
            c += BOLD_OFF
            if cfg.ruc:    c += centrar("RUC: " + cfg.ruc)
            if cfg.ciudad: c += centrar(cfg.ciudad)
            if cfg.tel:    c += centrar("TEL: " + cfg.tel)
            c += sep("=")

            # DATOS VENTA
            c += LEFT
            fecha_local = tz.localtime(venta.fecha_hora)
            c += izquierda("TICKET: TKT-" + str(venta.numero_factura))
            c += izquierda("FECHA : " + fecha_local.strftime("%d/%m/%Y  %H:%M"))
            cajero = venta.usuario.usuario if venta.usuario else "Sistema"
            c += izquierda("CAJERO: " + cajero)
            if venta.cliente:
                c += izquierda("CLIENT: " + venta.cliente.get_nombre_completo()[:40])
                c += izquierda("CI/RUC: " + str(venta.cliente.identificacion))

            # ORDEN DE TALLER
            if venta.orden_trabajo:
                ot = venta.orden_trabajo
                c += sep("-")
                c += CENTER
                c += BOLD_ON
                c += centrar("ORDEN DE TALLER")
                c += BOLD_OFF
                c += LEFT
                c += izquierda("OT    : " + str(ot.numero_orden))
                moto = ((ot.moto_marca or "") + " " + (ot.moto_modelo or "")).strip()
                if moto: c += izquierda("MOTO  : " + moto[:40])
                if ot.moto_placa: c += izquierda("PLACA : " + ot.moto_placa)
                if ot.moto_año: c += izquierda("ANO   : " + str(ot.moto_año))
                if ot.kilometraje_entrada: c += izquierda("KM    : " + str(ot.kilometraje_entrada))
                if ot.tecnico_principal:
                    t = ot.tecnico_principal
                    c += izquierda("TEC   : " + t.nombres + " " + t.apellidos)
                if ot.trabajo_realizado:
                    c += izquierda("TRAB  : " + ot.trabajo_realizado[:40])

            # ITEMS
            c += sep("=")
            c += BOLD_ON
            c += fila("DESCRIPCION", "TOTAL")
            c += BOLD_OFF
            c += sep("-")

            for det in venta.detalleventa_set.select_related("producto", "tipo_servicio", "tecnico").all():
                if det.nombre_personalizado:  nombre = det.nombre_personalizado
                elif det.producto:            nombre = det.producto.nombre
                elif det.tipo_servicio:       nombre = det.tipo_servicio.nombre
                else:                         nombre = "Item"

                total_str = S + "{:.{}f}".format(det.total, D)
                cant_str  = "{:.0f} x ".format(det.cantidad) + S + "{:.{}f}".format(det.precio_unitario, D)

                # nombre + total en misma linea
                c += fila(nombre[:38], total_str)
                if len(nombre) > 38:
                    c += izquierda("  " + nombre[38:])
                c += izquierda("  " + cant_str)
                if det.tecnico:
                    tec = det.tecnico.nombres + " " + det.tecnico.apellidos
                    c += izquierda("  TECNICO: " + tec[:36])

            # TOTALES
            c += sep("=")
            c += fila("SUBTOTAL", S + "{:.{}f}".format(venta.subtotal, D))
            if venta.descuento and venta.descuento > 0:
                c += fila("DESCUENTO", "-" + S + "{:.{}f}".format(venta.descuento, D))
            if venta.iva and venta.iva > 0:
                c += fila("IVA {:.0f}%".format(cfg.iva), S + "{:.{}f}".format(venta.iva, D))

            pagos = {"EFECTIVO":"EFECTIVO","TARJETA":"TARJETA","TRANSFERENCIA":"TRANSFERENCIA","CREDITO":"CREDITO","MIXTO":"MIXTO"}
            if venta.tipo_pago:
                c += izquierda("(" + pagos.get(venta.tipo_pago, venta.tipo_pago) + ")")

            c += sep("-")
            c += BOLD_ON
            c += fila("TOTAL A PAGAR", S + "{:.{}f}".format(venta.total, D))
            c += BOLD_OFF
            c += sep("=")

            # PIE
            c += CENTER
            c += b"\n"
            c += centrar("GRACIAS POR SU PREFERENCIA")
            c += centrar("Vuelva pronto!")
            c += FEED
            c += CUT

            if impresora_obj.tiene_gaveta:
                c += b"\x10\x14\x01\x00\x05"

            return c.hex()

        except Exception as e:
            logger.error("Error generando ticket: " + str(e), exc_info=True)
            raise

    @staticmethod
    def imprimir_ticket(venta, impresora_obj):
        try:
            hex_data = TicketPrinter.generar_comandos_ticket(venta, impresora_obj)
            from ..api.agente_views import crear_trabajo_impresion
            crear_trabajo_impresion(
                usuario=venta.usuario,
                impresora_nombre=impresora_obj.nombre_driver or impresora_obj.nombre,
                comandos_hex=hex_data, tipo="ticket", prioridad=1
            )
            return True
        except Exception as e:
            logger.error("Error imprimir ticket: " + str(e), exc_info=True)
            return False

    @staticmethod
    def imprimir_ticket_prueba(impresora_obj):
        try:
            cfg = get_config()
            c = b""
            c += CENTER
            c += BOLD_ON
            c += centrar("TICKET DE PRUEBA")
            c += BOLD_OFF
            c += centrar(cfg.nombre)
            if cfg.ruc: c += centrar("RUC: " + cfg.ruc)
            c += sep("=")
            c += centrar("Impresora funcionando OK")
            c += FEED
            c += CUT

            from ..api.agente_views import crear_trabajo_impresion, obtener_usuario_para_impresion
            crear_trabajo_impresion(
                usuario=obtener_usuario_para_impresion(),
                impresora_nombre=impresora_obj.nombre_driver or impresora_obj.nombre,
                comandos_hex=c.hex(), tipo="test", prioridad=1
            )
            return True
        except Exception as e:
            logger.error("Error ticket prueba: " + str(e), exc_info=True)
            return False

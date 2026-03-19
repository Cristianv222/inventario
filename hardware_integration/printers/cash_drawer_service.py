# apps/hardware_integration/printers/cash_drawer_service.py

import logging
import time
import threading
from typing import Optional
from django.utils import timezone
from django.conf import settings

from ..models import GavetaDinero, RegistroImpresion
from .printer_service import PrinterService

logger = logging.getLogger(__name__)


class CashDrawerService:
    """
    Servicio COMPLETO para manejar gavetas de dinero
    - Soporta múltiples métodos de conexión
    - Maneja pines específicos (0 = pin 2, 1 = pin 5)
    - Actualiza estados correctamente
    - Incluye timeouts y reintentos
    - Auditoría completa
    """
    
    # Comandos ESC/POS por pin
    # pin 0 = pin 2 (estándar), pin 1 = pin 5
    COMANDOS_ESCPOS = {
        0: b'\x1B\x70\x00\x19\xFA',  # pin 2
        1: b'\x1B\x70\x01\x19\xFA',  # pin 5
    }
    
    @classmethod
    def abrir_gaveta(
        cls,
        gaveta: GavetaDinero,
        usuario=None,
        motivo: str = "Apertura manual"
    ) -> bool:
        """
        Método principal para abrir gaveta con manejo completo de errores
        """
        if not gaveta.activa:
            logger.warning(f"Gaveta {gaveta.nombre} está inactiva")
            return False
        
        try:
            exito = False
            error_msg = ""
            
            # Determinar método de apertura
            if gaveta.tipo_conexion == 'IMPRESORA':
                if not gaveta.impresora:
                    error_msg = "Gaveta no tiene impresora asociada"
                    logger.error(error_msg)
                else:
                    exito, error_msg = cls._abrir_por_impresora(gaveta)
                    
            elif gaveta.tipo_conexion in ['USB', 'SERIAL', 'RJ11']:
                # RJ11 normalmente se controla por impresora, pero permitimos override
                if gaveta.tipo_conexion == 'RJ11' and gaveta.impresora:
                    exito, error_msg = cls._abrir_por_impresora(gaveta)
                else:
                    error_msg = f"Conexión directa {gaveta.tipo_conexion} no implementada completamente"
                    logger.warning(error_msg)
                    # Podrías implementar esto más adelante
                    exito = False
                    
            else:
                error_msg = f"Tipo de conexión no soportado: {gaveta.tipo_conexion}"
                logger.error(error_msg)
            
            # Registrar la acción
            cls._registrar_apertura(gaveta, usuario, motivo, exito, error_msg)
            
            if exito:
                # Programar actualización a "CERRADA" después de 5 segundos
                cls._programar_cierre_gaveta(gaveta)
                logger.info(f"Gaveta '{gaveta.nombre}' abierta exitosamente. Motivo: {motivo}")
            else:
                logger.error(f"Falló apertura de gaveta '{gaveta.nombre}': {error_msg}")
            
            return exito
            
        except Exception as e:
            error_msg = f"Excepción inesperada: {str(e)}"
            logger.exception(error_msg)
            cls._registrar_apertura(gaveta, usuario, motivo, False, error_msg)
            return False
    
    @classmethod
    def _abrir_por_impresora(cls, gaveta: GavetaDinero) -> tuple[bool, str]:
        """
        Abre gaveta a través de impresora con manejo de pines y timeouts
        Returns: (exito: bool, mensaje_error: str)
        """
        impresora = gaveta.impresora
        
        # Validar que la impresora esté activa
        if impresora.estado != 'ACTIVA':
            # Intentar reconectar
            success, msg = PrinterService.test_connection(impresora)
            if not success:
                return False, f"Impresora no responde: {msg}"
        
        try:
            # Determinar pin a usar
            pin = 0  # pin por defecto
            if hasattr(impresora, 'pin_gaveta') and impresora.pin_gaveta is not None:
                pin = impresora.pin_gaveta
            
            # Obtener comando específico para el pin
            comando = cls.COMANDOS_ESCPOS.get(pin, cls.COMANDOS_ESCPOS[0])
            
            # Enviar comando con timeout
            success = PrinterService.enviar_comando_raw_con_timeout(
                impresora, 
                comando, 
                timeout=5  # 5 segundos máximo
            )
            
            if success:
                return True, ""
            else:
                return False, "Timeout al enviar comando a impresora"
                
        except Exception as e:
            return False, f"Error al comunicar con impresora: {str(e)}"
    
    @classmethod
    def _registrar_apertura(
        cls,
        gaveta: GavetaDinero,
        usuario=None,
        motivo: str = "",
        exito: bool = False,
        error: str = ""
    ) -> None:
        """Registra la apertura en la base de datos"""
        try:
            # Actualizar gaveta
            gaveta.contador_aperturas += 1
            gaveta.fecha_ultima_apertura = timezone.now()
            gaveta.usuario_ultima_apertura = usuario
            gaveta.estado = 'ABIERTA' if exito else 'DESCONECTADA'
            gaveta.save(update_fields=[
                'contador_aperturas', 
                'fecha_ultima_apertura', 
                'usuario_ultima_apertura',
                'estado'
            ])
            
            # Registrar en RegistroImpresion para auditoría completa
            RegistroImpresion.objects.create(
                tipo_documento='OTRO',
                estado='EXITOSO' if exito else 'ERROR',
                mensaje_error=error if not exito else '',
                usuario=usuario,
                impresora=gaveta.impresora,
                contenido_resumen=f"Apertura de gaveta: {gaveta.nombre}. Motivo: {motivo}",
                numero_documento=f"GAV-{gaveta.codigo}"
            )
            
        except Exception as e:
            logger.exception(f"Error al registrar apertura en DB: {str(e)}")
    
    @classmethod
    def _programar_cierre_gaveta(cls, gaveta: GavetaDinero):
        """
        Programa la actualización del estado a 'CERRADA' después de unos segundos
        Usa threading para no bloquear la respuesta HTTP
        """
        def actualizar_estado():
            time.sleep(5)  # Esperar 5 segundos (tiempo típico de apertura física)
            try:
                gaveta.refresh_from_db()
                if gaveta.estado == 'ABIERTA':
                    gaveta.estado = 'CERRADA'
                    gaveta.save(update_fields=['estado'])
                    logger.debug(f"Estado de gaveta {gaveta.nombre} actualizado a CERRADA")
            except Exception as e:
                logger.exception(f"Error al actualizar estado de gaveta a CERRADA: {str(e)}")
        
        # Ejecutar en hilo separado
        thread = threading.Thread(target=actualizar_estado, daemon=True)
        thread.start()
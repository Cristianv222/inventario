import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging

logger = logging.getLogger(__name__)

class SRIMonitorConsumer(AsyncWebsocketConsumer):
    """
    Consumer para el monitoreo de facturación electrónica en tiempo real.
    Permite a los administradores ver el progreso de los comprobantes.
    """

    async def connect(self):
        # El grupo permite enviar mensajes a todos los usuarios conectados al panel
        self.group_name = "sri_monitor"

        # Unirse al grupo
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"WebSocket conectado al monitor SRI (Canal: {self.channel_name})")

    async def disconnect(self, close_code):
        # Salir del grupo
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.info(f"WebSocket desconectado del monitor SRI (Canal: {self.channel_name})")

    async def sri_status_update(self, event):
        """
        Recibe mensajes del grupo y los envía al cliente WebSocket.
        Este método es llamado por async_to_sync(channel_layer.group_send) desde las tareas Celery.
        """
        # El evento contiene: type, comprobante_id, estado, clave_acceso, numero_autorizacion, etc.
        data = event.copy()
        data.pop('type') # Quitamos el tipo de evento interno de channels
        
        await self.send(text_data=json.dumps(data))

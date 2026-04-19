import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import logging

logger = logging.getLogger(__name__)

class HardwareAgentConsumer(AsyncWebsocketConsumer):
    """
    Consumidor para el Agente de Hardware local (Windows).
    Permite notificaciones push para impresión y otros periféricos.
    """
    async def connect(self):
        # El grupo depende del usuario o puede ser global para el sistema
        self.user = self.scope.get('user')
        
        # Grupo global para todos los agentes (útil para sistemas pequeños)
        # O grupo por usuario: f"hardware_agent_{self.user.id}" si está autenticado
        self.group_name = "hardware_agent_global"
        
        # Aceptar la conexión
        await self.accept()
        
        # Unirse al grupo de avisos de impresión
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        logger.info(f"🔌 [WEB-SOCKET] Agente de hardware CONECTADO exitosamente: {self.channel_name}")
        
        # Enviar mensaje de bienvenida con estatus
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': '✅ Conexión establecida con el servidor ASGI CommerceBox',
            'polling_reduction': True
        }))

    async def disconnect(self, close_code):
        # Salir del grupo
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.warning(f"🔌 [WEB-SOCKET] Agente de hardware DESCONECTADO (código: {close_code})")

    async def receive(self, text_data):
        """
        Maneja mensajes recibidos desde el Agente (ej. estado de impresora)
        """
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
                
        except json.JSONDecodeError:
            pass

    async def new_print_job(self, event):
        """
        Handler para eventos de nuevo trabajo de impresión (enviados desde signals.py)
        """
        job_id = event.get('data', {}).get('id', 'N/A')
        logger.info(f"🚀 [PUSH-NOTIFY] Enviando señal de nuevo trabajo {job_id} al Agente vía WebSocket")
        
        # Enviamos la notificación al Agente local
        await self.send(text_data=json.dumps({
            'type': 'new_print_job',
            'data': event.get('data', {
                'message': 'Nuevo trabajo disponible'
            })
        }))

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class VentasConsumer(AsyncWebsocketConsumer):
    """
    Consumidor para manejar notificaciones de ventas y cola de impresión en tiempo real.
    """
    async def connect(self):
        self.user = self.scope["user"]
        self.tenant = self.scope.get("tenant")
        
        if not self.user.is_authenticated or not self.tenant:
            await self.close()
            return

        # Nombre del grupo basado en el código de la sucursal (para aislamiento)
        self.group_name = f"ventas_{self.tenant.codigo}"

        # Unirse al grupo
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        
        # Enviar mensaje de bienvenida/confirmación
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': f'Conectado a la cola de ventas: {self.tenant.nombre}'
        }))

    async def disconnect(self, close_code):
        # Salir del grupo
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # Reibir mensajes del WebSocket (del cliente)
    async def receive(self, text_data):
        data = json.loads(text_data)
        # Por ahora no procesamos mensajes entrantes del POS, solo notificaciones del servidor
        pass

    # Métodos para manejar eventos enviados desde el servidor (vía group_send)
    
    async def print_job_update(self, event):
        """Notifica cambios en la cola de impresión"""
        await self.send(text_data=json.dumps({
            'type': 'print_job_update',
            'data': event['data']
        }))

    async def printer_status_update(self, event):
        """Notifica cambios en el estado de una impresora"""
        await self.send(text_data=json.dumps({
            'type': 'printer_status_update',
            'data': event['data']
        }))

    async def new_sale_notification(self, event):
        """Notifica una nueva venta realizada"""
        await self.send(text_data=json.dumps({
            'type': 'new_sale',
            'data': event['data']
        }))

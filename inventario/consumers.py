import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ImportarProductosConsumer(AsyncWebsocketConsumer):
    """
    Consumidor para notificar el progreso de la importación de productos en tiempo real.
    """
    async def connect(self):
        self.user = self.scope["user"]
        self.tenant = self.scope.get("tenant")
        
        if not self.user.is_authenticated or not self.tenant:
            await self.close()
            return

        # El ID de tarea o un identificador único para la importación
        # Por ahora usamos un grupo general por tenant
        self.group_name = f"import_{self.tenant.schema_name}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def import_progress(self, event):
        """Envía el progreso al cliente"""
        await self.send(text_data=json.dumps({
            'type': 'progress',
            'progress': event['progress'],
            'current': event['current'],
            'total': event['total'],
            'message': event.get('message', '')
        }))

    async def import_completed(self, event):
        """Notifica la finalización"""
        await self.send(text_data=json.dumps({
            'type': 'completed',
            'success': event['success'],
            'processed': event['processed'],
            'errors': event['errors']
        }))

import asyncio
import json
from datetime import datetime
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .ranking import payload_publico, token_valido, PERIODOS

GRUPO_RANKING = 'ranking_taller'


class RankingConsumer(AsyncWebsocketConsumer):
    """Envía el ranking de técnicos al monitor / dashboard en tiempo real.

    Se autentica con el token de la pantalla (?t=...). Cada vez que cambia una
    orden o una venta (ver signals.py) se recalcula y se empuja a los clientes.
    """

    async def connect(self):
        qs = parse_qs(self.scope.get('query_string', b'').decode())
        token = (qs.get('t') or [''])[0]
        user = self.scope.get('user')
        usuario_ok = bool(user and user.is_authenticated and getattr(user, 'activo', True))
        # Entra quien trae el token del monitor o cualquier usuario con sesión iniciada
        if not (token_valido(token) or usuario_ok):
            await self.close(code=4403)
            return
        self._pendiente = False
        self._filtro = {}
        await self.channel_layer.group_add(GRUPO_RANKING, self.channel_name)
        await self.accept()
        await self._enviar()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(GRUPO_RANKING, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # El cliente pide refrescar de vez en cuando (p. ej. al cambiar el día)
        try:
            msg = json.loads(text_data or '{}')
            if msg.get('action') == 'set':
                # El widget del dashboard elige periodo (dia | semana | mes) y fecha
                per = msg.get('periodo')
                if per in PERIODOS:
                    try:
                        fecha = datetime.strptime(msg.get('fecha') or '', '%Y-%m-%d').date()
                    except ValueError:
                        fecha = None
                    self._filtro = {'periodo': per, 'fecha': fecha}
                else:
                    self._filtro = {}
                await self._enviar()
            elif msg.get('action') == 'refresh':
                await self._enviar()
        except Exception:
            pass

    async def ranking_update(self, event):
        # Agrupa ráfagas de cambios (una venta guarda varias filas seguidas)
        if getattr(self, '_pendiente', False):
            return
        self._pendiente = True
        await asyncio.sleep(1.5)
        self._pendiente = False
        await self._enviar()

    async def _enviar(self):
        try:
            data = await database_sync_to_async(payload_publico)(**getattr(self, '_filtro', {}))
            await self.send(text_data=json.dumps({'type': 'ranking', 'data': data}))
        except Exception:
            pass

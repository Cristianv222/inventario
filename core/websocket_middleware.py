from channels.db import database_sync_to_async
from django.db import connection
from core.models import Sucursal

class TenantWebSocketMiddleware:
    """
    Middleware simplificado para base de datos única.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # En una arquitectura única, el esquema siempre es public
        scope['schema_name'] = 'public'
        
        # Intentar determinar la sucursal (tenant anterior)
        tenant = await self.get_tenant()
        scope['tenant'] = tenant
        
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_tenant(self):
        """Obtiene la sucursal principal de manera sincrónica"""
        try:
            return Sucursal.objects.filter(es_principal=True).first() or Sucursal.objects.first()
        except Exception:
            return None

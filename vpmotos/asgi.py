import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vpmotos.settings')

# Inicializar la aplicación ASGI de Django para manejar HTTP al principio
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core.websocket_middleware import TenantWebSocketMiddleware
import vpmotos.routing

application = ProtocolTypeRouter({
    # Tráfico HTTP normal
    "http": django_asgi_app,
    
    # Tráfico de WebSockets
    "websocket": TenantWebSocketMiddleware(
        AuthMiddlewareStack(
            URLRouter(
                vpmotos.routing.websocket_urlpatterns
            )
        )
    ),
})

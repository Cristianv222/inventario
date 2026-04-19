from django.urls import re_path
from ventas.consumers import VentasConsumer
from inventario.consumers import ImportarProductosConsumer
from hardware_integration.consumers import HardwareAgentConsumer
from electronic_invoicing.consumers import SRIMonitorConsumer

websocket_urlpatterns = [
    re_path(r'ws/ventas/cola-impresion/?$', VentasConsumer.as_asgi()),
    re_path(r'ws/inventario/importar/?$', ImportarProductosConsumer.as_asgi()),
    re_path(r'ws/hardware/agente/?$', HardwareAgentConsumer.as_asgi()),
    re_path(r'ws/sri/monitor/$', SRIMonitorConsumer.as_asgi()),
]

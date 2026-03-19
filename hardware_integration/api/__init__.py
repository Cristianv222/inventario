# apps/hardware_integration/api/__init__.py

"""
API REST para comunicación con agentes de impresión locales
"""

from .agente_views import (
    registrar_agente,
    obtener_trabajos_pendientes,
    reportar_resultado
)
# apps/hardware_integration/api/__init__.py

"""
API REST para comunicación con agentes de impresión locales
"""

from .agente_views import (
    registrar_agente,
    obtener_trabajos_pendientes,
    reportar_resultado
)

__all__ = [
    'registrar_agente',
    'obtener_trabajos_pendientes',
    'reportar_resultado'
]
__all__ = [
    'registrar_agente',
    'obtener_trabajos_pendientes',
    'reportar_resultado'
]
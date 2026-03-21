# apps/hardware_integration/api/urls.py

from django.urls import path
from . import agente_views

app_name = 'hardware_api'

urlpatterns = [
    # ─── AGENTE DE IMPRESIÓN ──────────────────────────────────────────────────
    # Requieren autenticación con token (Authorization: Token <token>)
    path('agente/registrar/', agente_views.registrar_agente, name='agente_registrar'),
    path('agente/trabajos/', agente_views.obtener_trabajos_sin_auth, name='agente_trabajos'),
    path('agente/resultado/', agente_views.reportar_resultado, name='agente_resultado'),
    path('agente/estado/', agente_views.obtener_estado_agente, name='agente_estado'),
    path('agente/trabajos/<uuid:trabajo_id>/estado/', agente_views.actualizar_estado_trabajo, name='actualizar_estado_trabajo'),

    # ─── ENDPOINT SIN AUTH (solo para debugging/agente .exe) ─────────────────
    # ⚠️  Usar solo durante desarrollo. Reemplazar por el autenticado en producción.
    path('agente/trabajos/sin-auth/', agente_views.obtener_trabajos_sin_auth, name='agente_trabajos_sin_auth'),

    # ─── CÓDIGOS DE BARRAS Y ETIQUETAS ───────────────────────────────────────
    path('codigos-barras/imprimir/', agente_views.imprimir_codigo_barras, name='imprimir_codigo_barras'),
    path('codigos-barras/etiqueta/', agente_views.imprimir_etiqueta_producto, name='imprimir_etiqueta_producto'),
    path('codigos-barras/prueba/', agente_views.imprimir_prueba_codigos, name='imprimir_prueba_codigos'),
]

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [

    # ── Dashboard ─────────────────────────────────────────────
    path('', views.dashboard, name='dashboard'),

    # ── Sucursales — Vistas HTML ──────────────────────────────
    path('sucursales/', views.SucursalListView.as_view(), name='sucursales_lista'),
    path('sucursales/<int:pk>/', views.SucursalDetailView.as_view(), name='sucursales_detalle'),

    # ── Sucursales — API AJAX ─────────────────────────────────
    path('sucursales/api/', views.SucursalAPIView.as_view(), name='sucursales_api'),
    path('sucursales/api/<int:pk>/', views.SucursalAPIView.as_view(), name='sucursales_api_detalle'),
    path('sucursales/api/<int:pk>/toggle/', views.SucursalToggleActivaView.as_view(), name='sucursales_api_toggle'),

    # ── Dominios — API AJAX ───────────────────────────────────
    path('sucursales/api/<int:sucursal_pk>/dominios/', views.DominioAPIView.as_view(), name='dominios_api'),
    path('sucursales/api/<int:sucursal_pk>/dominios/<int:dominio_pk>/', views.DominioAPIView.as_view(), name='dominios_api_detalle'),

    # ── Parámetros — API AJAX ─────────────────────────────────
    path('sucursales/api/parametros/', views.ParametroAPIView.as_view(), name='parametros_api'),
    path('sucursales/api/parametros/<int:pk>/', views.ParametroAPIView.as_view(), name='parametros_api_detalle'),

    # ── Utilidades AJAX ───────────────────────────────────────
    path('sucursales/utils/schema-preview/', views.preview_schema_name, name='schema_preview'),

]
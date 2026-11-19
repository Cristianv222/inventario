from django.urls import path

from . import views

app_name = 'finanzas'

urlpatterns = [
    path('', views.estado_motor, name='estado_motor'),
    path('balance-comprobacion/', views.balance_comprobacion, name='balance_comprobacion'),
    path('estado-resultados/', views.estado_resultados, name='estado_resultados'),
    path('balance-general/', views.balance_general, name='balance_general'),
    path('flujo-caja/', views.flujo_caja, name='flujo_caja'),
]

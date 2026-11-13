from django.urls import path

from . import views

app_name = 'finanzas'

urlpatterns = [
    path('', views.estado_motor, name='estado_motor'),
]

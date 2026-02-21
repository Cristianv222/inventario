from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'usuarios'

urlpatterns = [
    # ── Autenticación ──────────────────────────────────────────
    path('login/',            views.login_view,      name='login'),
    path('logout/',           views.logout_view,     name='logout'),
    path('cambiar-password/', views.cambiar_password, name='cambiar_password'),

    # ── Gestión de Usuarios ────────────────────────────────────
    path('usuarios/',                              views.lista_usuarios,             name='lista_usuarios'),
    path('usuarios/nuevo/',                        views.crear_usuario,              name='crear_usuario'),
    path('usuarios/por-sucursal/',                 views.usuarios_por_sucursal,      name='usuarios_por_sucursal'),
    path('usuarios/<int:user_id>/editar/',         views.editar_usuario,             name='editar_usuario'),
    path('usuarios/<int:user_id>/activar/',        views.activar_desactivar_usuario, name='activar_desactivar_usuario'),
    path('usuarios/<int:user_id>/eliminar/',       views.eliminar_usuario,           name='eliminar_usuario'),
    path('usuarios/<int:user_id>/permisos/',       views.ver_permisos_usuario,       name='ver_permisos_usuario'),
    path('usuarios/<int:user_id>/sucursal/',       views.asignar_sucursal,           name='asignar_sucursal'),

    # ── Gestión de Permisos ────────────────────────────────────
    path('permisos/',                              views.lista_permisos,    name='lista_permisos'),
    path('permisos/crear/',                        views.crear_permiso,     name='crear_permiso'),
    path('permisos/<int:permiso_id>/editar/',      views.editar_permiso,    name='editar_permiso'),
    path('permisos/<int:permiso_id>/eliminar/',    views.eliminar_permiso,  name='eliminar_permiso'),
]
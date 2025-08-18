from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'usuarios'

urlpatterns = [
    # Vistas de autenticación
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('cambiar-password/', views.cambiar_password, name='cambiar_password'),
    
    # Gestión de usuarios
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/nuevo/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/<int:user_id>/editar/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/<int:user_id>/activar/', views.activar_desactivar_usuario, name='activar_desactivar_usuario'),
    
    # Gestión de roles
    path('roles/', views.lista_roles, name='lista_roles'),
    path('roles/nuevo/', views.crear_rol, name='crear_rol'),
    path('roles/<int:rol_id>/editar/', views.editar_rol, name='editar_rol'),
    path('roles/<int:rol_id>/activar/', views.activar_desactivar_rol, name='activar_desactivar_rol'),
    
    # Gestión de permisos
    path('permisos/', views.lista_permisos, name='lista_permisos'),
    path('permisos/crear/', views.crear_permiso, name='crear_permiso'),
    path('roles/<int:rol_id>/permisos/', views.asignar_permisos_rol, name='asignar_permisos_rol'),
]
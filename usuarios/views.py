from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Permission, ContentType
from django.contrib import messages
from django.urls import reverse
from .models import Usuario, Rol
from .forms import (
    CustomAuthenticationForm, CustomPasswordChangeForm, 
    UsuarioForm, RolForm, RolPermisosForm, PermisoForm
)
from .decorators import permiso_requerido

# Funciones de verificación de permisos
def is_admin(user):
    """Verifica si el usuario es administrador"""
    return user.is_authenticated and (user.is_staff or (user.rol and user.rol.nombre == "Administrador"))

def is_superuser(user):
    """Verifica si el usuario es superusuario"""
    return user.is_authenticated and user.is_superuser

# Vistas de autenticación
def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
        
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            usuario = form.cleaned_data.get('username')
            contraseña = form.cleaned_data.get('password')
            user = authenticate(username=usuario, password=contraseña)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', reverse('core:dashboard'))
                return redirect(next_url)
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'usuarios/login.html', {'form': form})

@login_required
def cambiar_password(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Mantener la sesión activa después de cambiar la contraseña
            update_session_auth_hash(request, user)
            messages.success(request, 'Tu contraseña ha sido actualizada correctamente.')
            return redirect('core:dashboard')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'usuarios/cambiar_password.html', {'form': form})

# Gestión de Usuarios
@login_required
@user_passes_test(is_admin)
def lista_usuarios(request):
    usuarios = Usuario.objects.all().select_related('rol')
    return render(request, 'usuarios/lista_usuarios.html', {'usuarios': usuarios})

@login_required
@user_passes_test(is_admin)
def crear_usuario(request):
    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('usuarios:lista_usuarios')
    else:
        form = UsuarioForm()
    
    return render(request, 'usuarios/form_usuario.html', {
        'form': form,
        'titulo': 'Nuevo Usuario'
    })

@login_required
@user_passes_test(is_admin)
def editar_usuario(request, user_id):
    usuario = get_object_or_404(Usuario, id=user_id)
    
    if request.method == 'POST':
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario actualizado correctamente.')
            return redirect('usuarios:lista_usuarios')
    else:
        form = UsuarioForm(instance=usuario)
    
    return render(request, 'usuarios/form_usuario.html', {
        'form': form,
        'titulo': 'Editar Usuario',
        'usuario': usuario
    })

@login_required
@user_passes_test(is_admin)
def activar_desactivar_usuario(request, user_id):
    usuario = get_object_or_404(Usuario, id=user_id)
    usuario.activo = not usuario.activo
    usuario.save()
    
    status = "activado" if usuario.activo else "desactivado"
    messages.success(request, f'Usuario {usuario.usuario} {status} correctamente.')
    return redirect('usuarios:lista_usuarios')

# Gestión de Roles
@login_required
@user_passes_test(is_admin)
def lista_roles(request):
    roles = Rol.objects.all()
    return render(request, 'usuarios/lista_roles.html', {'roles': roles})

@login_required
@user_passes_test(is_admin)
def crear_rol(request):
    if request.method == 'POST':
        form = RolForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rol creado correctamente.')
            return redirect('usuarios:lista_roles')
    else:
        form = RolForm()
    
    return render(request, 'usuarios/form_rol.html', {
        'form': form,
        'titulo': 'Nuevo Rol'
    })

@login_required
@user_passes_test(is_admin)
def editar_rol(request, rol_id):
    rol = get_object_or_404(Rol, id=rol_id)
    
    if request.method == 'POST':
        form = RolForm(request.POST, instance=rol)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rol actualizado correctamente.')
            return redirect('usuarios:lista_roles')
    else:
        form = RolForm(instance=rol)
    
    return render(request, 'usuarios/form_rol.html', {
        'form': form,
        'titulo': 'Editar Rol',
        'rol': rol
    })

@login_required
@user_passes_test(is_admin)
def activar_desactivar_rol(request, rol_id):
    rol = get_object_or_404(Rol, id=rol_id)
    rol.activo = not rol.activo
    rol.save()
    
    status = "activado" if rol.activo else "desactivado"
    messages.success(request, f'Rol {rol.nombre} {status} correctamente.')
    return redirect('usuarios:lista_roles')

# Gestión de Permisos
@login_required
@user_passes_test(is_superuser)
def lista_permisos(request):
    """Vista para listar todos los permisos disponibles (solo superusuario)"""
    # Organizar permisos por aplicación y modelo
    permisos_por_app = {}
    
    for ct in ContentType.objects.all().order_by('app_label'):
        app = ct.app_label
        if app not in permisos_por_app:
            permisos_por_app[app] = {}
            
        model = ct.model
        if model not in permisos_por_app[app]:
            permisos_por_app[app][model] = []
            
        permisos = Permission.objects.filter(content_type=ct)
        permisos_por_app[app][model].extend(permisos)
    
    return render(request, 'usuarios/lista_permisos.html', {
        'permisos_por_app': permisos_por_app
    })

@login_required
@user_passes_test(is_superuser)
def crear_permiso(request):
    """Vista para crear permisos personalizados (solo superusuario)"""
    if request.method == 'POST':
        form = PermisoForm(request.POST)
        if form.is_valid():
            content_type = form.cleaned_data['content_type']
            nombre = form.cleaned_data['nombre']
            codename = form.cleaned_data['codename']
            
            # Crear el permiso
            permiso = Permission.objects.create(
                name=nombre,
                codename=codename,
                content_type=content_type
            )
            
            messages.success(request, f'Permiso "{nombre}" creado correctamente.')
            return redirect('usuarios:lista_permisos')
    else:
        form = PermisoForm()
    
    return render(request, 'usuarios/form_permiso.html', {
        'form': form,
        'titulo': 'Crear Nuevo Permiso'
    })

@login_required
@user_passes_test(is_admin)
def asignar_permisos_rol(request, rol_id):
    """Vista para que administradores asignen permisos a roles"""
    rol = get_object_or_404(Rol, id=rol_id)
    
    if request.method == 'POST':
        form = RolPermisosForm(request.POST, instance=rol)
        if form.is_valid():
            form.save()
            messages.success(request, f'Permisos actualizados para el rol "{rol.nombre}".')
            return redirect('usuarios:lista_roles')
    else:
        form = RolPermisosForm(instance=rol)
    
    # Organizar permisos por aplicación para mejor visualización
    permisos_por_app = {}
    for perm in Permission.objects.all().select_related('content_type').order_by('content_type__app_label', 'content_type__model'):
        app = perm.content_type.app_label
        model = perm.content_type.model
        
        if app not in permisos_por_app:
            permisos_por_app[app] = {}
        
        if model not in permisos_por_app[app]:
            permisos_por_app[app][model] = []
            
        permisos_por_app[app][model].append(perm)
    
    return render(request, 'usuarios/asignar_permisos.html', {
        'form': form,
        'rol': rol,
        'permisos_por_app': permisos_por_app
    })
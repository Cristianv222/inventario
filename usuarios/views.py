"""
Views del módulo Usuarios - VPMOTOS
Autenticación, CRUD de usuarios, permisos y asignación de sucursales
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Permission, ContentType
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.db.models import Q
from django.views.decorators.http import require_POST

from .models import Usuario
from .forms import (
    CustomAuthenticationForm, CustomPasswordChangeForm,
    UsuarioForm, PermisoForm
)
from core.models import Sucursal


# ══════════════════════════════════════════════
# VERIFICACIÓN DE PERMISOS
# ══════════════════════════════════════════════

def is_admin(user):
    """Verifica si el usuario es administrador (staff o superuser)"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)

def is_superuser(user):
    """Verifica si el usuario es superusuario (acceso total)"""
    return user.is_authenticated and user.is_superuser


# ══════════════════════════════════════════════
# AUTENTICACIÓN
# ══════════════════════════════════════════════

def login_view(request):
    """Vista de inicio de sesión"""
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            usuario   = form.cleaned_data.get('username')
            contraseña = form.cleaned_data.get('password')
            user = authenticate(username=usuario, password=contraseña)

            if user is not None:
                if not user.activo:
                    messages.error(request, 'Tu cuenta está inactiva. Contacta al administrador.')
                else:
                    login(request, user)
                    next_url = request.GET.get('next', reverse('core:dashboard'))
                    messages.success(request, f'¡Bienvenido {user.nombre}!')
                    return redirect(next_url)
            else:
                messages.error(request, 'Usuario o contraseña incorrectos.')
    else:
        form = CustomAuthenticationForm()

    return render(request, 'usuarios/login.html', {'form': form})


def logout_view(request):
    """Cierre de sesión"""
    if request.method == 'POST':
        logout(request)
    return redirect('usuarios:login')


@login_required
def cambiar_password(request):
    """Vista para cambiar la contraseña del usuario actual"""
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Tu contraseña ha sido actualizada correctamente.')
            return redirect('core:dashboard')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = CustomPasswordChangeForm(request.user)

    return render(request, 'usuarios/cambiar_password.html', {
        'active_page': 'admin',
        'form':  form,
        'titulo': 'Cambiar Contraseña',
    })


# ══════════════════════════════════════════════
# GESTIÓN DE USUARIOS
# ══════════════════════════════════════════════

@login_required
@user_passes_test(is_admin)
def lista_usuarios(request):
    """Lista todos los usuarios del sistema con filtros"""
    busqueda        = request.GET.get('buscar', '')
    filtro_estado   = request.GET.get('estado', '')
    filtro_sucursal = request.GET.get('sucursal', '')

    usuarios = Usuario.objects.all().prefetch_related(
        'user_permissions', 'groups'
    ).select_related('sucursal')

    # Búsqueda por texto
    if busqueda:
        usuarios = usuarios.filter(
            Q(usuario__icontains=busqueda)  |
            Q(nombre__icontains=busqueda)   |
            Q(apellido__icontains=busqueda) |
            Q(email__icontains=busqueda)
        )

    # Filtro de estado
    if filtro_estado == 'activos':
        usuarios = usuarios.filter(activo=True)
    elif filtro_estado == 'inactivos':
        usuarios = usuarios.filter(activo=False)
    elif filtro_estado == 'admin':
        usuarios = usuarios.filter(is_staff=True)
    elif filtro_estado == 'superuser':
        usuarios = usuarios.filter(is_superuser=True)
    elif filtro_estado == 'sin_sucursal':
        usuarios = usuarios.filter(sucursal__isnull=True, puede_ver_todas_sucursales=False)

    # Filtro de sucursal
    if filtro_sucursal == 'todas':
        usuarios = usuarios.filter(puede_ver_todas_sucursales=True)
    elif filtro_sucursal:
        usuarios = usuarios.filter(sucursal_id=filtro_sucursal)

    usuarios = usuarios.order_by('-fecha_creacion')

    sucursales  = Sucursal.objects.filter(activa=True).order_by('-es_principal', 'nombre')
    sin_asignar = Usuario.objects.filter(
        sucursal__isnull=True, puede_ver_todas_sucursales=False
    ).count()

    return render(request, 'usuarios/lista_usuarios.html', {
        'active_page':      'admin',
        'usuarios':         usuarios,
        'busqueda':         busqueda,
        'filtro_estado':    filtro_estado,
        'filtro_sucursal':  filtro_sucursal,
        'sucursales':       sucursales,
        'total':            usuarios.count(),
        'sin_asignar':      sin_asignar,
    })


@login_required
@user_passes_test(is_admin)
def crear_usuario(request):
    """Crear un nuevo usuario con permisos y sucursal"""
    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()

            permisos_ids = request.POST.getlist('permisos')
            if permisos_ids:
                usuario.user_permissions.set(permisos_ids)

            messages.success(
                request,
                f'Usuario "{usuario.usuario}" creado correctamente. '
                f'Sucursal: {usuario.nombre_sucursal}. '
                f'Permisos asignados: {len(permisos_ids)}.'
            )
            return redirect('usuarios:lista_usuarios')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = UsuarioForm()

    return render(request, 'usuarios/form_usuario.html', {
        'active_page':          'admin',
        'form':                 form,
        'titulo':               'Crear Nuevo Usuario',
        'permisos_organizados': organizar_permisos(),
        'sucursales':           Sucursal.objects.filter(activa=True).order_by('-es_principal', 'nombre'),
        'usuario':              None,
        'permisos_usuario_ids': [],
    })


@login_required
@user_passes_test(is_admin)
def editar_usuario(request, user_id):
    """Editar un usuario existente, sus permisos y su sucursal"""
    usuario     = get_object_or_404(Usuario, id=user_id)
    es_el_mismo = request.user.id == usuario.id

    if request.method == 'POST':
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            # No puede desactivarse a sí mismo
            if es_el_mismo and not form.cleaned_data.get('activo'):
                messages.error(request, 'No puedes desactivar tu propia cuenta.')
                return redirect('usuarios:editar_usuario', user_id=user_id)

            # No puede quitarse permisos de admin
            if es_el_mismo and not form.cleaned_data.get('is_staff') and not form.cleaned_data.get('is_superuser'):
                messages.error(request, 'No puedes quitarte tus propios permisos de administrador.')
                return redirect('usuarios:editar_usuario', user_id=user_id)

            usuario      = form.save()
            permisos_ids = request.POST.getlist('permisos')
            usuario.user_permissions.set(permisos_ids)

            messages.success(
                request,
                f'Usuario "{usuario.usuario}" actualizado correctamente. '
                f'Sucursal: {usuario.nombre_sucursal}. '
                f'Permisos: {len(permisos_ids)}.'
            )
            return redirect('usuarios:lista_usuarios')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = UsuarioForm(instance=usuario)

    return render(request, 'usuarios/form_usuario.html', {
        'active_page':          'admin',
        'form':                 form,
        'titulo':               f'Editar Usuario: {usuario.usuario}',
        'permisos_organizados': organizar_permisos(),
        'sucursales':           Sucursal.objects.filter(activa=True).order_by('-es_principal', 'nombre'),
        'usuario':              usuario,
        'es_el_mismo':          es_el_mismo,
        'permisos_usuario_ids': list(usuario.user_permissions.values_list('id', flat=True)),
    })


@login_required
@user_passes_test(is_admin)
def activar_desactivar_usuario(request, user_id):
    """Activar o desactivar un usuario"""
    usuario = get_object_or_404(Usuario, id=user_id)

    if request.user.id == usuario.id:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('usuarios:lista_usuarios')

    usuario.activo = not usuario.activo
    usuario.save()

    estado = 'activado' if usuario.activo else 'desactivado'
    messages.success(request, f'Usuario "{usuario.usuario}" {estado} correctamente.')
    return redirect('usuarios:lista_usuarios')


@login_required
@user_passes_test(is_admin)
def eliminar_usuario(request, user_id):
    """Eliminar un usuario del sistema"""
    usuario = get_object_or_404(Usuario, id=user_id)

    if request.user.id == usuario.id:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')
        return redirect('usuarios:lista_usuarios')

    if usuario.is_superuser:
        messages.error(request, 'No se pueden eliminar cuentas de super administrador.')
        return redirect('usuarios:lista_usuarios')

    if request.method == 'POST':
        nombre = usuario.usuario
        usuario.delete()
        messages.success(request, f'Usuario "{nombre}" eliminado correctamente.')
        return redirect('usuarios:lista_usuarios')

    return render(request, 'usuarios/confirmar_eliminar_usuario.html', {
        'active_page': 'admin',
        'usuario': usuario,
    })


@login_required
@user_passes_test(is_admin)
def ver_permisos_usuario(request, user_id):
    """Ver todos los permisos de un usuario específico"""
    usuario = get_object_or_404(Usuario, id=user_id)

    permisos_usuario = usuario.user_permissions.all().select_related(
        'content_type'
    ).order_by('content_type__app_label', 'content_type__model', 'codename')

    permisos_por_app = {}
    for permiso in permisos_usuario:
        app   = permiso.content_type.app_label
        model = permiso.content_type.model
        permisos_por_app.setdefault(app, {}).setdefault(model, []).append(permiso)

    return render(request, 'usuarios/ver_permisos_usuario.html', {
        'active_page':      'admin',
        'usuario':          usuario,
        'permisos_por_app': permisos_por_app,
        'total_permisos':   permisos_usuario.count(),
    })


# ══════════════════════════════════════════════
# ASIGNACIÓN DE SUCURSALES (AJAX)
# ══════════════════════════════════════════════

@login_required
@user_passes_test(is_admin)
@require_POST
def asignar_sucursal(request, user_id):
    """
    AJAX: Asigna o quita una sucursal a un usuario.

    Body JSON:
        { "sucursal_id": 3 }        → sucursal específica
        { "sucursal_id": "todas" }  → acceso a todas (admin general)
        { "sucursal_id": null }     → sin sucursal asignada
    """
    usuario = get_object_or_404(Usuario, id=user_id)

    if usuario.is_superuser and not request.user.is_superuser:
        return JsonResponse(
            {'success': False, 'error': 'Sin permisos para modificar este usuario'},
            status=403
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)

    sucursal_id = data.get('sucursal_id')

    if sucursal_id == 'todas':
        usuario.puede_ver_todas_sucursales = True
        usuario.sucursal = None
        usuario.save(update_fields=['puede_ver_todas_sucursales', 'sucursal'])
        return JsonResponse({
            'success':        True,
            'message':        f'{usuario.get_nombre_completo()} ahora tiene acceso a todas las sucursales',
            'nombre_sucursal': 'Todas las sucursales',
            'puede_ver_todas': True,
        })

    elif sucursal_id is None:
        usuario.sucursal = None
        usuario.puede_ver_todas_sucursales = False
        usuario.save(update_fields=['sucursal', 'puede_ver_todas_sucursales'])
        return JsonResponse({
            'success':        True,
            'message':        f'{usuario.get_nombre_completo()} ya no tiene sucursal asignada',
            'nombre_sucursal': 'Sin asignar',
            'puede_ver_todas': False,
        })

    else:
        sucursal = get_object_or_404(Sucursal, pk=sucursal_id, activa=True)
        usuario.sucursal = sucursal
        usuario.puede_ver_todas_sucursales = False
        usuario.save(update_fields=['sucursal', 'puede_ver_todas_sucursales'])
        return JsonResponse({
            'success':        True,
            'message':        f'{usuario.get_nombre_completo()} asignado a "{sucursal.nombre}"',
            'nombre_sucursal': sucursal.nombre,
            'puede_ver_todas': False,
        })


@login_required
@user_passes_test(is_admin)
def usuarios_por_sucursal(request):
    """Vista: resumen de usuarios agrupados por sucursal"""
    sucursales = Sucursal.objects.filter(activa=True).prefetch_related(
        'usuarios'
    ).order_by('-es_principal', 'nombre')

    sin_sucursal  = Usuario.objects.filter(
        sucursal__isnull=True, puede_ver_todas_sucursales=False, activo=True
    )
    admin_general = Usuario.objects.filter(
        puede_ver_todas_sucursales=True, activo=True
    )

    return render(request, 'usuarios/usuarios_por_sucursal.html', {
        'active_page':   'admin',
        'sucursales':    sucursales,
        'sin_sucursal':  sin_sucursal,
        'admin_general': admin_general,
    })


# ══════════════════════════════════════════════
# GESTIÓN DE PERMISOS
# ══════════════════════════════════════════════

@login_required
@user_passes_test(is_superuser)
def lista_permisos(request):
    """Lista todos los permisos disponibles en el sistema (solo superusuario)"""
    busqueda   = request.GET.get('buscar', '')
    app_filtro = request.GET.get('app', '')

    permisos = Permission.objects.all().select_related('content_type')

    if busqueda:
        permisos = permisos.filter(
            Q(name__icontains=busqueda)             |
            Q(codename__icontains=busqueda)         |
            Q(content_type__model__icontains=busqueda)
        )

    if app_filtro:
        permisos = permisos.filter(content_type__app_label=app_filtro)

    permisos_por_app = {}
    for p in permisos.order_by('content_type__app_label', 'content_type__model', 'codename'):
        app   = p.content_type.app_label
        model = p.content_type.model
        permisos_por_app.setdefault(app, {}).setdefault(model, []).append(p)

    aplicaciones = ContentType.objects.values_list(
        'app_label', flat=True
    ).distinct().order_by('app_label')

    return render(request, 'usuarios/lista_permisos.html', {
        'active_page':      'admin',
        'permisos_por_app': permisos_por_app,
        'busqueda':         busqueda,
        'app_filtro':       app_filtro,
        'aplicaciones':     aplicaciones,
    })


@login_required
@user_passes_test(is_superuser)
def crear_permiso(request):
    """Crear un nuevo permiso personalizado (solo superusuario)"""
    if request.method == 'POST':
        form = PermisoForm(request.POST)
        if form.is_valid():
            modulo = form.cleaned_data['modulo']
            nombre = form.cleaned_data['nombre']
            codigo = form.cleaned_data['codigo']
            try:
                Permission.objects.create(name=nombre, codename=codigo, content_type=modulo)
                messages.success(request, f'Permiso "{nombre}" creado correctamente con código "{codigo}".')
                return redirect('usuarios:lista_permisos')
            except Exception as e:
                messages.error(request, f'Error al crear el permiso: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PermisoForm()

    return render(request, 'usuarios/form_permiso.html', {
        'active_page': 'admin',
        'form':   form,
        'titulo': 'Crear Nuevo Permiso',
    })


@login_required
@user_passes_test(is_superuser)
def editar_permiso(request, permiso_id):
    """Editar un permiso existente (solo superusuario)"""
    permiso = get_object_or_404(Permission, id=permiso_id)

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        if nombre:
            permiso.name = nombre
            permiso.save()
            messages.success(request, 'Permiso actualizado correctamente.')
            return redirect('usuarios:lista_permisos')
        else:
            messages.error(request, 'El nombre del permiso es obligatorio.')

    return render(request, 'usuarios/editar_permiso.html', {
        'active_page': 'admin',
        'permiso': permiso,
        'titulo':  f'Editar Permiso: {permiso.codename}',
    })


@login_required
@user_passes_test(is_superuser)
def eliminar_permiso(request, permiso_id):
    """Eliminar un permiso personalizado (solo superusuario)"""
    permiso = get_object_or_404(Permission, id=permiso_id)
    usuarios_con_permiso = Usuario.objects.filter(user_permissions=permiso).count()

    if request.method == 'POST':
        nombre = permiso.name
        codigo = permiso.codename
        try:
            permiso.delete()
            messages.success(request, f'Permiso "{nombre}" ({codigo}) eliminado correctamente.')
        except Exception as e:
            messages.error(request, f'Error al eliminar el permiso: {str(e)}')
        return redirect('usuarios:lista_permisos')

    return render(request, 'usuarios/confirmar_eliminar_permiso.html', {
        'active_page':          'admin',
        'permiso':              permiso,
        'usuarios_con_permiso': usuarios_con_permiso,
    })


# ══════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ══════════════════════════════════════════════

def organizar_permisos():
    """
    Organiza todos los permisos del sistema por aplicación y modelo
    para mostrarlos de forma estructurada en los formularios.
    """
    permisos_organizados = {}

    for ct in ContentType.objects.all().order_by('app_label', 'model'):
        app   = ct.app_label
        model = ct.model

        if app not in permisos_organizados:
            permisos_organizados[app] = {
                'nombre':         app.replace('_', ' ').title(),
                'modelos':        {},
                'total_permisos': 0,
            }

        if model not in permisos_organizados[app]['modelos']:
            permisos_organizados[app]['modelos'][model] = {
                'nombre':   model.replace('_', ' ').title(),
                'permisos': [],
            }

        for p in Permission.objects.filter(content_type=ct).order_by('codename'):
            permisos_organizados[app]['modelos'][model]['permisos'].append({
                'id':     p.id,
                'nombre': p.name,
                'codigo': p.codename,
                'objeto': p,
            })
            permisos_organizados[app]['total_permisos'] += 1

    return permisos_organizados


def obtener_permisos_por_categoria():
    """
    Agrupa los permisos en categorías CRUD
    para facilitar su asignación masiva.
    """
    categorias = {'crear': [], 'ver': [], 'editar': [], 'eliminar': [], 'otros': []}

    for p in Permission.objects.all().select_related('content_type'):
        codigo = p.codename.lower()
        if any(x in codigo for x in ('add', 'crear', 'create')):
            categorias['crear'].append(p)
        elif any(x in codigo for x in ('view', 'ver', 'list')):
            categorias['ver'].append(p)
        elif any(x in codigo for x in ('change', 'edit', 'modificar', 'actualizar')):
            categorias['editar'].append(p)
        elif any(x in codigo for x in ('delete', 'eliminar', 'remove')):
            categorias['eliminar'].append(p)
        else:
            categorias['otros'].append(p)

    return categorias
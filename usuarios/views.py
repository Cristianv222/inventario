from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Permission, ContentType
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q
from .models import Usuario
from .forms import (
    CustomAuthenticationForm, CustomPasswordChangeForm, 
    UsuarioForm, PermisoForm
)

# ============================================
# FUNCIONES DE VERIFICACIÓN DE PERMISOS
# ============================================

def is_admin(user):
    """Verifica si el usuario es administrador (staff o superuser)"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)

def is_superuser(user):
    """Verifica si el usuario es superusuario (acceso total)"""
    return user.is_authenticated and user.is_superuser

# ============================================
# VISTAS DE AUTENTICACIÓN
# ============================================

def login_view(request):
    """Vista de inicio de sesión"""
    if request.user.is_authenticated:
        return redirect('core:dashboard')
        
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            usuario = form.cleaned_data.get('username')
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

@login_required
def cambiar_password(request):
    """Vista para cambiar la contraseña del usuario actual"""
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Mantener la sesión activa después de cambiar la contraseña
            update_session_auth_hash(request, user)
            messages.success(request, 'Tu contraseña ha sido actualizada correctamente.')
            return redirect('core:dashboard')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'usuarios/cambiar_password.html', {
        'form': form,
        'titulo': 'Cambiar Contraseña'
    })

# ============================================
# GESTIÓN DE USUARIOS
# ============================================

@login_required
@user_passes_test(is_admin)
def lista_usuarios(request):
    """Lista todos los usuarios del sistema"""
    # Obtener parámetros de búsqueda y filtrado
    busqueda = request.GET.get('buscar', '')
    filtro_estado = request.GET.get('estado', '')
    
    # Query base
    usuarios = Usuario.objects.all().prefetch_related('user_permissions', 'groups')
    
    # Aplicar búsqueda
    if busqueda:
        usuarios = usuarios.filter(
            Q(usuario__icontains=busqueda) |
            Q(nombre__icontains=busqueda) |
            Q(apellido__icontains=busqueda) |
            Q(email__icontains=busqueda)
        )
    
    # Aplicar filtro de estado
    if filtro_estado == 'activos':
        usuarios = usuarios.filter(activo=True)
    elif filtro_estado == 'inactivos':
        usuarios = usuarios.filter(activo=False)
    elif filtro_estado == 'admin':
        usuarios = usuarios.filter(is_staff=True)
    elif filtro_estado == 'superuser':
        usuarios = usuarios.filter(is_superuser=True)
    
    # Ordenar
    usuarios = usuarios.order_by('-fecha_creacion')
    
    return render(request, 'usuarios/lista_usuarios.html', {
        'usuarios': usuarios,
        'busqueda': busqueda,
        'filtro_estado': filtro_estado
    })

@login_required
@user_passes_test(is_admin)
def crear_usuario(request):
    """Crear un nuevo usuario con sus permisos"""
    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            
            # Asignar permisos seleccionados
            permisos_ids = request.POST.getlist('permisos')
            if permisos_ids:
                usuario.user_permissions.set(permisos_ids)
            
            messages.success(
                request, 
                f'Usuario "{usuario.usuario}" creado correctamente con {len(permisos_ids)} permisos asignados.'
            )
            return redirect('usuarios:lista_usuarios')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = UsuarioForm()
    
    # Organizar permisos por aplicación y modelo para mejor visualización
    permisos_organizados = organizar_permisos()
    
    return render(request, 'usuarios/form_usuario.html', {
        'form': form,
        'titulo': 'Crear Nuevo Usuario',
        'permisos_organizados': permisos_organizados,
        'usuario': None,
        'permisos_usuario_ids': []
    })

@login_required
@user_passes_test(is_admin)
def editar_usuario(request, user_id):
    """Editar un usuario existente y sus permisos"""
    usuario = get_object_or_404(Usuario, id=user_id)
    
    # Prevenir que un usuario se edite a sí mismo ciertos campos críticos
    es_el_mismo = request.user.id == usuario.id
    
    if request.method == 'POST':
        # ===== DEBUGGING =====
        print("=" * 80)
        print("DEBUGGING EDITAR USUARIO")
        print("=" * 80)
        print(f"Usuario a editar: {usuario.usuario} (ID: {usuario.id})")
        print(f"Permisos actuales: {usuario.user_permissions.count()}")
        print("-" * 80)
        print("POST Data completo:")
        for key, value in request.POST.items():
            if key != 'csrfmiddlewaretoken':
                print(f"  {key}: {value}")
        print("-" * 80)
        permisos_recibidos = request.POST.getlist('permisos')
        print(f"Permisos recibidos (getlist): {permisos_recibidos}")
        print(f"Cantidad de permisos: {len(permisos_recibidos)}")
        print(f"Tipo de datos: {type(permisos_recibidos)}")
        if permisos_recibidos:
            print(f"Primer permiso (ejemplo): {permisos_recibidos[0]} (tipo: {type(permisos_recibidos[0])})")
        print("=" * 80)
        # ===== FIN DEBUGGING =====
        
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            # Validación: No permitir que un usuario se desactive a sí mismo
            if es_el_mismo and not form.cleaned_data.get('activo'):
                messages.error(request, 'No puedes desactivar tu propia cuenta.')
                return redirect('usuarios:editar_usuario', user_id=user_id)
            
            # Validación: No permitir que un usuario se quite permisos de admin
            if es_el_mismo and not form.cleaned_data.get('is_staff') and not form.cleaned_data.get('is_superuser'):
                messages.error(request, 'No puedes quitarte tus propios permisos de administrador.')
                return redirect('usuarios:editar_usuario', user_id=user_id)
            
            usuario = form.save()
            
            # Actualizar permisos seleccionados
            permisos_ids = request.POST.getlist('permisos')
            
            # ===== MÁS DEBUGGING =====
            print("-" * 80)
            print("DESPUÉS DE form.save():")
            print(f"Usuario guardado: {usuario.usuario}")
            print(f"Permisos IDs a asignar: {permisos_ids}")
            print(f"Tipo: {type(permisos_ids)}")
            print("-" * 80)
            # ===== FIN DEBUGGING =====
            
            usuario.user_permissions.set(permisos_ids)
            
            # ===== VERIFICACIÓN FINAL =====
            print("DESPUÉS DE user_permissions.set():")
            print(f"Permisos en BD: {usuario.user_permissions.count()}")
            permisos_guardados = list(usuario.user_permissions.values_list('id', 'codename'))
            print(f"Primeros 5 permisos guardados: {permisos_guardados[:5]}")
            print("=" * 80)
            # ===== FIN DEBUGGING =====
            
            messages.success(
                request, 
                f'Usuario "{usuario.usuario}" actualizado correctamente con {len(permisos_ids)} permisos.'
            )
            return redirect('usuarios:lista_usuarios')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
            print("ERRORES DEL FORMULARIO:", form.errors)
    else:
        form = UsuarioForm(instance=usuario)
    
    # Organizar permisos
    permisos_organizados = organizar_permisos()
    
    # Obtener IDs de permisos del usuario
    permisos_usuario_ids = list(usuario.user_permissions.values_list('id', flat=True))
    
    return render(request, 'usuarios/form_usuario.html', {
        'form': form,
        'titulo': f'Editar Usuario: {usuario.usuario}',
        'permisos_organizados': permisos_organizados,
        'usuario': usuario,
        'es_el_mismo': es_el_mismo,
        'permisos_usuario_ids': permisos_usuario_ids
    })

@login_required
@user_passes_test(is_admin)
def activar_desactivar_usuario(request, user_id):
    """Activar o desactivar un usuario"""
    usuario = get_object_or_404(Usuario, id=user_id)
    
    # No permitir que un usuario se desactive a sí mismo
    if request.user.id == usuario.id:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('usuarios:lista_usuarios')
    
    # Cambiar estado
    usuario.activo = not usuario.activo
    usuario.save()
    
    estado = "activado" if usuario.activo else "desactivado"
    messages.success(request, f'Usuario "{usuario.usuario}" {estado} correctamente.')
    
    return redirect('usuarios:lista_usuarios')

@login_required
@user_passes_test(is_admin)
def eliminar_usuario(request, user_id):
    """Eliminar un usuario (opcional - puedes usar solo activar/desactivar)"""
    usuario = get_object_or_404(Usuario, id=user_id)
    
    # No permitir que un usuario se elimine a sí mismo
    if request.user.id == usuario.id:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')
        return redirect('usuarios:lista_usuarios')
    
    # No permitir eliminar superusuarios (medida de seguridad)
    if usuario.is_superuser:
        messages.error(request, 'No se pueden eliminar cuentas de super administrador.')
        return redirect('usuarios:lista_usuarios')
    
    if request.method == 'POST':
        nombre_usuario = usuario.usuario
        usuario.delete()
        messages.success(request, f'Usuario "{nombre_usuario}" eliminado correctamente.')
        return redirect('usuarios:lista_usuarios')
    
    return render(request, 'usuarios/confirmar_eliminar_usuario.html', {
        'usuario': usuario
    })

@login_required
@user_passes_test(is_admin)
def ver_permisos_usuario(request, user_id):
    """Ver todos los permisos de un usuario específico"""
    usuario = get_object_or_404(Usuario, id=user_id)
    
    # Obtener permisos del usuario
    permisos_usuario = usuario.user_permissions.all().select_related('content_type').order_by(
        'content_type__app_label', 
        'content_type__model', 
        'codename'
    )
    
    # Organizar permisos por aplicación
    permisos_por_app = {}
    for permiso in permisos_usuario:
        app = permiso.content_type.app_label
        model = permiso.content_type.model
        
        if app not in permisos_por_app:
            permisos_por_app[app] = {}
        
        if model not in permisos_por_app[app]:
            permisos_por_app[app][model] = []
        
        permisos_por_app[app][model].append(permiso)
    
    return render(request, 'usuarios/ver_permisos_usuario.html', {
        'usuario': usuario,
        'permisos_por_app': permisos_por_app,
        'total_permisos': permisos_usuario.count()
    })

# ============================================
# GESTIÓN DE PERMISOS
# ============================================

@login_required
@user_passes_test(is_superuser)
def lista_permisos(request):
    """Lista todos los permisos disponibles en el sistema (solo superusuario)"""
    # Obtener parámetros de búsqueda
    busqueda = request.GET.get('buscar', '')
    app_filtro = request.GET.get('app', '')
    
    # Query base
    permisos = Permission.objects.all().select_related('content_type')
    
    # Aplicar búsqueda
    if busqueda:
        permisos = permisos.filter(
            Q(name__icontains=busqueda) |
            Q(codename__icontains=busqueda) |
            Q(content_type__model__icontains=busqueda)
        )
    
    # Filtrar por aplicación
    if app_filtro:
        permisos = permisos.filter(content_type__app_label=app_filtro)
    
    # Organizar permisos por aplicación y modelo
    permisos_por_app = {}
    for permiso in permisos.order_by('content_type__app_label', 'content_type__model', 'codename'):
        app = permiso.content_type.app_label
        model = permiso.content_type.model
        
        if app not in permisos_por_app:
            permisos_por_app[app] = {}
        
        if model not in permisos_por_app[app]:
            permisos_por_app[app][model] = []
        
        permisos_por_app[app][model].append(permiso)
    
    # Obtener lista de aplicaciones para el filtro
    aplicaciones = ContentType.objects.values_list('app_label', flat=True).distinct().order_by('app_label')
    
    return render(request, 'usuarios/lista_permisos.html', {
        'permisos_por_app': permisos_por_app,
        'busqueda': busqueda,
        'app_filtro': app_filtro,
        'aplicaciones': aplicaciones
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
                # Crear el permiso
                permiso = Permission.objects.create(
                    name=nombre,
                    codename=codigo,
                    content_type=modulo
                )
                
                messages.success(
                    request, 
                    f'Permiso "{nombre}" creado correctamente con código "{codigo}".'
                )
                return redirect('usuarios:lista_permisos')
            
            except Exception as e:
                messages.error(request, f'Error al crear el permiso: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PermisoForm()
    
    return render(request, 'usuarios/form_permiso.html', {
        'form': form,
        'titulo': 'Crear Nuevo Permiso'
    })

@login_required
@user_passes_test(is_superuser)
def editar_permiso(request, permiso_id):
    """Editar un permiso existente (solo superusuario)"""
    permiso = get_object_or_404(Permission, id=permiso_id)
    
    if request.method == 'POST':
        # Obtener datos del formulario
        nombre = request.POST.get('nombre')
        
        if nombre:
            permiso.name = nombre
            permiso.save()
            messages.success(request, f'Permiso actualizado correctamente.')
            return redirect('usuarios:lista_permisos')
        else:
            messages.error(request, 'El nombre del permiso es obligatorio.')
    
    return render(request, 'usuarios/editar_permiso.html', {
        'permiso': permiso,
        'titulo': f'Editar Permiso: {permiso.codename}'
    })

@login_required
@user_passes_test(is_superuser)
def eliminar_permiso(request, permiso_id):
    """Eliminar un permiso personalizado (solo superusuario)"""
    permiso = get_object_or_404(Permission, id=permiso_id)
    
    # Verificar cuántos usuarios tienen este permiso
    usuarios_con_permiso = Usuario.objects.filter(user_permissions=permiso).count()
    
    if request.method == 'POST':
        nombre_permiso = permiso.name
        codigo_permiso = permiso.codename
        
        try:
            permiso.delete()
            messages.success(
                request, 
                f'Permiso "{nombre_permiso}" ({codigo_permiso}) eliminado correctamente.'
            )
        except Exception as e:
            messages.error(request, f'Error al eliminar el permiso: {str(e)}')
        
        return redirect('usuarios:lista_permisos')
    
    return render(request, 'usuarios/confirmar_eliminar_permiso.html', {
        'permiso': permiso,
        'usuarios_con_permiso': usuarios_con_permiso
    })

# ============================================
# FUNCIONES AUXILIARES
# ============================================

def organizar_permisos():
    """
    Organiza todos los permisos del sistema por aplicación y modelo
    para mostrarlos de forma estructurada en los formularios
    """
    permisos_organizados = {}
    
    # Obtener todos los ContentTypes ordenados
    content_types = ContentType.objects.all().order_by('app_label', 'model')
    
    for ct in content_types:
        app_label = ct.app_label
        model_name = ct.model
        
        # Inicializar diccionario de app si no existe
        if app_label not in permisos_organizados:
            permisos_organizados[app_label] = {
                'nombre': app_label.replace('_', ' ').title(),
                'modelos': {},
                'total_permisos': 0
            }
        
        # Inicializar lista de permisos para el modelo si no existe
        if model_name not in permisos_organizados[app_label]['modelos']:
            permisos_organizados[app_label]['modelos'][model_name] = {
                'nombre': model_name.replace('_', ' ').title(),
                'permisos': []
            }
        
        # Obtener permisos para este ContentType
        permisos = Permission.objects.filter(content_type=ct).order_by('codename')
        
        # Agregar permisos con información detallada
        for permiso in permisos:
            permisos_organizados[app_label]['modelos'][model_name]['permisos'].append({
                'id': permiso.id,
                'nombre': permiso.name,
                'codigo': permiso.codename,
                'objeto': permiso
            })
            # Incrementar contador total de permisos por app
            permisos_organizados[app_label]['total_permisos'] += 1
    
    return permisos_organizados

def obtener_permisos_por_categoria():
    """
    Agrupa los permisos en categorías comunes (CRUD)
    para facilitar su asignación masiva
    """
    categorias = {
        'crear': [],
        'ver': [],
        'editar': [],
        'eliminar': [],
        'otros': []
    }
    
    permisos = Permission.objects.all().select_related('content_type')
    
    for permiso in permisos:
        codigo = permiso.codename.lower()
        
        if 'add' in codigo or 'crear' in codigo or 'create' in codigo:
            categorias['crear'].append(permiso)
        elif 'view' in codigo or 'ver' in codigo or 'list' in codigo:
            categorias['ver'].append(permiso)
        elif 'change' in codigo or 'edit' in codigo or 'modificar' in codigo or 'actualizar' in codigo:
            categorias['editar'].append(permiso)
        elif 'delete' in codigo or 'eliminar' in codigo or 'remove' in codigo:
            categorias['eliminar'].append(permiso)
        else:
            categorias['otros'].append(permiso)
    
    return categorias
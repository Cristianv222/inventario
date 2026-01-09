from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages

class RoleMiddleware:
    """
    Middleware que verifica permisos de usuarios.
    Trabaja directamente con permisos asignados al usuario (sin roles).
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Mapeo de URLs a permisos requeridos
        self.url_to_permission = {
            # Usuarios
            '/usuarios/usuarios/': ['view_usuario', 'change_usuario'],
            '/usuarios/usuarios/nuevo/': ['add_usuario'],
            '/usuarios/permisos/': ['view_permission'],
            '/usuarios/permisos/crear/': ['add_permission'],
            
            # Inventario
            '/inventario/': ['view_producto'],
            '/inventario/producto/nuevo/': ['add_producto'],
            '/inventario/producto/form/': ['add_producto'],
            '/inventario/categorias/': ['view_categoriaproducto'],
            '/inventario/categoria/nueva/': ['add_categoriaproducto'],
            '/inventario/marcas/': ['view_marca'],
            '/inventario/marca/nueva/': ['add_marca'],
            '/inventario/ajustes/': ['view_ajusteinventario', 'change_producto'],
            '/inventario/ajuste/nuevo/': ['add_ajusteinventario'],
            
            # Ventas
            '/ventas/': ['view_venta'],
            '/ventas/pos/': ['add_venta'],
            '/ventas/nueva/': ['add_venta'],
            
            # Clientes
            '/clientes/': ['view_cliente'],
            '/clientes/nuevo/': ['add_cliente'],
            
            # Taller
            '/taller/': ['view_ordentrabajo'],
            '/taller/ordenes/crear/': ['add_ordentrabajo'],
            '/taller/tecnicos/': ['view_tecnico'],
            '/taller/servicios/': ['view_servicio'],
            
            # Reportes - TODOS requieren ser admin o staff
            '/reportes/': 'ADMIN_ONLY',
            '/reportes/caja/': 'ADMIN_ONLY',
            '/reportes/gastos/': 'ADMIN_ONLY',
            '/reportes/estadisticas/': 'ADMIN_ONLY',
            '/reportes/inventario/': 'ADMIN_ONLY',
            '/reportes/ventas/': 'ADMIN_ONLY',
        }
    
    def __call__(self, request):
        # Rutas que NO requieren verificación
        exempt_paths = [
            '/admin/', 
            '/usuarios/login/', 
            '/usuarios/logout/',
            '/usuarios/cambiar-password/',
            '/static/',
            '/media/',
            '/favicon.ico',
        ]
        
        # Verificar si está en una ruta exenta
        for path in exempt_paths:
            if request.path.startswith(path):
                return self.get_response(request)
        
        # Verificar si el usuario está autenticado
        if not request.user.is_authenticated:
            if not request.path.startswith('/usuarios/login/'):
                return redirect(reverse('usuarios:login'))
            return self.get_response(request)
        
        # Verificar si el usuario está activo
        if not request.user.activo:
            messages.error(request, '⛔ Tu cuenta está inactiva. Contacta al administrador.')
            return redirect(reverse('usuarios:login'))
        
        # Dashboard siempre permitido para usuarios autenticados
        if request.path == '/':
            return self.get_response(request)
        
        # Superusuarios tienen acceso a TODO
        if request.user.is_superuser:
            return self.get_response(request)
        
        # Staff/Administradores tienen acceso a TODO
        if request.user.is_staff:
            return self.get_response(request)
        
        # APIs generalmente permitidas (se controlan en la vista)
        if '/api/' in request.path:
            return self.get_response(request)
        
        # Verificar permisos según la URL
        required_permissions = self.get_required_permissions(request.path)
        
        if required_permissions:
            # Si es ADMIN_ONLY (solo para administradores/staff)
            if required_permissions == 'ADMIN_ONLY':
                messages.error(
                    request, 
                    '⛔ Esta sección es solo para administradores.'
                )
                return redirect(reverse('core:dashboard'))
            
            # Verificar si tiene AL MENOS UNO de los permisos requeridos
            has_permission = False
            missing_permissions = []
            
            for perm in required_permissions:
                if self.user_has_permission(request.user, perm):
                    has_permission = True
                    break
                else:
                    missing_permissions.append(perm)
            
            if not has_permission:
                # Traducir nombres de permisos a español
                perm_names = {
                    'view': 'Ver',
                    'add': 'Crear',
                    'change': 'Modificar',
                    'delete': 'Eliminar',
                }
                
                # Obtener el nombre del modelo del primer permiso
                if missing_permissions:
                    first_perm = missing_permissions[0]
                    parts = first_perm.split('_')
                    action = parts[0]
                    model = ' '.join(parts[1:]) if len(parts) > 1 else 'recurso'
                    
                    action_es = perm_names.get(action, action)
                    
                    messages.error(
                        request, 
                        f'⛔ No tienes permiso para acceder a esta sección. '
                        f'Se requiere: {action_es} {model.title()}'
                    )
                else:
                    messages.error(request, '⛔ No tienes los permisos necesarios para esta acción.')
                
                return redirect(reverse('core:dashboard'))
        
        # Permitir acceso
        return self.get_response(request)
    
    def get_required_permissions(self, path):
        """
        Obtiene los permisos requeridos para una ruta.
        Retorna lista de permisos o 'ADMIN_ONLY' o None.
        """
        # Buscar coincidencia exacta primero
        if path in self.url_to_permission:
            perm = self.url_to_permission[path]
            if perm == 'ADMIN_ONLY':
                return 'ADMIN_ONLY'
            return perm if isinstance(perm, list) else [perm]
        
        # Buscar coincidencia por prefijo (más específica primero)
        # Ordenar por longitud descendente para que /inventario/producto/ coincida antes que /inventario/
        sorted_urls = sorted(self.url_to_permission.keys(), key=len, reverse=True)
        
        for url_pattern in sorted_urls:
            if path.startswith(url_pattern):
                perm = self.url_to_permission[url_pattern]
                if perm == 'ADMIN_ONLY':
                    return 'ADMIN_ONLY'
                return perm if isinstance(perm, list) else [perm]
        
        # Detectar automáticamente para URLs con /editar/ o /eliminar/
        if '/editar/' in path:
            # Extraer el módulo de la URL
            parts = path.strip('/').split('/')
            if parts:
                module = parts[0]
                return [f'change_{module}']
        
        if '/eliminar/' in path or '/activar/' in path:
            parts = path.strip('/').split('/')
            if parts:
                module = parts[0]
                return [f'delete_{module}']
        
        # No se encontró permiso específico - permitir (la vista debe tener su propio control)
        return None
    
    def user_has_permission(self, user, permission_codename):
        """
        Verifica si el usuario tiene un permiso específico.
        Ahora verifica directamente los permisos del usuario (sin roles).
        """
        if not user.is_authenticated:
            return False
        
        # Superusuarios tienen todos los permisos
        if user.is_superuser:
            return True
        
        # Staff tiene la mayoría de permisos
        if user.is_staff:
            return True
        
        # ✅ CORRECCIÓN: Cambiar de user.permisos a user.user_permissions
        return user.user_permissions.filter(codename=permission_codename).exists()
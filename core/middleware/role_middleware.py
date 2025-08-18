from django.shortcuts import redirect
from django.urls import reverse

class RoleMiddleware:
    """
    Middleware para controlar acceso a vistas según el rol del usuario.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Definir rutas permitidas por rol
        self.role_paths = {
            'Administrador': [
                '/usuarios/', '/inventario/', '/ventas/', '/taller/', '/clientes/', 
                '/compras/', '/reportes/', '/'
            ],
            'Vendedor': [
                '/ventas/', '/clientes/', '/inventario/buscar-producto/', 
                '/inventario/scanner/', '/'
            ],
            'Técnico': [
                '/taller/', '/clientes/', '/inventario/buscar-producto/', 
                '/inventario/scanner/', '/'
            ],
            'Bodeguero': [
                '/inventario/', '/compras/', '/'
            ],
        }
    
    def __call__(self, request):
        # No verificar en estas rutas
        exempt_paths = [
            '/admin/', 
            '/usuarios/login/', 
            '/usuarios/logout/'
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
        
        # Si es staff o superuser, permitir todo
        if request.user.is_staff or request.user.is_superuser:
            return self.get_response(request)
        
        # Verificar permisos por rol
        if request.user.rol:
            rol_nombre = request.user.rol.nombre
            allowed_paths = self.role_paths.get(rol_nombre, [])
            
            # Verificar si la ruta actual está permitida para este rol
            for allowed_path in allowed_paths:
                if request.path.startswith(allowed_path):
                    return self.get_response(request)
            
            # Si no tiene permiso, redirigir al dashboard
            return redirect(reverse('core:dashboard'))
        
        # Por defecto, permitir el acceso
        return self.get_response(request)
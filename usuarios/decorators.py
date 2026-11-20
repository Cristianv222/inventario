from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from functools import wraps

def permiso_requerido(codename):
    """
    Decorador para verificar si un usuario tiene un permiso específico basado en su rol
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            # Superusuarios pueden acceder a todo
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
                
            # Verificar si el usuario tiene el permiso requerido
            if hasattr(request.user, 'tiene_permiso') and request.user.tiene_permiso(codename):
                return view_func(request, *args, **kwargs)
                
            # Si no tiene permiso, mostrar error 403
            raise PermissionDenied("No tienes permiso para acceder a esta página.")
        return wrapper
    return decorator


def admin_requerido(view_func):
    """Permite el acceso solo a administradores (is_staff o is_superuser)."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Solo los administradores pueden acceder a esta página.")
    return wrapper
from django.shortcuts import redirect
from django.urls import reverse


class ForzarCambioPasswordMiddleware:
    """Si un usuario autenticado tiene debe_cambiar_password=True, lo obliga a
    ir a la pantalla de cambio de contraseña antes de usar el sistema."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and getattr(user, 'debe_cambiar_password', False):
            path = request.path
            try:
                permitidos = {
                    reverse('usuarios:cambiar_password_obligatorio'),
                    reverse('usuarios:logout'),
                }
            except Exception:
                permitidos = set()
            if (path not in permitidos
                    and path not in ('/manifest.json', '/manifest-tecnico.json', '/sw.js')
                    and not path.startswith('/static/')
                    and not path.startswith('/media/')
                    and not path.startswith('/admin/')):
                return redirect('usuarios:cambiar_password_obligatorio')
        return self.get_response(request)

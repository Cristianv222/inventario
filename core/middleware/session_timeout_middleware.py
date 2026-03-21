from django.utils import timezone
from django.contrib.auth import logout
from django.shortcuts import redirect

class MidnightLogoutMiddleware:
    """
    Middleware que cierra la sesión de los usuarios automáticamente a la medianoche.
    Rastrea la fecha del último acceso en la sesión y, si el día ha cambiado, 
    fuerza el cierre de sesión.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Obtener la fecha actual en la zona horaria del sistema
            current_date = timezone.now().date()
            
            # Obtener la fecha guardada en la sesión
            last_session_date = request.session.get('last_session_date')
            
            if last_session_date:
                # Si la fecha guardada es distinta a la actual, es un nuevo día
                if str(current_date) != last_session_date:
                    logout(request)
                    return redirect('usuarios:login')
            
            # Actualizar la fecha de la sesión
            request.session['last_session_date'] = str(current_date)

        response = self.get_response(request)
        return response

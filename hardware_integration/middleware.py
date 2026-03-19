# apps/hardware_integration/middleware.py

from django.utils.deprecation import MiddlewareMixin


class CsrfExemptAgenteMiddleware(MiddlewareMixin):
    """
    Excluye las rutas de la API del agente del CSRF check.
    El agente usa autenticación por Token, no necesita CSRF.
    """
    
    def process_request(self, request):
        # Rutas exentas de CSRF
        exempt_paths = [
            '/api/hardware/agente/registrar/',
            '/api/hardware/agente/trabajos/',
            '/api/hardware/agente/resultado/',
            '/api/hardware/agente/estado/',
        ]
        
        # Marcar como exenta si coincide
        if any(request.path.startswith(path) for path in exempt_paths):
            setattr(request, '_dont_enforce_csrf_checks', True)
        
        return None
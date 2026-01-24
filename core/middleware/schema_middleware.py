"""
Middleware para aplicar el schema de PostgreSQL automáticamente
según la sucursal del usuario autenticado
"""
from django.db import connection
from django.utils.deprecation import MiddlewareMixin
from django_tenants.utils import get_public_schema_name


class AutoSchemaMiddleware(MiddlewareMixin):
    """
    Middleware que aplica automáticamente el schema de PostgreSQL
    basado en la sucursal del usuario
    """
    
    def process_request(self, request):
        """
        Aplicar schema antes de procesar la request
        """
        # Solo procesar si el usuario está autenticado
        if not request.user.is_authenticated:
            return None
        
        # Determinar qué schema usar
        schema_name = self._get_schema_for_user(request.user)
        
        # Aplicar el schema
        if schema_name:
            try:
                connection.set_schema(schema_name)
                request.schema_name = schema_name
            except Exception as e:
                # Si hay error al aplicar schema, usar el público
                connection.set_schema(get_public_schema_name())
                request.schema_name = get_public_schema_name()
        
        return None
    
    def _get_schema_for_user(self, user):
        """
        Determinar qué schema usar para el usuario
        """
        # Admin general o puede ver todas: usar schema público
        if user.is_superuser or getattr(user, 'puede_ver_todas_sucursales', False):
            return get_public_schema_name()
        
        # Si tiene sucursal asignada: usar schema de esa sucursal
        if hasattr(user, 'sucursal') and user.sucursal:
            return user.sucursal.schema_name
        
        # Por defecto: schema público
        return get_public_schema_name()
    
    def process_response(self, request, response):
        """
        Limpiar schema después de procesar la request
        """
        # Volver al schema público después de cada request
        try:
            connection.set_schema(get_public_schema_name())
        except Exception:
            pass
        
        if hasattr(request, 'schema_name'):
            delattr(request, 'schema_name')
        
        return response
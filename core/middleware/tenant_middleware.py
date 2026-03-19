"""
Middleware para detectar la sucursal del usuario y aplicar el schema correspondiente
"""
from django.utils.deprecation import MiddlewareMixin
from django_tenants.utils import get_tenant_model, get_public_schema_name


class TenantFromUserMiddleware(MiddlewareMixin):
    """
    Middleware que detecta la sucursal del usuario autenticado
    y establece el tenant (schema) correspondiente
    """
    
    def process_request(self, request):
        """
        Detectar sucursal del usuario y aplicar schema
        """
        # Solo procesar si el usuario está autenticado
        if not request.user.is_authenticated:
            return None
        
        # Si ya hay un tenant asignado por otro middleware, no hacer nada
        if hasattr(request, 'tenant') and request.tenant:
            return None
        
        # Obtener modelo de Tenant (Sucursal)
        TenantModel = get_tenant_model()
        
        # Si el usuario puede ver todas las sucursales, usar schema público
        if request.user.puede_ver_todas_sucursales or request.user.is_superuser:
            try:
                # Usar la sucursal principal (MATRIZ) para admin general
                tenant = TenantModel.objects.filter(es_principal=True).first()
                if tenant:
                    request.tenant = tenant
                    request.sucursal_actual = tenant
                    return None
            except Exception:
                pass
        
        # Si el usuario tiene sucursal asignada, usar ese schema
        if hasattr(request.user, 'sucursal') and request.user.sucursal:
            try:
                request.tenant = request.user.sucursal
                request.sucursal_actual = request.user.sucursal
                return None
            except Exception as e:
                # Si hay error, dejar que el siguiente middleware maneje
                pass
        
        # Si no se pudo determinar sucursal, continuar con el flujo normal
        return None
    
    def process_response(self, request, response):
        """
        Limpiar referencias al tenant después de procesar la request
        """
        if hasattr(request, 'tenant'):
            delattr(request, 'tenant')
        if hasattr(request, 'sucursal_actual'):
            delattr(request, 'sucursal_actual')
        
        return response
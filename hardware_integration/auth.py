from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
import logging

logger = logging.getLogger(__name__)


class CustomTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        from django.apps import apps
        
        # Log en DEBUG para evitar spam, pero mantener visibilidad en desarrollo
        logger.debug(f"Validating token: {key[:5]}...")
        
        try:
            Token = apps.get_model('authtoken', 'Token')
        except Exception as e:
            logger.error(f"Error loading Token model: {e}")
            raise AuthenticationFailed('Error de sistema en la validación.')
        
        try:
            # Validación directa del token
            token = Token.objects.select_related('user').get(key=key)
            
            # Verificar si el usuario está activo
            if not token.user.is_active:
                raise AuthenticationFailed('Usuario inactivo o bloqueado.')
                
            logger.debug(f"Auth success: {token.user.usuario}")
            return (token.user, token)
        except Exception as e:
            logger.warning(f"Invalid token or auth error: {key[:5]}... Error: {e}")
            raise AuthenticationFailed('Token inválido o expirado.')

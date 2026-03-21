from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class CustomTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        from django.apps import apps
        
        logger.error(f"=== AUTH DEBUG: schema={connection.schema_name}, key={key[:10]}")
        
        try:
            Token = apps.get_model('authtoken', 'Token')
            logger.error(f"=== Token model OK: {Token}")
        except Exception as e:
            logger.error(f"=== Error getting Token model: {e}")
            raise AuthenticationFailed(f'Error modelo: {e}')
        
        connection.set_schema_to_public()
        logger.error(f"=== Schema after set_public: {connection.schema_name}")
        
        try:
            token = Token.objects.select_related('user').get(key=key)
            logger.error(f"=== Token found: {token.user.usuario}")
            return (token.user, token)
        except Exception as e:
            logger.error(f"=== Token lookup error: {e}")
            raise AuthenticationFailed(f'Token inválido: {e}')

"""
Context processors para agregar información de sucursales
a todos los templates
"""


def sucursal_actual(request):
    """
    Context processor que agrega información de la sucursal actual
    a todos los templates. En modo esquema único, siempre busca la principal.
    """
    context = {
        'sucursal_actual': None,
        'es_admin_general': False,
        'puede_cambiar_sucursal': False,
        'nombre_sucursal': 'Matriz',
        'codigo_sucursal': 'MATRIZ',
    }
    
    # Solo procesar si el usuario está autenticado
    if not request.user.is_authenticated:
        return context
    
    # En modo sucursal única, la sucursal actual es siempre la principal
    from core.models import Sucursal
    try:
        sucursal = Sucursal.get_sucursal_principal()
        if sucursal:
            context['sucursal_actual'] = sucursal
            context['nombre_sucursal'] = sucursal.nombre_corto
            context['codigo_sucursal'] = sucursal.codigo
    except Exception:
        pass

    # MantenerFlags de compatibilidad
    if request.user.is_superuser or getattr(request.user, 'puede_ver_todas_sucursales', False):
        context['es_admin_general'] = True
    
    return context
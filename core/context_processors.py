"""
Context processors para agregar información de sucursales
a todos los templates
"""


def sucursal_actual(request):
    """
    Context processor que agrega información de la sucursal actual
    a todos los templates
    """
    context = {
        'sucursal_actual': None,
        'es_admin_general': False,
        'puede_cambiar_sucursal': False,
    }
    
    # Solo procesar si el usuario está autenticado
    if not request.user.is_authenticated:
        return context
    
    # Verificar si es admin general
    if request.user.is_superuser or getattr(request.user, 'puede_ver_todas_sucursales', False):
        context['es_admin_general'] = True
        context['puede_cambiar_sucursal'] = True
        
        # Intentar obtener la sucursal principal
        try:
            from core.models import Sucursal
            sucursal = Sucursal.objects.filter(es_principal=True).first()
            if sucursal:
                context['sucursal_actual'] = sucursal
        except Exception:
            pass
    
    # Si tiene sucursal asignada
    elif hasattr(request.user, 'sucursal') and request.user.sucursal:
        context['sucursal_actual'] = request.user.sucursal
        context['puede_cambiar_sucursal'] = False
    
    # Agregar información adicional
    if context['sucursal_actual']:
        context['nombre_sucursal'] = context['sucursal_actual'].nombre_corto
        context['codigo_sucursal'] = context['sucursal_actual'].codigo
    else:
        context['nombre_sucursal'] = 'Sin asignar'
        context['codigo_sucursal'] = 'N/A'
    
    return context
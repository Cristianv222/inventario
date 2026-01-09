from django import template

register = template.Library()

@register.filter(name="traducir_permiso")
def traducir_permiso(nombre):
    """Traduce nombres de permisos de inglés a español"""
    
    # Diccionario de traducciones
    traducciones = {
        # Acciones
        "Can add": "Puede crear",
        "Can change": "Puede editar",
        "Can delete": "Puede eliminar",
        "Can view": "Puede ver",
        
        # Modelos comunes
        "usuario": "usuarios",
        "user": "usuarios",
        "permission": "permisos",
        "group": "grupos",
        "content type": "tipos de contenido",
        "log entry": "registros de actividad",
        "session": "sesiones",
        
        # Tu aplicación
        "producto": "productos",
        "categoria": "categorías",
        "marca": "marcas",
        "cliente": "clientes",
        "venta": "ventas",
        "orden": "órdenes de trabajo",
        "servicio": "servicios",
        "tecnico": "técnicos",
        "reporte": "reportes",
        "ajuste": "ajustes",
        "movimiento": "movimientos",
        "caja": "caja",
        "gasto": "gastos",
        "cierre": "cierres",
    }
    
    # Convertir a minúsculas para comparar
    nombre_lower = nombre.lower()
    
    # Aplicar traducciones
    for ingles, espanol in traducciones.items():
        nombre_lower = nombre_lower.replace(ingles.lower(), espanol)
    
    # Capitalizar primera letra
    return nombre_lower.capitalize()
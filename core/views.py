from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db import connection

@login_required
def dashboard(request):
    """Vista del panel principal"""
    # Obtener la lista de tablas en la base de datos
    existing_tables = connection.introspection.table_names()
    
    # Valores predeterminados
    total_productos = 0
    total_clientes = 0
    
    # Verificar si las tablas existen y consultar solo si existen
    if 'inventario_producto' in existing_tables:
        from inventario.models import Producto
        total_productos = Producto.objects.filter(activo=True).count()
    
    if 'clientes_cliente' in existing_tables:
        from clientes.models import Cliente
        total_clientes = Cliente.objects.filter(activo=True).count()
    
    context = {
        'active_page': 'dashboard',
        'total_productos': total_productos,
        'total_clientes': total_clientes,
    }
    return render(request, 'core/dashboard.html', context)
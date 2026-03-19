"""
Views principales de VPMOTOS - App Core
Incluye: Dashboard + gestión completa de Sucursales (CRUD con AJAX/modales)
"""
import json
import re
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction, models
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods

from .models import Sucursal, DominioSucursal, ParametroSistema
from .forms import SucursalForm, DominioSucursalForm


# ══════════════════════════════════════════════
# UTILIDADES INTERNAS
# ══════════════════════════════════════════════

def json_response(success, data=None, errors=None, status=200):
    """Helper para respuestas JSON consistentes"""
    payload = {'success': success}
    if data:
        payload.update(data)
    if errors:
        payload['errors'] = errors
    return JsonResponse(payload, status=status)


def get_sucursal_data(sucursal):
    """Serializar una Sucursal a dict para respuestas AJAX"""
    return {
        'id':               sucursal.pk,
        'schema_name':      sucursal.schema_name,
        'codigo':           sucursal.codigo,
        'nombre':           sucursal.nombre,
        'nombre_corto':     sucursal.nombre_corto,
        'direccion':        sucursal.direccion,
        'ciudad':           sucursal.ciudad,
        'provincia':        sucursal.provincia,
        'telefono':         sucursal.telefono or '',
        'celular':          sucursal.celular or '',
        'email':            sucursal.email or '',
        'ruc':              sucursal.ruc or '',
        'nombre_comercial': sucursal.nombre_comercial or '',
        'es_principal':     sucursal.es_principal,
        'activa':           sucursal.activa,
        'prefijo_facturas': sucursal.prefijo_facturas or '',
        'prefijo_ordenes':  sucursal.prefijo_ordenes or '',
        'fecha_apertura':   sucursal.fecha_apertura.strftime('%Y-%m-%d') if sucursal.fecha_apertura else '',
        'fecha_cierre':     sucursal.fecha_cierre.strftime('%Y-%m-%d') if sucursal.fecha_cierre else '',
        'observaciones':    sucursal.observaciones or '',
        'usuarios_count':   sucursal.get_usuarios_count(),
        'direccion_completa': sucursal.get_direccion_completa(),
        'dominios':         list(sucursal.domains.values('id', 'domain', 'is_primary')),
    }


# ══════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════

@login_required
def dashboard(request):
    """Vista del panel principal"""
    existing_tables = connection.introspection.table_names()

    # Sucursales: viven en core, siempre disponibles
    total_sucursales = Sucursal.objects.filter(activa=True).count()

    # Módulos opcionales: consultar solo si la tabla existe
    total_productos = 0
    total_clientes  = 0
    total_ordenes   = 0
    total_facturas  = 0
    total_usuarios  = 0

    if 'inventario_producto' in existing_tables:
        from inventario.models import Producto
        total_productos = Producto.objects.filter(activo=True).count()

    if 'clientes_cliente' in existing_tables:
        from clientes.models import Cliente
        total_clientes = Cliente.objects.filter(activo=True).count()

    if 'ordenes_ordenservicio' in existing_tables:
        from ordenes.models import OrdenServicio
        total_ordenes = OrdenServicio.objects.filter(activo=True).count()

    if 'facturacion_factura' in existing_tables:
        from facturacion.models import Factura
        total_facturas = Factura.objects.filter(activo=True).count()

    if 'usuarios_usuario' in existing_tables:
        from usuarios.models import Usuario
        total_usuarios = Usuario.objects.filter(activo=True).count()

    context = {
        'active_page':      'dashboard',
        'total_sucursales': total_sucursales,
        'total_productos':  total_productos,
        'total_clientes':   total_clientes,
        'total_ordenes':    total_ordenes,
        'total_facturas':   total_facturas,
        'total_usuarios':   total_usuarios,
    }
    return render(request, 'core/dashboard.html', context)


# ══════════════════════════════════════════════
# SUCURSALES — VISTAS HTML
# ══════════════════════════════════════════════

class SucursalListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    Lista principal de sucursales.
    Renderiza la página con todos los modales incluidos.
    Las operaciones CRUD se hacen vía AJAX.
    """
    permission_required = 'core.view_sucursal'
    template_name = 'core/sucursales/sucursales.html'

    def get(self, request):
        sucursales = Sucursal.objects.all().order_by('-es_principal', 'nombre')
        provincias = Sucursal.objects.values_list('provincia', flat=True).distinct().order_by('provincia')
        ciudades   = Sucursal.objects.values_list('ciudad', flat=True).distinct().order_by('ciudad')

        context = {
            'active_page': 'sucursales',
            'sucursales':  sucursales,
            'provincias':  provincias,
            'ciudades':    ciudades,
            'total':       sucursales.count(),
            'activas':     sucursales.filter(activa=True).count(),
            'inactivas':   sucursales.filter(activa=False).count(),
            'can_add':     request.user.has_perm('core.add_sucursal'),
            'can_change':  request.user.has_perm('core.change_sucursal'),
            'can_delete':  request.user.has_perm('core.delete_sucursal'),
        }
        return render(request, self.template_name, context)


class SucursalDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Vista de detalle de una sucursal con sus dominios"""
    permission_required = 'core.view_sucursal'
    template_name = 'core/sucursales/sucursal_detail.html'

    def get(self, request, pk):
        sucursal = get_object_or_404(Sucursal, pk=pk)
        dominios = sucursal.domains.all().order_by('-is_primary', 'domain')
        context = {
            'active_page': 'sucursales',
            'sucursal':    sucursal,
            'dominios':    dominios,
            'can_change':  request.user.has_perm('core.change_sucursal'),
            'can_delete':  request.user.has_perm('core.delete_sucursal'),
        }
        return render(request, self.template_name, context)


# ══════════════════════════════════════════════
# SUCURSALES — API AJAX CRUD
# ══════════════════════════════════════════════

class SucursalAPIView(LoginRequiredMixin, View):
    """Endpoints AJAX para operaciones CRUD de Sucursales"""

    def get(self, request, pk=None):
        """Obtener una sucursal por pk, o listar con filtros opcionales"""
        if pk:
            sucursal = get_object_or_404(Sucursal, pk=pk)
            return json_response(True, {'sucursal': get_sucursal_data(sucursal)})

        qs = Sucursal.objects.all()
        if activa := request.GET.get('activa'):
            qs = qs.filter(activa=activa == 'true')
        if provincia := request.GET.get('provincia'):
            qs = qs.filter(provincia__icontains=provincia)
        if q := request.GET.get('q'):
            qs = qs.filter(
                models.Q(nombre__icontains=q) |
                models.Q(codigo__icontains=q) |
                models.Q(ciudad__icontains=q)
            )

        data = [get_sucursal_data(s) for s in qs.order_by('-es_principal', 'nombre')]
        return json_response(True, {'sucursales': data, 'total': len(data)})

    def post(self, request):
        """Crear una nueva sucursal"""
        if not request.user.has_perm('core.add_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos para crear sucursales'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = request.POST.dict()

        form = SucursalForm(data)
        if not form.is_valid():
            return json_response(False, errors=form.errors, status=422)

        try:
            with transaction.atomic():
                sucursal = form.save(commit=False)
                if not sucursal.schema_name and sucursal.codigo:
                    sucursal.schema_name = re.sub(r'[^a-z0-9_]', '_', sucursal.codigo.lower())
                sucursal.full_clean()
                sucursal.save()

                dominio_val = data.get('dominio_primario', '').strip()
                if dominio_val:
                    DominioSucursal.objects.create(
                        tenant=sucursal,
                        domain=dominio_val,
                        is_primary=True,
                    )

            return json_response(True, {
                'message':  f'Sucursal "{sucursal.nombre}" creada exitosamente',
                'sucursal': get_sucursal_data(sucursal),
            }, status=201)

        except ValidationError as e:
            return json_response(False, errors=e.message_dict if hasattr(e, 'message_dict') else {'general': str(e)}, status=422)
        except IntegrityError:
            return json_response(False, errors={'general': 'Ya existe una sucursal con ese código o nombre'}, status=409)
        except Exception as e:
            return json_response(False, errors={'general': f'Error al crear: {str(e)}'}, status=500)

    def put(self, request, pk):
        """Actualizar una sucursal existente"""
        if not request.user.has_perm('core.change_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos para editar sucursales'}, status=403)

        sucursal = get_object_or_404(Sucursal, pk=pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return json_response(False, errors={'general': 'JSON inválido'}, status=400)

        form = SucursalForm(data, instance=sucursal)
        if not form.is_valid():
            return json_response(False, errors=form.errors, status=422)

        try:
            with transaction.atomic():
                sucursal = form.save(commit=False)
                sucursal.full_clean()
                sucursal.save()

            return json_response(True, {
                'message':  f'Sucursal "{sucursal.nombre}" actualizada exitosamente',
                'sucursal': get_sucursal_data(sucursal),
            })

        except ValidationError as e:
            return json_response(False, errors=e.message_dict if hasattr(e, 'message_dict') else {'general': str(e)}, status=422)
        except IntegrityError:
            return json_response(False, errors={'general': 'Conflicto de datos únicos'}, status=409)
        except Exception as e:
            return json_response(False, errors={'general': str(e)}, status=500)

    def delete(self, request, pk):
        """Desactivar (soft-delete) una sucursal"""
        if not request.user.has_perm('core.delete_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos para eliminar sucursales'}, status=403)

        sucursal = get_object_or_404(Sucursal, pk=pk)

        if sucursal.es_principal:
            return json_response(False, errors={'general': 'No se puede eliminar la sucursal principal'}, status=400)

        nombre = sucursal.nombre
        sucursal.activa = False
        sucursal.save(update_fields=['activa'])

        return json_response(True, {'message': f'Sucursal "{nombre}" desactivada exitosamente'})


class SucursalToggleActivaView(LoginRequiredMixin, View):
    """Activar / desactivar una sucursal via AJAX"""

    def post(self, request, pk):
        if not request.user.has_perm('core.change_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos'}, status=403)

        sucursal = get_object_or_404(Sucursal, pk=pk)

        if sucursal.es_principal and sucursal.activa:
            return json_response(False, errors={'general': 'No puede desactivar la sucursal principal'}, status=400)

        sucursal.activa = not sucursal.activa
        try:
            sucursal.full_clean()
            sucursal.save(update_fields=['activa'])
        except ValidationError as e:
            return json_response(False, errors={'general': str(e)}, status=422)

        estado = 'activada' if sucursal.activa else 'desactivada'
        return json_response(True, {
            'message': f'Sucursal {estado} exitosamente',
            'activa':  sucursal.activa,
        })


# ══════════════════════════════════════════════
# DOMINIOS — API AJAX CRUD
# ══════════════════════════════════════════════

class DominioAPIView(LoginRequiredMixin, View):
    """CRUD de dominios de una sucursal"""

    def post(self, request, sucursal_pk):
        """Agregar un nuevo dominio a la sucursal"""
        if not request.user.has_perm('core.change_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos'}, status=403)

        sucursal = get_object_or_404(Sucursal, pk=sucursal_pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = request.POST.dict()

        domain     = data.get('domain', '').strip()
        is_primary = data.get('is_primary', False)

        if not domain:
            return json_response(False, errors={'domain': 'El dominio es requerido'}, status=422)

        try:
            with transaction.atomic():
                if is_primary:
                    sucursal.domains.filter(is_primary=True).update(is_primary=False)

                dominio = DominioSucursal.objects.create(
                    tenant=sucursal,
                    domain=domain,
                    is_primary=is_primary,
                )

            return json_response(True, {
                'message': f'Dominio "{domain}" agregado',
                'dominio': {'id': dominio.pk, 'domain': dominio.domain, 'is_primary': dominio.is_primary},
            }, status=201)

        except IntegrityError:
            return json_response(False, errors={'domain': 'Este dominio ya existe'}, status=409)
        except Exception as e:
            return json_response(False, errors={'general': str(e)}, status=500)

    def patch(self, request, sucursal_pk, dominio_pk):
        """Marcar un dominio como primario"""
        if not request.user.has_perm('core.change_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos'}, status=403)

        sucursal = get_object_or_404(Sucursal, pk=sucursal_pk)
        dominio  = get_object_or_404(DominioSucursal, pk=dominio_pk, tenant=sucursal)

        with transaction.atomic():
            sucursal.domains.update(is_primary=False)
            dominio.is_primary = True
            dominio.save(update_fields=['is_primary'])

        return json_response(True, {'message': f'"{dominio.domain}" es ahora el dominio primario'})

    def delete(self, request, sucursal_pk, dominio_pk):
        """Eliminar un dominio"""
        if not request.user.has_perm('core.change_sucursal'):
            return json_response(False, errors={'general': 'Sin permisos'}, status=403)

        dominio = get_object_or_404(DominioSucursal, pk=dominio_pk, tenant_id=sucursal_pk)

        if dominio.is_primary:
            return json_response(False, errors={'general': 'No puede eliminar el dominio primario'}, status=400)

        dominio.delete()
        return json_response(True, {'message': 'Dominio eliminado'})


# ══════════════════════════════════════════════
# PARÁMETROS DEL SISTEMA — API AJAX
# ══════════════════════════════════════════════

class ParametroAPIView(LoginRequiredMixin, View):
    """CRUD de parámetros del sistema"""

    def get(self, request):
        params = list(ParametroSistema.objects.values(
            'id', 'nombre', 'valor', 'descripcion', 'fecha_modificacion'
        ))
        return json_response(True, {'parametros': params})

    def post(self, request):
        if not request.user.is_staff:
            return json_response(False, errors={'general': 'Sin permisos'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return json_response(False, errors={'general': 'JSON inválido'}, status=400)

        nombre = data.get('nombre', '').strip()
        valor  = data.get('valor', '').strip()

        if not nombre or not valor:
            return json_response(False, errors={'general': 'Nombre y valor son requeridos'}, status=422)

        param, created = ParametroSistema.objects.update_or_create(
            nombre=nombre,
            defaults={'valor': valor, 'descripcion': data.get('descripcion', '')}
        )
        accion = 'creado' if created else 'actualizado'
        return json_response(True, {'message': f'Parámetro {accion}', 'id': param.pk})

    def delete(self, request, pk):
        if not request.user.is_staff:
            return json_response(False, errors={'general': 'Sin permisos'}, status=403)
        param = get_object_or_404(ParametroSistema, pk=pk)
        param.delete()
        return json_response(True, {'message': 'Parámetro eliminado'})


# ══════════════════════════════════════════════
# UTILIDADES AJAX
# ══════════════════════════════════════════════

@login_required
def preview_schema_name(request):
    """AJAX: devuelve el schema_name generado a partir de un código y verifica disponibilidad"""
    codigo = request.GET.get('codigo', '')
    schema = re.sub(r'[^a-z0-9_]', '_', codigo.lower()).strip('_')
    disponible = not Sucursal.objects.filter(schema_name=schema).exists()
    return JsonResponse({'schema_name': schema, 'disponible': disponible})
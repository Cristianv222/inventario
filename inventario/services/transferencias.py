"""
Service layer para gestión de transferencias entre sucursales
Maneja la lógica de negocio y el cambio de schemas
"""
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import schema_context
from decimal import Decimal

from inventario.models import (
    Producto, 
    TransferenciaInventario, 
    DetalleTransferencia,
    MovimientoInventario
)
from core.models import Sucursal


class TransferenciaService:
    """Servicio para gestionar transferencias de inventario"""
    
    @staticmethod
    def validar_stock_disponible(sucursal_origen, productos_transferir):
        """
        Valida que haya stock suficiente en la sucursal origen
        
        Args:
            sucursal_origen: Instancia de Sucursal
            productos_transferir: Lista de dict con 'producto_id' y 'cantidad'
        
        Returns:
            tuple: (bool, list) - (es_valido, lista_errores)
        """
        errores = []
        
        # Cambiar al schema de la sucursal origen
        with schema_context(sucursal_origen.schema_name):
            for item in productos_transferir:
                try:
                    producto = Producto.objects.get(
                        id=item['producto_id'],
                        activo=True
                    )
                    
                    cantidad_solicitada = Decimal(str(item['cantidad']))
                    
                    if producto.stock_actual < cantidad_solicitada:
                        errores.append({
                            'codigo': producto.codigo_unico,
                            'nombre': producto.nombre,
                            'stock_disponible': float(producto.stock_actual),
                            'cantidad_solicitada': float(cantidad_solicitada),
                            'mensaje': f"Stock insuficiente para {producto.nombre}. "
                                     f"Disponible: {producto.stock_actual}, Solicitado: {cantidad_solicitada}"
                        })
                    
                except Producto.DoesNotExist:
                    errores.append({
                        'producto_id': item['producto_id'],
                        'mensaje': f"Producto con ID {item['producto_id']} no existe en {sucursal_origen.nombre}"
                    })
        
        return len(errores) == 0, errores
    
    @staticmethod
    @transaction.atomic
    def crear_transferencia(sucursal_origen, sucursal_destino, usuario, productos, observaciones=''):
        """
        Crea una nueva transferencia y decrementa el stock en origen
        
        Args:
            sucursal_origen: Instancia de Sucursal
            sucursal_destino: Instancia de Sucursal
            usuario: Usuario que realiza la transferencia
            productos: Lista de dict con 'producto_id', 'cantidad'
            observaciones: Texto con observaciones
        
        Returns:
            TransferenciaInventario: Instancia creada
        """
        # Validar que las sucursales sean diferentes
        if sucursal_origen.id == sucursal_destino.id:
            raise ValidationError("La sucursal origen y destino deben ser diferentes")
        
        # Validar stock disponible
        es_valido, errores = TransferenciaService.validar_stock_disponible(
            sucursal_origen, 
            productos
        )
        
        if not es_valido:
            raise ValidationError(errores)
        
        # Crear transferencia en schema PUBLIC
        with schema_context('public'):
            transferencia = TransferenciaInventario.objects.create(
                sucursal_origen=sucursal_origen,
                sucursal_destino=sucursal_destino,
                usuario_envia=usuario,
                estado='PENDIENTE',
                observaciones_envio=observaciones
            )
        
        # Procesar cada producto
        for item in productos:
            # Cambiar al schema de origen para obtener datos del producto
            with schema_context(sucursal_origen.schema_name):
                producto = Producto.objects.get(
                    id=item['producto_id'],
                    activo=True
                )
                
                cantidad = Decimal(str(item['cantidad']))
                
                # Guardar datos del producto para crear detalle
                producto_codigo = producto.codigo_unico
                producto_nombre = producto.nombre
                producto_precio = producto.precio_venta
                
                # Decrementar stock en origen
                producto.stock_actual -= cantidad
                producto.save()
                
                # Registrar movimiento
                MovimientoInventario.objects.create(
                    producto=producto,
                    usuario=usuario,
                    tipo_movimiento='SALIDA',
                    cantidad=cantidad,
                    precio_unitario=producto_precio,
                    motivo=f'Transferencia a {sucursal_destino.nombre} - Guía #{transferencia.numero_guia}',
                    referencia=transferencia.numero_guia
                )
            
            # Crear detalle de transferencia (en PUBLIC)
            with schema_context('public'):
                DetalleTransferencia.objects.create(
                    transferencia=transferencia,
                    producto_codigo=producto_codigo,
                    producto_nombre=producto_nombre,
                    cantidad_enviada=cantidad,
                    precio_unitario=producto_precio
                )
        
        return transferencia
    
    @staticmethod
    @transaction.atomic
    def recibir_transferencia(transferencia_id, usuario, productos_recibidos, observaciones=''):
        """
        Recibe una transferencia e incrementa el stock en destino
        
        Args:
            transferencia_id: ID de la transferencia
            usuario: Usuario que recibe
            productos_recibidos: Lista de dict con 'producto_id', 'cantidad_recibida'
            observaciones: Observaciones de recepción
        
        Returns:
            TransferenciaInventario: Instancia actualizada
        """
        # Obtener transferencia (en PUBLIC)
        with schema_context('public'):
            transferencia = TransferenciaInventario.objects.select_related(
                'sucursal_origen',
                'sucursal_destino'
            ).get(id=transferencia_id)
            
            # Validar que puede ser recibida
            if not transferencia.puede_ser_recibida():
                raise ValidationError(f"La transferencia está en estado {transferencia.estado} y no puede ser recibida")
            
            # Validar que el usuario pertenece a la sucursal destino
            if usuario.sucursal and usuario.sucursal.id != transferencia.sucursal_destino.id:
                if not usuario.puede_ver_todas_sucursales:
                    raise ValidationError("Solo usuarios de la sucursal destino pueden recibir la transferencia")
        
        # Procesar productos recibidos
        for item_recibido in productos_recibidos:
            # Buscar detalle en PUBLIC
            with schema_context('public'):
                detalle = DetalleTransferencia.objects.get(
                    transferencia=transferencia,
                    producto_codigo=item_recibido.get('producto_codigo') or item_recibido.get('codigo')
                )
                
                cantidad_recibida = Decimal(str(item_recibido['cantidad_recibida']))
                detalle.cantidad_recibida = cantidad_recibida
                
                # Agregar observaciones si hay diferencia
                if detalle.tiene_diferencia():
                    diferencia = detalle.get_diferencia()
                    obs = f"Diferencia: {'+' if diferencia > 0 else ''}{diferencia}. "
                    if 'observaciones' in item_recibido:
                        obs += item_recibido['observaciones']
                    detalle.observaciones = obs
                
                detalle.save()
            
            # Cambiar a schema destino para actualizar stock
            with schema_context(transferencia.sucursal_destino.schema_name):
                # Buscar o crear producto en destino
                try:
                    producto = Producto.objects.get(codigo_unico=detalle.producto_codigo)
                except Producto.DoesNotExist:
                    # Si el producto no existe en destino, obtener datos del origen y crearlo
                    with schema_context(transferencia.sucursal_origen.schema_name):
                        producto_origen = Producto.objects.get(codigo_unico=detalle.producto_codigo)
                        
                        # Datos para crear producto
                        datos_producto = {
                            'codigo_unico': producto_origen.codigo_unico,
                            'nombre': producto_origen.nombre,
                            'descripcion': producto_origen.descripcion,
                            'categoria': producto_origen.categoria,
                            'marca': producto_origen.marca,
                            'precio_compra': producto_origen.precio_compra,
                            'precio_venta': producto_origen.precio_venta,
                            'stock_minimo': producto_origen.stock_minimo,
                            'incluye_iva': producto_origen.incluye_iva,
                        }
                    
                    # Crear en destino
                    with schema_context(transferencia.sucursal_destino.schema_name):
                        producto = Producto.objects.create(
                            **datos_producto,
                            stock_actual=0,  # Inicia en 0, se incrementará abajo
                            activo=True
                        )
                
                # Incrementar stock
                producto.stock_actual += cantidad_recibida
                producto.save()
                
                # Registrar movimiento
                MovimientoInventario.objects.create(
                    producto=producto,
                    usuario=usuario,
                    tipo_movimiento='ENTRADA',
                    cantidad=cantidad_recibida,
                    precio_unitario=producto.precio_venta,
                    motivo=f'Transferencia desde {transferencia.sucursal_origen.nombre} - Guía #{transferencia.numero_guia}',
                    referencia=transferencia.numero_guia
                )
        
        # Actualizar transferencia (en PUBLIC)
        with schema_context('public'):
            transferencia.estado = 'RECIBIDA'
            transferencia.usuario_recibe = usuario
            transferencia.fecha_recepcion = timezone.now()
            transferencia.observaciones_recepcion = observaciones
            transferencia.save()
        
        return transferencia
    
    @staticmethod
    @transaction.atomic
    def cancelar_transferencia(transferencia_id, usuario, motivo):
        """
        Cancela una transferencia y revierte el stock en origen
        
        Args:
            transferencia_id: ID de la transferencia
            usuario: Usuario que cancela
            motivo: Motivo de cancelación
        """
        # Obtener transferencia (en PUBLIC)
        with schema_context('public'):
            transferencia = TransferenciaInventario.objects.select_related(
                'sucursal_origen',
                'sucursal_destino'
            ).prefetch_related('detalles').get(id=transferencia_id)
            
            # Validar que puede ser cancelada
            if not transferencia.puede_ser_cancelada():
                raise ValidationError(f"La transferencia está en estado {transferencia.estado} y no puede ser cancelada")
            
            detalles = list(transferencia.detalles.all())
        
        # Revertir stock para cada producto
        for detalle in detalles:
            with schema_context(transferencia.sucursal_origen.schema_name):
                try:
                    producto = Producto.objects.get(codigo_unico=detalle.producto_codigo)
                    
                    # Devolver stock
                    producto.stock_actual += detalle.cantidad_enviada
                    producto.save()
                    
                    # Registrar movimiento de ajuste
                    MovimientoInventario.objects.create(
                        producto=producto,
                        usuario=usuario,
                        tipo_movimiento='ENTRADA',
                        cantidad=detalle.cantidad_enviada,
                        precio_unitario=producto.precio_venta,
                        motivo=f'Cancelación de transferencia #{transferencia.numero_guia} - {motivo}',
                        referencia=transferencia.numero_guia
                    )
                    
                except Producto.DoesNotExist:
                    # Si el producto ya no existe, no se puede revertir
                    pass
        
        # Actualizar estado (en PUBLIC)
        with schema_context('public'):
            transferencia.estado = 'CANCELADA'
            transferencia.observaciones_recepcion = f"Cancelada por {usuario.get_full_name()}: {motivo}"
            transferencia.save()
        
        return transferencia
    
    @staticmethod
    def get_transferencias_pendientes_para_sucursal(sucursal):
        """
        Obtiene transferencias pendientes de recepción para una sucursal
        
        Args:
            sucursal: Instancia de Sucursal
        
        Returns:
            QuerySet de TransferenciaInventario
        """
        with schema_context('public'):
            return TransferenciaInventario.objects.filter(
                sucursal_destino=sucursal,
                estado__in=['PENDIENTE', 'EN_TRANSITO']
            ).select_related(
                'sucursal_origen',
                'sucursal_destino',
                'usuario_envia'
            ).prefetch_related('detalles')
    
    @staticmethod
    def get_transferencias_enviadas_por_sucursal(sucursal):
        """
        Obtiene transferencias enviadas por una sucursal
        
        Args:
            sucursal: Instancia de Sucursal
        
        Returns:
            QuerySet de TransferenciaInventario
        """
        with schema_context('public'):
            return TransferenciaInventario.objects.filter(
                sucursal_origen=sucursal
            ).select_related(
                'sucursal_origen',
                'sucursal_destino',
                'usuario_envia',
                'usuario_recibe'
            ).prefetch_related('detalles')
"""
Siembra un plan de cuentas base para Ecuador (estructura tipo Superintendencia
de Compañías / NIIF, simplificada). Idempotente: se puede correr varias veces.

Uso:
    python manage.py sembrar_plan_cuentas

Marca con '*' las cuentas de movimiento (hojas que aceptan asientos).
El tipo se hereda del dígito raíz; la naturaleza se deduce del tipo.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from finanzas.models import CuentaContable

# (codigo, nombre, es_movimiento)
# El tipo se infiere del primer dígito del código.
PLAN = [
    # 1 ACTIVO
    ('1', 'ACTIVO', False),
    ('1.1', 'Activo Corriente', False),
    ('1.1.01', 'Efectivo y equivalentes', False),
    ('1.1.01.01', 'Caja', True),
    ('1.1.01.02', 'Bancos', True),
    ('1.1.02', 'Cuentas por cobrar', False),
    ('1.1.02.01', 'Clientes', True),
    ('1.1.02.02', 'Provisión cuentas incobrables', True),
    ('1.1.03', 'Inventarios', False),
    ('1.1.03.01', 'Inventario de mercadería', True),
    ('1.1.04', 'Crédito tributario', False),
    ('1.1.04.01', 'IVA en compras (crédito tributario)', True),
    ('1.1.04.02', 'Retenciones a favor', True),
    ('1.2', 'Activo No Corriente', False),
    ('1.2.01', 'Propiedad, planta y equipo', False),
    ('1.2.01.01', 'Muebles y equipos', True),
    ('1.2.01.02', 'Vehículos', True),
    ('1.2.01.03', 'Depreciación acumulada', True),

    # 2 PASIVO
    ('2', 'PASIVO', False),
    ('2.1', 'Pasivo Corriente', False),
    ('2.1.01', 'Cuentas por pagar', False),
    ('2.1.01.01', 'Proveedores', True),
    ('2.1.02', 'Obligaciones fiscales', False),
    ('2.1.02.01', 'IVA en ventas (por pagar)', True),
    ('2.1.02.02', 'Retenciones por pagar', True),
    ('2.1.02.03', 'Impuesto a la renta por pagar', True),
    ('2.1.03', 'Obligaciones con empleados / IESS', False),
    ('2.1.03.01', 'Sueldos por pagar', True),
    ('2.1.03.02', 'IESS por pagar', True),
    ('2.1.03.03', 'Beneficios sociales por pagar', True),
    ('2.2', 'Pasivo No Corriente', False),
    ('2.2.01', 'Préstamos bancarios largo plazo', True),

    # 3 PATRIMONIO
    ('3', 'PATRIMONIO', False),
    ('3.1', 'Capital', False),
    ('3.1.01', 'Capital social', True),
    ('3.2', 'Resultados', False),
    ('3.2.01', 'Utilidad del ejercicio', True),
    ('3.2.02', 'Pérdidas acumuladas', True),
    ('3.2.03', 'Utilidades retenidas', True),

    # 4 INGRESOS
    ('4', 'INGRESOS', False),
    ('4.1', 'Ingresos operacionales', False),
    ('4.1.01', 'Ventas', False),
    ('4.1.01.01', 'Ventas de bienes', True),
    ('4.1.01.02', 'Ventas de servicios', True),
    ('4.1.02', 'Descuentos y devoluciones', False),
    ('4.1.02.01', 'Descuento en ventas', True),
    ('4.2', 'Ingresos no operacionales', False),
    ('4.2.01', 'Otros ingresos', True),

    # 5 COSTOS
    ('5', 'COSTOS', False),
    ('5.1', 'Costo de ventas', False),
    ('5.1.01', 'Costo de mercadería vendida', False),
    ('5.1.01.01', 'Costo de mercadería vendida', True),

    # 6 GASTOS
    ('6', 'GASTOS', False),
    ('6.1', 'Gastos operacionales', False),
    ('6.1.01', 'Gastos de administración', False),
    ('6.1.01.01', 'Sueldos y salarios', True),
    ('6.1.01.02', 'Aporte patronal IESS', True),
    ('6.1.01.03', 'Servicios básicos', True),
    ('6.1.01.04', 'Arriendo', True),
    ('6.1.02', 'Gastos de ventas', False),
    ('6.1.02.01', 'Publicidad y marketing', True),
    ('6.1.03', 'Gastos generales', False),
    ('6.1.03.01', 'Gastos varios', True),
    ('6.1.04', 'Gastos financieros', False),
    ('6.1.04.01', 'Intereses y comisiones bancarias', True),
    ('6.1.05', 'Depreciaciones', False),
    ('6.1.05.01', 'Gasto depreciación', True),
]

TIPO_POR_RAIZ = {
    '1': CuentaContable.TIPO_ACTIVO,
    '2': CuentaContable.TIPO_PASIVO,
    '3': CuentaContable.TIPO_PATRIMONIO,
    '4': CuentaContable.TIPO_INGRESO,
    '5': CuentaContable.TIPO_COSTO,
    '6': CuentaContable.TIPO_GASTO,
}


class Command(BaseCommand):
    help = 'Siembra el plan de cuentas base de Ecuador (idempotente).'

    @transaction.atomic
    def handle(self, *args, **options):
        creadas = 0
        actualizadas = 0

        for codigo, nombre, es_mov in PLAN:
            partes = codigo.split('.')
            nivel = len(partes)
            tipo = TIPO_POR_RAIZ[partes[0]]
            naturaleza = CuentaContable.naturaleza_para_tipo(tipo)
            padre = None
            if nivel > 1:
                codigo_padre = '.'.join(partes[:-1])
                padre = CuentaContable.objects.filter(codigo=codigo_padre).first()

            obj, creada = CuentaContable.objects.update_or_create(
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'tipo': tipo,
                    'naturaleza': naturaleza,
                    'padre': padre,
                    'nivel': nivel,
                    'es_movimiento': es_mov,
                    'activa': True,
                },
            )
            if creada:
                creadas += 1
            else:
                actualizadas += 1

        self.stdout.write(self.style.SUCCESS(
            f'Plan de cuentas sembrado: {creadas} creadas, '
            f'{actualizadas} actualizadas, {len(PLAN)} en total.'
        ))

"""Genera el asiento de cierre anual de las cuentas de resultado.

Salda Ingresos, Costos y Gastos del año contra la cuenta de Utilidad del
ejercicio (patrimonio). Debe ejecutarse antes de cerrar diciembre.

Uso:
  python manage.py cierre_anual --anio 2026
"""
from django.core.management.base import BaseCommand, CommandError

from finanzas.services.contabilidad import ErrorContable, asiento_cierre_anual


class Command(BaseCommand):
    help = 'Genera el asiento de cierre anual de cuentas de resultado.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, required=True)

    def handle(self, *args, **opts):
        try:
            asiento = asiento_cierre_anual(anio=opts['anio'])
        except ErrorContable as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f'Asiento de cierre anual {asiento.numero} creado para {opts["anio"]} '
            f'(Debe={asiento.total_debe}, Haber={asiento.total_haber}).'
        ))

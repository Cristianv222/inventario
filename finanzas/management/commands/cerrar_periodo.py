"""Cierra (o reabre) un período contable mensual.

Un período cerrado no admite nuevos asientos en ese mes.

Uso:
  python manage.py cerrar_periodo --anio 2026 --mes 1
  python manage.py cerrar_periodo --anio 2026 --mes 1 --reabrir
"""
from django.core.management.base import BaseCommand, CommandError

from finanzas.services.contabilidad import cerrar_periodo, reabrir_periodo


class Command(BaseCommand):
    help = 'Cierra o reabre un período contable mensual.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, required=True)
        parser.add_argument('--mes', type=int, required=True)
        parser.add_argument('--reabrir', action='store_true',
                            help='Reabre el período en lugar de cerrarlo.')

    def handle(self, *args, **opts):
        anio, mes = opts['anio'], opts['mes']
        if not 1 <= mes <= 12:
            raise CommandError('El mes debe estar entre 1 y 12.')

        if opts['reabrir']:
            reabrir_periodo(anio, mes)
            self.stdout.write(self.style.WARNING(
                f'Período {anio}-{mes:02d} reabierto.'))
        else:
            cerrar_periodo(anio, mes)
            self.stdout.write(self.style.SUCCESS(
                f'Período {anio}-{mes:02d} cerrado. No admite nuevos asientos.'))

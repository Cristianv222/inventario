"""Crea el asiento de apertura (saldos iniciales) desde un archivo JSON.

Formato del archivo:
{
  "fecha": "2026-01-01",
  "capital": "CAPITAL",            // clave de CUENTAS o código; cuadra el asiento
  "saldos": {
    "1.1.01.01": "5000.00",        // Caja
    "1.1.03.01": "12000.00",       // Inventario
    "2.1.01.01": "3000.00"         // Proveedores
  }
}

Uso:
  python manage.py asiento_apertura --archivo apertura.json
"""
import datetime
import json

from django.core.management.base import BaseCommand, CommandError

from finanzas.services.contabilidad import ErrorContable, generar_asiento_apertura


class Command(BaseCommand):
    help = 'Genera el asiento de apertura a partir de un archivo JSON de saldos iniciales.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', required=True,
                            help='Ruta al JSON con fecha, capital y saldos.')

    def handle(self, *args, **opts):
        try:
            with open(opts['archivo'], encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'No se pudo leer el archivo: {exc}')

        try:
            fecha = datetime.date.fromisoformat(data['fecha'])
        except (KeyError, ValueError) as exc:
            raise CommandError(f'Fecha inválida o ausente: {exc}')

        saldos = data.get('saldos') or {}
        if not saldos:
            raise CommandError('El archivo no contiene "saldos".')

        try:
            asiento = generar_asiento_apertura(
                fecha=fecha, saldos=saldos,
                cuenta_capital=data.get('capital', 'CAPITAL'),
            )
        except ErrorContable as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f'Asiento de apertura {asiento.numero} creado '
            f'(Debe={asiento.total_debe}, Haber={asiento.total_haber}, '
            f'cuadrado={asiento.cuadrado}).'
        ))

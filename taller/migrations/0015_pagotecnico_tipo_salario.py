from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('taller', '0014_consumos_y_abonos_tecnico'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagotecnico',
            name='tipo',
            field=models.CharField(choices=[('COMISION', 'Comisión'), ('SALARIO', 'Salario')], default='COMISION', max_length=10),
        ),
        migrations.AddField(
            model_name='pagotecnico',
            name='salario_bruto',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
    ]

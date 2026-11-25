from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('taller', '0016_iva_en_servicios'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='ordentrabajo',
            options={
                'ordering': ['-fecha_ingreso'],
                'permissions': [('reabrir_ordentrabajo', 'Permitir reabrir órdenes de trabajo')],
                'verbose_name': 'Orden de Trabajo',
                'verbose_name_plural': 'Órdenes de Trabajo',
            },
        ),
    ]

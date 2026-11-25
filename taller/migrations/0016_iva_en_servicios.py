from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('taller', '0015_pagotecnico_tipo_salario'),
    ]

    operations = [
        migrations.AddField(
            model_name='tiposervicio',
            name='incluye_iva',
            field=models.BooleanField(default=False, help_text='Agregar 15% de IVA sobre el precio base al cobrar este servicio'),
        ),
        migrations.AddField(
            model_name='servicioorden',
            name='aplica_iva',
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]

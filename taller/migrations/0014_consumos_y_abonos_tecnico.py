from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0013_configuraciontienda_resend_api_key'),
        ('taller', '0013_pagotecnico_semana_campos'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='adelantotecnico',
            name='abonado',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AddField(
            model_name='pagotecnico',
            name='consumos_descontados',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.CreateModel(
            name='ConsumoTecnico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('cantidad', models.DecimalField(decimal_places=2, max_digits=10)),
                ('precio_unitario', models.DecimalField(decimal_places=2, max_digits=10)),
                ('total', models.DecimalField(decimal_places=2, max_digits=12)),
                ('descripcion', models.CharField(blank=True, max_length=255)),
                ('abonado', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('liquidado', models.BooleanField(default=False)),
                ('anulado', models.BooleanField(default=False)),
                ('pago', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consumos', to='taller.pagotecnico')),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='consumos_tecnico', to='inventario.producto')),
                ('tecnico', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consumos', to='taller.tecnico')),
                ('usuario_registro', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Consumo de inventario del técnico',
                'verbose_name_plural': 'Consumos de inventario de técnicos',
                'ordering': ['-fecha'],
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('taller', '0012_tecnico_gana_comision_tecnico_gana_salario_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagotecnico',
            name='semana_inicio',
            field=models.DateField(blank=True, help_text='Lunes de la semana liquidada', null=True),
        ),
        migrations.AddField(
            model_name='pagotecnico',
            name='semana_fin',
            field=models.DateField(blank=True, help_text='Sábado de la semana liquidada', null=True),
        ),
        migrations.AddField(
            model_name='pagotecnico',
            name='porcentaje_comision',
            field=models.DecimalField(
                decimal_places=2,
                default=50,
                help_text='% comisión aplicado en esta liquidación',
                max_digits=5,
            ),
        ),
        migrations.AlterModelOptions(
            name='pagotecnico',
            options={
                'ordering': ['-semana_inicio', '-fecha'],
                'verbose_name': 'Liquidación semanal de técnico',
                'verbose_name_plural': 'Liquidaciones semanales de técnicos',
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    """Tiempo de revisión por tarea (Karla, 02-11-2026): lo que tarda quien revisa cada ejecución, en minutos.
    Vacío = el valor general (parámetro «minutos_revision», 15 min). Reemplaza el 25 % de las horas de ejecución."""

    dependencies = [("nucleo", "0014_calendario_2027_2028")]

    operations = [
        migrations.AddField(
            model_name="tarea",
            name="minutos_revision",
            field=models.PositiveIntegerField(blank=True, help_text="Minutos que tarda quien revisa, por ejecución. Vacío = el valor general (parámetro «minutos_revision», 15 min).", null=True),
        ),
    ]

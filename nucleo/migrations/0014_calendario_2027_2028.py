from django.db import migrations
from django.utils import timezone


def cargar(apps, schema_editor):
    """Karla (01-11-2026): «dejar cargado altiro 2027 y 2028 con los feriados del año y calendario».

    Los feriados vienen de la librería `holidays` (Chile) y quedan confirmados y los años abiertos, para que se puedan abrir los meses sin más pasos.
    Un feriado decretado a última hora se agrega o corrige después desde «Abrir mes». No toca lo que ya exista.
    """
    import holidays
    Feriado, Anio = apps.get_model("nucleo", "Feriado"), apps.get_model("nucleo", "Anio")
    for anio in (2027, 2028):
        existentes = set(Feriado.objects.filter(fecha__year=anio).values_list("fecha", flat=True))
        for fecha, nombre in sorted(holidays.country_holidays("CL", years=anio, language="es").items()):
            if fecha not in existentes:
                Feriado.objects.create(fecha=fecha, nombre=nombre, tipo="legal", origen="librería · carga inicial 2027-2028", confirmado=True, confirmado_en=timezone.now())
        Anio.objects.update_or_create(anio=anio, defaults={"estado": "abierto"})


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0013_evidencias")]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]

from django.db import migrations

ORDEN = {"Gerente AyF": 1, "Jefa Gestión y Control": 2, "Contadora Senior": 3, "Asistente Contable": 4}
EXTERNOS = ["Rafael", "RR.HH.", "Gerencia / Directorio", "Bodega", "Jefaturas de área", "Jefatura Lechería"]


def ordenar(apps, schema_editor):
    Cargo = apps.get_model("nucleo", "Cargo")
    # Karla (31-10-2026): el cargo se llama «Asistente Contable», no «Analista Contable».
    for c in Cargo.objects.filter(nombre="Analista Contable"):
        if Cargo.objects.filter(nombre="Asistente Contable").exists():
            continue
        c.nombre = "Asistente Contable"
        c.save()
    for nombre, orden in ORDEN.items():
        Cargo.objects.filter(nombre=nombre).update(orden=orden)
    Cargo.objects.filter(nombre__in=EXTERNOS).update(orden=50)


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0006_orden_de_cargos")]
    operations = [migrations.RunPython(ordenar, migrations.RunPython.noop)]

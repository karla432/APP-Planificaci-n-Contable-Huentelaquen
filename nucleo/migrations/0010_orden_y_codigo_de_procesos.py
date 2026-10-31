from django.db import migrations, models


def poblar(apps, schema_editor):
    """Procesos en el orden del Excel (por su primera tarea) y códigos PRO-TAR-SUB para lo que ya existe."""
    Proceso, Tarea = apps.get_model("nucleo", "Proceso"), apps.get_model("nucleo", "Tarea")
    primera = {}
    for t in Tarea.objects.order_by("secuencia", "id"):
        primera.setdefault(t.proceso_id, t.secuencia)
    procesos = sorted(Proceso.objects.all(), key=lambda p: (primera.get(p.pk, 10**9), p.nombre))
    for i, p in enumerate(procesos, start=1):
        p.orden, p.codigo = i, f"PRO-{i:02d}"
        p.save()
        numero, subs = {}, {}
        for t in Tarea.objects.filter(proceso=p).order_by("secuencia", "id"):
            n = numero.setdefault(t.tarea_principal, len(numero) + 1)
            subs[t.tarea_principal] = subs.get(t.tarea_principal, 0) + 1
            t.codigo = f"{p.codigo}-TAR-{n:02d}-SUB-{subs[t.tarea_principal]:02d}"
            t.save()


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0009_nombres_de_cargos")]
    operations = [
        migrations.AlterModelOptions(name="proceso", options={"ordering": ["orden", "nombre"]}),
        migrations.AddField(model_name="proceso", name="orden", field=models.PositiveSmallIntegerField(default=0, help_text="Orden en que se procesan (el del Excel). Se puede cambiar; el código no cambia.")),
        migrations.AddField(model_name="proceso", name="codigo", field=models.CharField(blank=True, default="", max_length=10, help_text="PRO-01, PRO-02… Lo asigna la app y no cambia.")),
        migrations.AlterField(model_name="tarea", name="codigo", field=models.CharField(max_length=30, unique=True)),
        migrations.RunPython(poblar, migrations.RunPython.noop),
        migrations.AlterField(model_name="proceso", name="codigo", field=models.CharField(blank=True, max_length=10, unique=True, help_text="PRO-01, PRO-02… Lo asigna la app y no cambia.")),
    ]

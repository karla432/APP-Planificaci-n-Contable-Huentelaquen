from django.db import migrations

ROLES = ["ADMIN_SISTEMA", "GERENTE", "JEFATURA", "COLABORADOR", "LECTURA"]


def crear_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nombre in ROLES:
        Group.objects.get_or_create(name=nombre)


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0004_intentos_fallidos"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(crear_roles, migrations.RunPython.noop)]

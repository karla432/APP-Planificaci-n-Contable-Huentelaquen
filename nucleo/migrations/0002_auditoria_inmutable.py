from django.db import migrations

# La bitácora solo admite INSERT (RC-04). Los triggers fallan con ABORT ante cualquier UPDATE o DELETE.
CREAR = [
    """CREATE TRIGGER auditoria_sin_update BEFORE UPDATE ON nucleo_eventoauditoria
       BEGIN SELECT RAISE(ABORT, 'La bitácora de auditoría no se puede modificar'); END;""",
    """CREATE TRIGGER auditoria_sin_delete BEFORE DELETE ON nucleo_eventoauditoria
       BEGIN SELECT RAISE(ABORT, 'La bitácora de auditoría no se puede borrar'); END;""",
]
QUITAR = [
    "DROP TRIGGER IF EXISTS auditoria_sin_update",
    "DROP TRIGGER IF EXISTS auditoria_sin_delete",
]


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0001_modelo_inicial")]
    operations = [migrations.RunSQL(sql=CREAR, reverse_sql=QUITAR)]

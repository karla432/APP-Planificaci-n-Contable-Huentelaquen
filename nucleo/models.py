"""Modelo de datos (docs/f1/02_modelo_datos_recurrencia.md).

Los instantes van en UTC (USE_TZ). Las fechas de negocio son `DateField` en America/Santiago.
No hay borrado físico: se desactiva. Todo valor supuesto lleva `estado_dato = pendiente_confirmar`.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.servicios.recurrencia import AJUSTES, TIPOS, Regla

ESTADO_DATO = [("confirmado", "Confirmado"), ("pendiente_confirmar", "Pendiente de confirmar")]


class Cargo(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    es_externo = models.BooleanField(default=False, help_text="Sin cuenta: la Jefa marca «Recibido».")
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=100, help_text="Orden en las listas: Gerente AyF, Jefa de Control, Contador Senior, Asistente Contable, y después los externos.")

    class Meta:
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Colaborador(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    nombre = models.CharField(max_length=120)
    correo = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Asignacion(models.Model):
    """Un cargo lo ejerce una persona con vigencia (subrogancias y reemplazos)."""

    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="asignaciones")
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, related_name="asignaciones")
    desde = models.DateField()
    hasta = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["cargo", "desde"]


class Proceso(models.Model):
    nombre = models.CharField(max_length=160, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Tarea(models.Model):
    codigo = models.CharField(max_length=12, unique=True)  # TAR-0001
    clave_estable = models.CharField(max_length=64, unique=True)  # hash de proceso + tarea + subtarea normalizados
    proceso = models.ForeignKey(Proceso, on_delete=models.PROTECT, related_name="tareas")
    tarea_principal = models.CharField(max_length=300)
    subtarea = models.TextField()
    cargo_ejecuta = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="tareas_que_ejecuta")
    cargo_revisa = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.PROTECT, related_name="tareas_que_revisa")
    revisa_excel = models.CharField(max_length=80, blank=True, help_text="Lo que decía la columna «Revisa» del Excel (trazabilidad).")
    # Regla de recurrencia (aplanada: una regla por tarea).
    regla_tipo = models.CharField(max_length=20, choices=[(t, t) for t in TIPOS], blank=True)
    regla_dia_semana = models.PositiveSmallIntegerField(null=True, blank=True)
    regla_n = models.PositiveSmallIntegerField(null=True, blank=True)
    regla_dia = models.PositiveSmallIntegerField(null=True, blank=True)
    regla_meses = models.CharField(max_length=40, blank=True, help_text="Meses separados por coma.")
    regla_ajuste = models.CharField(max_length=10, choices=[(a, a) for a in AJUSTES], default="siguiente")
    regla_franja = models.CharField(max_length=20, blank=True, help_text="mañana / tarde (informativa).")
    regla_estado = models.CharField(max_length=20, choices=ESTADO_DATO, default="confirmado")
    periodicidad_excel = models.CharField(max_length=40, blank=True)
    cuando_excel = models.CharField(max_length=120, blank=True)
    referencia_normativa = models.TextField(blank=True)
    minutos_estimados = models.PositiveIntegerField(null=True, blank=True, help_text="Por ejecución. Estimado: ver `fuente_horas`.")
    ejecuciones_mes = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    fuente_horas = models.CharField(max_length=12, default="estimacion", choices=[("estimacion", "Estimación base"), ("gerente", "Definida por la Gerente AyF")])
    secuencia = models.PositiveIntegerField(default=0, help_text="Orden en que se procesan las tareas (el del Excel).")
    dia_cierre = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Día hábil del cierre que indica el Excel (informativo).")
    activa = models.BooleanField(default=True)
    requiere_revision = models.BooleanField(default=False)
    motivo_revision = models.TextField(blank=True)

    class Meta:
        ordering = ["secuencia", "codigo"]

    def __str__(self):
        return f"{self.codigo} {self.subtarea[:60]}"

    @property
    def horas_estimadas(self) -> str:
        return "" if self.minutos_estimados is None else str(round(self.minutos_estimados / 60, 2)).replace(".", ",")

    def regla(self) -> Regla:
        meses = tuple(int(m) for m in self.regla_meses.split(",") if m.strip())
        return Regla(
            tipo=self.regla_tipo,
            dia_semana=self.regla_dia_semana,
            n=self.regla_n,
            dia=self.regla_dia,
            meses=meses,
            ajuste=self.regla_ajuste,
        )


class Anio(models.Model):
    anio = models.PositiveSmallIntegerField(unique=True)
    estado = models.CharField(max_length=10, default="borrador", choices=[("borrador", "Borrador"), ("abierto", "Abierto"), ("cerrado", "Cerrado")])


class Feriado(models.Model):
    fecha = models.DateField(unique=True)
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=15, default="legal", choices=[("legal", "Legal"), ("irrenunciable", "Irrenunciable"), ("decretado", "Decretado"), ("regional", "Regional")])
    origen = models.CharField(max_length=40, default="librería", help_text="librería / manual")
    confirmado = models.BooleanField(default=False)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confirmado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["fecha"]


class Periodo(models.Model):
    anio = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    estado = models.CharField(max_length=10, default="abierto", choices=[("abierto", "Abierto"), ("cerrado", "Cerrado")])
    inicio_medicion = models.DateField(null=True, blank=True)
    kpi_foto = models.JSONField(null=True, blank=True)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["anio", "mes"], name="periodo_unico")]
        ordering = ["-anio", "-mes"]

    def __str__(self):
        return f"{self.mes:02d}-{self.anio}"


class Ocurrencia(models.Model):
    PENDIENTE, HECHA, REVISADA, DEVUELTA, NO_APLICA, BLOQUEADA = "pendiente", "hecha", "revisada", "devuelta", "no_aplica", "bloqueada"
    ESTADOS = [(PENDIENTE, "Pendiente"), (HECHA, "Hecha"), (REVISADA, "Revisada"), (DEVUELTA, "Devuelta"), (NO_APLICA, "No aplica"), (BLOQUEADA, "Bloqueada")]

    tarea = models.ForeignKey(Tarea, on_delete=models.PROTECT, related_name="ocurrencias")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="ocurrencias")
    fecha_limite = models.DateField()
    # Copias vigentes al generarse: cambios posteriores no reescriben el pasado.
    cargo_ejecuta = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="+")
    colaborador = models.ForeignKey(Colaborador, null=True, blank=True, on_delete=models.PROTECT, related_name="ocurrencias")
    cargo_revisa = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    regla_copia = models.JSONField(default=dict)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    tipo_marca = models.CharField(max_length=10, default="HECHA", choices=[("HECHA", "Hecha"), ("RECIBIDA", "Recibida")])
    primera_hecha_en = models.DateTimeField(null=True, blank=True)  # la fija el servidor, una sola vez; base del KPI
    hecha_en = models.DateTimeField(null=True, blank=True)
    hecha_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    primera_revision_en = models.DateTimeField(null=True, blank=True)  # primera vez que se revisó o devolvió; base del KPI de revisión
    veces_devuelta = models.PositiveSmallIntegerField(default=0)  # base de la tasa de devolución
    comentario_devolucion = models.TextField(blank=True)
    por_excepcion = models.BooleanField(default=False)
    motivo_excepcion = models.TextField(blank=True)
    minutos_reales = models.PositiveIntegerField(null=True, blank=True)  # los registran los colaboradores más adelante
    minutos_estimados = models.PositiveIntegerField(null=True, blank=True)  # copia de la tarea al generarse
    motivo_bloqueo = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tarea", "periodo", "fecha_limite"], name="ocurrencia_unica")]
        ordering = ["fecha_limite", "tarea__codigo"]


class SolicitudNoAplica(models.Model):
    ocurrencia = models.ForeignKey(Ocurrencia, on_delete=models.PROTECT, related_name="solicitudes_no_aplica")
    motivo = models.TextField()
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    solicitada_en = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=10, default="pendiente", choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada")])
    resuelta_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    resuelta_en = models.DateTimeField(null=True, blank=True)


class Parametro(models.Model):
    clave = models.CharField(max_length=60, unique=True)
    valor = models.CharField(max_length=60)
    estado_dato = models.CharField(max_length=20, choices=ESTADO_DATO, default="pendiente_confirmar")
    nota = models.CharField(max_length=200, blank=True)


class EventoAuditoria(models.Model):
    """Bitácora append-only y sellada: triggers impiden UPDATE/DELETE; cada sello encadena el anterior."""

    momento = models.DateTimeField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    usuario_texto = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=60)
    entidad = models.CharField(max_length=60, blank=True)
    entidad_id = models.CharField(max_length=40, blank=True)
    antes = models.JSONField(null=True, blank=True)
    despues = models.JSONField(null=True, blank=True)
    motivo = models.TextField(blank=True)
    sello_anterior = models.CharField(max_length=64, blank=True)
    sello = models.CharField(max_length=64)

    class Meta:
        ordering = ["id"]


class IntentoFallido(models.Model):
    """Un intento fallido de ingreso. Alimenta el bloqueo temporal (`nucleo.bloqueo_acceso`); no es la bitácora."""

    nombre = models.CharField(max_length=150, db_index=True)
    momento = models.DateTimeField(default=timezone.now, db_index=True)
    origen = models.CharField(max_length=100, blank=True)

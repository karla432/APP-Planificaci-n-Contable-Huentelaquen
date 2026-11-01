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
    horas_mes_max = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Máximo de horas al mes que este cargo dedica a Huentelauquén (por ejemplo, el Gerente AyF: 80). Vacío = jornada completa.")
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


def horas_texto(minutos) -> str:
    """90 → «1,5»; 120 → «2»; 105 → «1,75». Vacío si no hay dato."""
    if minutos is None:
        return ""
    return f"{minutos / 60:.2f}".rstrip("0").rstrip(".").replace(".", ",")


ESTADOS_PLAN = [("pendiente", "Pendiente"), ("en_curso", "En curso"), ("completado", "Completado"), ("bloqueado", "Bloqueado")]


class Planificable(models.Model):
    """Campos de planificación comunes a los tres niveles (proceso, tarea, subtarea)."""

    estado_plan = models.CharField(max_length=12, choices=ESTADOS_PLAN, default="pendiente")
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_termino = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.fecha_inicio and self.fecha_termino and self.fecha_termino < self.fecha_inicio:
            from django.core.exceptions import ValidationError
            raise ValidationError({"fecha_termino": "La fecha de término no puede ser anterior a la de inicio."})


def _fechas_validas(nombre: str):
    return models.CheckConstraint(
        condition=models.Q(fecha_inicio__isnull=True) | models.Q(fecha_termino__isnull=True) | models.Q(fecha_termino__gte=models.F("fecha_inicio")), name=nombre)


class Proceso(Planificable):
    """Nivel 1. Código OO-PPP: OO es el orden de ejecución (campo aparte) y PPP la sigla de tres letras."""

    nombre = models.CharField(max_length=160, unique=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0, help_text="Orden de ejecución (1, 2, 3…). Único. Cambiarlo actualiza el prefijo de todos los códigos del proceso.")
    sigla = models.CharField(max_length=3, unique=True, blank=True, help_text="Tres letras mayúsculas que identifican al proceso (VEN, COM…).")
    codigo = models.CharField(max_length=10, unique=True, blank=True, help_text="OO-PPP, por ejemplo 02-VEN. Lo genera la app.")
    responsable = models.ForeignKey("Cargo", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["orden", "nombre"]
        constraints = [models.UniqueConstraint(fields=["orden"], name="proceso_orden_unico"), _fechas_validas("proceso_fechas_validas")]

    def save(self, *args, **kwargs):
        from nucleo import siglas
        from nucleo.servicios import codigos
        if not self.orden:
            self.orden = (Proceso.objects.aggregate(m=models.Max("orden"))["m"] or 0) + 1
        if not self.sigla:
            self.sigla = siglas.derivar(self.nombre, set(Proceso.objects.exclude(pk=self.pk).values_list("sigla", flat=True)))
        self.sigla = self.sigla.upper()
        anterior, self.codigo = self.codigo, f"{self.orden:02d}-{self.sigla}"
        super().save(*args, **kwargs)
        if anterior and anterior != self.codigo:
            codigos.al_cambiar_el_codigo_del_proceso(self, anterior)

    def __str__(self):
        return self.nombre


class TareaPrincipal(Planificable):
    """Nivel 2. Código OO-PPP.TT. La app llama «Tarea» a este nivel y «Subtarea» al siguiente (el modelo `Tarea`)."""

    proceso = models.ForeignKey(Proceso, on_delete=models.PROTECT, related_name="tareas_principales")
    nombre = models.CharField(max_length=300)
    numero = models.PositiveSmallIntegerField(default=0, help_text="Correlativo dentro del proceso (TT).")
    codigo = models.CharField(max_length=16, unique=True, blank=True)
    activa = models.BooleanField(default=True)
    responsable = models.ForeignKey("Cargo", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["proceso__orden", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["proceso", "numero"], name="tarea_principal_numero_unico"),
            models.UniqueConstraint(fields=["proceso", "nombre"], name="tarea_principal_nombre_unico"),
            _fechas_validas("tarea_principal_fechas_validas"),
        ]

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = (TareaPrincipal.objects.filter(proceso=self.proceso).aggregate(m=models.Max("numero"))["m"] or 0) + 1
        if self.numero > 99:
            raise ValueError("Un proceso admite hasta 99 tareas (el correlativo TT tiene dos dígitos).")
        self.codigo = f"{self.proceso.codigo}.{self.numero:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} {self.nombre}"


class DependenciaProceso(models.Model):
    """`proceso` solo puede empezar cuando termina `depende_de`. Sin ciclos (se valida en el servicio)."""

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="dependencias")
    depende_de = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="dependientes")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["proceso", "depende_de"], name="dependencia_unica"),
            models.CheckConstraint(condition=~models.Q(proceso=models.F("depende_de")), name="dependencia_no_a_si_mismo"),
        ]


class CambioDeCodigo(models.Model):
    """Historial: cuando un código cambia (reordenar, cambiar sigla o mover una subtarea) el anterior queda aquí y sigue siendo buscable."""

    nivel = models.PositiveSmallIntegerField()
    objeto_id = models.PositiveIntegerField()
    codigo_anterior = models.CharField(max_length=30, db_index=True)
    codigo_nuevo = models.CharField(max_length=30)
    motivo = models.CharField(max_length=160, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    momento = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Tarea(Planificable):
    """Nivel 3 (la «Subtarea»). Código OO-PPP.TT.SSS. Lleva la regla de recurrencia, el responsable y todo lo que se ejecuta mes a mes."""

    codigo = models.CharField(max_length=30, unique=True)  # 02-VEN.01.003: se genera solo
    padre = models.ForeignKey(TareaPrincipal, null=True, blank=True, on_delete=models.PROTECT, related_name="subtareas")
    numero = models.PositiveSmallIntegerField(default=0, help_text="Correlativo dentro de la tarea (SSS).")
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
    MODOS_CIERRE = [("igual", "Igual que el resto del mes"), ("reasignar", "La hace otro cargo en la semana del cierre"), ("pausar", "Se pausa en la semana del cierre")]
    modo_cierre = models.CharField(max_length=10, choices=MODOS_CIERRE, default="igual", help_text="Qué pasa con esta tarea desde el primer día hábil hasta el día 8 (la semana del cierre).")
    cargo_cierre = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Quién la ejecuta en la semana del cierre (si se reasigna).")
    cargo_revisa_cierre = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Quién la revisa en la semana del cierre (si se reasigna).")

    class Meta:
        ordering = ["secuencia", "codigo"]
        constraints = [models.UniqueConstraint(fields=["padre", "numero"], name="subtarea_numero_unico"), _fechas_validas("subtarea_fechas_validas")]

    def save(self, *args, **kwargs):
        if kwargs.get("update_fields") is None:
            from nucleo.servicios import codigos
            codigos.preparar_subtarea(self)  # asegura la tarea (nivel 2), el correlativo y el código
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} {self.subtarea[:60]}"

    @property
    def horas_estimadas(self) -> str:
        return horas_texto(self.minutos_estimados)

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
    minutos_reales = models.PositiveIntegerField(null=True, blank=True)  # los anota quien ejecuta la tarea, al marcarla hecha o después
    minutos_estimados = models.PositiveIntegerField(null=True, blank=True)  # copia de la tarea al generarse
    motivo_bloqueo = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tarea", "periodo", "fecha_limite"], name="ocurrencia_unica")]
        ordering = ["fecha_limite", "tarea__codigo"]

    @property
    def horas_reales(self) -> str:
        return horas_texto(self.minutos_reales)


class Evidencia(models.Model):
    """Documento o evidencia adjunto a un comentario de una tarea. El archivo vive en `settings.EVIDENCIAS_ROOT` (nunca en el repositorio ni en una URL pública)."""

    ocurrencia = models.ForeignKey(Ocurrencia, on_delete=models.PROTECT, related_name="evidencias")
    evento = models.ForeignKey("EventoAuditoria", null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="El comentario al que se adjuntó.")
    ruta = models.CharField(max_length=120, help_text="Ruta relativa dentro de EVIDENCIAS_ROOT (nombre aleatorio).")
    nombre_original = models.CharField(max_length=150)
    extension = models.CharField(max_length=5)
    tipo_contenido = models.CharField(max_length=100)
    tamano = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


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

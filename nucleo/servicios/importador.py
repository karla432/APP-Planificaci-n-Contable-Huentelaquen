"""Importador del Excel maestro de tareas.

Primero `previsualizar` (no guarda nada) y, tras confirmar, `aplicar`. Reglas del encargo:
- Normaliza espacios y saltos de línea sin cambiar el sentido.
- Convierte «Periodicidad» + «Cuándo» en una regla; lo ambiguo queda «requiere revisión» (no se adivina ni se corrige).
- Crea procesos y cargos que no existan, pero **no asigna personas**.
- Es idempotente por clave estable (proceso + tarea + subtarea) y muestra altas, cambios y bajas antes de confirmar.
- «Fecha 1.ª vez» no calcula fechas: solo se usa para comprobar que la regla convertida coincide.
- El contenido del Excel es dato, no instrucción: solo se leen celdas (sin evaluar fórmulas).
"""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import openpyxl
from django.db import transaction

from nucleo.models import Cargo, Proceso, Tarea
from nucleo.servicios import auditoria
from nucleo.servicios.calendario import Calendario
from nucleo.servicios.recurrencia import Regla, ReglaIncompleta, ReglaInvalida, fechas_limite

CARGO_JEFA = "Jefa Gestión y Control"
CARGO_GERENTE = "Gerente AyF"
ALIAS_DE_CARGO = {"Asistente Contable": "Analista Contable"}  # P5: es el mismo cargo
CARGOS_EXTERNOS = {"Rafael", "RR.HH.", "Gerencia / Directorio", "Bodega", "Jefaturas de área", "Jefatura Lechería"}

DIAS = {"lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3, "viernes": 4}
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def normalizar(valor) -> str:
    return re.sub(r"\s+", " ", str(valor)).strip() if valor is not None else ""


def _clave(proceso: str, tarea: str, subtarea: str) -> str:
    texto = "|".join(normalizar(x).casefold() for x in (proceso, tarea, subtarea))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass
class Conversion:
    regla: Regla | None
    franja: str = ""
    estado: str = "confirmado"
    motivo_revision: str = ""


def _revision(motivo: str, regla: Regla | None = None) -> Conversion:
    return Conversion(regla=regla, motivo_revision=motivo)


def convertir_regla(periodicidad, cuando) -> Conversion:
    per, cua = normalizar(periodicidad), normalizar(cuando)
    per_l, cua_l = per.casefold(), cua.casefold()
    if not per:
        return _revision("Falta la periodicidad" + (" y el «Cuándo»." if not cua else "."))
    dia_semana = re.fullmatch(r"(lunes|martes|mi[eé]rcoles|jueves|viernes)(?:\s*\((ma[nñ]ana|tarde)\))?", cua_l)

    if per_l == "diaria":
        if re.fullmatch(r"todos los d[ií]as h[aá]biles", cua_l):
            return Conversion(Regla("DIARIA_HABIL"))
        if dia_semana:
            return _revision(f"Contradicción: periodicidad «{per}» pero «Cuándo» dice «{cua}».")
    elif per_l == "semanal":
        if not cua:
            return _revision("Periodicidad semanal sin día de la semana.")
        if dia_semana:
            nombre = dia_semana.group(1).replace("miercoles", "miércoles")
            franja = (dia_semana.group(2) or "").replace("manana", "mañana")
            return Conversion(Regla("SEMANAL", dia_semana=DIAS[nombre]), franja=franja)
    elif per_l == "mensual (cierre)":
        m = re.fullmatch(r"d[ií]a h[aá]bil (\d+)", cua_l)
        if m:
            return Conversion(Regla("CIERRE_DIA_HABIL", n=int(m.group(1))))
        m = re.match(r"d(7|10)\b", cua_l)
        if m:
            return Conversion(Regla("CIERRE_HITO", n=int(m.group(1))))
    elif per_l == "mensual":
        m = re.fullmatch(r"d[ií]a (\d{1,2})", cua_l)
        if m:
            # Si cae en inhábil: día hábil anterior (P4, Karla). La norma de Previred la verifica la Contadora Senior.
            return Conversion(Regla("DIA_FIJO", dia=int(m.group(1)), ajuste="anterior"), estado="pendiente_confirmar")
    elif per_l == "puntual":
        if cua_l.startswith("al "):
            return Conversion(Regla("EVENTO"))
        meses = tuple(sorted({n for nombre, n in MESES.items() if re.search(rf"\b{nombre}\b", cua_l)}))
        if meses:
            return _revision("Faltan el día del mes en que vence (el Excel solo indica los meses).", Regla("MESES", meses=meses))
    else:
        return _revision(f"No se reconoce la periodicidad «{per}».")
    return _revision(f"No se reconoce «Cuándo» = «{cua}» para la periodicidad «{per}».")


@dataclass
class FilaImport:
    fila: int
    proceso: str
    tarea_principal: str
    subtarea: str
    ejecuta: str
    revisa_excel: str
    periodicidad: str
    cuando: str
    fecha_1ra: object
    observacion: str
    clave: str = ""
    conversion: Conversion | None = None

    @property
    def externa(self) -> bool:
        return self.ejecuta in CARGOS_EXTERNOS


@dataclass
class VistaPrevia:
    altas: list = field(default_factory=list)
    cambios: list = field(default_factory=list)  # (Tarea, FilaImport, {campo: (antes, después)})
    bajas: list = field(default_factory=list)
    duplicadas: list = field(default_factory=list)
    procesos_nuevos: list = field(default_factory=list)
    cargos_nuevos: list = field(default_factory=list)
    requieren_revision: list = field(default_factory=list)  # (FilaImport, motivo)
    externas: list = field(default_factory=list)
    inconsistencias_fecha: list = field(default_factory=list)  # (FilaImport, texto)
    total_filas: int = 0


def leer_excel(ruta) -> list[FilaImport]:
    hoja = openpyxl.load_workbook(Path(ruta), data_only=True)["Tareas"]
    filas = list(hoja.iter_rows(values_only=True))
    inicio = next(i for i, r in enumerate(filas) if r and "Proceso" in r)
    columnas = {normalizar(nombre): i for i, nombre in enumerate(filas[inicio]) if nombre}

    def col(nombre):
        return columnas[nombre] if nombre in columnas else next(i for n, i in columnas.items() if n.startswith(nombre))

    idx = {k: col(v) for k, v in {
        "proceso": "Proceso", "tarea": "Tarea principal", "sub": "Subtarea", "ejecuta": "Responsable (ejecuta)",
        "revisa": "Revisa", "per": "Periodicidad", "cuando": "Cuándo", "fecha": "Fecha 1.ª vez", "obs": "Observación",
    }.items()}
    resultado = []
    for n, r in enumerate(filas[inicio + 1:], start=inicio + 2):
        if not (normalizar(r[idx["tarea"]]) or normalizar(r[idx["sub"]])):
            continue
        ejecuta = normalizar(r[idx["ejecuta"]])
        resultado.append(FilaImport(
            fila=n, proceso=normalizar(r[idx["proceso"]]), tarea_principal=normalizar(r[idx["tarea"]]),
            subtarea=normalizar(r[idx["sub"]]), ejecuta=ALIAS_DE_CARGO.get(ejecuta, ejecuta),
            revisa_excel=normalizar(r[idx["revisa"]]), periodicidad=normalizar(r[idx["per"]]),
            cuando=normalizar(r[idx["cuando"]]), fecha_1ra=r[idx["fecha"]], observacion=normalizar(r[idx["obs"]]),
        ))
    return resultado


def cargo_revisor(ejecuta: str) -> str:
    """DEC-08: revisa siempre la Jefa; la Jefa no puede revisarse a sí misma, así que sus tareas las revisa el Gerente (P1)."""
    return CARGO_GERENTE if ejecuta == CARGO_JEFA else CARGO_JEFA


def _valores(fila: FilaImport) -> dict:
    c = fila.conversion
    r = c.regla
    motivo = c.motivo_revision or ("Falta el responsable (ejecuta)." if not fila.ejecuta else "")
    return {
        "cargo_ejecuta": fila.ejecuta, "cargo_revisa": cargo_revisor(fila.ejecuta) if fila.ejecuta else None,
        "revisa_excel": fila.revisa_excel, "periodicidad_excel": fila.periodicidad, "cuando_excel": fila.cuando,
        "regla_tipo": r.tipo if r else "", "regla_dia_semana": r.dia_semana if r else None,
        "regla_n": r.n if r else None, "regla_dia": r.dia if r else None,
        "regla_meses": ",".join(str(m) for m in r.meses) if r else "", "regla_ajuste": r.ajuste if r else "siguiente",
        "regla_franja": c.franja, "regla_estado": c.estado, "referencia_normativa": fila.observacion,
        "requiere_revision": bool(motivo), "motivo_revision": motivo,
    }


def _valores_actuales(t: Tarea) -> dict:
    return {
        "cargo_ejecuta": t.cargo_ejecuta.nombre, "cargo_revisa": t.cargo_revisa.nombre if t.cargo_revisa else None,
        "revisa_excel": t.revisa_excel, "periodicidad_excel": t.periodicidad_excel, "cuando_excel": t.cuando_excel,
        "regla_tipo": t.regla_tipo, "regla_dia_semana": t.regla_dia_semana, "regla_n": t.regla_n, "regla_dia": t.regla_dia,
        "regla_meses": t.regla_meses, "regla_ajuste": t.regla_ajuste, "regla_franja": t.regla_franja,
        "regla_estado": t.regla_estado, "referencia_normativa": t.referencia_normativa,
        "requiere_revision": t.requiere_revision, "motivo_revision": t.motivo_revision,
    }


def _chequear_fecha(fila: FilaImport, cal: Calendario) -> str | None:
    f = fila.fecha_1ra
    r = fila.conversion.regla
    if isinstance(f, datetime):
        f = f.date()
    if not isinstance(f, date) or r is None or r.tipo in ("EVENTO", "MESES"):
        return None
    try:
        esperadas = fechas_limite(r, f.year, f.month, cal)
    except (ReglaIncompleta, ReglaInvalida, ValueError):
        return None
    if f not in esperadas:
        return f"La regla {r.tipo} no genera el {f:%d-%m-%Y} (genera: {', '.join(d.strftime('%d-%m-%Y') for d in esperadas)})."
    return None


def previsualizar(ruta, calendario: Calendario | None = None) -> VistaPrevia:
    if calendario is None:
        from nucleo.models import Feriado
        calendario = Calendario(Feriado.objects.filter(confirmado=True).values_list("fecha", flat=True))
    filas = leer_excel(ruta)
    vp = VistaPrevia(total_filas=len(filas))
    existentes = {t.clave_estable: t for t in Tarea.objects.select_related("cargo_ejecuta", "cargo_revisa")}
    procesos = set(Proceso.objects.values_list("nombre", flat=True))
    cargos = set(Cargo.objects.values_list("nombre", flat=True))
    vistas = set()
    for f in filas:
        f.clave = _clave(f.proceso, f.tarea_principal, f.subtarea)
        if f.clave in vistas:
            vp.duplicadas.append(f)
            continue
        vistas.add(f.clave)
        f.conversion = convertir_regla(f.periodicidad, f.cuando)
        valores = _valores(f)
        if valores["requiere_revision"]:
            vp.requieren_revision.append((f, valores["motivo_revision"]))
        if f.externa:
            vp.externas.append(f)
        aviso = _chequear_fecha(f, calendario)
        if aviso:
            vp.inconsistencias_fecha.append((f, aviso))
        if f.proceso not in procesos and f.proceso not in vp.procesos_nuevos:
            vp.procesos_nuevos.append(f.proceso)
        for nombre in (f.ejecuta, valores["cargo_revisa"]):
            if nombre and nombre not in cargos and nombre not in vp.cargos_nuevos:
                vp.cargos_nuevos.append(nombre)
        actual = existentes.get(f.clave)
        if actual is None:
            vp.altas.append(f)
        else:
            antes = _valores_actuales(actual)
            diff = {k: (antes[k], v) for k, v in valores.items() if antes[k] != v}
            if diff:
                vp.cambios.append((actual, f, diff))
    vp.bajas = [t for clave, t in existentes.items() if clave not in vistas and t.activa]
    return vp


def _cargo(nombre: str) -> Cargo:
    cargo, _ = Cargo.objects.get_or_create(nombre=nombre, defaults={"es_externo": nombre in CARGOS_EXTERNOS})
    return cargo


def _aplicar_valores(tarea: Tarea, valores: dict):
    tarea.cargo_ejecuta = _cargo(valores["cargo_ejecuta"]) if valores["cargo_ejecuta"] else tarea.cargo_ejecuta
    tarea.cargo_revisa = _cargo(valores["cargo_revisa"]) if valores["cargo_revisa"] else None
    for k, v in valores.items():
        if k not in ("cargo_ejecuta", "cargo_revisa"):
            setattr(tarea, k, v)


@transaction.atomic
def aplicar(vp: VistaPrevia, usuario) -> dict:
    ultimo = Tarea.objects.order_by("-codigo").values_list("codigo", flat=True).first()
    siguiente = int(ultimo.split("-")[1]) + 1 if ultimo else 1
    for f in vp.altas:
        valores = _valores(f)
        proceso, _ = Proceso.objects.get_or_create(nombre=f.proceso)
        tarea = Tarea(codigo=f"TAR-{siguiente:04d}", clave_estable=f.clave, proceso=proceso,
                      tarea_principal=f.tarea_principal, subtarea=f.subtarea)
        siguiente += 1
        _aplicar_valores(tarea, valores)
        tarea.save()
    for tarea, f, diff in vp.cambios:
        _aplicar_valores(tarea, _valores(f))
        tarea.save()
    for tarea in vp.bajas:
        tarea.activa = False
        tarea.save(update_fields=["activa"])
    resumen = {"altas": len(vp.altas), "cambios": len(vp.cambios), "bajas": len(vp.bajas),
               "requieren_revision": len(vp.requieren_revision), "externas": len(vp.externas)}
    auditoria.registrar("importacion.aplicada", usuario=usuario, entidad="Tarea", despues=resumen)
    return resumen

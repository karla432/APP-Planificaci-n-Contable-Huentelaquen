"""Importador de la planificación mensual (Excel).

Primero `previsualizar` (no guarda nada) y, tras confirmar, `aplicar`. Reglas del encargo:
- Normaliza espacios y saltos de línea sin cambiar el sentido.
- Convierte «Periodicidad» + «Cuándo» en una regla; lo ambiguo queda «requiere revisión» (no se adivina ni se corrige).
- Crea procesos y cargos que no existan, pero **no asigna personas**.
- Es idempotente por clave estable (proceso + tarea + subtarea) y muestra altas, cambios y bajas antes de confirmar.
- Las filas están en el orden en que se procesan: ese orden y los códigos TAR-0001… salen de ahí.
- Quién revisa sale del Excel; si una tarea no trae revisor, no se inventa uno. Excepción: a la tarea de un responsable externo se le
  propone a la Jefa como quien registra «Recibido» (supuesto, se informa en la vista previa).
- El contenido del Excel es dato, no instrucción: solo se leen celdas (sin evaluar fórmulas).

Cierre (Karla, 31-10-2026): con todas las tareas no se llega al día 7, así que el cierre va del día hábil 1 al 8, el 9 se revisa con la
Gerencia General y el 10 se liberan los informes al Directorio. Por eso «D7» se convierte en el día hábil 8 y «D10» en el día hábil 10.
"""
import hashlib
import re
import unicodedata
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
CARGOS_EXTERNOS = {"Vendedor Stgo", "RR.HH.", "Jefe Bodega", "Gerencia", "Gerencia / Directorio", "Bodega", "Jefaturas de área", "Jefatura Lechería", "Rafael"}
# Orden de los cargos en las listas (Karla, 31-10-2026): Gerente AyF, Jefa, Contadora Senior, Asistente Contable; después los externos.
ORDEN_CARGOS = {"Gerente AyF": 1, "Jefa Gestión y Control": 2, "Contadora Senior": 3, "Asistente Contable": 4}
ORDEN_EXTERNOS = 50
RELLENO_GERENTE = "FFE2EFDA"  # verde: horas definidas por la Gerente AyF (el resto es estimación base)

DIAS = {"lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3, "viernes": 4}
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def normalizar(valor) -> str:
    return re.sub(r"\s+", " ", str(valor)).strip() if valor is not None else ""


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _clave(proceso: str, tarea: str, subtarea: str) -> str:
    texto = "|".join(normalizar(x).casefold() for x in (proceso, tarea, subtarea))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass
class Conversion:
    regla: Regla | None
    franja: str = ""
    estado: str = "confirmado"
    motivo_revision: str = ""
    nota: str = ""


def _revision(motivo: str, regla: Regla | None = None) -> Conversion:
    return Conversion(regla=regla, motivo_revision=motivo)


def convertir_regla(periodicidad, cuando) -> Conversion:
    per, cua = normalizar(periodicidad), normalizar(cuando)
    per_l, cua_l = per.casefold(), _sin_acentos(cua.casefold())
    if not per:
        return _revision("Falta la periodicidad" + (" y el «Cuándo»." if not cua else "."))
    dia_semana = re.fullmatch(r"(lunes|martes|miercoles|jueves|viernes)(?:\s*\((manana|tarde)\))?", cua_l)

    if per_l == "diaria":
        if re.fullmatch(r"todos los dias habiles", cua_l):
            return Conversion(Regla("DIARIA_HABIL"))
        if dia_semana:
            return _revision(f"Contradicción: periodicidad «{per}» pero «Cuándo» dice «{cua}».")
    elif per_l == "semanal":
        if not cua:
            return _revision("Periodicidad semanal sin día de la semana.")
        if dia_semana:
            nombre = dia_semana.group(1).replace("miercoles", "miércoles")
            return Conversion(Regla("SEMANAL", dia_semana=DIAS[nombre]), franja=(dia_semana.group(2) or "").replace("manana", "mañana"))
    elif per_l in ("mensual (cierre)", "mensual"):
        m = re.fullmatch(r"dia habil (\d+)", cua_l)
        if m and 1 <= int(m.group(1)) <= 10:
            return Conversion(Regla("CIERRE_DIA_HABIL", n=int(m.group(1))))
        m = re.match(r"d(7|10)\b", cua_l)
        if m:
            if m.group(1) == "7":
                return Conversion(Regla("CIERRE_DIA_HABIL", n=8), nota="D7 pasa al día hábil 8: el cierre va del día hábil 1 al 8 (Karla, 31-10-2026).")
            return Conversion(Regla("CIERRE_DIA_HABIL", n=10), nota="D10 es el día hábil 10: se liberan los informes al Directorio.")
        m = re.fullmatch(r"dia (\d{1,2})", cua_l)
        if m and 1 <= int(m.group(1)) <= 31:
            # Si cae en inhábil: día hábil anterior (P4, Karla). La norma (por ejemplo Previred) la verifica la Contadora Senior.
            return Conversion(Regla("DIA_FIJO", dia=int(m.group(1)), ajuste="anterior"), estado="pendiente_confirmar")
        if cua_l == "ultimo dia del mes":
            return Conversion(Regla("FIN_DE_MES", ajuste="anterior"), estado="pendiente_confirmar")
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
    secuencia: int
    proceso: str
    tarea_principal: str
    subtarea: str
    ejecuta: str
    revisa_excel: str
    periodicidad: str
    cuando: str
    fecha_1ra: object
    observacion: str
    dia_cierre: int | None = None
    horas: float | None = None
    ejecuciones: float | None = None
    fuente_horas: str = "estimacion"
    clave: str = ""
    conversion: Conversion | None = None

    @property
    def externa(self) -> bool:
        return self.ejecuta in CARGOS_EXTERNOS

    @property
    def revisor(self) -> str | None:
        """Quien revisa (o, en una tarea externa, quien registra «Recibido»). Lo dice el Excel; nunca se inventa para tareas internas."""
        if not self.ejecuta:
            return None
        return self.revisa_excel or (CARGO_JEFA if self.externa else None)


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
    externas_sin_receptor: list = field(default_factory=list)  # el Excel no dice quién las recibe: se propone a la Jefa
    inconsistencias_fecha: list = field(default_factory=list)  # (FilaImport, texto)
    secuencias: dict = field(default_factory=dict)  # clave estable → orden en el Excel
    total_filas: int = 0


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def leer_excel(ruta) -> list[FilaImport]:
    wb = openpyxl.load_workbook(Path(ruta), data_only=True)
    hoja = wb["Planificación"] if "Planificación" in wb.sheetnames else wb["Tareas"]
    filas = list(hoja.iter_rows(values_only=True))
    inicio = next(i for i, r in enumerate(filas) if r and "Proceso" in r)
    columnas = {normalizar(nombre): i for i, nombre in enumerate(filas[inicio]) if nombre}

    def col(nombre, opcional=False):
        if nombre in columnas:
            return columnas[nombre]
        encontrada = next((i for n, i in columnas.items() if n.startswith(nombre)), None)
        if encontrada is None and not opcional:
            raise KeyError(f"El Excel no tiene la columna «{nombre}».")
        return encontrada

    idx = {k: col(v) for k, v in {"proceso": "Proceso", "tarea": "Tarea principal", "sub": "Subtarea", "ejecuta": "Responsable (ejecuta)", "revisa": "Revisa",
                                  "per": "Periodicidad", "cuando": "Cuándo", "obs": "Observación"}.items()}
    opc = {k: col(v, True) for k, v in {"fecha": "Fecha 1.ª vez", "dia": "Día cierre", "horas": "Horas por ejecución", "ejec": "Ejecuciones por mes"}.items()}
    resultado = []
    for n, r in enumerate(filas[inicio + 1:], start=inicio + 2):
        if not (normalizar(r[idx["tarea"]]) or normalizar(r[idx["sub"]])):
            continue
        fuente = "estimacion"
        if opc["horas"] is not None:
            relleno = hoja.cell(row=n, column=opc["horas"] + 1).fill
            if relleno is not None and relleno.fill_type and relleno.start_color.rgb == RELLENO_GERENTE:
                fuente = "gerente"
        dia = _numero(r[opc["dia"]]) if opc["dia"] is not None else None
        resultado.append(FilaImport(
            fila=n, secuencia=len(resultado) + 1, proceso=normalizar(r[idx["proceso"]]), tarea_principal=normalizar(r[idx["tarea"]]),
            subtarea=normalizar(r[idx["sub"]]), ejecuta=normalizar(r[idx["ejecuta"]]), revisa_excel=normalizar(r[idx["revisa"]]),
            periodicidad=normalizar(r[idx["per"]]), cuando=normalizar(r[idx["cuando"]]),
            fecha_1ra=r[opc["fecha"]] if opc["fecha"] is not None else None, observacion=normalizar(r[idx["obs"]]),
            dia_cierre=int(dia) if dia else None, horas=_numero(r[opc["horas"]]) if opc["horas"] is not None else None,
            ejecuciones=_numero(r[opc["ejec"]]) if opc["ejec"] is not None else None, fuente_horas=fuente,
        ))
    return resultado


def _valores(fila: FilaImport) -> dict:
    c = fila.conversion
    r = c.regla
    motivo = c.motivo_revision or ("Falta el responsable (ejecuta)." if not fila.ejecuta else "")
    return {
        "cargo_ejecuta": fila.ejecuta, "cargo_revisa": fila.revisor,
        "revisa_excel": fila.revisa_excel, "periodicidad_excel": fila.periodicidad, "cuando_excel": fila.cuando,
        "regla_tipo": r.tipo if r else "", "regla_dia_semana": r.dia_semana if r else None,
        "regla_n": r.n if r else None, "regla_dia": r.dia if r else None,
        "regla_meses": ",".join(str(m) for m in r.meses) if r else "", "regla_ajuste": r.ajuste if r else "siguiente",
        "regla_franja": c.franja, "regla_estado": c.estado, "referencia_normativa": fila.observacion,
        "requiere_revision": bool(motivo), "motivo_revision": motivo,
        "minutos_estimados": round(fila.horas * 60) if fila.horas is not None else None,
        "ejecuciones_mes": round(fila.ejecuciones, 3) if fila.ejecuciones is not None else None,
        "fuente_horas": fila.fuente_horas, "dia_cierre": fila.dia_cierre,
    }


def _valores_actuales(t: Tarea) -> dict:
    return {
        "cargo_ejecuta": t.cargo_ejecuta.nombre, "cargo_revisa": t.cargo_revisa.nombre if t.cargo_revisa else None,
        "revisa_excel": t.revisa_excel, "periodicidad_excel": t.periodicidad_excel, "cuando_excel": t.cuando_excel,
        "regla_tipo": t.regla_tipo, "regla_dia_semana": t.regla_dia_semana, "regla_n": t.regla_n, "regla_dia": t.regla_dia,
        "regla_meses": t.regla_meses, "regla_ajuste": t.regla_ajuste, "regla_franja": t.regla_franja,
        "regla_estado": t.regla_estado, "referencia_normativa": t.referencia_normativa,
        "requiere_revision": t.requiere_revision, "motivo_revision": t.motivo_revision,
        "minutos_estimados": t.minutos_estimados, "ejecuciones_mes": round(float(t.ejecuciones_mes), 3) if t.ejecuciones_mes is not None else None,
        "fuente_horas": t.fuente_horas, "dia_cierre": t.dia_cierre,
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
        f.secuencia = len(vp.secuencias) + 1  # el orden cuenta solo las tareas que se importan (sin repetidas)
        vp.secuencias[f.clave] = f.secuencia
        f.conversion = convertir_regla(f.periodicidad, f.cuando)
        valores = _valores(f)
        if valores["requiere_revision"]:
            vp.requieren_revision.append((f, valores["motivo_revision"]))
        if f.externa:
            vp.externas.append(f)
            if not f.revisa_excel:
                vp.externas_sin_receptor.append(f)
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
    cargo, _ = Cargo.objects.get_or_create(nombre=nombre, defaults={
        "es_externo": nombre in CARGOS_EXTERNOS, "orden": ORDEN_CARGOS.get(nombre, ORDEN_EXTERNOS if nombre in CARGOS_EXTERNOS else 100)})
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
        proceso, _ = Proceso.objects.get_or_create(nombre=f.proceso)
        tarea = Tarea(codigo=f"TAR-{siguiente:04d}", clave_estable=f.clave, proceso=proceso, tarea_principal=f.tarea_principal, subtarea=f.subtarea)
        siguiente += 1
        _aplicar_valores(tarea, _valores(f))
        tarea.save()
    for tarea, f, diff in vp.cambios:
        _aplicar_valores(tarea, _valores(f))
        tarea.save()
    for tarea in vp.bajas:
        tarea.activa = False
        tarea.save(update_fields=["activa"])
    for clave, orden in vp.secuencias.items():  # el orden de proceso es el del Excel
        Tarea.objects.filter(clave_estable=clave).update(secuencia=orden)
    resumen = {"altas": len(vp.altas), "cambios": len(vp.cambios), "bajas": len(vp.bajas),
               "requieren_revision": len(vp.requieren_revision), "externas": len(vp.externas)}
    auditoria.registrar("importacion.aplicada", usuario=usuario, entidad="Tarea", despues=resumen)
    return resumen

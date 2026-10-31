"""Código de cada tarea: PRO-TAR-SUB (Karla, 31-10-2026).

PRO-01-TAR-03-SUB-02 = proceso 1 · tarea principal número 3 de ese proceso · subtarea número 2 de esa tarea principal.
El código se asigna una sola vez y no cambia, aunque después se reordenen los procesos o se edite la tarea.
"""
import re

from nucleo.models import Proceso, Tarea

PATRON = re.compile(r"^(PRO-\d+)-TAR-(\d+)-SUB-(\d+)$")


def formato(proceso: Proceso, n_tarea: int, n_sub: int) -> str:
    return f"{proceso.codigo}-TAR-{n_tarea:02d}-SUB-{n_sub:02d}"


def codigo_de_tarea(proceso: Proceso, tarea_principal: str) -> str:
    """El código siguiente libre: si la tarea principal ya existe en el proceso, la subtarea nueva sigue su numeración; si no, abre una tarea principal nueva."""
    numero_de: dict[str, int] = {}
    subs: dict[str, int] = {}
    mayor = 0
    for principal, codigo in Tarea.objects.filter(proceso=proceso).values_list("tarea_principal", "codigo"):
        m = PATRON.match(codigo)
        if not m:
            continue
        n, s = int(m.group(2)), int(m.group(3))
        numero_de.setdefault(principal, n)
        subs[principal] = max(subs.get(principal, 0), s)
        mayor = max(mayor, n)
    if tarea_principal in numero_de:
        return formato(proceso, numero_de[tarea_principal], subs[tarea_principal] + 1)
    return formato(proceso, mayor + 1, 1)

"""Documentos y evidencias adjuntos a los comentarios de una tarea."""
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from nucleo.models import Evidencia, EventoAuditoria, Ocurrencia
from nucleo.servicios import ejecucion, evidencias, periodos
from nucleo.servicios.errores import ErrorDeNegocio
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"


@pytest.fixture(autouse=True)
def entorno(monkeypatch, settings, tmp_path):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 12, 4))
    settings.EVIDENCIAS_ROOT = tmp_path / "evidencias"


@pytest.fixture
def mundo():
    ger, cont, asist = cargo("Gerente AyF"), cargo("Contador Senior"), cargo("Asistente Contable")
    p = {"ger": persona("Gerente", ger), "cont": persona("Contador", cont), "asist": persona("Asistente", asist)}
    u = {k: usuario_con_rol(k, r, p[k]) for k, r in (("ger", "GERENTE"), ("cont", "COLABORADOR"), ("asist", "COLABORADOR"))}
    u["lectura"] = usuario_con_rol("lectura", "LECTURA")
    u["admin"] = usuario_con_rol("admin", "ADMIN_SISTEMA")
    u["jefa"] = usuario_con_rol("jefa", "JEFATURA", persona("Jefa", cargo("Jefa de Control")))
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=ger, n=3)
    periodos.abrir_mes(2026, 12, usuario=None)
    return {"u": u, "o": Ocurrencia.objects.get()}


def archivo(nombre="respaldo.pdf", contenido=PDF):
    return SimpleUploadedFile(nombre, contenido)


def cli(u):
    c = Client()
    c.force_login(u)
    return c


# ---- Adjuntar ------------------------------------------------------------------------------------------------


def test_un_comentario_puede_llevar_un_documento_y_queda_en_la_bitacora(mundo, settings):
    ev = ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "Va el respaldo del banco", archivo())
    adj = Evidencia.objects.get()
    assert adj.evento_id == ev.pk and adj.nombre_original == "respaldo.pdf" and adj.tipo_contenido == "application/pdf" and adj.tamano == len(PDF)
    assert (settings.EVIDENCIAS_ROOT / adj.ruta).read_bytes() == PDF and "respaldo" not in adj.ruta  # se guarda con nombre aleatorio
    assert ev.despues["archivo"] == "respaldo.pdf" and len(ev.despues["sha256"]) == 64
    h = ejecucion.historial_de(mundo["o"])[0]
    assert h.comentario == "Va el respaldo del banco" and [a.nombre_original for a in h.adjuntos] == ["respaldo.pdf"]


def test_se_puede_adjuntar_sin_escribir_texto_pero_no_enviar_vacio(mundo):
    ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "", archivo())
    assert Evidencia.objects.count() == 1
    with pytest.raises(ErrorDeNegocio, match="adjunta un documento"):
        ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "  ")


@pytest.mark.parametrize("nombre,contenido,texto", [
    ("virus.exe", b"MZ....", "tipo de archivo"),
    ("pagina.html", b"<script>alert(1)</script>", "tipo de archivo"),
    ("falso.pdf", b"esto no es un pdf", "no corresponde"),
    ("falso.png", PDF, "no corresponde"),
    ("hoja.xlsx", b"texto cualquiera", "no corresponde"),
    ("vacio.pdf", b"", "vacío"),
    ("grande.pdf", PDF + b"0" * (10 * 1024 * 1024), "10 MB"),
    ("binario.csv", b"a,b\n\x00\x01\x02", "no es de texto"),
])
def test_un_archivo_inadecuado_se_rechaza_y_no_deja_nada(mundo, nombre, contenido, texto):
    antes = EventoAuditoria.objects.count()
    with pytest.raises(ErrorDeNegocio, match=texto):
        ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "intento", archivo(nombre, contenido))
    assert not Evidencia.objects.exists() and EventoAuditoria.objects.count() == antes


@pytest.mark.parametrize("nombre,contenido", [("hoja.xlsx", b"PK\x03\x04datos"), ("carta.docx", b"PK\x03\x04datos"), ("viejo.xls", b"\xd0\xcf\x11\xe0datos"),
                                              ("datos.csv", "año;valor\n2026;1".encode()), ("nota.txt", b"hola"), ("foto.jpg", b"\xff\xd8\xff\xe0datos"), ("foto.png", b"\x89PNG\r\n\x1a\ndatos")])
def test_los_tipos_permitidos_se_aceptan(mundo, nombre, contenido):
    ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "ok", archivo(nombre, contenido))
    assert Evidencia.objects.get().extension == nombre.rsplit(".", 1)[1]


def test_el_nombre_del_archivo_se_limpia(mundo):
    ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "x", archivo("../../etc/pas\x00swd.pdf"))
    assert Evidencia.objects.get().nombre_original == "passwd.pdf"


def test_un_periodo_cerrado_no_admite_comentarios_ni_adjuntos(mundo):
    mundo["o"].periodo.estado = "cerrado"
    mundo["o"].periodo.save()
    with pytest.raises(ErrorDeNegocio, match="cerrado"):
        ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "x", archivo())
    assert not Evidencia.objects.exists()


# ---- Quién lo ve --------------------------------------------------------------------------------------------------------


@pytest.fixture
def con_adjunto(mundo):
    ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "Respaldo", archivo())
    return Evidencia.objects.get()


@pytest.mark.parametrize("quien", ["cont", "ger", "jefa"])
def test_lo_ven_quien_ejecuta_a_quien_se_reporta_y_la_jefatura(mundo, con_adjunto, quien):
    r = cli(mundo["u"][quien]).get(reverse("evidencia", args=[con_adjunto.pk]))
    assert r.status_code == 200 and b"".join(r.streaming_content) == PDF
    assert r["Content-Type"] == "application/pdf" and "inline" in r["Content-Disposition"]
    assert r["X-Content-Type-Options"] == "nosniff" and "sandbox" in r["Content-Security-Policy"] and "no-store" in r["Cache-Control"]


@pytest.mark.parametrize("quien", ["asist", "lectura", "admin"])
def test_los_demas_no_lo_ven(mundo, con_adjunto, quien):
    assert cli(mundo["u"][quien]).get(reverse("evidencia", args=[con_adjunto.pk])).status_code == 403


def test_sin_sesion_no_hay_acceso(mundo, con_adjunto):
    assert Client().get(reverse("evidencia", args=[con_adjunto.pk])).status_code == 302


def test_lo_que_no_es_pdf_o_imagen_se_descarga_y_no_se_muestra(mundo):
    ejecucion.comentar(mundo["o"], mundo["u"]["cont"], "hoja", archivo("hoja.xlsx", b"PK\x03\x04datos"))
    r = cli(mundo["u"]["ger"]).get(reverse("evidencia", args=[Evidencia.objects.get().pk]))
    assert "attachment" in r["Content-Disposition"] and "hoja.xlsx" in r["Content-Disposition"]


def test_un_pdf_se_puede_forzar_a_descargar(mundo, con_adjunto):
    r = cli(mundo["u"]["ger"]).get(reverse("evidencia", args=[con_adjunto.pk]), {"descargar": "1"})
    assert "attachment" in r["Content-Disposition"]


def test_una_ruta_manipulada_no_puede_salir_de_la_carpeta_de_evidencias(mundo, con_adjunto):
    Evidencia.objects.filter(pk=con_adjunto.pk).update(ruta="../../../../etc/passwd")
    assert cli(mundo["u"]["ger"]).get(reverse("evidencia", args=[con_adjunto.pk])).status_code == 404


# ---- Pantalla ----------------------------------------------------------------------------------------------------------


def test_el_detalle_pide_el_adjunto_y_muestra_el_enlace_a_quien_corresponde(mundo, con_adjunto):
    ver = lambda q: cli(mundo["u"][q]).get(reverse("detalle_ocurrencia", args=[mundo["o"].pk])).content.decode()
    html = ver("ger")
    assert "Adjuntar documento o evidencia" in html and 'enctype="multipart/form-data"' in html and "respaldo.pdf" in html and reverse("evidencia", args=[con_adjunto.pk]) in html
    restringido = ver("asist")
    assert "respaldo.pdf" not in restringido and "Adjunto restringido" in restringido


def test_comentar_con_archivo_desde_la_pantalla(mundo):
    r = cli(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[mundo["o"].pk, "comentar"]),
                                     {"comentario": "Con respaldo", "archivo": archivo(), "siguiente": reverse("detalle_ocurrencia", args=[mundo["o"].pk])}, follow=True)
    html = r.content.decode()
    assert "Con respaldo" in html and "respaldo.pdf" in html and Evidencia.objects.count() == 1


def test_un_archivo_malo_desde_la_pantalla_avisa_y_no_guarda(mundo):
    r = cli(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[mundo["o"].pk, "comentar"]),
                                     {"comentario": "x", "archivo": archivo("virus.exe", b"MZ"), "siguiente": reverse("detalle_ocurrencia", args=[mundo["o"].pk])}, follow=True)
    assert "tipo de archivo" in r.content.decode() and not Evidencia.objects.exists()

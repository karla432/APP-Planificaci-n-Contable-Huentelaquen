from django.conf import settings


def modo_prueba(request):
    return {"modo_prueba": settings.ACCESO_RAPIDO}

"""Adaptador del modelo top (vision_top.py) al contrato de algoritmos/__init__.py."""
import os
from . import vision_top as V

VERSION = "top-v3"
VARIABLES = {"apertura": {"unidad": "0-10", "nombre": "Apertura válvula",
                          "rango": (-0.6, 10.5), "salto_max": 4, "nexlab": "opening"}}

_lector = None


def leer(rutas):
    global _lector
    if _lector is None:
        ref = os.path.join(os.path.dirname(__file__), "foto_referencia_top.jpg")
        _lector = V.LectorTop(ref, V.CALIBRACION_VIGENTE)
    rutas = [str(r) for r in rutas]
    return [{"archivo": os.path.basename(ruta), "variable": "apertura", "valor": r["apertura"],
             "estado": r["estado"], "detalle": " | ".join(r["notas"])}
            for ruta, r in zip(rutas, _lector.leer_dia(rutas))]

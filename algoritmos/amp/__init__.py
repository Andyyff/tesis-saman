"""Adaptador del modelo amp (amp_v10.py, V10 congelada) al contrato de algoritmos/__init__.py."""
import math
import os
from .amp_v10 import AMPV10

VERSION = "amp-v10"
VARIABLES = {f"f{i}": {"unidad": "A", "nombre": f"Amperaje F{i}", "rango": (0, 200),
                       "salto_max": 30, "nexlab": f"amp_f{i}"} for i in (1, 2, 3)}

_modelo = None


def leer(rutas):
    global _modelo
    if _modelo is None:
        _modelo = AMPV10()
    filas = []
    for ruta in map(str, rutas):
        for r in _modelo.predict_image(ruta):
            medida = not math.isnan(r["value"])
            filas.append({"archivo": os.path.basename(ruta), "variable": r["phase"].lower(),
                          "valor": r["value"] if medida else None,
                          "estado": "medida" if medida else r["status"].lower(), "detalle": r["rule"] or ""})
    return filas

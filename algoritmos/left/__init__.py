"""Adaptador del modelo left (vision_left.py, v3) al contrato de algoritmos/__init__.py."""
import os
import numpy as np
from . import vision_left as V

VERSION = "left-v3"
VARIABLES = {"distancia_a": {"unidad": "mm", "nombre": "Distancia pesa A", "rango": (0, 200), "salto_max": 20},
             "distancia_b": {"unidad": "mm", "nombre": "Distancia pesa B", "rango": (0, 200), "salto_max": 20},
             "angulo": {"unidad": "°", "nombre": "Ángulo palanca", "rango": (0, 180), "salto_max": 10}}

_lector = None


def leer(rutas):
    global _lector
    if _lector is None:
        aqui = os.path.dirname(__file__)
        _lector = V.LectorLeft(os.path.join(aqui, "referencia_left.jpg"), np.load(os.path.join(aqui, "fondo_fijo.npy")))
    filas = []
    for ruta in map(str, rutas):
        archivo, s = os.path.basename(ruta), _lector.leer(ruta)
        if "error" in s:
            filas += [dict(archivo=archivo, variable=v, valor=None, estado="imagen_ilegible", detalle=s["error"])
                      for v in VARIABLES]
            continue
        for barra in ("a", "b"):
            m = s["varillas"][barra]
            estado = {"varilla_sin_pesa": "sin_pesa"}.get(m["estado"], m["estado"])
            filas.append(dict(archivo=archivo, variable=f"distancia_{barra}", valor=m["distancia_mm"],
                              estado=estado, detalle=" | ".join(m["notas"])))
        a = s["angulo"]
        filas.append(dict(archivo=archivo, variable="angulo", valor=a["angulo_grados"],
                          estado="medida" if a["angulo_grados"] is not None else "angulo_no_medido",
                          detalle=" | ".join(a["notas"])))
    return filas

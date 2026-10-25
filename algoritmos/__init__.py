"""Registro de algoritmos: lo único que el flujo sabe de ellos.

Contrato que cumple cada carpeta algoritmos/<camara>/__init__.py:

    VERSION  = "top-v3"                      # cambiarla cada vez que cambia el resultado
    VARIABLES = {"apertura": {"unidad": "0-10", "nombre": "Apertura válvula",
                              "rango": (-0.6, 10.5), "nexlab": "opening"}}
    def leer(rutas: list[str]) -> list[dict]:
        # una fila por (foto, variable):
        # {"archivo": "RIC-0001-TOP_2026-10-25_11-11-35.jpg", "variable": "apertura",
        #  "valor": 8.95 o None, "estado": "medida" u otro motivo, "detalle": "..."}

    ejemplos/ con fotos y esperado.csv (archivo, estado, <variable>) para probar.py

"rango": un valor fuera de rango no llega al panel (queda vacío con estado fuera_de_rango).
"salto_max" (opcional): cambio entre dos casilleros seguidos que se marca para revisar (no se borra).
"nexlab": campo del JSON de Nexlab que mide lo mismo, para guardarlo al lado como referencia.
"""
import importlib

CAMARAS = ["top", "left", "amp"]


def cargar(camara):
    return importlib.import_module(f"algoritmos.{camara}")

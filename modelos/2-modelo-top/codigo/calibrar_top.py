#!/usr/bin/env python3
"""calibrar_top.py — ajusta la escala 0-10 contra el `opening` de Nexlab con
VARIOS dias y la valida dejando un dia afuera cada vez.

    python3 calibrar_top.py salida_dia1.csv datos_dia1.json salida_dia2.csv datos_dia2.json ...

Los CSV son de medir_dia_top.py (usa su columna posicion_px; da igual si se
genero con o sin calibracion). Los JSON los baja descargar_top.py.
Imprime la recta para pegar en vision_top.py (CALIBRACION_VIGENTE).
Usa solo fotos de color normal, sin error de Nexlab y con nuestra medicion.
"""
import csv, json, sys, numpy as np

args = sys.argv[1:]
D = {}
for c, j in zip(args[0::2], args[1::2]):
    nos = {r["archivo"]: r for r in csv.DictReader(open(c))}
    pts = []
    for r in json.load(open(j)):
        o = nos.get(r["filename"])
        if not o or r["err"] or o["estado"] != "medida" or float(o["tinte_camara"] or 9) >= 1.3:
            continue
        pts.append((float(o["posicion_px"]), r["opening"]))
    D[j[-15:-5]] = np.array(pts)
    print(f"{j[-15:-5]}: {len(pts)} fotos, Nexlab de {min(p[1] for p in pts)} a {max(p[1] for p in pts)}")

def ajuste_robusto(P):
    k, b = np.polyfit(P[:, 0], P[:, 1], 1)
    for _ in range(3):   # descarta errores groseros de Nexlab (ej. 0,6 con el mango en 9)
        e = P[:, 1] - (k * P[:, 0] + b); ok = np.abs(e) < max(0.5, 4 * np.median(np.abs(e)))
        k, b = np.polyfit(P[ok, 0], P[ok, 1], 1)
    return k, b

print("\nDejando un dia afuera (se ajusta con los demas y se prueba en ese):")
for d in D:
    tr = np.vstack([D[k] for k in D if k != d]); k, b = ajuste_robusto(tr)
    e = D[d][:, 1] - (k * D[d][:, 0] + b)
    print(f"  {d}: |error| mediana {np.median(np.abs(e)):.3f}  p95 {np.percentile(np.abs(e),95):.3f}  (pendiente {k:.4f})")
k, b = ajuste_robusto(np.vstack(list(D.values())))
print(f"\nCalibracion con todos: apertura = {k:.5f} * posicion_px + {b:.4f}   (1 unidad = {1/k:.1f} px)")
print(f"Para vision_top.py:  CALIBRACION_VIGENTE = Calibracion.desde_recta({k:.5f}, {b:.4f})")

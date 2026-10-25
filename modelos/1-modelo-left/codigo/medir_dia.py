#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
medir_dia.py — Herramienta de produccion. Toma una fecha, lee todas las fotos
"left" de ese dia y devuelve una tabla con las dos variables que la planta
necesita, por barra y por foto.

    python3 medir_dia.py 2026-09-19
    python3 medir_dia.py 2026-09-19 --salida mediciones.csv

SOBRE LOS MILIMETROS
--------------------
La distancia sale directo en mm (dato de Latitud: 1 hendidura = 10 mm).
--paso-a / --paso-b solo se usan si algun dia hay que pisar ese valor.

COLUMNAS DE SALIDA
------------------
    fecha_hora            momento de la foto
    archivo               nombre de la foto original
    barra                 "a" (arriba) o "b" (abajo)
    estado                medida | sin_pesa | no_medida  (ver abajo)
    distancia_pasos       la misma distancia, en hendiduras (1 = 10 mm)
    distancia_mm          distancia tapon verde -> centro de la pesa, en mm
    distancia_px          idem en pixeles, para trazabilidad
    angulo_grados         angulo acordado con Latitud: varilla de adelante vs linea
                          perilla -> ficha magenta de arriba. Es UNO por foto
                          (se repite igual en las filas de "a" y "b")
    confianza_distancia   0 a 1
    confianza_angulo      0 a 1
    color_pesa            tono medido de la pesa
    detalle               por que no se pudo medir, cuando corresponde

Los tres estados posibles, y que significan para quien lee la tabla:
    medida    -> hay distancia y angulo
    sin_pesa  -> la barra esta sin pesa montada. NO es una falla: es el
                 estado real de la maquina, y el angulo igual es valido
    no_medida -> no se pudo leer; la columna `detalle` dice por que
"""
import argparse, csv, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_left as V

AQUI = os.path.dirname(os.path.abspath(__file__))
ENDPOINT = "http://sam-analysis.nexlab.com.uy/data"   # http: el servidor no tiene https
REF = os.path.join(AQUI, "referencia_left.jpg")
FONDO = os.path.join(AQUI, "fondo_fijo.npy")

CAMPOS = ["fecha_hora", "archivo", "barra", "estado", "distancia_pasos", "distancia_mm",
          "distancia_px", "angulo_grados", "confianza_distancia", "confianza_angulo",
          "color_pesa", "detalle"]


def bajar_dia(fecha, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    url = f"{ENDPOINT}?date={fecha}&env=prod&name_filter=left"
    regs = json.load(urllib.request.urlopen(url, timeout=90))
    for r in regs:
        r["_ruta"] = os.path.join(carpeta, r["filename"])

    def uno(r):
        if os.path.exists(r["_ruta"]) and os.path.getsize(r["_ruta"]) > 1000:
            return True
        try:
            urllib.request.urlretrieve(r["input_img_path"], r["_ruta"]); return True
        except Exception:
            return False
    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(uno, regs))
    return [r for r in regs if os.path.exists(r["_ruta"])]


def fila(reg, salida, barra, paso_mm):
    v = salida["varillas"][barra]
    ang = salida["angulo"]
    est = {"medida": "medida", "varilla_sin_pesa": "sin_pesa"}.get(v["estado"], "no_medida")
    detalle = "" if est != "no_medida" else "; ".join(v["notas"])[:150]
    mm = ""
    if v["distancia_pasos"] is not None and paso_mm:
        mm = round(v["distancia_pasos"] * paso_mm, 2)
    elif v.get("distancia_mm") is not None:
        mm = v["distancia_mm"]
    color = ""
    if v.get("pesa") and v["pesa"].get("color"):
        color = v["pesa"]["color"]["nombre"]
    return {
        "fecha_hora": reg["date"], "archivo": reg["filename"], "barra": barra,
        "estado": est,
        "distancia_pasos": v["distancia_pasos"] if v["distancia_pasos"] is not None else "",
        "distancia_mm": mm,
        "distancia_px": v["distancia_px"] if v["distancia_px"] is not None else "",
        "angulo_grados": ang["angulo_grados"] if ang["angulo_grados"] is not None else "",
        "confianza_distancia": v["confianza"],
        "confianza_angulo": ang["confianza"],
        "color_pesa": color, "detalle": detalle,
    }


def main():
    ap = argparse.ArgumentParser(description="Mide un dia completo de la camara 'left'.")
    ap.add_argument("fecha", help="YYYY-MM-DD")
    ap.add_argument("--paso-a", type=float, default=None,
                    help="paso de rosca de la barra de arriba, en mm")
    ap.add_argument("--paso-b", type=float, default=None,
                    help="paso de rosca de la barra de abajo, en mm")
    ap.add_argument("--salida", default=None, help="archivo CSV de salida")
    ap.add_argument("--fotos", default=os.path.join(AQUI, "fotos_dia"),
                    help="carpeta donde guardar las fotos descargadas")
    a = ap.parse_args()

    print(f"Descargando las fotos del {a.fecha}...", flush=True)
    regs = bajar_dia(a.fecha, os.path.join(a.fotos, a.fecha))
    if not regs:
        print("No hay fotos para esa fecha."); return
    print(f"{len(regs)} fotos. Midiendo...", flush=True)

    lector = V.LectorLeft(REF, np.load(FONDO) if os.path.exists(FONDO) else None)
    filas = []
    for i, r in enumerate(regs):
        s = lector.leer(r["_ruta"])
        if "error" in s:
            continue
        filas.append(fila(r, s, "a", a.paso_a))
        filas.append(fila(r, s, "b", a.paso_b))
        if (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{len(regs)}", flush=True)

    destino = a.salida or os.path.join(AQUI, f"mediciones_left_{a.fecha}.csv")
    with open(destino, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS); w.writeheader(); w.writerows(filas)

    med = sum(1 for f in filas if f["estado"] == "medida")
    sp = sum(1 for f in filas if f["estado"] == "sin_pesa")
    alta = sum(1 for f in filas if f["estado"] == "medida" and f["confianza_distancia"] >= 0.9)
    print(f"\n{'='*58}\nRESUMEN DEL {a.fecha}")
    print(f"  fotos procesadas          {len(filas)//2}")
    print(f"  barras con medicion       {med} ({med/len(filas)*100:.1f}%)")
    print(f"     de esas, confianza alta {alta} ({alta/max(med,1)*100:.1f}%)")
    print(f"  barras sin pesa montada   {sp} ({sp/len(filas)*100:.1f}%)")
    print(f"  no medidas                {len(filas)-med-sp}")
    if not (a.paso_a and a.paso_b):
        print("\n  NOTA: la columna distancia_mm esta vacia porque falta el paso de")
        print("  rosca. La medicion valida es distancia_pasos. Cuando se consiga el")
        print(f"  paso, correr con --paso-a X --paso-b Y y queda en milimetros.")
    print(f"\n  archivo: {destino}\n{'='*58}")


if __name__ == "__main__":
    main()

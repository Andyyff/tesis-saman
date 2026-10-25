#!/usr/bin/env python3
"""medir_dia_top.py — una carpeta de fotos "top" -> un CSV de mediciones.

    python3 medir_dia_top.py CARPETA_FOTOS [--ref FOTO_REFERENCIA] [--salida x.csv]
    python3 medir_dia_top.py CARPETA --calib P1 V1 P2 V2   # pasa a escala 0-10

`posicion_px`: pixeles a lo largo de la trayectoria del mango, desde la foto de
referencia. `apertura`: escala 0-10, con la calibracion vigente (ver vision_top.py).
--calib P1 V1 P2 V2: usar otra calibracion (dos pares posicion_px -> valor).
--sin-calib: dejar `apertura` vacia.
"""
import argparse, csv, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_top as V

ap = argparse.ArgumentParser()
ap.add_argument("carpeta"); ap.add_argument("--ref", default=None)
ap.add_argument("--salida", default=None); ap.add_argument("--calib", nargs=4, type=float); ap.add_argument("--sin-calib", action="store_true")
a = ap.parse_args()
fs = sorted(glob.glob(os.path.join(a.carpeta, "*.jpg")))
ref = a.ref or os.path.join(os.path.dirname(os.path.abspath(__file__)), "foto_referencia_top.jpg")
cal = None if a.sin_calib else (V.Calibracion(*a.calib) if a.calib else V.CALIBRACION_VIGENTE)
L = V.LectorTop(ref, cal)
salida = a.salida or os.path.basename(os.path.normpath(a.carpeta)) + "_top.csv"
campos = ["fecha_hora", "archivo", "estado", "posicion_px", "apertura", "confianza",
          "metodo", "tinte_camara", "desvio_transversal_px", "detalle"]
with open(salida, "w", newline="") as fh:
    w = csv.DictWriter(fh, campos); w.writeheader()
    resultados = L.leer_dia(fs)   # dos pasadas: alineacion propia o prestada de una vecina
    for i, (f, r) in enumerate(zip(fs, resultados), 1):
        n = r["archivo"]
        fecha, hora = n[-23:-13], n[-12:-4].replace("-", ":")
        w.writerow(dict(fecha_hora=f"{fecha} {hora}", archivo=n, estado=r["estado"],
                        posicion_px=r["posicion_px"] if r["posicion_px"] is not None else "",
                        apertura=r["apertura"] if r["apertura"] is not None else "",
                        confianza=r["confianza"], metodo=r["metodo"] or "",
                        tinte_camara=r.get("tinte_camara"), desvio_transversal_px=r.get("desvio_transversal_px", ""),
                        detalle=" | ".join(r["notas"])))
        print(f"[{i}/{len(fs)}] {n} {r['estado']} {r['posicion_px']}", end="\r")
print(f"\nlisto: {salida}")

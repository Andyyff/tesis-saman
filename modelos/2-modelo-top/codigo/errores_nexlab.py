"""Resumen de los JSON de Nexlab (sin fotos), dia por dia.

- errores_declarados: Nexlab marca `err` (dato seguro).
- caidas_aisladas: una foto que se aparta mucho de sus dos vecinas cuando las
  vecinas coinciden (ej. 9 -> 0 -> 9). AMBIGUAS: validado en 4 dias con fotos,
  de 16 caidas solo 5 eran errores de Nexlab; las otras 11 eran cierres REALES
  de la valvula durante una foto. Con el JSON solo NO se pueden separar: hace
  falta la imagen (vision_top.py).

    python3 errores_nexlab.py CARPETA_CON_UN_SUBDIRECTORIO_POR_DIA
"""
import json, glob, os, datetime as dt, csv, sys
UMBRAL, ACUERDO_VECINAS, MAX_MIN = 1.5, 0.5, 20
def sospechosos(datos):
    R = sorted(datos, key=lambda r: r["date"])
    T = [dt.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S") for r in R]
    out = []
    for i in range(1, len(R) - 1):
        a, b, c = R[i - 1], R[i], R[i + 1]
        if a["err"] or b["err"] or c["err"]:
            continue
        if (T[i + 1] - T[i - 1]).total_seconds() > 2 * MAX_MIN * 60:
            continue
        if abs(a["opening"] - c["opening"]) <= ACUERDO_VECINAS and \
           abs(b["opening"] - (a["opening"] + c["opening"]) / 2) >= UMBRAL:
            out.append((b["filename"], a["opening"], b["opening"], c["opening"]))
    return out
if __name__ == "__main__":
    base = sys.argv[1]
    filas = []
    for j in sorted(glob.glob(os.path.join(base, "*", "datos_top_*.json"))):
        d = json.load(open(j)); f = os.path.basename(j)[10:20]
        s = sospechosos(d)
        filas.append(dict(fecha=f, fotos=len(d), errores_declarados=sum(1 for r in d if r["err"]),
                          caidas_aisladas=len(s), ejemplos=" ".join(x[0][-12:-4] for x in s[:4])))
    w = csv.DictWriter(open("errores_nexlab_por_dia.csv", "w", newline=""), list(filas[0].keys()))
    w.writeheader(); w.writerows(filas)
    F = sum(r["fotos"] for r in filas); E = sum(r["errores_declarados"] for r in filas); S = sum(r["caidas_aisladas"] for r in filas)
    print(f"{len(filas)} dias, {F} fotos: errores declarados {E} ({100*E/F:.1f}%), caidas aisladas (ambiguas) {S} ({100*S/F:.1f}%)")
    print("dias con mas caidas aisladas:", sorted(((r["caidas_aisladas"], r["fecha"]) for r in filas), reverse=True)[:6])

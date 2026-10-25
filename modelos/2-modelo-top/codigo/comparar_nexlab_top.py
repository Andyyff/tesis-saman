#!/usr/bin/env python3
"""comparar_nexlab_top.py — compara nuestra medicion con el `opening` de Nexlab.

    python3 comparar_nexlab_top.py SALIDA_NUESTRA.csv datos_top_FECHA.json

SALIDA_NUESTRA.csv la genera medir_dia_top.py; el JSON lo baja descargar_top.py.
Genera reporte_comparacion_nexlab_FECHA.txt y comparacion_nexlab_FECHA.png.
"""
import csv, json, sys, datetime as dt, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

nuestro = {r["archivo"]: r for r in csv.DictReader(open(sys.argv[1]))}
nx = {r["filename"]: r for r in json.load(open(sys.argv[2]))}
fecha = next(iter(nx.values()))["date"][:10]
out = []; P = lambda *a: out.append(" ".join(str(x) for x in a))
T = lambda s: dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

P(f"COMPARACION CON NEXLAB · camara top · {fecha} · {len(nx)} fotos")
P("\n1) QUIEN MIDE QUE")
cats = {}
for f, r in nx.items():
    o = nuestro.get(f)
    nex = "error" if r["err"] else ("valor 0" if r["opening"] == 0 else "valor")
    nue = o["estado"] if o else "sin dato"
    cats.setdefault((nex, nue), []).append(f[-12:-4])
for (a, b), v in sorted(cats.items(), key=lambda x: -len(x[1])):
    P(f"   Nexlab {a:<12} | nuestro {b:<16} {len(v):>4}" + (f"   {', '.join(v)}" if len(v) <= 6 else ""))

S = []
for f, r in sorted(nx.items()):
    o = nuestro.get(f)
    # Un 0 de Nexlab SIN error puede ser real (valvula cerrada, verificado a ojo):
    # se compara como cualquier otro valor.
    if not o or r["err"] or o["estado"] != "medida" or not o["apertura"]:
        continue
    verde = float(o["tinte_camara"] or 9) >= 1.3
    S.append((T(r["date"]), r["opening"], float(o["apertura"]), verde))
t = np.array([s[0] for s in S]); N = np.array([s[1] for s in S]); O = np.array([s[2] for s in S]); V = np.array([s[3] for s in S])
d = N - O
P(f"\n2) DONDE MIDEN LOS DOS: {len(S)} fotos ({V.sum()} con color de camara roto)")
P("   (la calibracion v2 se ajusto con 21/08, 28/08, 02/09 y 04/09: en esos dias la comparacion es optimista)")
P(f"   fotos normales: |diferencia| mediana {np.median(np.abs(d[~V])):.3f}, p95 {np.percentile(np.abs(d[~V]),95):.3f}")
if V.any():
    P(f"   fotos verdes:   |diferencia| mediana {np.median(np.abs(d[V])):.3f}  (n={V.sum()})")
P("\n2b) DISCREPANCIAS MAYORES A 1 UNIDAD (mirar la foto; en todas las revisadas el error era de Nexlab)")
for ti, n_, o_, v_ in zip(t, N, O, V):
    if abs(n_ - o_) > 1:
        P(f"   {ti:%H:%M:%S}  Nexlab {n_}  nuestro {o_:.2f}" + ("  (foto verde)" if v_ else ""))
P("\n3) RUIDO: salto entre fotos consecutivas (<=15 min), fotos normales, en unidades 0-10")
m = ~V; tt, NN, OO = t[m], N[m], O[m]
ok = np.array([(b - a).total_seconds() <= 900 for a, b in zip(tt, tt[1:])])
jn, jo = np.abs(np.diff(NN))[ok], np.abs(np.diff(OO))[ok]
P(f"   Nexlab : mediana {np.median(jn):.3f}  p90 {np.percentile(jn,90):.3f}   (redondea a 0,1)")
P(f"   nuestro: mediana {np.median(jo):.3f}  p90 {np.percentile(jo,90):.3f}")
open(f"reporte_comparacion_nexlab_{fecha}.txt", "w").write("\n".join(out)); print("\n".join(out))

todos = [(T(f"{o['fecha_hora']}"), o) for o in nuestro.values()]
fig, ax = plt.subplots(figsize=(11, 4))
ax.plot(t[~V], N[~V], ".", color="#999", label="Nexlab (opening)")
if V.any(): ax.plot(t[V], N[V], "x", color="#c00", label="Nexlab en fotos verdes")
tt2 = [a for a, o in todos if o["apertura"]]; oo2 = [float(o["apertura"]) for a, o in todos if o["apertura"]]
orden = np.argsort(tt2); ax.plot(np.array(tt2)[orden], np.array(oo2)[orden], "-", color="#1f6fb4", lw=1.2, label="nuestro (apertura)")
for f, r in nx.items():
    o = nuestro.get(f)
    if o and o["estado"] == "mango_no_visible":
        ax.axvline(T(r["date"]), color="#e0a000", lw=1, alpha=.7)
ax.plot([], [], color="#e0a000", label="mango no visible (ej. tapado por el operario)")
ax.set_ylabel("apertura (escala 0-10)"); ax.set_ylim(-0.6, 10.2); ax.set_title(f"Camara top · {fecha}")
ax.legend(fontsize=8, loc="lower right"); ax.grid(alpha=.3); fig.tight_layout()
fig.savefig(f"comparacion_nexlab_{fecha}.png", dpi=110)

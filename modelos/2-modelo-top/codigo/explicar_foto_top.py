#!/usr/bin/env python3
"""explicar_foto_top.py — dibuja una foto "top" con flechas que explican que
usa el algoritmo para medir la apertura.

    python3 explicar_foto_top.py FOTO.jpg salida.png [--nexlab "texto"]
"""
import sys, os, math, argparse
import numpy as np, cv2
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, ConnectionPatch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_top as V

ap = argparse.ArgumentParser()
ap.add_argument("foto"); ap.add_argument("salida"); ap.add_argument("--nexlab", default=None)
a = ap.parse_args()
base = os.path.dirname(os.path.abspath(__file__))
L = V.LectorTop(os.path.join(base, "foto_referencia_top.jpg"), V.CALIBRACION_VIGENTE)
res = L.leer(a.foto)
img = cv2.imread(a.foto)
A, diag = L.reg.estimar(img)
al = L.reg.aplicar(img, A)
rgb = cv2.cvtColor(al, cv2.COLOR_BGR2RGB)

# coincidencias usadas para alinear (puntos de la maquina, en el marco alineado)
k, d = L.reg.orb.detectAndCompute(V.preparar(img), None)
m = [x for x, y in L.reg.bf.knnMatch(d, L.reg.dr, k=2) if x.distance < 0.75 * y.distance]
src = np.float32([k[x.queryIdx].pt for x in m]); dst = np.float32([L.reg.kr[x.trainIdx].pt for x in m])
_, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
pts = dst[inl.ravel().astype(bool)]

AZUL, AMAR, VERD, ROJO, BLAN = "#2b7bd6", "#f2c200", "#1fa04a", "#d6402b", "#ffffff"
fig = plt.figure(figsize=(16, 9.6), dpi=110)
ax = fig.add_axes([0.01, 0.06, 0.55, 0.86]); az = fig.add_axes([0.60, 0.06, 0.39, 0.86])
for x in (ax, az): x.set_xticks([]); x.set_yticks([])
fig.suptitle("Cámara top · cómo se mide la apertura de la válvula", fontsize=19, fontweight="bold", x=0.01, ha="left", y=0.985)
fecha = os.path.basename(a.foto)[-23:-4].replace("_", "  ", 1).replace("-", ":", 2)[::-1].replace("-", ":", 2)[::-1]
sub = f"Foto {os.path.basename(a.foto)[-23:-13]} {os.path.basename(a.foto)[-12:-4].replace('-', ':')}"
sub += f"   ·   resultado: apertura {res['apertura']:.1f}" if res.get("apertura") is not None else f"   ·   {res['estado']}"
if a.nexlab: sub += f"   ·   Nexlab: {a.nexlab}"
fig.text(0.01, 0.935, sub, fontsize=12.5, color="#444")

# ---------------- panel izquierdo: foto completa ----------------
ax.imshow(rgb)
ax.scatter(pts[:, 0], pts[:, 1], s=7, c=AZUL, alpha=0.85, linewidths=0)
py, px = V.PARCHE_BLANCO
ax.add_patch(Rectangle((px.start, py.start), px.stop - px.start, py.stop - py.start, fill=False, ec=AMAR, lw=2.5))
zy0, zy1, zx0, zx1 = 150, 600, 340, 560
ax.add_patch(Rectangle((zx0, zy0), zx1 - zx0, zy1 - zy0, fill=False, ec=BLAN, lw=2, ls="--"))

def nota(axx, n, txt, xy, xytext, color, ha="left"):
    axx.annotate(f"{n}  {txt}", xy=xy, xytext=xytext, fontsize=11.5, color="black", ha=ha, va="center",
                 bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=color, lw=2.2),
                 arrowprops=dict(arrowstyle="-|>", color=color, lw=2.6, mutation_scale=20,
                                 shrinkA=2, shrinkB=4, connectionstyle="arc3,rad=0.12"))

xs = pts[:, 0]; ys = pts[:, 1]
caja1 = (610, 965)
ax.annotate("1  Puntos fijos de la máquina (azules): se usan para ALINEAR\n"
            "la foto con la de referencia y corregir si la cámara se corrió",
            xy=caja1, fontsize=11.5, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=AZUL, lw=2.2))
objetivos = []
for cond in ((xs > 800) & (ys > 650), (xs < 300) & (ys < 450), (xs > 900) & (ys < 300)):
    c = pts[cond]
    if len(c): objetivos.append(tuple(c[len(c) // 2]))
for k_, ob in enumerate(objetivos[:3]):
    ax.annotate("", xy=ob, xytext=(caja1[0] - 120 + 120 * k_, caja1[1] - 28),
                arrowprops=dict(arrowstyle="-|>", color=AZUL, lw=2.4, mutation_scale=18, shrinkB=3))
nota(ax, "2", "Zona blanca de la máquina:\nreferencia para CORREGIR EL COLOR\n(fotos verdes o violetas)",
     (px.start, py.stop - 30), (20, 840), AMAR)
nota(ax, "3", "Zona de la palanca\n(ampliada a la derecha)", (zx1, zy0 + 40), (700, 90), "#666")
ax.set_xlim(0, rgb.shape[1]); ax.set_ylim(rgb.shape[0], 0)

# ---------------- panel derecho: zoom de la palanca ----------------
crop = rgb[zy0:zy1, zx0:zx1]
az.imshow(crop, extent=(zx0, zx1, zy1, zy0))
sel = (V._YC > zy0) & (V._YC < zy1)
az.plot(V._XC[sel], V._YC[sel], color=BLAN, lw=2.2)
cal = L.calibracion
for v in range(0, 11):
    s = (v - cal.b) / cal.k
    y = float(np.interp(V._S_REF - s, V._SC, V._YC)); x = float(np.polyval(V.CURVA, y))
    if zy0 < y < zy1:
        az.plot([x - 7, x + 7], [y, y], color=AMAR, lw=2)
        az.text(x - 11, y, str(v), color=AMAR, fontsize=11, fontweight="bold", ha="right", va="center",
                path_effects=[__import__("matplotlib.patheffects", fromlist=["x"]).withStroke(linewidth=3, foreground="black")])
if res.get("mango"):
    mx, my = res["mango"]
    az.add_patch(Circle((mx, my), 13, fill=False, ec=VERD, lw=3))
    nota(az, "4", "Mango verde: se ubica por su color\n(mancha verde de 300-600 px\nSOBRE el recorrido)", (mx - 6, my - 10), (zx0 + 75, zy0 + 40), VERD)
    y0m = float(np.interp(V._S_REF + cal.b / cal.k * 0 - (0 - cal.b) / cal.k, V._SC, V._YC))
s0 = (0 - cal.b) / cal.k
y0 = float(np.interp(V._S_REF - s0, V._SC, V._YC)); x0 = float(np.polyval(V.CURVA, y0))
yc = zy0 + (zy1 - zy0) * 0.55; xc = float(np.polyval(V.CURVA, yc))
nota(az, "5", "Recorrido del mango (curva blanca):\nse mide CUÁNTO avanzó a lo largo\nde él, en píxeles", (xc + 1, yc), (zx0 + 115, yc + 30), BLAN)
nota(az, "6", "Escala 0-10 (amarillo):\n1 unidad = 34 px de recorrido,\ncalibrada contra Nexlab con\n682 fotos de 4 días", (x0 - 14, y0), (zx0 + 95, zy1 - 45), AMAR)
az.set_xlim(zx0, zx1); az.set_ylim(zy1, zy0)
for sp in az.spines.values(): sp.set_edgecolor("#666"); sp.set_linestyle("--"); sp.set_linewidth(2)

fig.text(0.01, 0.018, "Controles: si la foto no se puede alinear se usa la de una foto vecina (la cámara está fija) · "
         "con el color irrecuperable (tinte > 6) o sin mango visible, NO se inventa un número: se informa el motivo.",
         fontsize=10.5, color="#444")
fig.savefig(a.salida, dpi=110)
print(res["estado"], res.get("apertura"))

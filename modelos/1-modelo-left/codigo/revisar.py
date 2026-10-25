#!/usr/bin/env python3
"""Revision visual EN SERIO: una foto por imagen, a resolucion util.

    python3 revisar.py FOTO BARRA [FOTO BARRA ...]
    python3 revisar.py --dia 2026-09-16 --barra b --cada 4

Por que existe: estuve revisando casos en planchas de 6 imagenes, donde cada
overlay de 660x450 quedaba achicado a menos de la mitad. A esa escala no se
distingue una pesa celeste de un reflejo de la maquina, y di por buenas cosas
que estaban mal. Esto rinde CADA caso solo, recortado alrededor de la varilla
que importa y ampliado, que es la unica forma honesta de mirar.
"""
import sys, os, glob
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_left as V

REF = "referencia_left.jpg"
SALIDA = "revision"
COL = {"a": (0, 150, 255), "b": (255, 130, 0)}


def buscar(nombre):
    for pat in ("corpus/**/", "corpus_total/", "corpus_prueba/**/", "fotos_dia/**/",
                "corpus_auditoria/", "muestra_agosto/"):
        g = glob.glob(pat + nombre, recursive=True)
        if g:
            return g[0]
    g = glob.glob(f"**/*{nombre}*", recursive=True)
    return g[0] if g else None


def render(lector, ruta, barra, etiqueta="", escala=2.4):
    img = cv2.imread(ruta)
    alineada, _ = lector.reg.alinear(img)
    if alineada is None:
        alineada = img
    wb = V.balance_de_blancos(alineada)
    gris = cv2.cvtColor(wb, cv2.COLOR_BGR2GRAY).astype(np.float32)
    res = lector.leer(ruta)
    v = res["varillas"][barra]
    eje = V.buscar_varilla(gris, barra)

    # recorte centrado en LA varilla que se esta revisando, no en toda la escena
    if eje is not None:
        t0, t1 = 0.0, float(V.BANDA["x1"] - V.BANDA["x0"])
        p = eje["p0"] + eje["u"] * t0
        q = eje["p0"] + eje["u"] * t1
        ys = [p[1], q[1]]
        y0 = int(max(0, min(ys) - 95)); y1 = int(min(wb.shape[0], max(ys) + 95))
        x0 = int(max(0, min(p[0], q[0]) - 40)); x1 = int(min(wb.shape[1], max(p[0], q[0]) + 60))
    else:
        y0, y1, x0, x1 = 250, 700, 350, 1010

    vis = wb.copy()
    if eje is not None and v.get("tramo_rosca_px"):
        ta, tb = v["tramo_rosca_px"]
        a = eje["p0"] + eje["u"] * ta; b = eje["p0"] + eje["u"] * tb
        cv2.line(vis, tuple(a.astype(int)), tuple(b.astype(int)), (70, 70, 70), 1)
    c = COL[barra]
    if v.get("origen"):
        o = tuple(int(z) for z in v["origen"])
        cv2.drawMarker(vis, o, c, cv2.MARKER_TILTED_CROSS, 24, 2)
    if v.get("pesa"):
        pc = tuple(int(z) for z in v["pesa"]["centro"])
        cv2.circle(vis, pc, 16, c, 2)
        if v.get("origen"):
            cv2.line(vis, tuple(int(z) for z in v["origen"]), pc, c, 2)

    vis = vis[y0:y1, x0:x1]
    vis = cv2.resize(vis, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)

    alto = 96
    barra_txt = np.full((alto, vis.shape[1], 3), 20, np.uint8)
    nom = os.path.basename(ruta)
    lineas = [f"{nom}   barra {barra}   {etiqueta}",
              f"estado: {v['estado']}   distancia: {v['distancia_px']} px"
              f" = {v.get('distancia_mm')} mm   angulo: {v['inclinacion_grados']}",
              f"metodo: {v['metodo']} / {v.get('metodo_pesa')}   "
              f"confianza: {v['confianza']} (dist) {v['confianza_angulo']} (angulo)"]
    for i, ln in enumerate(lineas):
        cv2.putText(barra_txt, ln[:150], (10, 26 + i * 24), 0, 0.62, (0, 255, 255), 1, cv2.LINE_AA)
    out = np.vstack([barra_txt, vis])
    for i, n in enumerate(v.get("notas", [])[:3]):
        pie = np.full((26, out.shape[1], 3), 20, np.uint8)
        cv2.putText(pie, ("- " + n)[:150], (10, 18), 0, 0.5, (180, 220, 180), 1, cv2.LINE_AA)
        out = np.vstack([out, pie])
    return out


def main():
    os.makedirs(SALIDA, exist_ok=True)
    L = V.LectorLeft(REF, np.load("fondo_fijo.npy") if os.path.exists("fondo_fijo.npy") else None)
    args = sys.argv[1:]
    casos = []
    if "--dia" in args:
        dia = args[args.index("--dia") + 1]
        barra = args[args.index("--barra") + 1] if "--barra" in args else "b"
        cada = int(args[args.index("--cada") + 1]) if "--cada" in args else 6
        fs = sorted(set(glob.glob(f"corpus*/**/*{dia}*.jpg", recursive=True) +
                        glob.glob(f"fotos_dia/**/*{dia}*.jpg", recursive=True)))[::cada]
        casos = [(f, barra) for f in fs]
    else:
        for i in range(0, len(args) - 1, 2):
            p = buscar(args[i]) or args[i]
            casos.append((p, args[i + 1]))
    for k, (p, b) in enumerate(casos):
        if not os.path.exists(p):
            print("no encuentro", p); continue
        out = render(L, p, b)
        nom = f"{SALIDA}/{k:02d}_{os.path.basename(p)[-19:-4]}_{b}.png"
        cv2.imwrite(nom, out)
        print(nom, out.shape)


if __name__ == "__main__":
    main()

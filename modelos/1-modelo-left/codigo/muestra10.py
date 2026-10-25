#!/usr/bin/env python3
"""Dibuja lo que mide el algoritmo sobre la FOTO ORIGINAL (no la alineada),
una imagen por caso, a resolucion util. Para mirar el modelo en casos variados."""
import sys, os, glob, math
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_left as V

REF = "referencia_left.jpg"
COL = {"a": (0, 170, 255), "b": (255, 140, 0)}
ANG = (60, 255, 60)

CASOS = [
    ("RIC-0001-LEFT_2026-09-16_00-27-", "Noche normal"),
    ("RIC-0001-LEFT_2026-09-16_13-18-", "Dia, luz fuerte"),
    ("RIC-0001-LEFT_2026-08-12_14-08-06.jpg", "Pesa metalica sin pintar (barra b)"),
    ("RIC-0001-LEFT_2026-07-01_02-18-20.jpg", "Barras sin pesa"),
    ("RIC-0001-LEFT_2026-09-01_03-24-11.jpg", "Pesa rosada pegada a la perilla"),
    ("RIC-0001-LEFT_2026-08-03_12-42-53.jpg", "Donde Nexlab se equivoco (dijo 92 grados)"),
    ("RIC-0001-LEFT_2026-08-24_00-52-39.jpg", "Angulo bajo"),
    ("RIC-0001-LEFT_2026-09-21_00-33-00.jpg", "Angulo alto"),
    ("RIC-0001-LEFT_2026-07-18_21-07-48.jpg", "Alineacion deformada (el problema a arreglar)"),
    ("RIC-0001-LEFT_2026-07-04_02-19-04.jpg", "Foto con el color roto (violeta)"),
]


def buscar(nombre):
    for pat in ("corpus/**/", "corpus_total/", "corpus_prueba/**/", "fotos_dia/**/",
                "corpus_auditoria/", "muestra_agosto/"):
        g = sorted(glob.glob(pat + nombre + ("" if nombre.endswith(".jpg") else "*"), recursive=True))
        if g:
            return g[0]
    return None


def a_orig(p, H):
    return V._a_original(p, H)


def escala_de(H):
    if not H:
        return None
    A = np.array(H)[:2, :2] / np.array(H)[2, 2]
    return float(np.sqrt(abs(np.linalg.det(A))))


def texto(img, s, org, col, esc=0.62, grosor=2):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), grosor + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, grosor, cv2.LINE_AA)


def render(L, ruta, titulo, salida, n):
    img = cv2.imread(ruta)
    s = L.leer(ruta)
    H = s["registro"].get("H")
    vis = img.copy()
    Z = 2  # ampliacion
    x0, y0, x1, y1 = 470, 250, 1000, 700

    lineas = []
    for b in "ab":
        v = s["varillas"][b]
        est = v["estado"]
        if v.get("origen"):
            o = a_orig(v["origen"], H)
            cv2.circle(vis, (int(o[0]), int(o[1])), 4, COL[b], -1)
        if v.get("pesa") and v["pesa"].get("centro") and v.get("origen"):
            c = a_orig(v["pesa"]["centro"], H)
            cv2.line(vis, (int(o[0]), int(o[1])), (int(c[0]), int(c[1])), COL[b], 2)
            cv2.drawMarker(vis, (int(c[0]), int(c[1])), COL[b], cv2.MARKER_CROSS, 16, 2)
        if est == "medida":
            lineas.append((f"barra {b}: {v['distancia_mm']:.0f} mm  (confianza {v['confianza']:.2f})", COL[b]))
        else:
            lineas.append((f"barra {b}: {est.replace('_', ' ')}", COL[b]))

    a = s["angulo"]
    if a["angulo_grados"] is not None:
        t, k, f = [tuple(int(round(z)) for z in p) for p in (a["tapon"], a["perilla"], a["ficha"])]
        cv2.line(vis, t, k, ANG, 1, cv2.LINE_AA); cv2.line(vis, k, f, ANG, 1, cv2.LINE_AA)
        for p in (t, k, f):
            cv2.circle(vis, p, 3, ANG, -1)
        lineas.append((f"angulo: {a['angulo_grados']:.1f} grados  (confianza {a['confianza']:.2f})", ANG))
    else:
        lineas.append(("angulo: no medido", ANG))

    rec = cv2.resize(vis[y0:y1, x0:x1], None, fx=Z, fy=Z, interpolation=cv2.INTER_CUBIC)
    cab = np.full((40 + 30 * (len(lineas) + 1), rec.shape[1], 3), 25, np.uint8)
    hora = os.path.basename(ruta)[14:33].replace("_", " ")
    texto(cab, f"{n}. {titulo}   -   {hora}", (12, 30), (255, 255, 255), 0.75)
    for i, (l, c) in enumerate(lineas):
        texto(cab, l, (12, 64 + 30 * i), c)
    esc = escala_de(H)
    reg = s["registro"]
    al = ("alineacion: no se alineo" if not reg.get("registrado") else
          f"alineacion: corrida {reg.get('correccion_px')} px, escala {esc:.2f}")
    notas = "; ".join(a["notas"])
    texto(cab, al + (("   |   " + notas) if notas else ""), (12, 64 + 30 * len(lineas)), (190, 190, 190), 0.5, 1)
    cv2.imwrite(salida, np.vstack([cab, rec]), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return s


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "muestra10"
    os.makedirs(dest, exist_ok=True)
    L = V.LectorLeft(REF, np.load("fondo_fijo.npy"))
    for i, (nom, tit) in enumerate(CASOS, 1):
        r = buscar(nom)
        if not r:
            print("NO ESTA", nom); continue
        s = render(L, r, tit, os.path.join(dest, f"{i:02d}.jpg"), i)
        a = s["angulo"]; va, vb = s["varillas"]["a"], s["varillas"]["b"]
        print(i, os.path.basename(r)[14:33], tit, "| a:", va["estado"], va.get("distancia_mm"),
              "| b:", vb["estado"], vb.get("distancia_mm"), "| ang:", a["angulo_grados"], a["confianza"],
              "| escala", escala_de(s["registro"].get("H")))

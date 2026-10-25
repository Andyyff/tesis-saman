#!/usr/bin/env python3
"""10 casos, cada uno con el ANTES (version anterior, izquierda) y el DESPUES
(version actual, derecha), dibujados sobre la foto original."""
import sys, os, importlib.util
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import muestra10 as M

def cargar(nombre, ruta):
    sp = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m

if __name__ == "__main__":
    antes_py = sys.argv[1]; dest = sys.argv[2]
    os.makedirs(dest, exist_ok=True)
    VA = cargar("v_antes", antes_py); VD = cargar("v_despues", "vision_left.py")
    ff = np.load("fondo_fijo.npy")
    LA = VA.LectorLeft(M.REF, ff); LD = VD.LectorLeft(M.REF, ff)
    for i, (nom, tit) in enumerate(M.CASOS, 1):
        r = M.buscar(nom)
        M.V = VA; M.render(LA, r, tit + "  [ANTES]", "/tmp/_a.jpg", i)
        M.V = VD; M.render(LD, r, tit + "  [DESPUES]", "/tmp/_d.jpg", i)
        a = cv2.imread("/tmp/_a.jpg"); d = cv2.imread("/tmp/_d.jpg")
        h = max(a.shape[0], d.shape[0])
        pad = lambda x: np.vstack([x, np.full((h - x.shape[0], x.shape[1], 3), 25, np.uint8)])
        sep = np.full((h, 12, 3), 255, np.uint8)
        cv2.imwrite(os.path.join(dest, f"caso-{i:02d}.jpg"), np.hstack([pad(a), sep, pad(d)]),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(i, tit)

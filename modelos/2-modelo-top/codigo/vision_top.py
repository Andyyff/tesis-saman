#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision_top.py — Lectura de la camara "top" (palanca de apertura).
Tesis UM · planta de Jose Pedro Varela. Escrito desde cero, no usa nada de Nexlab.

QUE SE MIDE
-----------
La palanca gira alrededor del eje del tambor y termina en un mango verde. En la
foto no hay una escala 0-10 legible, asi que lo que se mide es DONDE ESTA EL
MANGO a lo largo de su trayectoria, en pixeles del marco alineado:

    posicion_px = proyeccion del centro del mango sobre la direccion de la
                  trayectoria, medida desde la posicion en la foto de referencia.

En un dia real (02/09, 153 fotos) el mango se mueve sobre una recta con 0,6 px
de ruido transversal: es un movimiento de UNA dimension, y esta es esa dimension.
Pasar a la escala 0-10 necesita dos puntos de calibracion (ver `Calibracion`),
igual que en "left" hace falta el paso de rosca para pasar a milimetros.

DECISIONES (lo aprendido en "left" aplicado aca)
------------------------------------------------
1) La alineacion no depende del color. Se alinea sobre el canal con mas
   contraste, ecualizado. Asi las fotos que la camara saca verdes se alinean
   igual que las normales.
2) Dos metodos independientes para ubicar el mango:
     - COLOR: el mango verde.
     - FORMA: la silueta de la palanca (bordes), comparada con la de la foto de
       referencia. No mira un solo pixel de color.
   Cuando el color sirve corren los dos, y tienen que coincidir. Si no
   coinciden, no se informa un numero: se avisa. Cuando el color no sirve,
   queda el de forma, con menos confianza.
3) La validacion de la alineacion no necesita color: cuantas coincidencias
   sostienen la alineacion y que tan repartidas estan por la foto.
"""

import os, math
import numpy as np
import cv2

# ------------------------------------------------------------- constantes
# Todas en el marco de la foto de referencia (RIC-0001-TOP_2026-09-02_00-04-53).
ZONA_FIJA_EXCLUIR = (slice(100, 700), slice(300, 1280))  # tapa con arroz y palanca: cambian
PARCHE_BLANCO = (slice(450, 650), slice(250, 400))       # disco blanco de la tapa
VENTANA_MANGO = dict(x0=380, x1=490, y0=165, y1=280)     # donde puede estar el mango
DIR_TRAYECTORIA = np.array([0.371, -0.929])               # medida el 02/09 (ver doc)
# --- v2: recorrido completo (ajustado con 657 fotos de 4 dias: 21/08, 28/08, 02/09, 04/09)
# El mango no se mueve en linea recta: baja casi vertical siguiendo esta curva
# x = a*y^2 + b*y + c (marco de la referencia). Desvio de las fotos a la curva: 0,7 px mediano.
CURVA = [0.001206022315949379, -0.820677630054019, 554.0567043204784]
Y_REF = 224.65                 # altura del mango en la foto de referencia
VENTANA_AMPLIA = dict(x0=330, x1=620, y0=130, y1=640)   # todo el recorrido posible
RECORRIDO_FISICO_PX = (-330.0, 45.0)  # v3: el mango no sale de aqui (apertura ~-0,5 a ~10,3); visto
                                      # en 9 dias: de -312 (cerrada) a +19 (9,5)
MAX_DESVIO_CURVA = 12.0       # px: una mancha verde mas lejos de la curva no es el mango
ZONA_FORMA = 15.0             # px: la forma solo se usa como control cerca de la referencia
TOL_FORMA_GROSERA = 8.0       # px: diferencia color/forma que se considera grosera
TINTE_MAX_UTILIZABLE = 1.30
TINTE_MAX_RECUPERABLE = 6.0   # hasta 4 el balance de blancos recupera el color (49 de 51 fotos
                              # coinciden con sus vecinas); con 200+ un canal esta muerto y
                              # aparecen manchas verdes falsas (25/08 06:26, 06/09 13:34)   # por encima, el color de camara no es confiable
VERDE = dict(a_max=-25, b_min=5, L_min=60)
VERDE_AREA = (200, 2000)       # v3: el mango mide 307-591 px en 9 dias; una mancha de 74 px
                               # sobre la curva se tomo por mango el 18/08 08:43 (mal)
VERDE_AREA_MAX = 2500
# Alineacion (v3). La camara esta fija: entre fotos solo se corre unos pocos
# px, sin zoom ni giro apreciable (medido en 9 dias). Por eso se usa un modelo
# de semejanza (corrimiento + giro + escala), no una homografia: con las
# coincidencias concentradas, la homografia se "torcia" y daba 30 px de
# correccion en la palanca cuando la camara se habia corrido 10 (17-18/08).
MIN_INLIERS = 40              # minimo de coincidencias que sostienen la alineacion
MIN_REPARTO_PX = 40           # desvio minimo de esas coincidencias (no amontonadas)
MAX_CORRIMIENTO_PX = 40       # mas que esto no es la camara fija: se rechaza
MAX_GIRO_GRADOS = 1.5
MAX_CAMBIO_ESCALA = 0.03
MAX_HORAS_VECINA = 3.0        # alineacion prestada de una foto vecina del mismo dia
TOL_ACUERDO_PX = 3.0          # color y forma tienen que coincidir a menos de esto
MIN_SCORE_FORMA = 0.45        # correlacion minima para creerle al metodo de forma
PLANTILLA_GRUESA = dict(x0=395, x1=475, y0=190, y1=250)   # mango + varilla: distintiva, sesgada
PLANTILLA = dict(x0=406, x1=448, y0=204, y1=242)          # SOLO el mango: precisa, poco distintiva
RADIO_AFINADO = 4.0           # px: la plantilla fina busca solo a esta distancia de la gruesa
# Una plantilla mas grande incluia un tramo de varilla, que esta mas cerca del
# eje de giro y se mueve menos que el mango: el metodo de forma leia 13 % menos
# de movimiento que el de color (pendiente 0,87). Mirando solo el mango, no.
FRANJA_TRANSVERSAL = 6.0      # px: cuanto puede apartarse el mango de su trayectoria
RECORRIDO = (-40.0, 55.0)     # px a lo largo de la trayectoria. El 02/09 se movio de -1 a 11:
                              # el rango es generoso a proposito, pero NO esta probado mas alla


def preparar(bgr):
    """Imagen en grises que no depende del tinte: el canal con mas contraste,
    ecualizado localmente."""
    canal = max(cv2.split(bgr), key=lambda c: float(c.std()))
    return cv2.createCLAHE(2.0, (8, 8)).apply(canal)


def gradiente(gris):
    g = cv2.GaussianBlur(gris.astype(np.float32), (0, 0), 1.2)
    return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def tinte_camara(bgr):
    z = bgr[PARCHE_BLANCO].reshape(-1, 3).astype(np.float32)
    z = z[(z.max(1) < 250) & (z.mean(1) > 60)]
    if len(z) < 500:
        return None
    m = z.mean(0)
    return round(float(m.max() / max(m.min(), 1.0)), 2)


class Registrador:
    def __init__(self, ref_bgr):
        self.h, self.w = ref_bgr.shape[:2]
        r = preparar(ref_bgr)
        mask = np.full(r.shape, 255, np.uint8)
        mask[ZONA_FIJA_EXCLUIR] = 0
        self.orb = cv2.ORB_create(5000)
        self.kr, self.dr = self.orb.detectAndCompute(r, mask)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING)

    def estimar(self, bgr):
        """Transformacion foto -> referencia (matriz 2x3) y su diagnostico.
        No aplica nada: `alinear` decide si se usa."""
        diag = dict(registrado=False, inliers=0, reparto_px=0.0, correccion_px=None,
                    giro_grados=None, escala=None, motivo=None, prestada=False)
        k, d = self.orb.detectAndCompute(preparar(bgr), None)
        if d is None or len(k) < 50:
            diag["motivo"] = "sin rasgos"
            return None, diag
        m = [a for a, b in self.bf.knnMatch(d, self.dr, k=2) if a.distance < 0.75 * b.distance]
        if len(m) < 20:
            diag["motivo"] = f"pocas coincidencias ({len(m)})"
            return None, diag
        s = np.float32([k[x.queryIdx].pt for x in m])
        t = np.float32([self.kr[x.trainIdx].pt for x in m])
        A, inl = cv2.estimateAffinePartial2D(s, t, method=cv2.RANSAC, ransacReprojThreshold=3.0,
                                             maxIters=5000, confidence=0.999)
        if A is None:
            diag["motivo"] = "sin transformacion"
            return None, diag
        inl = inl.ravel().astype(bool)
        reparto = float(np.min(np.std(s[inl], 0))) if inl.sum() > 2 else 0.0
        esc = math.hypot(A[0, 0], A[1, 0]); giro = math.degrees(math.atan2(A[1, 0], A[0, 0]))
        p = np.array([430.0, 222.0])
        corr = float(np.linalg.norm(A[:, :2] @ p + A[:, 2] - p))
        diag.update(inliers=int(inl.sum()), reparto_px=round(reparto, 1), correccion_px=round(corr, 2),
                    giro_grados=round(giro, 3), escala=round(esc, 4))
        problemas = []
        if inl.sum() < MIN_INLIERS: problemas.append(f"{int(inl.sum())} coincidencias")
        if reparto < MIN_REPARTO_PX: problemas.append(f"reparto {reparto:.0f}px")
        if corr > MAX_CORRIMIENTO_PX: problemas.append(f"corrimiento {corr:.0f}px")
        if abs(giro) > MAX_GIRO_GRADOS: problemas.append(f"giro {giro:.1f} grados")
        if abs(esc - 1) > MAX_CAMBIO_ESCALA: problemas.append(f"escala {esc:.3f}")
        if problemas:
            diag["motivo"] = "alineacion no confiable (" + ", ".join(problemas) + ")"
            return A, diag
        diag["registrado"] = True
        return A, diag

    def aplicar(self, bgr, A):
        return cv2.warpAffine(bgr, A, (self.w, self.h))

    def alinear(self, bgr, prestada=None):
        """`prestada`: (A, diag) de una foto vecina del mismo dia, a usar si
        esta foto no se puede alinear sola. La camara esta fija, asi que la
        vecina sirve; se marca y baja la confianza."""
        A, diag = self.estimar(bgr)
        if diag["registrado"]:
            return self.aplicar(bgr, A), A, diag
        if prestada is not None:
            Ap, info = prestada
            diag.update(registrado=True, prestada=True, correccion_px=info.get("correccion_px"),
                        motivo=diag["motivo"] + f" -> se usa la alineacion de {info['de']}")
            return self.aplicar(bgr, Ap), Ap, diag
        return bgr, A, diag


def balance_de_blancos(bgr, p=6.0):
    """Corrige el tinte de camara usando el disco blanco de la tapa como carta
    de gris (mismo criterio que en "left": nunca gray-world, el arroz y el piso
    arrastran el promedio). Con esto el mango verde aparece tambien en las
    fotos que la camara saca verdes: el 02/09 aparecio en las 13."""
    f = bgr.astype(np.float32)
    z = f[PARCHE_BLANCO].reshape(-1, 3)
    z = z[(z.max(1) < 250) & (z.mean(1) > 40)]
    if len(z) < 500:
        return bgr
    m = (np.power(z, p).mean(0)) ** (1 / p)
    return np.clip(f * (m.mean() / np.maximum(m, 1e-6)), 0, 255).astype(np.uint8)


_YC = np.linspace(100, 700, 12001)
_XC = np.polyval(CURVA, _YC)
_SC = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(_XC), np.diff(_YC)))])
_S_REF = float(np.interp(Y_REF, _YC, _SC))


def sobre_la_curva(x, y):
    """(posicion a lo largo del recorrido desde la referencia, positivo = hacia
    arriba = mas apertura; distancia con signo a la curva)."""
    i = int(np.argmin((_XC - x) ** 2 + (_YC - y) ** 2))
    tx, ty = (_XC[min(i + 1, len(_XC) - 1)] - _XC[max(i - 1, 0)], _YC[min(i + 1, len(_YC) - 1)] - _YC[max(i - 1, 0)])
    n = math.hypot(tx, ty) or 1.0
    lado = ((x - _XC[i]) * ty - (y - _YC[i]) * tx) / n
    return _S_REF - float(_SC[i]), float(lado)


def mango_por_color(al, ventana=None):
    """Mancha verde del mango. v2: busca en todo el recorrido y, si hay varias
    manchas (pasa en fotos verdes, con restos de tinte), elige la que esta
    SOBRE la trayectoria, no la mas grande."""
    if ventana is None:
        ventana = VENTANA_AMPLIA
    v = ventana
    roi = al[v["y0"]:v["y1"], v["x0"]:v["x1"]]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.int16)
    L, A, B = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    m = ((A < VERDE["a_max"]) & (B > VERDE["b_min"]) & (L > VERDE["L_min"])).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, ct = cv2.connectedComponentsWithStats(m)
    cand = []
    for i in range(1, n):
        if not (VERDE_AREA[0] <= st[i, 4] <= VERDE_AREA_MAX):
            continue
        x, y = float(ct[i][0] + v["x0"]), float(ct[i][1] + v["y0"])
        if ventana is VENTANA_AMPLIA:
            pos_c, lado = sobre_la_curva(x, y)
            if abs(lado) > MAX_DESVIO_CURVA:
                continue
            if not (RECORRIDO_FISICO_PX[0] <= pos_c <= RECORRIDO_FISICO_PX[1]):
                continue
        else:
            lado = 0.0
        cand.append((abs(lado), -int(st[i, 4]), x, y, int(st[i, 4])))
    if not cand:
        return None
    cand.sort()
    _, _, x, y, area = cand[0]
    return dict(x=x, y=y, area=area, manchas=len(cand))


def mango_por_color_v1(al):
    v = VENTANA_MANGO
    roi = al[v["y0"]:v["y1"], v["x0"]:v["x1"]]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.int16)
    L, A, B = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    m = ((A < VERDE["a_max"]) & (B > VERDE["b_min"]) & (L > VERDE["L_min"])).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, ct = cv2.connectedComponentsWithStats(m)
    bl = [(int(st[i, 4]), ct[i]) for i in range(1, n) if VERDE_AREA[0] <= st[i, 4] <= VERDE_AREA[1]]
    if not bl:
        return None
    area, c = max(bl, key=lambda b: b[0])
    return dict(x=float(c[0] + v["x0"]), y=float(c[1] + v["y0"]), area=area)


class LectorTop:
    def __init__(self, ruta_referencia, calibracion=None):
        ref = cv2.imread(ruta_referencia)
        if ref is None:
            raise FileNotFoundError(ruta_referencia)
        self.ruta_ref = os.path.abspath(ruta_referencia)
        self.reg = Registrador(ref)
        self.calibracion = calibracion
        # posicion del mango en la referencia = cero de la medicion
        c = mango_por_color(ref)
        if c is None:
            raise ValueError("la foto de referencia tiene que mostrar el mango verde")
        self.p_ref = np.array([c["x"], c["y"]])
        # plantilla de FORMA: bordes del mango y la varilla en la referencia
        # Dos plantillas, en dos pasos. La gruesa (mango + varilla) es muy
        # distintiva pero lee ~13 % menos de movimiento, porque la varilla esta
        # mas cerca del eje de giro. La fina (solo el mango) es precisa pero a
        # veces se engancha en otra cosa. Gruesa para ubicar, fina para medir.
        G = gradiente(preparar(ref))
        self.plantillas = {}
        for nombre, p in (("gruesa", PLANTILLA_GRUESA), ("fina", PLANTILLA)):
            self.plantillas[nombre] = (G[p["y0"]:p["y1"], p["x0"]:p["x1"]],
                                       self.p_ref - np.array([p["x0"], p["y0"]]))

    def _buscar(self, G, nombre, centro=None, radio=None):
        """Busca una plantilla sobre el gradiente G. Solo acepta posiciones SOBRE
        la trayectoria del mango (sin esto, una plantilla chica se enganchaba en
        un bulon a 80 px) y, si se da `centro`, a menos de `radio` de el."""
        plant, off = self.plantillas[nombre]
        v = VENTANA_MANGO; m = 25
        x_or, y_or = v["x0"] - m, v["y0"] - m
        zona = G[y_or:v["y1"] + m, x_or:v["x1"] + m]
        r = cv2.matchTemplate(zona, plant, cv2.TM_CCOEFF_NORMED)
        yy, xx = np.mgrid[0:r.shape[0], 0:r.shape[1]]
        cx = xx + x_or + off[0]; cy = yy + y_or + off[1]
        dx, dy = cx - self.p_ref[0], cy - self.p_ref[1]
        a_lo_largo = dx * DIR_TRAYECTORIA[0] + dy * DIR_TRAYECTORIA[1]
        transversal = -dx * DIR_TRAYECTORIA[1] + dy * DIR_TRAYECTORIA[0]
        ok = (np.abs(transversal) <= FRANJA_TRANSVERSAL) & \
             (a_lo_largo >= RECORRIDO[0]) & (a_lo_largo <= RECORRIDO[1])
        if centro is not None:
            ok &= np.hypot(cx - centro[0], cy - centro[1]) <= radio
        r = np.where(ok, r, -1.0).astype(np.float32)
        _, score, _, (x, y) = cv2.minMaxLoc(r)

        def sub(a, b, c):   # vertice de la parabola: precision sub-pixel
            den = a - 2 * b + c
            return float(np.clip(0.5 * (a - c) / den, -1, 1)) if abs(den) > 1e-6 else 0.0
        fx = x + (sub(r[y, x - 1], r[y, x], r[y, x + 1]) if 0 < x < r.shape[1] - 1 and min(r[y, x - 1], r[y, x + 1]) > -1 else 0.0)
        fy = y + (sub(r[y - 1, x], r[y, x], r[y + 1, x]) if 0 < y < r.shape[0] - 1 and min(r[y - 1, x], r[y + 1, x]) > -1 else 0.0)
        return float(fx + x_or + off[0]), float(fy + y_or + off[1]), float(score)

    def mango_por_forma(self, al):
        G = gradiente(preparar(al))
        gx, gy, g_score = self._buscar(G, "gruesa")
        fx, fy, f_score = self._buscar(G, "fina", centro=(gx, gy), radio=RADIO_AFINADO)
        # el puntaje que decide si se le cree es el de la gruesa (la distintiva)
        return dict(x=fx, y=fy, score=round(g_score, 3), score_fino=round(f_score, 3),
                    gruesa=[round(gx, 1), round(gy, 1)])

    def _posicion(self, c):
        d = np.array([c["x"], c["y"]]) - self.p_ref
        return float(d @ DIR_TRAYECTORIA), float(d @ np.array([-DIR_TRAYECTORIA[1], DIR_TRAYECTORIA[0]]))

    def leer(self, ruta, prestada=None):
        img = cv2.imread(ruta)
        out = dict(archivo=os.path.basename(ruta), estado=None, posicion_px=None, apertura=None,
                   metodo=None, confianza=0.0, notas=[])
        if img is None:
            out.update(estado="error_lectura")
            return out
        out["es_referencia"] = os.path.abspath(ruta) == self.ruta_ref
        tinte = tinte_camara(img)
        color_ok = tinte is not None and tinte < TINTE_MAX_UTILIZABLE
        al, H, diag = self.reg.alinear(img, prestada)
        out.update(registro=diag, tinte_camara=tinte, color_usable=color_ok)
        if not diag["registrado"]:
            out.update(estado="alineacion_fallida")
            out["notas"].append(diag["motivo"])
            out["notas"].append("sin vecina alineada a menos de %.0f h" % MAX_HORAS_VECINA)
            return out

        if tinte is None or tinte > TINTE_MAX_RECUPERABLE:
            out.update(estado="color_inutilizable")
            out["notas"].append(f"tinte de camara {tinte}: el color no se puede recuperar, no se mide")
            return out
        col = mango_por_color(balance_de_blancos(al))
        out["color"] = col
        if col is None:
            # Sin mancha verde sobre la trayectoria. Con color bueno, lo visto
            # hasta ahora es el operario tapando el mango con la mano (04/09).
            # OJO: en v1 este estado se llamaba "palanca_ausente" y se asigno a 4
            # fotos del 02/09 donde la palanca estaba en realidad ABAJO DE TODO
            # (apertura ~0), fuera de la ventana chica de v1. Error corregido.
            # Con color roto: no se puede decidir; no se inventa.
            if color_ok:
                out.update(estado="mango_no_visible")
                out["notas"].append("no se ve el mango verde sobre su recorrido (por ejemplo, el operario lo esta tapando con la mano)")
            else:
                out.update(estado="mango_no_encontrado")
                out["notas"].append(f"tinte de camara {tinte} y no aparecio el mango tras corregir el color")
            return out

        pos, lado = sobre_la_curva(col["x"], col["y"])
        metodo, conf = "color", 1.0
        # Control por FORMA, solo cerca de la referencia: la plantilla sale de
        # la foto de referencia y lejos de ahi la palanca se ve distinta.
        # Entre dias la forma se corre 1-4 px del color de forma sistematica
        # (posible manguito que se desplaza), por eso solo una diferencia
        # GROSERA baja la confianza.
        if abs(pos) <= ZONA_FORMA:
            frm = self.mango_por_forma(al)
            out["forma"] = frm
            if frm["score"] >= MIN_SCORE_FORMA:
                dist = math.hypot(col["x"] - frm["x"], col["y"] - frm["y"])
                out["acuerdo_px"] = round(dist, 2)
                if dist <= TOL_ACUERDO_PX:
                    metodo = "color+forma"
                elif dist > TOL_FORMA_GROSERA:
                    conf = 0.75
                    out["notas"].append(f"la forma difiere {dist:.1f}px del color")
        if not color_ok:
            conf = round(conf * 0.9, 3)
            out["notas"].append(f"tinte de camara {tinte}: color corregido por balance de blancos")
        if col.get("manchas", 1) > 1:
            out["notas"].append(f"{col['manchas']} manchas verdes sobre el recorrido: se tomo la mas cercana a la curva")
        if abs(lado) > 4.0:
            conf = round(conf * 0.7, 3)
            out["notas"].append(f"el mango quedo {lado:.1f}px fuera de su recorrido")

        if diag.get("prestada"):
            conf = round(conf * 0.8, 3)
            out["notas"].append("alineacion prestada de una foto vecina (la camara esta fija)")
        out.update(estado="medida", metodo=metodo, confianza=conf,
                   posicion_px=round(pos, 2), desvio_transversal_px=round(lado, 2),
                   mango=[round(col["x"], 1), round(col["y"], 1)])
        if self.calibracion:
            out["apertura"] = self.calibracion.a_escala(pos)
            lo, hi = RANGO_CALIBRADO
            if not (lo - 0.3 <= out["apertura"] <= hi + 0.3):
                out["notas"].append(f"apertura {out['apertura']} fuera del rango calibrado ({lo}-{hi}): menos precisa")
        return out

    def leer_dia(self, rutas):
        """Lee todas las fotos de un dia en dos pasadas: 1) alinea cada una
        sola; 2) a las que no se pudieron alinear les presta la alineacion de
        la foto bien alineada mas cercana en el tiempo (si esta a menos de
        MAX_HORAS_VECINA). Devuelve los resultados en el mismo orden."""
        import datetime as _dt
        def hora(r):
            b = os.path.basename(r)[-23:-4]
            try:
                return _dt.datetime.strptime(b, "%Y-%m-%d_%H-%M-%S")
            except ValueError:
                return None
        est = {}
        for r in rutas:
            img = cv2.imread(r)
            est[r] = self.reg.estimar(img) if img is not None else (None, {"registrado": False})
        buenas = [(hora(r), r) for r in rutas if est[r][1]["registrado"] and hora(r)]
        res = []
        for r in rutas:
            prest = None
            if not est[r][1]["registrado"] and hora(r) and buenas:
                h = hora(r)
                dh, vec = min(((abs((hb - h).total_seconds()) / 3600, rb) for hb, rb in buenas), key=lambda x: x[0])
                if dh <= MAX_HORAS_VECINA:
                    prest = (est[vec][0], dict(est[vec][1], de=os.path.basename(vec)[-12:-4]))
            res.append(self.leer(r, prest))
        return res

    def dibujar(self, ruta, salida, recorte=(150, 600, 340, 560)):
        """Foto alineada con la medicion encima: linea blanca = recorrido del
        mango (la curva), marcas cada 1 unidad de apertura si hay calibracion,
        circulo verde = mango encontrado."""
        res = self.leer(ruta)
        al, _, _ = self.reg.alinear(cv2.imread(ruta))
        vis = al.copy()
        pts = np.stack([_XC, _YC], 1)[(_YC > recorte[0]) & (_YC < recorte[1])].astype(np.int32)
        cv2.polylines(vis, [pts], False, (255, 255, 255), 1)
        if self.calibracion:
            for v in range(0, 11):
                s = (v - self.calibracion.b) / self.calibracion.k
                y = float(np.interp(_S_REF - s, _SC, _YC)); x = float(np.polyval(CURVA, y))
                if recorte[0] < y < recorte[1]:
                    cv2.line(vis, (int(x) - 5, int(y)), (int(x) + 5, int(y)), (0, 255, 255), 1)
                    cv2.putText(vis, str(v), (int(x) - 22, int(y) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
        if res.get("mango"):
            cv2.circle(vis, (int(res["mango"][0]), int(res["mango"][1])), 10, (0, 200, 0), 2)
        y0, y1, x0, x1 = recorte
        vis = cv2.resize(vis[y0:y1, x0:x1], None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
        t1 = res["archivo"][-23:-4]
        t2 = (f"apertura {res['apertura']}  cf={res['confianza']}" if res["estado"] == "medida" else res["estado"])
        for k, t in enumerate((t1, t2)):
            cv2.putText(vis, t, (5, 16 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
            cv2.putText(vis, t, (5, 16 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.imwrite(salida, vis)
        return res


class Calibracion:
    """Convierte posicion_px a la escala 0-10 con una recta que pasa por dos
    puntos conocidos: (posicion_px_1, valor_1), (posicion_px_2, valor_2).
    En un rango chico el arco es practicamente una recta. Sin estos dos puntos
    la columna `apertura` sale vacia: no se inventa."""
    def __init__(self, p1, v1, p2, v2):
        self.k = (v2 - v1) / (p2 - p1)
        self.b = v1 - self.k * p1

    @classmethod
    def desde_recta(cls, k, b):
        c = cls.__new__(cls); c.k, c.b = k, b
        return c

    def a_escala(self, pos):
        return round(self.k * pos + self.b, 3)


# Calibracion vigente (v2): apertura = 0,02909 * posicion_px + 8,9553  (1 unidad = 34,4 px)
# Ajustada (con descarte de errores groseros) contra el `opening` de Nexlab en
# 682 fotos de 4 dias (21/08, 28/08, 02/09, 04/09) que cubren TODA la escala:
# de 0 (valvula cerrada, verificado a ojo) a 9,5. Rehacer con calibrar_top.py.
# Validada dejando un dia afuera: error tipico 0,07-0,17 unidades (p95 <= 0,30)
# en el dia que no se uso para ajustar; del orden del ruido de Nexlab.
# Vale solo con foto_referencia_top.jpg y la camara en la posicion de 21/08 en
# adelante (el 06/08 y el 09/08 estaba en otra posicion).
CALIBRACION_VIGENTE = Calibracion.desde_recta(0.02909, 8.9553)
RANGO_CALIBRADO = (0.0, 9.5)

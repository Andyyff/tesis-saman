#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision_left.py — Algoritmo propio de lectura de la camara "left".
Tesis UM · monitoreo del pulido por abrasion · planta de Jose Pedro Varela.

Escrito desde cero. No reutiliza el algoritmo de Nexlab ni toma sus numeros
como verdad: sus mensajes de error se usaron unicamente para encontrar fotos
dificiles con las cuales probar esto.

CUATRO DECISIONES DE FONDO
--------------------------
1) CADA VARILLA SE MIDE SOLA.
   Que falle "a" no puede tocar a "b". El sistema actual descarta la foto
   entera cuando se le cae una referencia; aca eso es imposible por
   construccion: son dos mediciones independientes que solo comparten el
   marco geometrico.

2) LA VARILLA SE ENCUENTRA POR SU ROSCA, NO POR SU COLOR.
   La varilla es una barra roscada: su textura es una sucesion periodica de
   crestas brillantes, con un periodo de entre 9 y 22 px. Nada mas en la
   escena tiene esa firma (el piso tiene vetas irregulares, la maquina es
   lisa). Se busca la recta que maximiza esa periodicidad. Recien despues
   se buscan los objetos de color, y solo SOBRE esa recta — por eso una
   chapa amarilla en el piso o la pesa de la otra varilla no pueden
   confundir la medicion.

3) LA GEOMETRIA SALE DEL REGISTRO, NO DE LAS ANCLAS MAGENTA.
   Cada foto se alinea contra una foto de referencia usando las partes fijas
   de la maquina (ORB + RANSAC). En ese marco alineado, la horizontal y las
   regiones de busqueda son constantes. Las 3 chapitas magenta pasan de ser
   un requisito a ser un control de calidad: si estan, confirman el registro;
   si no estan, no pasa nada. El sistema actual hace lo contrario — sin 3
   anclas no mide — y eso solo explica la mayor parte de sus fallas.

4) LA ROSCA TAMBIEN ES UNA REGLA.
   El periodo de la rosca da una escala LOCAL (px por paso) que corrige la
   perspectiva a lo largo de la propia varilla, y permite informar la
   distancia en PASOS DE ROSCA: una unidad invariante al zoom, a la distancia
   de la camara y a la escala mm/pixel. Si alguna vez se mide el paso con un
   calibre, toda la serie historica queda convertida a milimetros de una sola
   vez, retroactivamente.

BALANCE DE BLANCOS
------------------
No se usa gray-world: el piso de madera rojiza domina el promedio y empuja
toda la imagen al cyan (probado: convertia la pesa celeste en "verde"). Se
usa el cuerpo blanco de la maquina como carta de gris incorporada a la
escena, que es lo que fisicamente corresponde.
"""

import os, math
import numpy as np
import cv2

# ---------------------------------------------------------------- constantes

BANDA = dict(x0=380, x1=980, y0=280, y1=670)   # donde pueden estar las varillas
Y_SEPARA = 480                                  # frontera entre varilla "a" y "b"
VENTANA_ANCLAS = dict(x0=835, x1=945, y0=560, y1=900)
PARCHE_BLANCO = (slice(120, 760), slice(960, 1275))   # cuerpo blanco de la maquina

ROSCA_PX_MIN, ROSCA_PX_MAX = 9.0, 22.0
MUESTRAS_MIN_FFT = 32         # ninguna ventana de analisis puede ser mas corta
TINTE_MAX_UTILIZABLE = 12.0   # desvio de color por encima del cual el color no sirve
ENERGIA_MIN_VARILLA = 4.0        # por debajo de esto no hay rosca creible

# Umbrales de color, medidos sobre el corpus (Lab, imagen ya balanceada).
#   ficha verde  : a* ~ -47 / -30,  b* ~ +28 / +16
#   pesa celeste : a* ~ -18,        b* ~ -13   <- se separa por b*
#   pesa rosa    : a* ~ +38,        b* ~  -2
#   chapa amarilla del piso: a* ~ +8, b* ~ +38
VERDE = dict(a_max=-20, b_min=8, L_min=40)
VERDE_AREA = (120, 2500)
PESA_S_MIN = 80
PESA_BRILLO_REL = 0.72   # brillo para SEMBRAR: encontrar la pesa sin agarrar el piso
# Umbrales laxos para COMPLETAR la pesa una vez encontrada. Hacen falta porque
# la mitad inferior de la pesa queda en sombra y no llega al umbral estricto:
# con un solo umbral, el blob detectado era la mitad de arriba y el centro
# quedaba corrido ~25 px, un sesgo sistematico del orden del 11 % en la
# distancia. Es el mismo truco que usa la deteccion de bordes por histeresis:
# umbral alto para decidir que algo esta, umbral bajo para decidir hasta donde
# llega.
PESA_S_LAXO = 62
PESA_BRILLO_LAXO = 0.38
PESA_BRILLO_QUEMADO = 0.98   # reflejo que quema el sensor: sigue siendo la pesa
CRECIMIENTO_PESA = 45    # px de kernel: la pesa no crece mas alla de esto desde su semilla
PESA_AREA = (400, 9000)
PESA_LADO_MAX = 115      # px: una pesa no es mas grande que esto
ANCLA_AREA = (30, 500)

# --- pesa sin pintar montada en el extremo de la barra ---------------------
#
# Hay pesas de acero desnudo. Su saturacion es ~9 y el umbral del detector de
# color es 80: no pasa un solo pixel. Y cuando ademas quedan montadas contra
# la maquina, tampoco dejan "hueco" en la rosca — ahi la rosca ya se terminaba.
# Resultado medido el 12/08: 31 de 36 fotos informaban "varilla sin pesa" con
# la pesa puesta, y sin bajar la confianza, porque un estado no es una medida.
#
# Probados con datos y DESCARTADOS antes de llegar a esto: saturacion, brillo
# fuera del eje, textura local, resta contra un fondo de brillo aprendido y
# energia de rosca. Ninguno separa el acero de la maquina blanca que tiene
# detras.
#
# Lo que si separa es lo mas obvio: LA PESA ES GORDA Y LA BARRA ES FLACA.
# Medido sobre el 12/08 (22 fotos con pesa, 14 sin, el mismo dia y la misma
# camara): barra sola 0-12 px de ancho, barra con pesa 34-36 px.
#
# Dos guardas mas, porque la barra "a" termina contra el cuerpo blanco de la
# maquina y ahi todo es ancho y claro:
#   - el ensanchamiento se mide CONTRA EL ANCHO DE LA PROPIA BARRA en esa
#     misma foto, no contra un numero fijo;
#   - tiene que ser un BULTO ACOTADO, no una meseta: una pesa se termina, la
#     maquina no. Si sigue ancho pasando el pivote, es la maquina.
ANCHO_CLARO_REL = 0.88   # brillo, relativo al blanco de la maquina
ANCHO_EXTRA_MIN = 16     # px que la pesa suma al ancho de la barra desnuda
ANCHO_LARGO_MIN = 24     # px: cuanto tiene que sostenerse el ensanchamiento

# Un hueco en la rosca solo es una pesa si hay algo SOLIDO Y CLARO llenandolo.
# Medido: el cano azul que cruza por detras da brillo 0,53; una pesa real 1,00.
HUECO_BRILLO_MIN = 0.75

# Fraccion minima de la barra que un objeto tiene que tapar para ser una pesa.
# Ver cubre_la_barra(). Con el reflejo especular incluido en la mascara:
#     pesas de verdad      0,66 a 0,94
#     carton, chapa, cano  0,13 a 0,21
# El umbral queda a mitad de camino, con margen de 3 veces para cada lado.
CUBRE_MIN = 0.40

# Rango fisico de la distancia pesa->tapon.
#
# El piso NO es un numero fijo. Lo fue (90 px) y estaba mal: ese valor salio de
# una bimodalidad del histograma que en realidad era un error nuestro — el
# origen mal ubicado cuando faltaba la ficha verde. Corregido ese error, la
# distribucion es continua de 0 a 340 px, y una auditoria sobre dias nuevos
# mostro un dia entero (09/09) con las barras retraidas y las pesas realmente
# pegadas al tapon: distancias de 30 a 80 px, correctas, que el piso fijo
# tiraba a la basura.
#
# El criterio correcto es fisico: la pesa es un cilindro y el tapon tambien,
# asi que sus centros no pueden estar mas cerca que la suma de sus radios.
# Por debajo de eso, la "pesa" y el origen son el mismo objeto.
# Tope de arriba: es FISICO, sale de la ficha que midio Latitud.
# La barra entera mide 230 mm desde el borde de afuera del tapon hasta el
# centro de la perilla. Nuestro origen es el borde INTERNO del tapon, o sea
# unos 22 mm mas adentro, y la ultima hendidura —el punto mas lejos donde se
# puede enroscar una pesa— esta a 35 mm de la perilla. El maximo fisico es
# entonces 230 - 22 - 35 = 173 mm. Se deja 200 mm de margen porque el tapon
# detectado varia unos milimetros.
#
# El tope anterior era 360 px, que no era un numero fisico: son 308 mm en la
# varilla "a". Con el, el algoritmo informaba distancias MAS LARGAS QUE LA
# BARRA ENTERA sin que saltara ninguna alarma — Alfonso encontro una de 290 mm.
DIST_MAX_MM = 200.0
DIST_MAX = 360.0          # tope en px, se mantiene como red de seguridad
RADIO_TAPON_PX = 12.0
DIST_MIN_ABS = 25.0


def distancia_minima(largo_pesa_px):
    """Minima separacion fisicamente posible entre el CENTRO de la pesa y el
    origen, dada la propia pesa medida en esta foto.

    El origen es el borde INTERNO del tapon, o sea la cara del tapon contra la
    que se apoya la pesa. Desde ahi, lo mas cerca que puede estar el centro de
    la pesa es su propio medio largo. Antes se sumaba ademas el radio del
    tapon, que era correcto cuando el origen era el CENTRO del tapon; al mover
    el origen quedo contado dos veces y rechazaba pesas apoyadas contra el."""
    return max(DIST_MIN_ABS, (largo_pesa_px or 40.0) / 2.0)

DIST_EJE_FICHA = 26      # px: cuanto puede alejarse del eje una ficha valida
DIST_EJE_PESA  = 26


# ------------------------------------------------------------------ utilidad

def tinte_camara(bgr):
    """Cuan lejos del gris esta el cuerpo blanco de la maquina. 1.0 = neutro.
    Valores altos marcan una falla de color de la camara (las fotos que salen
    enteras violetas o verdosas). No es un defecto nuestro ni algo que se
    pueda corregir del todo: cuando un canal se muere, el color deja de ser
    informacion utilizable y hay que medir por geometria."""
    z = bgr[PARCHE_BLANCO].reshape(-1, 3).astype(np.float32)
    z = z[(z.max(1) < 252) & (z.mean(1) > 40)]
    if len(z) < 500:
        return None
    m = z.mean(0)
    return round(float(m.max() / max(m.min(), 1e-6)), 2)


def balance_de_blancos(bgr, p=6.0):
    """Shades-of-Gray sobre el cuerpo blanco de la maquina (carta de gris
    natural de la escena). Devuelve la imagen con el tinte de camara
    corregido, que es lo que hace que las fotos violeta o verdosas dejen de
    ser un caso especial."""
    f = bgr.astype(np.float32)
    z = f[PARCHE_BLANCO].reshape(-1, 3)
    z = z[(z.max(1) < 250) & (z.mean(1) > 60)]
    if len(z) < 500:                       # sin parche util, ultimo recurso
        z = f.reshape(-1, 3)
        z = z[(z.max(1) < 250) & (z.mean(1) > 40)]
        if len(z) < 500:
            return bgr
    m = (np.power(z, p).mean(0)) ** (1 / p)
    return np.clip(f * (m.mean() / np.maximum(m, 1e-6)), 0, 255).astype(np.uint8)


def _blobs(mask, area_min, area_max):
    n, etq, st, ct = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        a = st[i, cv2.CC_STAT_AREA]
        if area_min <= a <= area_max:
            out.append(dict(x=float(ct[i][0]), y=float(ct[i][1]), area=int(a),
                            w=int(st[i, cv2.CC_STAT_WIDTH]),
                            h=int(st[i, cv2.CC_STAT_HEIGHT]),
                            id=i, etq=etq))
    return out


def _dentro(b, caja):
    return caja["x0"] <= b["x"] <= caja["x1"] and caja["y0"] <= b["y"] <= caja["y1"]


# ------------------------------------------------------------------- registro

class Registrador:
    """Alinea cualquier foto contra una de referencia.

    VERSION 3 (03/10). Por que se cambio:
    La version anterior estimaba una homografia completa (8 grados de
    libertad: puede estirar, achicar, inclinar y deformar la foto). Con pocos
    rasgos buenos esa homografia salia deformada: en ~150 de 882 fotos
    escalaba la imagen entre 0,7 y 2 veces, y en alguna la daba vuelta. Pero
    la camara real casi no se mueve: la perilla roja (atornillada a la
    maquina) queda a 1,2 px de su lugar de mediana y a 3,3 px como maximo
    sobre 192 fotos al azar SIN alinear nada.

    Ahora:
      1. Solo se permite CORRER, GIRAR y un cambio de escala minimo
         (estimateAffinePartial2D, 4 grados de libertad). Una camara
         atornillada no puede deformar la imagen.
      2. Limites fisicos: escala 1 +- 4 %, giro <= 3 grados, corrimiento
         <= 60 px. Fuera de eso la estimacion esta mal, no la camara.
      3. Testigo independiente: la PERILLA ROJA. No se usa para alinear (su
         zona esta fuera de la mascara de rasgos) y es una pieza fija de la
         maquina. Despues de alinear tiene que caer a <= 4 px de su lugar. Si
         la alineacion no la deja ahi pero sin alinear ya esta en su lugar,
         la camara no se movio y se usa la foto tal cual.
      Las fichas magenta NO sirven de testigo: estan en la chapa del chute,
      que se corre sola (5 px de mediana respecto de la maquina, y fue
      derivando de 8 px en julio a 1 px en septiembre).

    Resultado medido en 3 dias completos (603 fotos): fotos alineadas 514 ->
    596; salto mediano de la distancia entre fotos seguidas, 18/07: barra a
    2,5 -> 0,4 mm, barra b 2,0 -> 0,6 mm; saltos de mas de 10 mm 28 -> 1.
    Detalle en 03_validacion/2026-10-03_alineacion-v3.md.
    """

    TOL_TESTIGO = 4.0       # px: la perilla tiene que quedar a esta distancia
    TOL_ANCLA = 12.0        # px de tolerancia para las fichas (respaldo)
    ESCALA_MAX = 0.04
    GIRO_MAX = 3.0
    CORRIDA_MAX = 60.0

    def __init__(self, ruta_referencia, n_rasgos=4000):
        self.ref = cv2.imread(ruta_referencia)
        if self.ref is None:
            raise FileNotFoundError(ruta_referencia)
        self.h, self.w = self.ref.shape[:2]
        gris = cv2.cvtColor(self.ref, cv2.COLOR_BGR2GRAY)

        # partes fijas de la maquina; fuera: las varillas y pesas (se mueven),
        # el borde de arriba, y las fichas magenta y la perilla (testigos)
        fija = np.zeros((self.h, self.w), np.uint8)
        fija[:, 620:] = 255
        fija[270:680, 620:1000] = 0
        fija[0:160, :] = 0
        fija[590:880, 840:915] = 0
        self.mascara = fija

        self.orb = cv2.ORB_create(n_rasgos, scaleFactor=1.2, nlevels=8)
        self.kp_ref, self.desc_ref = self.orb.detectAndCompute(gris, fija)
        self.orb2 = cv2.ORB_create(8000, scaleFactor=1.15, nlevels=10)
        self.kp_ref2, self.desc_ref2 = self.orb2.detectAndCompute(gris, fija)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        wb_ref = balance_de_blancos(self.ref)
        self.anclas_ref = [(b["x"], b["y"]) for b in detectar_anclas(wb_ref)]
        self.perilla_ref = detectar_perilla(wb_ref)

    def _similitud(self, gris, orb, kp_ref, desc_ref, ratio):
        kp, desc = orb.detectAndCompute(gris, self.mascara)
        if desc is None or len(kp) < 20:
            return None, 0, 0
        pares = self.matcher.knnMatch(desc, desc_ref, k=2)
        buenas = [p[0] for p in pares if len(p) == 2 and p[0].distance < ratio * p[1].distance]
        if len(buenas) < 10:
            return None, len(buenas), 0
        src = np.float32([kp[m.queryIdx].pt for m in buenas])
        dst = np.float32([kp_ref[m.trainIdx].pt for m in buenas])
        M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                             ransacReprojThreshold=3.0, maxIters=5000,
                                             confidence=0.995)
        if M is None:
            return None, len(buenas), 0
        return np.vstack([M, [0.0, 0.0, 1.0]]), len(buenas), int(inl.sum())

    @staticmethod
    def _parametros(H):
        escala = math.hypot(H[0, 0], H[1, 0])
        giro = math.degrees(math.atan2(H[1, 0], H[0, 0]))
        corrida = math.hypot(H[0, 2], H[1, 2])
        return escala, giro, corrida

    def _correccion(self, H):
        sondas = np.float32([[700, 400], [850, 550], [550, 450]]).reshape(-1, 1, 2)
        return float(np.linalg.norm(cv2.perspectiveTransform(sondas, H) - sondas, axis=2).mean())

    def _error_testigo(self, k, H):
        if k is None or self.perilla_ref is None:
            return None
        p = cv2.perspectiveTransform(np.float64([[k]]), np.asarray(H, np.float64))[0, 0]
        return math.hypot(p[0] - self.perilla_ref[0], p[1] - self.perilla_ref[1])

    def _anclas_validan(self, bgr, H):
        if not self.anclas_ref:
            return 0
        al = cv2.warpPerspective(bgr, H, (self.w, self.h))
        halladas = [(b["x"], b["y"]) for b in detectar_anclas(balance_de_blancos(al))]
        return sum(1 for ax, ay in self.anclas_ref
                   if any(math.hypot(hx - ax, hy - ay) <= self.TOL_ANCLA for hx, hy in halladas))

    def alinear(self, bgr):
        gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        diag = dict(registrado=False, coincidencias=0, inliers=0, correccion_px=None,
                    escala=None, giro=None, testigo_px=None, metodo=None, pasada=0,
                    motivo=None)
        I = np.eye(3)

        H = None
        for pasada, (orb, kpr, dsr, ratio) in enumerate(
                ((self.orb, self.kp_ref, self.desc_ref, 0.75),
                 (self.orb2, self.kp_ref2, self.desc_ref2, 0.80)), start=1):
            Hc, ngood, inl = self._similitud(gris, orb, kpr, dsr, ratio)
            diag.update(coincidencias=ngood, inliers=inl, pasada=pasada)
            if Hc is None or inl < 12:
                diag["motivo"] = "pocas coincidencias con la referencia"
                continue
            esc, giro, corr = self._parametros(Hc)
            if abs(esc - 1) > self.ESCALA_MAX or abs(giro) > self.GIRO_MAX or corr > self.CORRIDA_MAX:
                diag["motivo"] = (f"alineacion imposible para una camara fija (escala {esc:.2f}, "
                                  f"giro {giro:.1f}, corrida {corr:.0f} px)")
                continue
            H = Hc
            diag.update(escala=round(esc, 4), giro=round(giro, 2))
            break

        # testigo: la perilla
        k = detectar_perilla(balance_de_blancos(bgr))
        e_sin = self._error_testigo(k, I)
        e_con = self._error_testigo(k, H) if H is not None else None

        elegido = None
        if e_sin is not None:
            # hay testigo: se elige lo que deja la perilla en su lugar
            if e_con is not None and e_con <= self.TOL_TESTIGO and e_con <= e_sin + 0.5:
                elegido, diag["metodo"], diag["testigo_px"] = H, "alineada", round(e_con, 2)
            elif e_sin <= self.TOL_TESTIGO:
                elegido, diag["metodo"], diag["testigo_px"] = I, "camara_quieta", round(e_sin, 2)
            elif e_con is not None and e_con < e_sin:
                elegido, diag["metodo"], diag["testigo_px"] = H, "alineada", round(e_con, 2)
                if e_con > 2 * self.TOL_TESTIGO:
                    elegido = None
                    diag["motivo"] = f"la perilla queda a {e_con:.0f} px de su lugar"
        elif H is not None:
            # sin perilla visible: respaldo con las fichas
            if self._anclas_validan(bgr, H) >= 2:
                elegido, diag["metodo"] = H, "alineada_por_fichas"
            else:
                diag["motivo"] = "sin testigo para confirmar la alineacion"

        if elegido is None:
            return bgr, diag
        diag.update(registrado=True, motivo=None, H=elegido.tolist(),
                    correccion_px=round(self._correccion(elegido), 2))
        if elegido is I:
            return bgr, diag
        return cv2.warpPerspective(bgr, elegido, (self.w, self.h)), diag


# ----------------------------------------------------- la rosca: firma y regla

def perfil(gris, p0, u, t0, t1, paso=1.0, medio_ancho=4):
    """Brillo a lo largo de una recta, promediado transversalmente."""
    u = u / (np.linalg.norm(u) + 1e-9)
    nrm = np.array([-u[1], u[0]])
    ts = np.arange(t0, t1, paso)
    if len(ts) < 8:
        return ts, np.zeros(len(ts), np.float32)
    pts = p0[None, :] + ts[:, None] * u[None, :]
    acc = np.zeros(len(ts), np.float32); cnt = np.zeros(len(ts), np.float32)
    H, W = gris.shape
    for o in range(-medio_ancho, medio_ancho + 1):
        q = pts + nrm[None, :] * o
        x = np.round(q[:, 0]).astype(int); y = np.round(q[:, 1]).astype(int)
        ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        acc[ok] += gris[y[ok], x[ok]]; cnt[ok] += 1
    return ts, np.where(cnt > 0, acc / np.maximum(cnt, 1), 0.0)


def energia_rosca(valores, paso=1.0, banda_px=None):
    """Cuanta 'barra roscada' hay en este perfil -> (energia, periodo_px).
    La energia es la altura del pico espectral en la banda de la rosca,
    medida contra el fondo del propio espectro."""
    v = np.asarray(valores, np.float32)
    if len(v) < MUESTRAS_MIN_FFT or v.std() < 1.0:
        # Menos muestras que esto y el analisis de frecuencia no significa nada.
        # Quien llame con una ventana mas corta se queda ciego sin enterarse,
        # asi que la constante esta arriba y documentada.
        return 0.0, None
    v = v - cv2.GaussianBlur(v.reshape(-1, 1), (0, 0), 12 / paso).ravel()
    v = v * np.hanning(len(v))
    esp = np.abs(np.fft.rfft(v))
    frec = np.fft.rfftfreq(len(v), d=paso)
    pmin, pmax = banda_px or (ROSCA_PX_MIN, ROSCA_PX_MAX)
    banda = (frec > 1.0 / pmax) & (frec < 1.0 / pmin)
    if not banda.any() or esp[1:].sum() <= 0:
        return 0.0, None
    k = int(np.argmax(np.where(banda, esp, 0)))
    return float(esp[k] / (esp[1:].mean() + 1e-9)), (float(1 / frec[k]) if frec[k] > 0 else None)


# Las varillas estan atornilladas a la maquina: en el marco alineado, el punto
# por donde entran a la maquina es fijo. Medido sobre el corpus (n=339):
# la varilla "b" pasa por y=514+-25 en x=880, y la "a" por y=358 (+50/-50).
# Eso convierte la busqueda en un solo grado de libertad por varilla — el
# angulo — y hace imposible que una veta del piso se haga pasar por varilla.
X_PIVOTE = 880
PIVOTE = {"a": (298, 432), "b": (468, 562)}
# Rango de busqueda del angulo, en el signo INTERNO (el reportado es este
# cambiado de signo: interno -24 = reportado +24).
#
# Estaba en -24 y el angulo reportado llegaba a 26,5 grados en el 2,6 % de las
# lecturas de la varilla "a" — o sea, la barra real se sale del rango. Se
# escapaba porque el afinado grueso de buscar_varilla no estaba acotado; el
# afinado por cresta si lo esta, y por eso en esas fotos el mejor estimador del
# angulo se descartaba EN SILENCIO (medido: 2 de cada 3 salian sin puntos de
# cresta, contra 14-22 puntos en el rango normal).
# Se amplia a -32 para que la barra quepa con margen. El tope de arriba se deja
# en +7: el minimo reportado observado es -4,25, sobra margen.
ANG_MIN, ANG_MAX = -32.0, 7.0          # grados; negativo = sube hacia la derecha

# Paso aparente de la rosca, en pixeles, medido sobre el corpus. Es distinto
# en cada varilla porque estan a distinta distancia de la camara, y es una
# constante de la escena: la rosca no cambia de paso. Sirve de filtro fuerte —
# las vetas del piso de madera tienen un periodo de ~20 px y quedan afuera de
# las dos bandas.
PASO_ROSCA = {"a": (10.0, 13.6), "b": (13.0, 17.2)}

# Paso de rosca CALIBRADO, en px, por varilla.
#
# Latitud midio la barra fisica: las hendiduras estan cada 10 mm exactos. O sea
# que el paso es una CONSTANTE de la escena — no puede cambiar de una foto a la
# siguiente. El valor que devuelve la FFT si cambia, pero no porque cambie la
# barra: cambia porque el pico espectral cae en un bin u otro. Medido sobre
# 2.842 lecturas hay solo 53 valores distintos de paso en la varilla "a"
# (11.54, 11.67, 11.88, 12.00 ...), que son exactamente los periodos de bin, con
# un desvio del 2,86 %. Ese 2,86 % es ruido de cuantizacion y se iba entero al
# resultado final, porque el paso es el divisor que convierte px a milimetros.
#
# Entonces: para medir se usa el paso calibrado, y el medido en cada foto queda
# como control. Si el medido se aparta mucho del calibrado, algo pasa con la
# foto (la camara se movio de verdad, o el eje esta mal) y se avisa.
# Pero el paso aparente SI depende del angulo de la barra: al inclinarse cambia
# su distancia a la camara y la perspectiva la acorta. Medido sobre 2.842
# lecturas: en la varilla "b" el paso baja 4,3 % entre 0 y 20 grados, y en la
# "a" apenas 0,5 % (esta mas lejos, la perspectiva la afecta menos). Eso es
# geometria real, no ruido, asi que se modela con una recta por varilla en vez
# de tirarla.
PASO_POR_ANGULO = {"a": (-0.0031, 11.704), "b": (-0.0325, 14.976)}   # px = m*grados + b
PASO_MM = 10.0                # mm entre hendiduras (medido por Latitud)
# Cuando el paso medido en la foto se aparta MUCHO del modelo, se usa el medido.
# Historia: estuvo en 5 %. Con la alineacion vieja (que a veces estiraba la
# foto) el paso medido compensaba ese estiramiento y 5 % era lo mejor. Con la
# alineacion nueva (03/10) la foto ya no se estira, y el paso medido por FFT
# esta cuantizado (+-3 %): con 5 % el divisor saltaba entre el modelo y el
# medido de una foto a la siguiente y metia saltos de ~5 % en la distancia
# (ej.: 16/09 00:27 barra b, 120 -> 126 mm sin que nada cambie). Medido sobre 3
# dias completos (603 fotos): 15 % baja el salto entre fotos seguidas el 16/09
# (barra b 1,19 -> 0,96 mm; barra a 4,04 -> 3,72 mm) y no cambia los otros dos
# dias. Queda solo como red para un cambio grosero (por ej. que cambien la
# lente o acerquen la camara).
PASO_DESVIO_MAX = 0.15


def paso_de_rosca(nombre, angulo_grados, paso_medido=None):
    """El divisor que convierte pixeles a milimetros. Ver los comentarios de
    PASO_POR_ANGULO: modelo segun el angulo, salvo que la foto diga otra cosa
    muy distinta."""
    m, c = PASO_POR_ANGULO[nombre]
    modelo = m * float(angulo_grados or 0.0) + c
    if paso_medido and abs(paso_medido - modelo) / modelo > PASO_DESVIO_MAX:
        return float(paso_medido), True
    return float(modelo), False


def afinar_por_cresta(gris, eje, t_ini, t_fin, banda_px, ang_min=None, ang_max=None):
    """Ajuste fino del eje siguiendo la cresta de la varilla.

    Hasta aca el eje viene de un barrido grueso: una recta que cruza la
    varilla en diagonal todavia recoge rosca en parte de su recorrido, asi
    que el angulo queda impreciso — y con el corredor de busqueda corrido
    unos pocos grados, la pesa se escapa.

    Aca se construye una imagen rectificada del corredor (posicion a lo largo
    de la varilla x desplazamiento transversal), se mide en cada tramo a que
    altura transversal esta la textura de rosca, y se ajusta una recta a esas
    alturas. Es seguir la cresta, que es lo que un ojo humano hace solo."""
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    ts = np.arange(t_ini, t_fin, 1.0)
    if len(ts) < 80:
        return eje
    offs = np.arange(-30, 31, 1.0)
    base = eje["p0"][None, :] + ts[:, None] * u[None, :]
    H, W = gris.shape
    M = np.zeros((len(offs), len(ts)), np.float32)
    for i, o in enumerate(offs):
        q = base + nrm[None, :] * o
        x = np.clip(np.round(q[:, 0]).astype(int), 0, W - 1)
        y = np.clip(np.round(q[:, 1]).astype(int), 0, H - 1)
        M[i] = gris[y, x]
    # pasa-altos a lo largo de la varilla: deja solo la textura de la rosca
    M = M - cv2.GaussianBlur(M, (0, 0), sigmaX=6, sigmaY=0.01)
    E = cv2.GaussianBlur(np.abs(M), (0, 0), sigmaX=18, sigmaY=1.2)

    pts = []
    ancho = 40
    # se muestrea cada 10 px (antes cada 20): mas puntos de apoyo para el
    # ajuste, que es lo que fija el angulo
    for c in range(ancho // 2, len(ts) - ancho // 2, 10):
        col = E[:, c - ancho // 2:c + ancho // 2].mean(1)
        j = int(np.argmax(col))
        nitidez = col[j] / (np.median(col) + 1e-9)
        if nitidez > 1.6 and 1 <= j <= len(offs) - 2:
            # interpolacion parabolica para precision sub-pixel
            y0, y1, y2 = col[j - 1], col[j], col[j + 1]
            den = (y0 - 2 * y1 + y2)
            corr = 0.5 * (y0 - y2) / den if abs(den) > 1e-6 else 0.0
            pts.append((ts[c], offs[j] + float(np.clip(corr, -1, 1)), nitidez))
    if len(pts) < 5:
        return eje
    tt = np.array([p[0] for p in pts]); ss = np.array([p[1] for p in pts])
    # ajuste robusto, sin ponderar: probado contra el corpus, ponderar por la
    # nitidez de la cresta empeora la mediana en las dos barras.
    for _ in range(2):
        b, a = np.polyfit(tt, ss, 1)
        res = np.abs(ss - (a + b * tt))
        keep = res <= max(3.0, 2.0 * np.median(res))
        if keep.sum() < 4:
            break
        tt, ss = tt[keep], ss[keep]
    b, a = np.polyfit(tt, ss, 1)
    if abs(math.degrees(math.atan(b))) > 8:
        return eje
    ang = eje["inclinacion"] + math.degrees(math.atan(b))
    # tope duro: el ajuste fino no puede sacar la barra de su rango fisico.
    # Sin esto aparecian angulos de 32° con un rango de busqueda de -7 a 24.
    if ang_min is not None and not (ang_min - 1.0 <= ang <= ang_max + 1.0):
        return eje
    u2 = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
    p0 = eje["p0"] + nrm * a
    _, val = perfil(gris, p0, u2, t_ini, t_fin, paso=1.0, medio_ancho=2)
    e, per = energia_rosca(val, banda_px=banda_px)
    if e < eje["energia"] * 0.7:
        return eje
    residuo = float(np.median(np.abs(ss - (a + b * tt))))
    nuevo = dict(eje)
    nuevo.update(p0=p0, u=u2, inclinacion=ang, energia=e, periodo=per or eje["periodo"],
                 base_angulo_px=float(tt.max() - tt.min()), puntos_cresta=int(len(tt)),
                 residuo_cresta=round(residuo, 2))
    return nuevo


def buscar_varilla(gris, nombre):
    """Encuentra LA recta de una varilla, dentro de su propio espacio de
    busqueda. Cada varilla se busca aparte: no compiten entre si, asi que no
    existe el caso de que una se quede con las dos rectas."""
    x0, x1 = BANDA["x0"], BANDA["x1"]
    yp0, yp1 = PIVOTE[nombre]

    def recta(yp, ang):
        u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        p_piv = np.array([X_PIVOTE, yp], float)
        p0 = p_piv + u * ((x0 - X_PIVOTE) / u[0])      # llevada a x = x0
        return p0, u

    banda = PASO_ROSCA[nombre]

    def puntaje(yp, ang, neto=False):
        p0, u = recta(yp, ang)
        _, val = perfil(gris, p0, u, 0, x1 - x0, paso=1.0, medio_ancho=3)
        e, per = energia_rosca(val, banda_px=banda)
        if not neto:
            return e, per
        nrm = np.array([-u[1], u[0]])
        vec = []
        for off in (-17, 17):
            _, v2 = perfil(gris, p0 + nrm * off, u, 0, x1 - x0, paso=1.0, medio_ancho=3)
            vec.append(energia_rosca(v2, banda_px=banda)[0])
        return e - max(vec), per

    cand = []
    for yp in range(yp0, yp1 + 1, 4):
        for ang in np.arange(ANG_MIN, ANG_MAX + 0.01, 2.0):
            e, per = puntaje(yp, ang)
            if e >= ENERGIA_MIN_VARILLA:
                cand.append((e, yp, ang, per))
    if not cand:
        return None
    cand.sort(key=lambda c: -c[0])

    # Criterio de seleccion: no gana la recta con el pico espectral mas alto,
    # sino la que sostiene rosca a lo LARGO. Una veta del piso o un borde de
    # la maquina pueden dar un pico alto en un tramo corto; solo la varilla
    # mantiene la textura periodica durante 150 px o mas seguidos. Esto es lo
    # que evita que el algoritmo confunda la madera del piso con la barra.
    vistos, mejores = set(), []
    for e, yp, ang, per in cand:
        clave = (yp // 8, round(ang / 4))
        if clave in vistos:
            continue
        vistos.add(clave)
        mejores.append((e, yp, ang, per))
        if len(mejores) >= 14:
            break

    evaluadas = []
    for e, yp, ang, per in mejores:
        p0, u = recta(yp, ang)
        a, b = extension_varilla(gris, dict(p0=p0, u=u), banda)
        if a is None:
            continue
        neto, _ = puntaje(yp, ang, neto=True)
        if neto <= 0.8:                      # no se despega de su entorno: es veta ancha
            continue
        evaluadas.append((b - a, e, yp, ang, per))
    if not evaluadas:
        return None
    evaluadas.sort(key=lambda z: (-round(z[0] / 30), -z[1]))   # largo primero, energia despues
    largo, e, yp, ang, per = evaluadas[0]
    if largo < 110:
        return None

    # afinado fino, en dos pasadas, la segunda restringida al tramo donde de
    # verdad hay rosca (si no, la FFT se diluye con el piso y la maquina y la
    # inclinacion sale sesgada).
    t0, t1 = 0.0, float(x1 - x0)
    for pasada, (ra, pa, ry) in enumerate(((3.0, 0.5, 6), (1.0, 0.25, 3))):
        mejor = (-1, yp, ang, per)
        for da in np.arange(-ra, ra + 1e-9, pa):
            # acotado al mismo rango que el barrido grueso: antes no lo estaba
            # y por eso aparecian angulos fuera de los limites declarados
            if not (ANG_MIN - 1.0 <= ang + da <= ANG_MAX + 1.0):
                continue
            for dy in range(-ry, ry + 1, 2):
                p0, u = recta(yp + dy, ang + da)
                _, val = perfil(gris, p0, u, t0, t1, paso=1.0, medio_ancho=2)
                ee, pp = energia_rosca(val, banda_px=banda)
                if ee > mejor[0]:
                    mejor = (ee, yp + dy, ang + da, pp)
        e, yp, ang, per = mejor
        if pasada == 0:
            p0, u = recta(yp, ang)
            a, b = extension_varilla(gris, dict(p0=p0, u=u), banda)
            if a is not None and (b - a) > 90:
                t0, t1 = max(0.0, a - 10), min(float(x1 - x0), b + 10)

    p0, u = recta(yp, ang)
    eje = dict(p0=p0, u=u, energia=e, periodo=per, inclinacion=ang,
               y_pivote=yp, banda=banda)
    # el seguimiento de cresta se aplica varias veces: cada pasada acerca el
    # corredor a la varilla real, y la siguiente lo ve mejor. Converge en 2 o 3.
    for _ in range(4):
        a, b = extension_varilla(gris, eje, banda)
        if a is None or (b - a) <= 100:
            break
        prev = eje["inclinacion"]
        eje = afinar_por_cresta(gris, eje, a, b, banda, ANG_MIN, ANG_MAX)
        if abs(eje["inclinacion"] - prev) < 0.25:
            break
    return eje


def tramos_de_rosca(gris, eje, banda_px=None):
    """Todos los tramos del eje donde hay textura de rosca, como lista de
    (t_inicio, t_fin). La pesa parte la barra en dos, asi que casi siempre hay
    mas de uno, y tomarlos todos es lo que permite encontrar la punta libre."""
    x0, x1 = BANDA["x0"], BANDA["x1"]
    ventana, paso = 60.0, 10.0
    marcas = []
    t = 0.0
    while t + ventana <= (x1 - x0):
        _, val = perfil(gris, eje["p0"], eje["u"], t, t + ventana, paso=1.0, medio_ancho=3)
        e, _ = energia_rosca(val, banda_px=banda_px)
        marcas.append((t + ventana / 2, e))
        t += paso
    buenos = [t for t, e in marcas if e >= 3.2]
    if not buenos:
        return []
    grupos, act = [], [buenos[0]]
    for a, b in zip(buenos, buenos[1:]):
        if b - a <= paso * 1.6:
            act.append(b)
        else:
            grupos.append(act); act = [b]
    grupos.append(act)
    return [(g[0] - ventana / 2, g[-1] + ventana / 2) for g in grupos]


def punta_libre(tramos, t_pesa, t_pivote, hueco_max=62.0, largo_max=385.0):
    """Donde termina fisicamente la barra, del lado libre.

    Este era el agujero que se comia 64 de las 77 lecturas descartadas: cuando
    falta la ficha verde, se tomaba como origen el arranque del tramo de rosca
    MAS LARGO. Pero la pesa tapa la rosca, asi que el tramo mas largo suele
    arrancar justo despues de la pesa — origen y pesa quedaban pegados y la
    distancia daba 20 px.

    Lo correcto es caminar hacia atras desde la pesa, encadenando tramos de
    rosca separados por huecos chicos (los que deja la propia pesa), y parar
    cuando el hueco es grande (ahi ya no es la barra) o cuando la barra
    quedaria mas larga de lo fisicamente posible."""
    if not tramos:
        return None
    previos = [tr for tr in tramos if tr[0] <= t_pesa + 10]
    if not previos:
        return None
    origen = previos[-1][0]
    for a, b in reversed(previos[:-1]):
        if origen - b > hueco_max:
            break
        if t_pivote is not None and (t_pivote - a) > largo_max:
            break
        origen = a
    return origen


def extension_varilla(gris, eje, banda_px=None, todos=False):
    """Recorre el eje y devuelve donde hay rosca de verdad.

    todos=False -> (t_inicio, t_fin) del tramo contiguo mas largo.
    todos=True  -> (t_primero, t_ultimo) abarcando TODOS los tramos con rosca.

    La distincion importa y fue un error de diseño no tenerla: la pesa TAPA la
    rosca, asi que parte la barra en dos tramos. Usando solo el tramo contiguo
    mas largo, el ajuste del angulo se hacia sobre media barra — y con una base
    corta, el angulo sale ruidoso. Medido: con menos de 200 px de barra el
    angulo salta 3,1° entre fotos consecutivas; con mas de 280 px, 1,0°.
    Para medir el angulo hay que usar la barra entera, saltando el hueco."""
    x0, x1 = BANDA["x0"], BANDA["x1"]
    ventana, paso = 60.0, 10.0
    marcas = []
    t = 0.0
    while t + ventana <= (x1 - x0):
        _, val = perfil(gris, eje["p0"], eje["u"], t, t + ventana, paso=1.0, medio_ancho=3)
        e, _ = energia_rosca(val, banda_px=banda_px)
        marcas.append((t + ventana / 2, e))
        t += paso
    buenos = [t for t, e in marcas if e >= 3.2]
    if not buenos:
        return None, None
    tramos, act = [], [buenos[0]]
    for a, b in zip(buenos, buenos[1:]):
        if b - a <= paso * 1.6:
            act.append(b)
        else:
            tramos.append(act); act = [b]
    tramos.append(act)
    if not todos:
        mejor = max(tramos, key=len)
        return mejor[0] - ventana / 2, mejor[-1] + ventana / 2
    # solo tramos con cuerpo, para que una veta suelta no infle la base
    largos = [tr for tr in tramos if (tr[-1] - tr[0]) >= 40]
    if not largos:
        largos = [max(tramos, key=len)]
    return largos[0][0] - ventana / 2, largos[-1][-1] + ventana / 2


def detectar_anclas(wb):
    """Las 3 chapitas magenta del borde del chute. Solo control de calidad del
    registro: no intervienen en ninguna medicion. Se buscan en una ventana
    chica porque el piso de madera vira a magenta en las fotos con tinte
    violeta y generaria decenas de falsos positivos."""
    lab = cv2.cvtColor(wb, cv2.COLOR_BGR2LAB).astype(np.int16)
    L, A, B = lab[:, :, 0], lab[:, :, 1] - 128, lab[:, :, 2] - 128
    m = ((A > 26) & (B < 24) & (L > 45)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    c = [b for b in _blobs(m, *ANCLA_AREA)
         if _dentro(b, VENTANA_ANCLAS) and 0.45 < b["w"] / max(b["h"], 1) < 2.2]
    return sorted(c, key=lambda b: b["y"])


# ------------------------------------------------------- angulo de la palanca
# DEFINICION ACORDADA EN PLANTA (25/09) con Latitud:
#   el angulo entre la varilla de adelante ("b") y la linea que baja desde
#   donde termina la varilla (la perilla roja) hasta la ficha magenta de arriba.
#
#            tapon verde ●━━━━━━━━━━━━━━━━━━━● perilla (vertice)
#                                           ╱
#                                          ●  ficha magenta de arriba
#
# Es la misma definicion que usa Nexlab (verificado: sobre 240 fotos la
# diferencia mediana es 0,0 grados).
#
# Por que es mejor que la inclinacion contra la horizontal de la foto: las dos
# rectas se miden en la MISMA foto, sobre piezas de la maquina. Si la camara
# se gira, giran las dos y el angulo no cambia. Ya no depende de la camara.
#
# Los tres puntos:
#   - punta de la varilla: sobre el centro de la barra, a la altura del tapon
#     verde (ver angulo_palanca)
#   - perilla: mancha roja en el extremo de la varilla. No se mueve: sobre 240
#     fotos su centro vario 1,6 px en x y 2,8 px en y.
#   - ficha: la de mas arriba de las 3 magenta.
# Si la perilla o la ficha no se encuentran, se usa su posicion de siempre
# (son piezas fijas y la camara se mueve poco) y se baja la confianza.
PERILLA_REF = (903.5, 508.0)
FICHA_REF = (873.6, 627.1)
PERILLA_VENTANA = dict(x0=880, x1=935, y0=460, y1=560)
PERILLA_AREA = (150, 900)
TOL_PIEZA_FIJA = 15.0


def detectar_perilla(wb):
    """Centro de la perilla roja del extremo de la varilla b, o None.

    Si la pesa roja/rosada esta corrida hasta el fondo, su mancha se pega a la
    de la perilla y el centro de la mancha unida no sirve. Pero la perilla es
    siempre lo rojo que esta mas a la DERECHA: se toma su borde derecho y se
    corre medio ancho. Calibrado sobre 192 fotos con la perilla suelta:
    centro = borde derecho - 12,4 px (desvio 0,55 px); y = altura media de la
    mitad derecha + 0,4 px (desvio 0,14 px). En 8 de 200 fotos al azar la
    perilla estaba pegada a la pesa."""
    v = PERILLA_VENTANA
    lab = cv2.cvtColor(wb[v["y0"]:v["y1"], v["x0"]:v["x1"]], cv2.COLOR_BGR2LAB).astype(np.int16)
    m = (((lab[:, :, 1] - 128) > 22) & (lab[:, :, 0] > 40)).astype(np.uint8)
    n, et, st, cen = cv2.connectedComponentsWithStats(m)
    mejor = None
    for i in range(1, n):
        ys, xs = np.where(et == i)
        xs = xs + v["x0"]; ys = ys + v["y0"]
        cerca = (np.abs(xs - PERILLA_REF[0]) < 16) & (np.abs(ys - PERILLA_REF[1]) < 16)
        if cerca.sum() < 30:
            continue
        if mejor is None or st[i, 4] > mejor[0]:
            mejor = (st[i, 4], xs, ys, i)
    if mejor is None:
        return None
    area, xs, ys, i = mejor
    suelta = (PERILLA_AREA[0] <= area <= PERILLA_AREA[1] and st[i, 2] <= 40 and st[i, 3] <= 40)
    if suelta:
        c = (float(cen[i][0]) + v["x0"], float(cen[i][1]) + v["y0"])
    else:
        filas = np.abs(ys - PERILLA_REF[1]) < 14
        if filas.sum() < 20:
            return None
        x_der = float(np.percentile(xs[filas], 98))
        mitad = xs >= x_der - 13
        c = (x_der - 12.4, float(ys[mitad].mean()) + 0.4)
    if math.hypot(c[0] - PERILLA_REF[0], c[1] - PERILLA_REF[1]) > TOL_PIEZA_FIJA:
        return None
    return c


TAPON_B_ZONA = dict(x0=500, x1=720, y0=470, y1=640)   # donde puede estar el tapon de b


def manchas_tapon_b(mv):
    """Centros de las manchas verdes donde puede estar el tapon de la varilla b
    (marco alineado). En 139 de 141 fotos al azar hay exactamente una."""
    z = TAPON_B_ZONA
    sub = (mv[z["y0"]:z["y1"], z["x0"]:z["x1"]] > 0).astype(np.uint8)
    n, _, st, cen = cv2.connectedComponentsWithStats(sub)
    return [(float(cen[i][0]) + z["x0"], float(cen[i][1]) + z["y0"], int(st[i, 4]))
            for i in range(1, n) if st[i, 4] >= 80]


def _a_original(punto, H):
    """Lleva un punto del marco alineado a la foto original."""
    if H is None:
        return (float(punto[0]), float(punto[1]))
    q = cv2.perspectiveTransform(np.array([[punto]], np.float64), np.linalg.inv(np.array(H)))
    return (float(q[0, 0, 0]), float(q[0, 0, 1]))


def angulo_palanca(wb_original, mv, med_b, H, color_usable):
    """Angulo acordado (ver arriba), calculado sobre la FOTO ORIGINAL, no la
    alineada.

    Por que: el angulo entre dos rectas de la misma foto no cambia si la camara
    se mueve o gira, asi que no necesita alineacion. Y si la alineacion sale
    mal (pasa: hay fotos donde acepta una correccion de 60-80 px que no existe)
    deformaria el angulo. Entonces: la punta de la varilla se encuentra en la
    foto alineada (ahi esta la busqueda de la rosca) y se devuelve a la foto
    original deshaciendo la alineacion; la perilla y la ficha se buscan
    directamente en la original. La camara real se mueve poco (99 % de las
    fotos a menos de 9 px de la referencia), asi que las ventanas de busqueda
    fijas alcanzan.

    Devuelve angulo_grados = None si la varilla b no se encontro."""
    r = dict(angulo_grados=None, confianza=0.0, tapon=None, perilla=None, ficha=None,
             notas=[])
    if med_b.get("origen") is None:
        r["notas"].append("no se encontro la varilla de adelante")
        return r
    conf = 1.0

    # punta de la varilla, sobre el centro de la barra. Orden de preferencia:
    #  1. punto del eje en el tapon, corregido de costado mirando la rosca
    #  2. centro de la mancha verde del tapon
    #  3. punto del eje sin corregir
    #
    # Control: la punta tiene que caer SOBRE el tapon verde. Normalmente queda
    # a ~15 px del centro de la mancha verde (es el borde interno del tapon;
    # maximo visto 18 px en 141 fotos). Si queda a mas de 30 px, la busqueda
    # por rosca se equivoco de recta y se usa la mancha verde.
    manchas = manchas_tapon_b(mv) if color_usable else []
    tapon = tuple(med_b["punta_centrada"]) if med_b.get("punta_centrada") else None
    sin_corregir = tapon is None
    if tapon is None:
        tapon = tuple(med_b["origen"])
    if manchas:
        cerca = min(manchas, key=lambda m: math.hypot(m[0] - tapon[0], m[1] - tapon[1]))
        if math.hypot(cerca[0] - tapon[0], cerca[1] - tapon[1]) > 30:
            m = max(manchas, key=lambda m: m[2])
            tapon = (m[0], m[1]); conf *= 0.75; sin_corregir = False
            r["notas"].append("la rosca dio una punta fuera del tapon: se usa el centro del tapon verde")
        elif sin_corregir:
            tapon = (cerca[0], cerca[1]); conf *= 0.85; sin_corregir = False
            r["notas"].append("punta tomada del centro del tapon verde")
    if sin_corregir:
        conf *= 0.6
        r["notas"].append("punta tomada sobre el eje de la rosca, sin tapon verde para controlar")
    tapon = _a_original(tapon, H)

    # Control de la alineacion: la camara real se mueve pocos pixeles, asi que
    # en la foto original la punta tiene que seguir cayendo en la zona del
    # tapon. Si deshacer la alineacion la manda lejos, la alineacion estaba
    # mal: se busca el tapon verde directamente en la foto original.
    z = TAPON_B_ZONA
    if not (z["x0"] - 60 <= tapon[0] <= z["x1"] + 60 and z["y0"] - 60 <= tapon[1] <= z["y1"] + 60):
        mv0, _ = mascaras_color(wb_original)
        m0 = manchas_tapon_b(mv0) if color_usable else []
        if not m0:
            r["notas"].append("alineacion dudosa y sin tapon verde visible: no se mide el angulo")
            return r
        m = max(m0, key=lambda m: m[2])
        tapon = (m[0], m[1]); conf = min(conf, 0.6)
        r["notas"].append("alineacion dudosa: tapon buscado directo en la foto original")

    perilla = detectar_perilla(wb_original) if color_usable else None
    if perilla is None:
        perilla = _a_original(PERILLA_REF, H); conf *= 0.8
        r["notas"].append("perilla no detectada: se usa su posicion fija")

    ficha = None
    anclas = detectar_anclas(wb_original) if color_usable else []
    if anclas:
        a = anclas[0]
        if math.hypot(a["x"] - FICHA_REF[0], a["y"] - FICHA_REF[1]) <= TOL_PIEZA_FIJA:
            ficha = (float(a["x"]), float(a["y"]))
    if ficha is None:
        ficha = _a_original(FICHA_REF, H); conf *= 0.9
        r["notas"].append("ficha magenta de arriba no detectada: se usa su posicion fija")

    if not color_usable:
        # sin color no se puede confirmar ninguno de los tres puntos: la punta
        # sale solo de la rosca y perilla/ficha de su posicion de siempre
        conf = min(conf, 0.5)
        r["notas"].append("color roto: ningun punto se pudo confirmar")

    v1 = np.array(tapon) - np.array(perilla)
    v2 = np.array(ficha) - np.array(perilla)
    c = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    r["angulo_grados"] = round(math.degrees(math.acos(max(-1.0, min(1.0, c)))), 2)
    r["confianza"] = round(conf, 3)
    r["tapon"] = [round(tapon[0], 1), round(tapon[1], 1)]
    r["perilla"] = [round(perilla[0], 1), round(perilla[1], 1)]
    r["ficha"] = [round(ficha[0], 1), round(ficha[1], 1)]
    return r


def cobertura_sobre_eje(mask, eje, t0, t1, medio_ancho=28, paso=1.0, mejor_mitad=False):
    """Para cada punto a lo largo de la varilla, que fraccion de la franja
    transversal esta encendida en la mascara.

    Este es el cambio que hace robusta la deteccion de la pesa: en vez de
    buscar "manchas de color" sueltas y despues preguntarse si caen sobre la
    varilla, se mira directamente EL CORREDOR DE LA VARILLA. Asi no importa
    que la barra brillante parta la mancha en dos, ni que la maquina tape
    media pesa: lo que se mide es cuanto color hay pegado a la varilla en
    cada posicion."""
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    ts = np.arange(t0, t1, paso)
    if len(ts) < 5:
        return ts, np.zeros(len(ts), np.float32)
    base = eje["p0"][None, :] + ts[:, None] * u[None, :]
    H, W = mask.shape
    lados = {}
    for lado, rango in (("sup", range(-medio_ancho, 1)), ("inf", range(0, medio_ancho + 1))):
        acc = np.zeros(len(ts), np.float32); cnt = np.zeros(len(ts), np.float32)
        for o in rango:
            q = base + nrm[None, :] * o
            x = np.round(q[:, 0]).astype(int); y = np.round(q[:, 1]).astype(int)
            ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
            acc[ok] += (mask[y[ok], x[ok]] > 0)
            cnt[ok] += 1
        lados[lado] = (acc, cnt)
    if not mejor_mitad:
        acc = lados["sup"][0] + lados["inf"][0]
        cnt = lados["sup"][1] + lados["inf"][1]
        return ts, np.where(cnt > 0, acc / np.maximum(cnt, 1), 0.0)
    # MEJOR MITAD. El borde de la maquina en primer plano tapa por abajo la
    # pesa de la barra de arriba: mirando el corredor entero, la cobertura
    # nunca llega al umbral aunque la mitad visible este perfecta. Tomando la
    # mejor de las dos mitades, media pesa alcanza para ubicarla.
    sup = np.where(lados["sup"][1] > 0, lados["sup"][0] / np.maximum(lados["sup"][1], 1), 0.0)
    inf = np.where(lados["inf"][1] > 0, lados["inf"][0] / np.maximum(lados["inf"][1], 1), 0.0)
    return ts, np.maximum(sup, inf)


def rachas(ts, cov, umbral, largo_min, largo_max):
    """Tramos contiguos donde la cobertura supera el umbral."""
    out, ini = [], None
    for i, (t, c) in enumerate(zip(ts, cov)):
        if c >= umbral and ini is None:
            ini = t
        elif c < umbral and ini is not None:
            if largo_min <= t - ini <= largo_max:
                out.append((ini, t, float(cov[max(0, i - 3)])))
            ini = None
    if ini is not None and largo_min <= ts[-1] - ini <= largo_max:
        out.append((ini, float(ts[-1]), float(cov[-1])))
    return out


def brillo_relativo(wb):
    """Brillo de cada pixel medido contra el blanco de la maquina: la misma
    referencia interna que usa mascaras_color, asi una foto de las 3 de la
    manana y una del mediodia quedan en la misma escala."""
    Vv = cv2.cvtColor(wb, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32)
    blanco = max(float(np.percentile(Vv[PARCHE_BLANCO], 75)), 40.0)
    return Vv / blanco


def brillo_en_el_tramo(rel, eje, t_a, t_b, medio_ancho=8):
    """Brillo tipico (relativo al blanco de la maquina) del objeto que esta
    sobre la barra entre t_a y t_b. Sirve para distinguir un objeto solido y
    claro de un fondo oscuro que pasa por detras."""
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    H, W = rel.shape
    vals = []
    for t in np.arange(t_a, t_b + 0.1, 2.0):
        base = eje["p0"] + u * t
        for o in np.arange(-medio_ancho, medio_ancho + 0.1, 2.0):
            q = base + nrm * o
            x = int(round(q[0])); y = int(round(q[1]))
            if 0 <= x < W and 0 <= y < H:
                vals.append(rel[y, x])
    return float(np.median(vals)) if vals else 0.0


def _ancho_claro(rel, eje, t, offs):
    """Cuantos px de ancho tiene el objeto claro montado sobre la barra en la
    posicion t: se camina hacia los dos lados desde el eje mientras siga
    claro."""
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    base = eje["p0"] + u * t
    H, W = rel.shape
    col = np.empty(len(offs), np.float32)
    for i, o in enumerate(offs):
        q = base + nrm * o
        x = int(round(q[0])); y = int(round(q[1]))
        col[i] = rel[y, x] if (0 <= x < W and 0 <= y < H) else 0.0
    c = len(offs) // 2
    i = c
    while i > 0 and col[i - 1] > ANCHO_CLARO_REL:
        i -= 1
    j = c
    while j < len(offs) - 1 and col[j + 1] > ANCHO_CLARO_REL:
        j += 1
    return float(offs[j] - offs[i])


def pesa_en_el_extremo(rel, eje, t_pivote):
    """Busca una pesa montada contra la maquina, midiendo el ANCHO del objeto
    que hay sobre la barra. Ver el comentario de ANCHO_EXTRA_MIN.

    Devuelve (t_a, t_b) del bulto, o None."""
    offs = np.arange(-40, 41, 1.0)
    # ancho de la barra desnuda, en esta misma foto, lejos de la maquina
    ref = [_ancho_claro(rel, eje, t, offs)
           for t in np.arange(t_pivote - 150, t_pivote - 75, 6.0)]
    ancho_barra = float(np.median(ref)) if ref else 12.0
    umbral = ancho_barra + ANCHO_EXTRA_MIN

    ts = np.arange(t_pivote - 75, t_pivote + 13, 4.0)
    an = np.array([_ancho_claro(rel, eje, t, offs) for t in ts])
    gordo = an >= umbral
    if not gordo.any():
        return None
    # una pesa se TERMINA; la maquina no. Si todavia esta ancho pasando el
    # pivote, lo que se ve es la maquina, no una pesa.
    if gordo[-1]:
        return None
    tramos, i0 = [], None
    for i, g in enumerate(gordo):
        if g and i0 is None:
            i0 = i
        elif not g and i0 is not None:
            tramos.append((i0, i)); i0 = None
    tramos = [(a, b) for a, b in tramos if ts[b - 1] - ts[a] >= ANCHO_LARGO_MIN]
    if not tramos:
        return None
    a, b = max(tramos, key=lambda z: ts[z[1] - 1] - ts[z[0]])
    return float(ts[a]), float(ts[b - 1])


def mascaras_color(wb, fondo_fijo=None):
    """Mascaras de los dos colores que importan, sobre la imagen balanceada.

    El brillo se mide RELATIVO al blanco de la maquina, no en valor absoluto:
    de noche la escena entera baja y un umbral fijo dejaria de encontrar las
    pesas. Con la referencia interna, una foto de las 3 de la manana y una
    del mediodia usan el mismo criterio.

    fondo_fijo: mascara de objetos saturados que estan SIEMPRE en el mismo
    lugar del marco alineado (la chapa naranja del piso, la perilla roja del
    extremo de la varilla). Como no se mueven nunca, no pueden ser pesas."""
    hsv = cv2.cvtColor(wb, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(wb, cv2.COLOR_BGR2LAB).astype(np.int16)
    S = hsv[:, :, 1].astype(np.float32); Vv = hsv[:, :, 2].astype(np.float32)
    L, A, B = lab[:, :, 0], lab[:, :, 1] - 128, lab[:, :, 2] - 128
    blanco = max(float(np.percentile(Vv[PARCHE_BLANCO], 75)), 40.0)
    rel = Vv / blanco

    verde = (A < VERDE["a_max"]) & (B > VERDE["b_min"]) & (rel > 0.40)

    semilla = (S > PESA_S_MIN) & (rel > PESA_BRILLO_REL) & (~verde)
    if fondo_fijo is not None:
        semilla = semilla & (fondo_fijo == 0)
    k = np.ones((3, 3), np.uint8)
    semilla = cv2.morphologyEx(semilla.astype(np.uint8) * 255, cv2.MORPH_OPEN, k)

    # completar la pesa hacia su parte en sombra, pero solo cerca de una
    # semilla: asi el piso de madera, que no siembra en ningun lado, no entra
    # Tercer nivel: el BRILLO ESPECULAR de la pesa. Una pesa de plastico
    # brillante tiene un reflejo que quema el sensor: ahi el pixel pierde el
    # color (saturacion baja) y los dos umbrales de arriba lo dejan afuera.
    # Justo por ese reflejo suele pasar la barra, asi que la mascara quedaba
    # sin la parte que importa para verificar que la pesa esta ensartada.
    # Medido: agregando los pixeles quemados pegados a una semilla, las pesas
    # reales pasan de tapar 0,01-0,52 de la barra a tapar 0,66-0,94, y lo que
    # no es pesa sube apenas de 0,00 a 0,13-0,21.
    laxo = (((S > PESA_S_LAXO) & (rel > PESA_BRILLO_LAXO) | (rel > PESA_BRILLO_QUEMADO))
            & (~verde)).astype(np.uint8) * 255
    cerca = cv2.dilate(semilla, np.ones((CRECIMIENTO_PESA, CRECIMIENTO_PESA), np.uint8))
    pesa = cv2.bitwise_or(semilla, cv2.bitwise_and(laxo, cerca))
    if fondo_fijo is not None:
        pesa = cv2.bitwise_and(pesa, (fondo_fijo == 0).astype(np.uint8) * 255)

    mv = cv2.morphologyEx(verde.astype(np.uint8) * 255, cv2.MORPH_OPEN, k)
    mp = cv2.morphologyEx(pesa, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mv, mp


def tono_en_tramo(wb, mask, eje, t_a, t_b, medio_ancho=20):
    """Tono medio de los pixeles encendidos dentro de un tramo del corredor."""
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    ts = np.arange(t_a, t_b, 1.0)
    hs = []
    hsv = cv2.cvtColor(wb, cv2.COLOR_BGR2HSV)
    H, W = mask.shape
    for o in range(-medio_ancho, medio_ancho + 1):
        q = eje["p0"][None, :] + ts[:, None] * u[None, :] + nrm[None, :] * o
        x = np.round(q[:, 0]).astype(int); y = np.round(q[:, 1]).astype(int)
        ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        xx, yy = x[ok], y[ok]
        sel = mask[yy, xx] > 0
        if sel.any():
            hs.append(hsv[yy[sel], xx[sel], 0].astype(np.float32))
    if not hs:
        return None
    h = float(np.median(np.concatenate(hs))) * 2
    for lim, nom in ((20, "rojo"), (45, "naranja"), (70, "amarillo"), (160, "verde"),
                     (200, "celeste"), (260, "azul"), (320, "magenta"), (361, "rojo")):
        if h < lim:
            return dict(tono_grados=round(h, 1), nombre=nom)
    return dict(tono_grados=round(h, 1), nombre="?")


def centro_transversal(gris, eje, t0, t1, busca=14.0):
    """Corrimiento transversal (px) de la barra respecto del eje, medido sobre
    la rosca entre t0 y t1: se prueba cada corrimiento y gana el que tiene mas
    textura de rosca. None si no hay rosca que medir."""
    if t1 <= t0:
        return None
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    H, W = gris.shape
    offs = np.arange(-busca, busca + 0.1, 1.0)
    col = []
    for o in offs:
        v = []
        for t in np.arange(t0, t1 + 0.1, 1.0):
            q = eje["p0"] + u * t + nrm * o
            x = int(round(q[0])); y = int(round(q[1]))
            v.append(gris[y, x] if (0 <= x < W and 0 <= y < H) else 0.0)
        v = np.asarray(v, np.float32)
        v = v - cv2.GaussianBlur(v.reshape(-1, 1), (0, 0), 8).ravel()
        col.append(float(np.abs(v).mean()))
    col = np.asarray(col)
    if col.max() <= 0:
        return None
    return float(offs[int(np.argmax(col))])


def offset_de_la_barra(gris, eje, t_a, t_b, margen=22.0, busca=14.0):
    """Donde esta la barra, transversalmente, a la altura del objeto.

    El eje que devuelve buscar_varilla() queda a veces corrido unos pixeles y
    pasa por el borde de la barra en vez de por su centro (es el problema del
    eje lateral, conocido y medido). Aca se mide la posicion REAL de la barra
    mirando justo AFUERA del objeto, a los dos lados, donde la rosca se ve, y
    se promedia. Encima del objeto no se puede medir: la pesa tapa la rosca,
    que es justamente la senal.
    """
    vals = [x for x in (centro_transversal(gris, eje, t_a - margen - 18, t_a - margen, busca),
                        centro_transversal(gris, eje, t_b + margen, t_b + margen + 18, busca))
            if x is not None]
    return float(np.mean(vals)) if vals else 0.0


def cubre_la_barra(mask, eje, t_a, t_b, centro=0.0, medio_ancho=4.0):
    """Que fraccion de LA BARRA MISMA, entre t_a y t_b, esta tapada por el
    objeto.

    Este es el discriminador que decide si un objeto es una pesa. Una pesa
    esta ENSARTADA en la barra: la tapa, asi que los pixeles de la barra son
    superficie de la pesa y entran en su mascara de color. Un objeto que esta
    DETRAS o AL COSTADO (la chapa naranja del piso, el carton, el cano azul)
    deja ver la barra, que es metal desnudo y no entra en esa mascara.

    'centro' es donde esta la barra de verdad, que lo da offset_de_la_barra().
    Sin esa correccion el test se rompe: con el eje corrido 5 px, pesas
    perfectamente visibles daban 5-18 % y se rechazaban; y al ensanchar la
    banda para compensar, se colaba el carton del piso que esta justo al lado
    de la barra.

    Medido sobre 17 candidatos etiquetados a ojo, uno por uno, a resolucion
    util, con la barra localizada:
        pesas de verdad          0,17 a 0,88
        carton, chapa, cano      0,00 en LOS 7 casos
    No se pisan.

    Reemplaza a tapa_la_rosca(), que medía si el objeto apagaba la textura de
    la rosca. Sobre el mismo conjunto ese test daba 0,29-0,87 en las pesas y
    0,21-0,87 en lo que no lo era: NO SEPARABA NADA. Tenia falsos positivos
    con confianza 1,0 (la chapa del piso) y falsos negativos (pesas rosas
    perfectamente visibles rechazadas).
    """
    u = eje["u"]; nrm = np.array([-u[1], u[0]])
    H, W = mask.shape
    v = []
    for t in np.arange(t_a, t_b + 0.1, 1.0):
        base = eje["p0"] + u * t
        for o in np.arange(centro - medio_ancho, centro + medio_ancho + 0.1, 1.0):
            q = base + nrm * o
            x = int(round(q[0])); y = int(round(q[1]))
            if 0 <= x < W and 0 <= y < H:
                v.append(1.0 if mask[y, x] > 0 else 0.0)
    return float(np.mean(v)) if v else 0.0


def tapa_la_rosca(gris, eje, t_centro, banda_px=None, umbral=0.80):
    """¿Este objeto TAPA la barra, o esta detras de ella?

    Una pesa es un cilindro ensartado en la barra: donde esta la pesa, la
    rosca deja de verse. Una chapa apoyada en el piso, por mas que en la foto
    quede justo atras de la barra, no la tapa — la rosca se sigue viendo
    entera por encima.

    Esto hacia falta: la chapa naranja del piso se estaba tomando como pesa,
    con confianza 1.0. Yo la habia dado por 'decorado fijo', pero es una chapa
    suelta que se mueve, asi que la mascara de fondo no la cubria siempre.

    Medido: sobre una pesa real la rosca cae al 0.26-0.68 de lo que vale al
    lado; sobre la chapa del piso queda en 0.96."""
    def energia(t0):
        _, val = perfil(gris, eje["p0"], eje["u"], t0 - 20, t0 + 20, paso=1.0, medio_ancho=3)
        return energia_rosca(val, banda_px=banda_px)[0]
    # Se miran TRES ventanas: sobre el objeto y a cada lado. Lo que define a
    # una pesa es que la rosca se apague en ALGUNA de ellas — encima si la
    # pesa esta en el medio de la barra, o del lado de adentro si la pesa esta
    # al final. Comparar solo "encima contra el maximo de los lados" descartaba
    # las pesas que estan pegadas a la maquina, que son muchas.
    e = [energia(t_centro), energia(t_centro - 55), energia(t_centro + 55)]
    alto = max(e)
    if alto < 3.0:
        return True, None        # sin rosca creible alrededor, no se puede juzgar
    ratio = min(e) / alto
    return ratio <= umbral, round(ratio, 2)


def hueco_en_la_rosca(gris, eje, t_ini, t_fin, banda_px=None):
    """Busca el tramo de la barra donde la rosca se apaga: ahi esta la pesa,
    que la tapa. Devuelve (t_a, t_b) o None.

    Es el camino que no mira un solo pixel de color, y el unico que sirve
    cuando la camara falla el color y saca la foto entera violeta.

    Se busca una caida RELATIVA, no un umbral absoluto. La ventana de analisis
    mide 40 px y la pesa unos 45, asi que la ventana siempre pisa un poco de
    rosca a los costados y la energia nunca llega a cero: con un umbral fijo
    la pesa no se detectaba. Lo que si se ve, y es lo que mira el ojo, es que
    la energia CAE respecto del resto de la barra."""
    banda_px = banda_px or eje.get("banda")
    ventana, paso = 40.0, 4.0
    ts, en = [], []
    t = t_ini
    while t + ventana <= t_fin:
        _, val = perfil(gris, eje["p0"], eje["u"], t, t + ventana, paso=1.0, medio_ancho=3)
        e, _ = energia_rosca(val, banda_px=banda_px)
        ts.append(t + ventana / 2); en.append(e)
        t += paso
    if len(en) < 8:
        return None
    en = np.array(en, np.float32); ts = np.array(ts)
    referencia = float(np.percentile(en, 80))
    if referencia < 3.0:
        return None                      # no hay rosca creible en ningun lado
    bajo = en < 0.62 * referencia

    tramos, i0 = [], None
    for i, b in enumerate(bajo):
        if b and i0 is None:
            i0 = i
        elif not b and i0 is not None:
            tramos.append((i0, i)); i0 = None
    if i0 is not None:
        tramos.append((i0, len(bajo)))
    tramos = [(a, b) for a, b in tramos if 18 <= (ts[b - 1] - ts[a]) <= 140]
    if not tramos:
        return None
    # el hueco mas profundo, no el mas largo: una pesa apaga la rosca de verdad
    a, b = min(tramos, key=lambda z: float(en[z[0]:z[1]].mean()))
    return float(ts[a]), float(ts[b - 1])


# --------------------------------------------------------- medicion por varilla

def medir_varilla(gris, wb, mv, mp, eje, nombre, color_usable=True, rel=None):
    """Mide UNA varilla. Nunca mira a la otra: ese aislamiento es el punto.

    Cascada, de mejor a peor:
      1. eje por rosca + ficha verde sobre el corredor -> origen = ficha  (1.00)
      2. eje por rosca, sin ficha verde -> origen = fin fisico de la rosca (0.70)
      3. sin eje creible -> falla SOLO esta varilla, la otra sigue midiendo
    """
    r = dict(varilla=nombre, metodo=None, distancia_px=None, distancia_pasos=None,
             distancia_mm=None,
             paso_rosca_px=None, inclinacion_grados=None, energia_rosca=None,
             ficha_verde=None, pesa=None, origen=None, tramo_rosca_px=None,
             estado=None, notas=[])

    if eje is None:
        r["metodo"] = "sin_varilla"
        r["estado"] = "varilla_no_encontrada"
        r["notas"].append("no se encontro una recta con textura de rosca creible")
        return r

    r["energia_rosca"] = round(float(eje["energia"]), 2)
    # el paso QUE SE USA para medir se decide al final (ver paso_de_rosca);
    # aca solo se guarda el que salio de la FFT de esta foto, como diagnostico
    r["paso_medido_px"] = round(eje["periodo"], 2) if eje["periodo"] else None
    # inclinacion contra la horizontal del marco alineado; positiva = la punta
    # libre cae. Es la magnitud fisica que interesa: la varilla flexiona con
    # la carga, y eso hay que leerlo de la geometria de la varilla, nunca de
    # donde quedo la pesa.
    r["inclinacion_grados"] = round(-eje["inclinacion"], 3)

    tramos = tramos_de_rosca(gris, eje, eje.get("banda"))
    t_pivote = (X_PIVOTE - eje["p0"][0]) / eje["u"][0]
    t_ini, t_fin = extension_varilla(gris, eje, eje.get("banda"))
    if t_ini is None:
        r["metodo"] = "sin_varilla"
        r["estado"] = "varilla_no_encontrada"
        r["notas"].append("la recta no sostiene rosca en ningun tramo")
        return r
    r["tramo_rosca_px"] = [round(t_ini, 1), round(t_fin, 1)]

    # La ventana hacia la punta libre es generosa a proposito. El tapon verde
    # esta SIEMPRE un poco antes de donde arranca la rosca (el tapon tapa la
    # punta de la barra, asi que ahi no hay rosca que detectar). Pero cuanto
    # arranca la rosca depende de la luz: de dia, con mas contraste quemado, el
    # tramo detectado empieza 50-80 px mas adentro, y con una ventana corta el
    # tapon quedaba afuera. Medido sobre un dia completo: de noche se detectaba
    # el tapon y de dia no, con el tapon en la misma posicion en las dos.
    ta = max(0.0, t_ini - 150)
    tb = min(float(BANDA["x1"] - BANDA["x0"]), t_fin + 70)

    # --- ficha verde sobre el corredor -------------------------------------
    if color_usable:
        # mejor_mitad, por el mismo motivo que en la pesa: el eje se ajusta
        # sobre la rosca, que puede arrancar 150 px adentro, y extrapolar hasta
        # el tapon amplifica cualquier error de angulo. Si el corredor queda
        # corrido, el tapon igual cubre una de las dos mitades.
        ts, cov_v = cobertura_sobre_eje(mv, eje, ta, tb, medio_ancho=20, mejor_mitad=True)
        cand_f = rachas(ts, cov_v, 0.30, 12, 90)
        # El tapon es el verde que esta pegado al arranque de la rosca, no el
        # verde que este mas a la izquierda: con la ventana ancha, tomar el mas
        # a la izquierda podria agarrar cualquier cosa verde del fondo.
        antes = [c for c in cand_f if (c[0] + c[1]) / 2 <= t_ini + 25]
        ficha = (max(antes, key=lambda z: (z[0] + z[1]) / 2) if antes
                 else (min(cand_f, key=lambda z: z[0]) if cand_f else None))
    else:
        ficha = None
        r["notas"].append("color inutilizable en esta foto: no se busco la ficha verde")

    # --- pesa sobre el corredor --------------------------------------------
    ts2, cov_p = (cobertura_sobre_eje(mp, eje, ta, tb, medio_ancho=18, mejor_mitad=True)
                  if color_usable else (np.array([]), np.array([])))
    # La ventana de aceptacion se estira hacia el final de la varilla porque
    # la pesa TAPA la rosca: muchas veces el tramo con textura termina
    # justamente donde empieza la pesa.
    cand_p = [] if not color_usable else [c for c in rachas(ts2, cov_p, 0.30, 14, 130)
              if t_ini - 30 <= (c[0] + c[1]) / 2 <= t_fin + 70]
    # Descartar la PERILLA del extremo. Cada barra termina, del lado de la
    # maquina, en una perilla roja que no es una pesa. Discriminador fisico:
    # una pesa es un cilindro ensartado en la barra, asi que TAPA la rosca; la
    # perilla esta pasando el final de la rosca. Entonces, si la barra muestra
    # rosca continua a lo largo de mas de 300 px (o sea que no hay nada montado
    # encima) y el unico candidato cae mas alla de ese final, ese candidato es
    # la perilla. Sin esto se informaban distancias de barras peladas.
    # La guarda correcta es POSICIONAL: la perilla esta donde la barra entra a
    # la maquina, o sea en el pivote; una pesa esta siempre antes. Medido:
    #     perillas   t - t_pivote = +29, +38, +49
    #     pesas      t - t_pivote = -16, -34, -45 ...
    # La guarda anterior comparaba contra el final del tramo con rosca, y eso
    # mataba las pesas montadas contra la maquina: la rosca se termina donde
    # empieza la pesa, asi que una pesa al final queda siempre "pasando el
    # final". Se perdia un dia entero de la barra b cada vez que la montaban
    # ahi.
    cand_p = [c for c in cand_p if (c[0] + c[1]) / 2 <= t_pivote - 5]
    # Solo sobrevive lo que TAPA LA BARRA (ver cubre_la_barra)
    verificadas = []
    for c in cand_p:
        d_barra = offset_de_la_barra(gris, eje, c[0], c[1])
        cubre = cubre_la_barra(mp, eje, c[0], c[1], centro=d_barra)
        if cubre >= CUBRE_MIN:
            verificadas.append(c)
        else:
            r["notas"].append(f"descartado un objeto a t={int((c[0]+c[1])/2)}: tapa solo el "
                              f"{cubre*100:.0f} % de la barra, esta detras o al costado, "
                              "no ensartado en ella")
    cand_p = verificadas
    pesa = max(cand_p, key=lambda z: (z[1] - z[0])) if cand_p else None

    # --- pesa sin pintar montada contra la maquina (ver ANCHO_EXTRA_MIN)
    if not pesa and rel is not None and color_usable:
        # se exige color_usable aunque el metodo no mire color: en las fotos
        # que la camara saca violetas el balance de blancos deforma el brillo
        # y el ancho medido deja de significar nada (verificado: daba una
        # pesa inexistente en la unica foto rota del 12/08).
        ext = pesa_en_el_extremo(rel, eje, t_pivote)
        # Misma guarda que usa el camino de color: el centro de la pesa tiene
        # que caer DENTRO del tramo con rosca, no pasando su final. Sin esto,
        # en la varilla "a" —que termina contra el cuerpo blanco de la
        # maquina— el metodo tomaba la maquina por pesa. Medido: mata 7 de los
        # 9 falsos positivos que aparecieron en la regresion, sin perder
        # ninguna deteccion buena.
        if ext is not None and (ext[0] + ext[1]) / 2 > t_fin - 8:
            ext = None
        if ext is not None:
            pesa = (ext[0], ext[1], 0.0)
            r["metodo_pesa"] = "ancho_en_el_extremo"
            r["notas"].append("pesa sin pintar detectada por su ancho sobre la barra: "
                              "el detector de color no la ve")

    # --- pesa: si el color no la encontro, se busca por el hueco en la rosca
    if not pesa:
        # CAMINO SIN COLOR. La pesa es un cilindro que abraza la barra, asi
        # que donde esta la pesa la rosca deja de verse. Ese hueco ubica la
        # pesa sin mirar un solo pixel de color — que es lo que salva las
        # fotos en las que la camara falla el color y sale todo violeta.
        hueco = hueco_en_la_rosca(gris, eje, t_ini, t_fin)
        # La perilla del extremo no es una pesa: esta justo donde la barra
        # entra a la maquina, y ahi una pesa no puede estar.
        if hueco and (hueco[0] + hueco[1]) / 2 > t_pivote - 20:
            hueco = None
        # Una pesa ensartada parte la rosca en dos: tiene que haber rosca de
        # los DOS lados del hueco. Un "hueco" pegado al arranque de la rosca es
        # solo donde la rosca empieza (el tapon, o el aire si no hay tapon).
        # 40 px = algo mas que el largo del tapon (25-30 px): sin color, el
        # arranque de la rosca puede quedar estimado del lado de afuera del tapon.
        # Visto el 03/10 en una foto violeta (07-04 02:19): el tapon se tomaba
        # por pesa a 20 mm.
        if hueco and hueco[0] < t_ini + 40:
            hueco = None
        # Y el hueco tiene que estar LLENO de algo. Este camino mide AUSENCIA
        # de rosca, nunca comprobaba que hubiera un objeto ahi: cualquier cosa
        # que baje el contraste (el cano azul que cruza por detras, una sombra,
        # la lona, alguien pasando) fabricaba una pesa que no existe. Verificado
        # en 09-11_19-05: varilla pelada, 97 px de "distancia" justo donde cruza
        # el cano. Brillo en el cano 0,53; en una pesa de verdad 1,00. Con el
        # umbral en 0,75 no se pisan.
        if hueco is not None and rel is not None:
            if brillo_en_el_tramo(rel, eje, hueco[0], hueco[1]) < HUECO_BRILLO_MIN:
                r["notas"].append("se descarto un hueco en la rosca a t="
                                  f"{int((hueco[0]+hueco[1])/2)}: no hay nada claro ahi, "
                                  "es fondo oscuro detras de la barra")
                hueco = None
        if hueco:
            pesa = (hueco[0], hueco[1], 0.0)
            r["metodo_pesa"] = "hueco_en_la_rosca"
            r["notas"].append("pesa ubicada por el hueco que deja en la rosca, sin usar color")
    r.setdefault("metodo_pesa", "color" if pesa else None)

    # --- origen de la medicion ---------------------------------------------
    if ficha:
        # ORIGEN = el borde INTERNO del tapon (el lado que toca la rosca), no
        # su centro.
        #
        # Medido sobre 285 pares de fotos consecutivas en las que la maquina no
        # se movio, comparando los tres puntos posibles:
        #   punta libre del tapon : 2,57 mm (barra a) / 0,68 mm (barra b)
        #   centro del tapon      : 2,14 mm / 1,02 mm   <- lo que se usaba
        #   borde interno         : 1,71 mm / 0,68 mm   <- gana en las dos
        # Tiene sentido fisico: es un limite duro entre dos texturas muy
        # distintas (pintura lisa contra rosca), no un borde contra el fondo
        # que se corre con la luz, ni un centroide que se mueve cuando el blob
        # se detecta a medias.
        #
        # Ademas deja consistentes los dos caminos: cuando no hay tapon,
        # punta_libre() ya devuelve el arranque de la rosca, que es ese mismo
        # punto. Antes los dos origenes estaban separados medio tapon.
        #
        # Segun la ficha de Latitud (22 mm del borde del tapon a la primera
        # hendidura, tapon de ~20-23 mm) este punto cae practicamente SOBRE LA
        # PRIMERA HENDIDURA. Para pasar a la convencion de Latitud —que mide
        # desde el borde de afuera del tapon— hay que sumar el largo del tapon.
        t_origen = ficha[1]
        r["largo_tapon_px"] = round(ficha[1] - ficha[0], 1)
        r["metodo"] = "ficha_verde"
        p = eje["p0"] + eje["u"] * t_origen
        r["ficha_verde"] = [round(float(p[0]), 1), round(float(p[1]), 1)]
    else:
        # Sin ficha verde, el origen es la punta libre fisica de la barra, y
        # hay que buscarla del OTRO lado de la pesa. Tomar el arranque del
        # tramo de rosca mas largo — que es lo que se hacia — daba el punto
        # equivocado, porque la pesa corta la rosca y el tramo mas largo
        # arranca justo despues de ella.
        t_ref = (pesa[0] + pesa[1]) / 2 if pesa else t_ini
        t_origen = punta_libre(tramos, t_ref, t_pivote)
        if t_origen is None:
            t_origen = t_ini
        r["metodo"] = "extremo_varilla"
        r["notas"].append("sin ficha verde: el origen se toma en la punta fisica de la barra")
    p_o = eje["p0"] + eje["u"] * t_origen
    r["origen"] = [round(float(p_o[0]), 1), round(float(p_o[1]), 1)]

    # Punta de la barra CENTRADA sobre la barra real, para el angulo. El eje
    # de la rosca a veces queda corrido de costado 10-20 px; se corrige
    # midiendo donde esta la rosca justo al lado del tapon (30 px de rosca
    # libre, sin pesa encima). Si la pesa esta pegada al tapon, no hay rosca
    # que mirar y se deja sin corregir (lo resuelve angulo_palanca).
    r["punta_centrada"] = None
    w0, w1 = t_origen + 4, t_origen + 34
    if pesa and pesa[0] < w1 + 4 and pesa[1] > w0 - 4:
        w1 = min(w1, pesa[0] - 4)
    if w1 - w0 >= 15:
        off = centro_transversal(gris, eje, w0, w1)
        if off is not None and abs(off) < 13:
            u = eje["u"]; nrm = np.array([-u[1], u[0]])
            q = p_o + nrm * off
            r["punta_centrada"] = [round(float(q[0]), 1), round(float(q[1]), 1)]

    if not pesa:
        # "no encontre la pesa" no es lo mismo que "no hay pesa puesta". Si la
        # rosca se ve fuerte y continua de punta a punta, no hay nada montado
        # sobre la barra. Pasa de verdad: hay dias en que trabajan con las
        # barras peladas. Es una lectura correcta, no una falla.
        largo = t_fin - t_ini
        llega_al_final = t_fin >= t_pivote - 60
        if not color_usable:
            r["estado"] = "color_inutilizable"
            r["notas"].append("color de camara roto: no se puede ver la pesa ni afirmar que no este")
        elif largo >= 220 and (eje["energia"] or 0) >= 8 and llega_al_final:
            r["estado"] = "varilla_sin_pesa"
            r["notas"].append("la rosca se ve continua de punta a punta: no hay pesa montada")
        else:
            r["estado"] = "pesa_no_encontrada"
            r["notas"].append("no se detecto pesa sobre esta barra: hay eje e inclinacion, no hay distancia")
        return r

    t_pesa = (pesa[0] + pesa[1]) / 2
    p_p = eje["p0"] + eje["u"] * t_pesa
    r["pesa"] = dict(centro=[round(float(p_p[0]), 1), round(float(p_p[1]), 1)],
                     largo_px=round(pesa[1] - pesa[0], 1),
                     color=(tono_en_tramo(wb, mp, eje, pesa[0], pesa[1])
                            if r["metodo_pesa"] == "color" else None))

    # La pesa esta ensartada en la barra, del lado de la maquina respecto del
    # tapon. No puede estar MAS ALLA de la punta libre: ahi no hay barra.
    # Esto estaba escrito con abs(), asi que una deteccion del lado equivocado
    # daba una distancia positiva y perfectamente creible. Con el origen en el
    # centro del tapon casi no pasaba (1 caso en 2.147); al mover el origen al
    # borde interno aparecieron 3 mas, todos con la "pesa" pegada al tapon por
    # afuera. El signo ahora se comprueba.
    if t_pesa <= t_origen + 2.0:
        r["notas"].append(f"se descarto un objeto a t={int(t_pesa)}: esta del lado de "
                          "afuera del tapon, ahi no hay barra donde ensartar una pesa")
        r["pesa"] = None
        largo = t_fin - t_ini
        if color_usable and largo >= 150 and (eje["energia"] or 0) >= 6 and t_fin >= t_pivote - 60:
            r["estado"] = "varilla_sin_pesa"
        else:
            r["estado"] = "pesa_no_encontrada"
        return r

    dist = t_pesa - t_origen
    d_min = distancia_minima(pesa[1] - pesa[0])
    paso_px, _ = paso_de_rosca(nombre, r["inclinacion_grados"], eje.get("periodo"))
    d_max = min(DIST_MAX, DIST_MAX_MM * paso_px / PASO_MM)
    if not (d_min <= dist <= d_max):
        # AQUI NO SE PUEDE AFIRMAR "no hay pesa montada".
        #
        # Habia una rama que, si la distancia caia fuera de rango y la rosca se
        # veia entera, devolvia varilla_sin_pesa. Es una AFIRMACION, y estaba
        # mal: cuando la pesa esta pegada al tapon, la distancia queda por
        # debajo del minimo y el algoritmo decia "no hay pesa montada" con una
        # pesa celeste enorme a la vista (09-12 15:40, barra b). Encontrar algo
        # y no poder ubicarlo no es lo mismo que no haber encontrado nada:
        # lo primero es una abstencion, lo segundo una lectura.
        r["descartada_por_rango"] = round(dist, 1)
        r["estado"] = "descartada_por_rango"
        r["notas"].append(f"descartada: {dist*PASO_MM/paso_px:.0f} mm esta fuera del rango "
                          f"fisico de la barra ({d_min*PASO_MM/paso_px:.0f}-{DIST_MAX_MM:.0f} mm "
                          f"para una pesa de {pesa[1]-pesa[0]:.0f} px)")
        return r
    r["distancia_px"] = round(dist, 1)
    r["estado"] = "medida"
    paso, uso_medido = paso_de_rosca(nombre, r["inclinacion_grados"], eje.get("periodo"))
    r["paso_rosca_px"] = round(paso, 2)
    r["paso_medido_px"] = round(float(eje["periodo"]), 2) if eje.get("periodo") else None
    r["distancia_pasos"] = round(dist / paso, 2)
    r["distancia_mm"] = round(dist / paso * PASO_MM, 1)
    if uso_medido:
        r["notas"].append(f"el paso de rosca de esta foto ({paso:.1f} px) se aparta del modelo: "
                          f"la geometria del eje esta corrida, se usa el medido")
    return r


def confianza_angulo(med, diag_reg, n_anclas):
    """Confianza del ANGULO, que es independiente de la de la distancia: el
    angulo sale del eje de la barra y no necesita ni la ficha verde ni la
    pesa. Separarlas importa porque son dos variables distintas que Latitud
    necesita, y una puede ser confiable mientras la otra no."""
    if med.get("inclinacion_grados") is None or med["metodo"] == "sin_varilla":
        return 0.0
    if diag_reg["registrado"]:
        f_marco = 1.00 if n_anclas >= 3 else (0.92 if n_anclas >= 1 else 0.85)
    else:
        f_marco = 0.40
    f_eje = float(np.clip((med["energia_rosca"] or 0) / 12.0, 0.40, 1.0))
    # la base del ajuste: un angulo medido sobre 120 px de barra vale menos
    # que uno medido sobre 350
    tr = med.get("tramo_rosca_px")
    largo = (tr[1] - tr[0]) if tr else 0
    f_base = float(np.clip(largo / 300.0, 0.45, 1.0))
    return round(f_marco * f_eje * f_base, 3)


def confianza(med, diag_reg, n_anclas):
    """La confianza no es una formula estadistica inventada: sale de por que
    escalon de la cascada paso la lectura y de que tan sustentado quedo el
    marco geometrico. Es trazable y se explica en una frase."""
    if med["metodo"] in (None, "sin_varilla") or med["distancia_px"] is None:
        return 0.0
    f_origen = {"ficha_verde": 1.00, "extremo_varilla": 0.70}.get(med["metodo"], 0.40)
    if diag_reg["registrado"]:
        f_marco = 1.00 if n_anclas >= 3 else (0.92 if n_anclas >= 1 else 0.85)
    else:
        f_marco = 0.55 if n_anclas >= 3 else 0.35
    f_eje = float(np.clip((med["energia_rosca"] or 0) / 12.0, 0.45, 1.0))
    if med.get("metodo_pesa") == "hueco_en_la_rosca":
        f_eje *= 0.65
    elif med.get("metodo_pesa") == "ancho_en_el_extremo":
        # la pesa se ubico por su ancho, no por su color ni por el hueco que
        # deja: es el escalon mas debil de la cascada y se avisa.
        f_eje *= 0.75
    return round(f_origen * f_marco * f_eje, 3)


def construir_fondo_fijo(registrador, rutas, umbral=0.62):
    """Aprende que pixeles saturados estan SIEMPRE en el mismo lugar.

    Justificacion: una pesa se mueve (es lo unico que hace). Un objeto
    saturado que aparece en la misma coordenada del marco alineado en casi
    todas las fotos de dias distintos es parte del decorado — la chapa
    naranja del piso, la perilla roja del extremo de la varilla — y por
    definicion no puede ser una pesa. Es un criterio que sale de los datos,
    no un recorte a mano."""
    acum, n = None, 0
    for ruta in rutas:
        img = cv2.imread(ruta)
        if img is None:
            continue
        al, _ = registrador.alinear(img)
        wb = balance_de_blancos(al)
        # se aprende con EXACTAMENTE el mismo detector que se usa despues.
        # Aprenderlo con un criterio mas estricto dejaba fuera la parte en
        # sombra de la chapa naranja del piso, que despues volvia a colarse.
        _, mp = mascaras_color(wb, None)
        m = (mp > 0).astype(np.float32)
        acum = m if acum is None else acum + m
        n += 1
    if not n:
        return None
    fijo = ((acum / n) >= umbral).astype(np.uint8) * 255
    return cv2.dilate(fijo, np.ones((5, 5), np.uint8))


class LectorLeft:
    def __init__(self, ruta_referencia, fondo_fijo=None):
        self.reg = Registrador(ruta_referencia)
        self.fondo_fijo = fondo_fijo

    def leer(self, ruta_foto):
        img = cv2.imread(ruta_foto)
        if img is None:
            return dict(archivo=os.path.basename(ruta_foto), error="no se pudo abrir la imagen")

        alineada, diag = self.reg.alinear(img)
        wb = balance_de_blancos(alineada)
        gris = cv2.cvtColor(wb, cv2.COLOR_BGR2GRAY).astype(np.float32)

        tinte = tinte_camara(alineada)
        # Cuando la camara falla el color (fotos enteras violetas), el color
        # deja de ser informacion: un canal esta practicamente muerto y
        # "corregirlo" solo amplifica ruido. En vez de inventar un numero, se
        # avisa y se mide por geometria, con menos confianza.
        # Umbral medido sobre el corpus: hay dos grupos bien separados. Con
        # desvio de hasta ~12 el color queda degradado pero utilizable (las
        # fichas verdes y las pesas se siguen distinguiendo tras corregir);
        # arriba de 30 un canal esta practicamente muerto y el color deja de
        # ser informacion. El umbral anterior (3.0) tiraba 10 fotos que si se
        # podian leer.
        color_usable = (tinte is not None and tinte < TINTE_MAX_UTILIZABLE)
        anclas = detectar_anclas(wb) if color_usable else []
        mv, mp = mascaras_color(wb, self.fondo_fijo)
        rel = brillo_relativo(wb)
        asign = {n: buscar_varilla(gris, n) for n in ("a", "b")}
        ejes = [e for e in asign.values() if e is not None]

        salida = dict(archivo=os.path.basename(ruta_foto), registro=diag,
                      tinte_camara=tinte, color_usable=color_usable,
                      anclas_magenta=len(anclas), ejes_hallados=len(ejes), varillas={})
        for nombre in ("a", "b"):
            med = medir_varilla(gris, wb, mv, mp, asign[nombre], nombre, color_usable, rel)
            med["confianza"] = confianza(med, diag, len(anclas))
            med["confianza_angulo"] = confianza_angulo(med, diag, len(anclas))
            salida["varillas"][nombre] = med

        # el angulo acordado es uno por foto y sale de la varilla de adelante
        salida["angulo"] = angulo_palanca(balance_de_blancos(img), mv, salida["varillas"]["b"],
                                          diag.get("H"), color_usable)

        med_ok = [v for v in salida["varillas"].values() if v["distancia_px"] is not None]
        salida["varillas_medidas"] = len(med_ok)
        salida["confianza_media"] = (round(sum(v["confianza"] for v in med_ok) / len(med_ok), 3)
                                     if med_ok else 0.0)
        return salida

    # ------------------------------------------------------------- diagnostico
    def dibujar(self, ruta_foto, ruta_salida, recorte=(250, 700, 350, 1010)):
        """Overlay de inspeccion. Sin verdad de referencia, mirar el resultado
        dibujado sobre la foto es la unica forma honesta de verificar un
        algoritmo de vision."""
        img = cv2.imread(ruta_foto)
        alineada, _ = self.reg.alinear(img)
        wb = balance_de_blancos(alineada)
        gris = cv2.cvtColor(wb, cv2.COLOR_BGR2GRAY).astype(np.float32)
        res = self.leer(ruta_foto)
        vis = wb.copy()
        for b in detectar_anclas(wb):
            cv2.circle(vis, (int(b["x"]), int(b["y"])), 11, (0, 220, 220), 2)
        for nombre, col in (("a", (0, 150, 255)), ("b", (255, 130, 0))):
            v = res["varillas"][nombre]
            eje = buscar_varilla(gris, nombre)
            if eje is not None and v.get("tramo_rosca_px"):
                t0, t1 = v["tramo_rosca_px"]
                p = eje["p0"] + eje["u"] * t0; q = eje["p0"] + eje["u"] * t1
                cv2.line(vis, tuple(p.astype(int)), tuple(q.astype(int)), (60, 60, 60), 1)
            if v["origen"]:
                o = tuple(int(z) for z in v["origen"])
                cv2.drawMarker(vis, o, col, cv2.MARKER_TILTED_CROSS, 26, 3)
            if v["pesa"]:
                c = tuple(int(z) for z in v["pesa"]["centro"])
                cv2.circle(vis, c, 17, col, 3)
                if v["origen"]:
                    cv2.line(vis, tuple(int(z) for z in v["origen"]), c, col, 2)
        y0, y1, x0, x1 = recorte
        vis = vis[y0:y1, x0:x1].copy()
        fila = 20
        cv2.putText(vis, os.path.basename(ruta_foto)[:34], (6, fila),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        for nombre, col in (("a", (0, 150, 255)), ("b", (255, 130, 0))):
            v = res["varillas"][nombre]
            fila += 20
            if v["distancia_px"] is None:
                # El estado importa: "no hay pesa montada" es una lectura
                # correcta de la escena, no una falla. Ponerlos juntos como
                # "sin medicion" hace que quien mira la foto crea que el
                # algoritmo fallo cuando en realidad acerto.
                etq = {"varilla_sin_pesa": "SIN PESA MONTADA (correcto)",
                       "color_inutilizable": "color de camara roto",
                       "descartada_por_rango": "descartada: fuera de rango fisico",
                       "pesa_no_encontrada": "NO encontro la pesa",
                       "varilla_no_encontrada": "NO encontro la barra"}
                t = f"{nombre}: {etq.get(v.get('estado'), 'sin medicion')}"
            else:
                t = (f"{nombre}: {v['distancia_px']:.0f}px = {v['distancia_pasos']:.1f} pasos"
                     f"  {v['metodo']}  cf={v['confianza']}")
            cv2.putText(vis, t, (6, fila), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        cv2.imwrite(ruta_salida, vis)
        return res

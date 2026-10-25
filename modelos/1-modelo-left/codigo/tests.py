#!/usr/bin/env python3
"""Suite de tests del algoritmo LEFT.

    python3 tests.py            # todo
    python3 tests.py --rapido   # saltea los que tardan minutos

Cada caso de aqui fue VERIFICADO A OJO sobre la foto. No hay ninguna etiqueta
copiada de Nexlab: sus numeros son justamente lo que este algoritmo reemplaza.

La idea: poder tocar el codigo sin miedo. Si un test falla, algo se rompio.
"""
import sys, os, glob, json, collections, datetime as dt
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_left as V

REF = "referencia_left.jpg"
RAPIDO = "--rapido" in sys.argv
_cache = {}


def lector():
    if "L" not in _cache:
        ff = np.load("fondo_fijo.npy") if os.path.exists("fondo_fijo.npy") else None
        _cache["L"] = V.LectorLeft(REF, ff)
    return _cache["L"]


def foto(nombre):
    """Encuentra una foto por su nombre en cualquiera de los corpus."""
    for pat in ("corpus/**/", "corpus_total/", "corpus_prueba/**/", "fotos_dia/**/",
                "corpus_auditoria/", "muestra_agosto/"):
        g = glob.glob(pat + nombre, recursive=True)
        if g:
            return g[0]
    return None


def leer(nombre, barra):
    if nombre not in _cache:
        p = foto(nombre)
        if p is None:
            return None
        _cache[nombre] = lector().leer(p)
    return _cache[nombre]["varillas"][barra]


def hora(nombre):
    return dt.datetime.strptime(nombre.split("LEFT_")[1][:19], "%Y-%m-%d_%H-%M-%S")


# ---------------------------------------------------------------- casos a ojo
# 12/08: la pesa METALICA estuvo puesta de 00:14 a 16:02 y la sacaron ~16:30.
# Verificado foto por foto sobre las 36 del dia.
DIA_METALICA = "2026-08-12"
CON_PESA_0812 = {"00-14", "01-48", "01-57", "03-21", "03-27", "05-03", "05-41", "06-01",
                 "08-14", "08-41", "09-34", "10-01", "12-29", "12-49", "13-08", "13-21",
                 "13-34", "13-41", "14-08", "14-28", "15-28", "16-02"}

# Varillas PELADAS, foto por foto. Cada una de estas la mire yo sobre la imagen.
#
# OJO: no sirve etiquetar un dia entero. Las pesas se montan y se sacan durante
# la jornada — el 12/08 sacaron la metalica a las 16:30 y el 17/08 tambien
# quedaron peladas a la tarde. Una etiqueta por dia daba 16 "fallas" que en
# realidad eran mediciones correctas.
PELADAS_FOTO = [
    ("RIC-0001-LEFT_2026-08-12_19-48-33.jpg", "a"), ("RIC-0001-LEFT_2026-08-12_19-48-33.jpg", "b"),
    ("RIC-0001-LEFT_2026-08-12_21-21-21.jpg", "b"), ("RIC-0001-LEFT_2026-08-12_23-01-29.jpg", "b"),
    ("RIC-0001-LEFT_2026-08-12_14-08-06.jpg", "a"), ("RIC-0001-LEFT_2026-08-12_00-14-58.jpg", "a"),
    ("RIC-0001-LEFT_2026-08-17_19-16-28.jpg", "a"), ("RIC-0001-LEFT_2026-08-17_19-16-28.jpg", "b"),
    ("RIC-0001-LEFT_2026-09-11_22-07-58.jpg", "a"), ("RIC-0001-LEFT_2026-09-11_22-07-58.jpg", "b"),
    ("RIC-0001-LEFT_2026-09-11_19-05-40.jpg", "a"), ("RIC-0001-LEFT_2026-09-11_20-52-27.jpg", "a"),
    ("RIC-0001-LEFT_2026-09-11_20-45-05.jpg", "a"), ("RIC-0001-LEFT_2026-09-11_18-18-42.jpg", "a"),
    ("RIC-0001-LEFT_2026-09-12_00-40-19.jpg", "a"), ("RIC-0001-LEFT_2026-09-12_00-40-19.jpg", "b"),
    ("RIC-0001-LEFT_2026-08-07_00-38-16.jpg", "a"), ("RIC-0001-LEFT_2026-08-07_00-38-16.jpg", "b"),
    ("RIC-0001-LEFT_2026-08-13_01-14-45.jpg", "a"), ("RIC-0001-LEFT_2026-08-10_19-09-04.jpg", "a"),
    ("RIC-0001-LEFT_2026-07-01_09-20-53.jpg", "b"),
]

# Pesas fantasma: fondo oscuro tomado por pesa. No pueden dar "medida".
FANTASMAS = [("RIC-0001-LEFT_2026-09-11_19-05-40.jpg", "a"),
             ("RIC-0001-LEFT_2026-08-10_19-09-04.jpg", "a")]

# Una pesa de cada color, para que ningun camino dependa del color.
# Pesas que SI estan puestas y tienen que medirse. Verificadas a ojo, una por
# una, a resolucion util. Son el espejo de PELADAS_FOTO.
CON_PESA_FOTO = [
    ("RIC-0001-LEFT_2026-09-12_15-40-31.jpg", "b"),   # pegada al tapon: decia "no hay pesa"
    ("RIC-0001-LEFT_2026-08-25_23-33-15.jpg", "b"),   # contra la maquina
    ("RIC-0001-LEFT_2026-09-16_23-20-48.jpg", "b"),
    ("RIC-0001-LEFT_2026-09-16_17-00-48.jpg", "a"),
    ("RIC-0001-LEFT_2026-09-16_02-14-00.jpg", "b"),
    ("RIC-0001-LEFT_2026-08-17_16-10-06.jpg", "b"),
    ("RIC-0001-LEFT_2026-08-17_07-23-02.jpg", "a"),
    ("RIC-0001-LEFT_2026-07-22_23-47-56.jpg", "a"),
    ("RIC-0001-LEFT_2026-09-15_19-54-30.jpg", "a"),
    ("RIC-0001-LEFT_2026-09-15_19-54-30.jpg", "b"),
    ("RIC-0001-LEFT_2026-07-10_14-51-22.jpg", "a"),
    ("RIC-0001-LEFT_2026-07-10_14-51-22.jpg", "b"),
]

COLORES = [("RIC-0001-LEFT_2026-08-12_14-08-06.jpg", "b", "metalica"),
           ("RIC-0001-LEFT_2026-08-17_07-23-02.jpg", "a", "celeste"),
           ("RIC-0001-LEFT_2026-09-11_00-18-49.jpg", "b", "rosa"),
           ("RIC-0001-LEFT_2026-08-12_00-14-58.jpg", "b", "metalica")]

resultados = []


def check(nombre, ok, detalle="", conocido=False):
    resultados.append((nombre, ok, detalle, conocido))
    marca = "PASA " if ok else ("FALLA CONOCIDA" if conocido else "FALLA")
    print(f"  [{marca:14s}] {nombre}")
    if detalle:
        print(f"                   {detalle}")


# ------------------------------------------------------------------- T-01
def t01():
    print("\nT-01  la pesa sin pintar del 12/08 se mide")
    fs = sorted(glob.glob(f"corpus_total/*{DIA_METALICA}*.jpg"))
    med = mal = 0
    for p in fs:
        h = os.path.basename(p).split("_")[-1][:5]
        v = lector().leer(p)["varillas"]["b"]
        if h in CON_PESA_0812:
            if v["estado"] == "medida":
                med += 1
        elif v["estado"] == "medida":
            mal += 1
    check("T-01 pesa metalica medida", med >= 18 and mal == 0,
          f"{med} de 22 fotos con pesa medidas; {mal} medidas donde NO hay pesa (tiene que ser 0)")


# ------------------------------------------------------------------- T-02
def t02():
    print("\nT-02  no inventa pesas donde no hay  (el test mas importante)")
    malas = []
    for f, b in PELADAS_FOTO:
        v = leer(f, b)
        if v is None:
            continue
        if v["estado"] == "medida":
            malas.append(f"{f[-19:]} {b} d={v['distancia_px']} cf={v['confianza']}")
    check("T-02a cero pesas inventadas", not malas,
          f"{len(PELADAS_FOTO)} varillas peladas verificadas a ojo, {len(malas)} pasaron a 'medida'"
          + ("" if not malas else "\n                   " + "\n                   ".join(malas[:8])))

    # Version sin etiquetas: una pesa no aparece y desaparece en 5 minutos.
    # Entre dos fotos seguidas, "medida" <-> "varilla_sin_pesa" es un cambio
    # que casi siempre significa que el algoritmo se equivoco en una de las dos.
    d = collections.defaultdict(list)
    fs = sorted(glob.glob("fotos_dia/**/*.jpg", recursive=True))
    fs = fs[::3] if RAPIDO else fs
    for p in fs:
        r = lector().leer(p)
        for b in "ab":
            d[b].append((hora(os.path.basename(p)), r["varillas"][b]["estado"]))
    salt = tot = 0
    for b in "ab":
        x = sorted(d[b])
        for i in range(1, len(x)):
            if (x[i][0] - x[i - 1][0]).total_seconds() > 900:
                continue
            e0, e1 = x[i - 1][1], x[i][1]
            if {e0, e1} <= {"medida", "varilla_sin_pesa"}:
                tot += 1
                salt += (e0 != e1)
    tasa = salt / max(tot, 1)
    check("T-02b coherencia entre fotos seguidas", tot > 0 and tasa <= 0.02,
          f"{salt} saltos medida<->sin_pesa en {tot} pares seguidos = {100*tasa:.1f} % "
          f"(una pesa no aparece ni desaparece en 5 minutos)")


# ------------------------------------------------------------------- T-02c
def t02c():
    print("\nT-02c  no se pierde ninguna pesa que esta a la vista")
    malas = []
    for f, b in CON_PESA_FOTO:
        v = leer(f, b)
        if v is None:
            continue
        if v["estado"] != "medida":
            malas.append(f"{f[-19:]} {b} -> {v['estado']}")
    check("T-02c mide las pesas que estan", not malas,
          f"{len(CON_PESA_FOTO)} pesas verificadas a ojo, {len(malas)} no se midieron"
          + ("" if not malas else "\n                   " + "\n                   ".join(malas[:8])))


# ------------------------------------------------------------------- T-03
def t03():
    print("\nT-03  el fondo oscuro detras de la barra no es una pesa")
    mal = [f"{f[-19:]} {b}" for f, b in FANTASMAS
           if (leer(f, b) or {}).get("estado") == "medida"]
    check("T-03 sin pesas fantasma", not mal, f"{len(FANTASMAS)} casos, {len(mal)} fallan " + " ".join(mal))


# ------------------------------------------------------------------- T-04
def t04():
    print("\nT-04  en los angulos extremos se aplica el afinado por cresta")
    sin = tot = 0
    for n in ("resultados_prueba.json", "resultados_total.json"):
        if not os.path.exists(n):
            continue
        for r in json.load(open(n)):
            for b in "ab":
                v = r["varillas"][b]
                if v.get("inclinacion_grados") and v["inclinacion_grados"] > 23:
                    p = foto(r["archivo"])
                    if p is None:
                        continue
                    img, _ = lector().reg.alinear(cv2.imread(p))
                    g = cv2.cvtColor(V.balance_de_blancos(img), cv2.COLOR_BGR2GRAY).astype(np.float32)
                    eje = V.buscar_varilla(g, b)
                    if eje is None:
                        continue
                    tot += 1
                    if "puntos_cresta" not in eje:
                        sin += 1
                    if tot >= (8 if RAPIDO else 25):
                        break
            if tot >= (8 if RAPIDO else 25):
                break
        if tot >= (8 if RAPIDO else 25):
            break
    check("T-04 afinado en angulos extremos", tot > 0 and sin == 0,
          f"{tot} lecturas con angulo > 23 grados, {sin} sin afinar")


# ------------------------------------------------------------------- T-05
def t05():
    print("\nT-05  el color de la pesa no puede decidir si se mide o no")
    mal = []
    for f, b, col in COLORES:
        v = leer(f, b)
        if v is None:
            mal.append(f"{f[-19:]} no esta en los corpus")
        elif v["estado"] != "medida":
            mal.append(f"{col} {f[-19:]} {b} -> {v['estado']}")
    check("T-05 mide con cualquier color", not mal, "; ".join(mal) or f"{len(COLORES)} colores, todos medidos")


# ------------------------------------------------------------------- T-08/09
def t0809():
    print("\nT-08/09  repetibilidad entre fotos consecutivas (la maquina no se movio)")
    d = collections.defaultdict(list)
    fs = sorted(glob.glob("fotos_dia/**/*.jpg", recursive=True))
    # En modo rapido se toma un tramo SEGUIDO de fotos. Antes se tomaba una de
    # cada 4, y como quedaban a ~28 min entre si no habia ningun par "seguido"
    # y el test pasaba sin medir nada.
    fs = fs[:70] if RAPIDO else fs
    for p in fs:
        r = lector().leer(p)
        ang = r["angulo"]["angulo_grados"] if r["angulo"]["confianza"] >= 0.9 else None
        for b in "ab":
            v = r["varillas"][b]
            if v["estado"] == "medida" and v["confianza"] >= 0.9:
                d[b].append((hora(os.path.basename(p)), v["distancia_mm"], ang))
    ok = True
    det = []
    for b in "ab":
        x = sorted(d[b])
        sd = [abs(x[i][1] - x[i - 1][1]) for i in range(1, len(x))
              if (x[i][0] - x[i - 1][0]).total_seconds() <= 900]
        sa = [abs(x[i][2] - x[i - 1][2]) for i in range(1, len(x))
              if (x[i][0] - x[i - 1][0]).total_seconds() <= 900
              and x[i][2] is not None and x[i - 1][2] is not None]
        if not sd or not sa:
            det.append(f"barra {b}: sin pares de fotos seguidas para comparar")
            ok = False
            continue
        md, ma = float(np.median(sd)), float(np.median(sa))
        det.append(f"barra {b}: distancia {md:.2f} mm, angulo {ma:.2f} grados (n={len(sd)})")
        ok &= (md <= 2.0 and ma <= 1.5)
    check("T-08/09 repetibilidad", ok, "; ".join(det))


# ------------------------------------------------------------------- T-10
def t10():
    print("\nT-10  aguanta ruido y desenfoque (compresion, suciedad en el lente)")
    fs = sorted(glob.glob("corpus_total/*.jpg"))[:(20 if RAPIDO else 60)]
    igual = tot = 0
    rng = np.random.default_rng(7)
    for p in fs:
        base = lector().leer(p)
        img = cv2.imread(p)
        ruido = np.clip(img.astype(np.float32) + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
        ruido = cv2.GaussianBlur(ruido, (3, 3), 0)
        tmp = "/tmp/_ruido.jpg"
        cv2.imwrite(tmp, ruido)
        suc = lector().leer(tmp)
        for b in "ab":
            tot += 1
            igual += (base["varillas"][b]["estado"] == suc["varillas"][b]["estado"])
        _cache.pop(tmp, None)
    check("T-10 robustez a ruido", tot and igual / tot >= 0.95,
          f"{igual}/{tot} lecturas mantienen el estado ({100*igual/max(tot,1):.0f} %)")


# ------------------------------------------------------------------- T-11
def t11():
    print("\nT-11  un dia normal completo")
    fs = sorted(glob.glob("fotos_dia/**/*.jpg", recursive=True))
    fs = fs[::4] if RAPIDO else fs
    c = collections.Counter()
    for p in fs:
        r = lector().leer(p)
        for b in "ab":
            c[r["varillas"][b]["estado"]] += 1
    n = sum(c.values())
    res = n - c["pesa_no_encontrada"] - c["varilla_no_encontrada"] - c["descartada_por_rango"]
    check("T-11 dia normal >= 98 % resuelto", n and res / n >= 0.98,
          f"{res}/{n} = {100*res/max(n,1):.1f} %   {dict(c)}")


# ------------------------------------------------------------------- T-12
def t12():
    print("\nT-12  cuando algo falta, la confianza baja (no se miente con cara de seguro)")
    alta = []
    fs = sorted(glob.glob("corpus_total/*.jpg"))
    fs = fs[::6] if RAPIDO else fs[::2]
    n = 0
    for p in fs:
        r = lector().leer(p)
        degradada = (r["anclas_magenta"] < 3) or (not r["color_usable"]) or (not r["registro"]["registrado"])
        for b in "ab":
            v = r["varillas"][b]
            if v["estado"] != "medida":
                continue
            flojo = degradada or v["metodo"] != "ficha_verde" or v.get("metodo_pesa") != "color"
            if flojo:
                n += 1
                if v["confianza"] >= 0.95:
                    alta.append(os.path.basename(p) + " " + b)
    check("T-12 la cascada degrada la confianza", not alta,
          f"{n} lecturas por un camino degradado; {len(alta)} salieron con confianza >= 0,95")


# ------------------------------------------------------------------- T-07
def t07():
    print("\nT-07  si algo tapa la barra no se puede AFIRMAR que no hay pesa")
    casos = [("RIC-0001-LEFT_2026-08-06_19-38-46.jpg", "a"),
             ("RIC-0001-LEFT_2026-07-17_15-35-00.jpg", "a")]
    mal = []
    for f, b in casos:
        v = leer(f, b)
        if v is None:
            continue
        if v["estado"] == "varilla_sin_pesa":
            mal.append(f[-19:] + " " + b)
    check("T-07 no afirma bajo oclusion", not mal,
          "ITEM ABIERTO S-05: " + " ".join(mal) if mal else "ok", conocido=True)


# ------------------------------------------------------------------- T-13
def t13():
    print("\nT-13  el angulo no cambia si se gira o corre la camara")
    # No necesita etiquetas: se gira/corre la MISMA foto y el angulo tiene que
    # dar lo mismo, porque las dos rectas estan pegadas a la maquina.
    fs = sorted(glob.glob("corpus_total/*.jpg"))[::(40 if RAPIDO else 20)]
    cambios = []
    for p in fs:
        img = cv2.imread(p)
        a0 = lector().leer(p)["angulo"]["angulo_grados"]
        if a0 is None:
            continue
        for rot, dx in ((2.0, 0), (-2.0, 0), (0.0, 8)):
            M = cv2.getRotationMatrix2D((880, 560), rot, 1.0); M[0, 2] += dx
            im2 = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)
            tmp = "/tmp/_girada.jpg"
            cv2.imwrite(tmp, im2, [cv2.IMWRITE_JPEG_QUALITY, 95])
            _cache.pop(tmp, None)
            a1 = lector().leer(tmp)["angulo"]["angulo_grados"]
            _cache.pop(tmp, None)
            if a1 is not None:
                cambios.append(abs(a1 - a0))
    c = np.array(cambios)
    check("T-13 angulo invariante a la camara", len(c) > 0 and np.median(c) <= 0.3 and c.max() <= 2.0,
          f"{len(c)} pruebas: cambio mediano {np.median(c):.2f} grados, maximo {c.max():.2f}")


def main():
    if not os.path.exists(REF):
        print("Hay que correr esto desde la carpeta del algoritmo."); sys.exit(2)
    print("=" * 66)
    print("SUITE DE TESTS DEL ALGORITMO LEFT" + ("   (modo rapido)" if RAPIDO else ""))
    print("=" * 66)
    for f in (t01, t02, t02c, t03, t04, t05, t07, t0809, t10, t11, t12, t13):
        try:
            f()
        except Exception as e:
            check(f.__name__, False, f"el test se rompio: {e}")
    print("\n" + "=" * 66)
    fallan = [r for r in resultados if not r[1] and not r[3]]
    conocidas = [r for r in resultados if not r[1] and r[3]]
    print(f"PASAN {sum(1 for r in resultados if r[1])}/{len(resultados)}"
          f"   fallan {len(fallan)}   fallas conocidas {len(conocidas)}")
    if fallan:
        print("\nSE ROMPIO:")
        for r in fallan:
            print("  -", r[0])
    print("=" * 66)
    sys.exit(1 if fallan else 0)


if __name__ == "__main__":
    main()

"""
descargar_top.py — baja fotos y datos de Nexlab de VARIOS dias.

Funciona en dos pasos (se elige con MODO, abajo):

  MODO = "explorar"   Recorre un rango de fechas bajando SOLO el JSON de cada dia
                      (rapido, sin fotos) y arma un ranking: en que dias se movio
                      mas la palanca segun Nexlab y en cuales tuvo mas errores.
                      Guarda el ranking en descargas/top/ranking_dias.csv y
                      sugiere que dias bajar.

  MODO = "descargar"  Baja todo (JSON + CSV + fotos de input y de output) de los
                      dias elegidos. Los elige solo con el ranking (los CANTIDAD
                      mejores) o se le pasa una lista a mano en FECHAS_A_MANO.

Lo normal: correr una vez con "explorar", mirar el ranking, y despues con
"descargar". Si se corta, al volver a correrlo sigue desde donde quedo.

Funciona en Jupyter y en la terminal. Necesita:  pip install requests
"""
import csv, datetime as dt, json, os, statistics
import requests

# ============================== CONFIGURACION ==============================
MODO = "explorar"                 # "explorar" o "descargar"

# Rango a explorar (ambos incluidos)
DESDE = "2026-08-01"
HASTA = "2026-09-22"

# Cuantos dias bajar en modo "descargar" (se toman los mejores del ranking)
CANTIDAD = 5
# ...o si queres elegirlos vos, ponelos aca y se usan estos en vez del ranking:
FECHAS_A_MANO = []                # ej: ["2026-08-14", "2026-09-05"]

# Fotos de output (las dibujadas por Nexlab): utiles para mirar, pero sus valores
# ya vienen en el JSON. En False se baja la mitad de peso.
BAJAR_OUTPUT = False

URL = "http://sam-analysis.nexlab.com.uy/data"
FILTRO = "top"                    # "top", "left" o "amp"
CARPETA_BASE = "descargas"        # o una ruta fija: r"C:\Users\andyf\Desktop\descargas"
# ===========================================================================

CARPETA_FILTRO = os.path.join(CARPETA_BASE, FILTRO)
RANKING = os.path.join(CARPETA_FILTRO, "ranking_dias.csv")


def es_link_de_imagen(valor):
    return (isinstance(valor, str) and valor.startswith("http")
            and valor.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")))


def pedir_json(fecha):
    """JSON del backend para un dia. Si ya se bajo antes, lo lee del disco."""
    carpeta = os.path.join(CARPETA_FILTRO, fecha)
    ruta = os.path.join(carpeta, f"datos_{FILTRO}_{fecha}.json")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    r = requests.get(URL, params={"date": fecha, "env": "prod", "name_filter": FILTRO}, timeout=60)
    if r.status_code != 200:
        print(f"  {fecha}: error del backend, codigo {r.status_code}")
        return None
    datos = r.json()
    if datos:
        os.makedirs(carpeta, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
    return datos


def resumir_dia(fecha, datos):
    """Numeros de un dia, para decidir si vale la pena bajar sus fotos."""
    n = len(datos)
    errores = sum(1 for d in datos if d.get("err"))
    ceros_sin_error = sum(1 for d in datos if not d.get("err") and d.get("opening") == 0)
    vals = [d["opening"] for d in datos
            if not d.get("err") and isinstance(d.get("opening"), (int, float)) and d["opening"] > 0]
    fila = dict(fecha=fecha, fotos=n, errores=errores, ceros_sin_error=ceros_sin_error,
                opening_min="", opening_max="", rango="", desvio="", valores_distintos=0)
    if vals:
        fila.update(opening_min=min(vals), opening_max=max(vals),
                    rango=round(max(vals) - min(vals), 2),
                    desvio=round(statistics.pstdev(vals), 3),
                    valores_distintos=len(set(vals)))
    return fila


def explorar():
    d0 = dt.date.fromisoformat(DESDE)
    d1 = dt.date.fromisoformat(HASTA)
    filas = []
    print(f"Explorando {DESDE} a {HASTA} (solo datos, sin fotos)...")
    for i in range((d1 - d0).days + 1):
        fecha = (d0 + dt.timedelta(days=i)).isoformat()
        try:
            datos = pedir_json(fecha)
        except Exception as e:
            print(f"  {fecha}: ERROR {e}")
            continue
        if not datos:
            print(f"  {fecha}: sin registros")
            continue
        f = resumir_dia(fecha, datos)
        filas.append(f)
        print(f"  {fecha}: {f['fotos']:>3} fotos  opening {f['opening_min']}-{f['opening_max']}"
              f"  (rango {f['rango']})  errores {f['errores']}  ceros sin error {f['ceros_sin_error']}")
    if not filas:
        print("No se encontro ningun dia con datos en ese rango.")
        return
    # Orden: primero los que mas movimiento tuvieron; a igualdad, mas errores
    filas.sort(key=lambda f: (-(f["rango"] or 0), -f["errores"]))
    os.makedirs(CARPETA_FILTRO, exist_ok=True)
    with open(RANKING, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"\nRanking guardado en: {os.path.abspath(RANKING)}")
    print(f"\nDias con MAS MOVIMIENTO de la palanca (los que conviene bajar):")
    for f in filas[:CANTIDAD]:
        print(f"  {f['fecha']}  opening {f['opening_min']}-{f['opening_max']}  errores {f['errores']}")
    mas_err = sorted(filas, key=lambda f: -(f["errores"] + f["ceros_sin_error"]))[:3]
    print("\nDias con MAS ERRORES de Nexlab (tambien interesantes):")
    for f in mas_err:
        print(f"  {f['fecha']}  errores {f['errores']}  ceros sin error {f['ceros_sin_error']}")
    print('\nPara bajar las fotos: cambia MODO = "descargar" y volve a correr.')


def descargar_dia(fecha):
    carpeta = os.path.join(CARPETA_FILTRO, fecha)
    print(f"\n=== {fecha} ===")
    datos = pedir_json(fecha)          # guarda el JSON si todavia no estaba
    if not datos:
        print("  sin registros")
        return
    campos = []
    for reg in datos:
        for k in reg:
            if k not in campos:
                campos.append(k)
    campos_img = [k for k in campos if any(es_link_de_imagen(r.get(k)) for r in datos)]
    if not BAJAR_OUTPUT:
        campos_img_bajar = [k for k in campos_img if "output" not in k.lower()]
    else:
        campos_img_bajar = campos_img

    with open(os.path.join(carpeta, f"valores_{FILTRO}_{fecha}.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, [k for k in campos if k not in campos_img], extrasaction="ignore")
        w.writeheader()
        for reg in datos:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in reg.items()})

    ok = err = 0
    for i, reg in enumerate(datos, 1):
        base = os.path.splitext(reg.get("filename") or f"registro_{i}")[0]
        for campo in campos_img_bajar:
            link = reg.get(campo)
            if not es_link_de_imagen(link):
                continue
            sub = os.path.join(carpeta, campo)
            os.makedirs(sub, exist_ok=True)
            ext = os.path.splitext(link.split("?")[0])[1] or ".jpg"
            ruta = os.path.join(sub, base + ext)
            if os.path.exists(ruta):
                ok += 1
                continue
            try:
                img = requests.get(link, timeout=30)
                if img.status_code == 200:
                    with open(ruta, "wb") as f:
                        f.write(img.content)
                    ok += 1
                else:
                    err += 1
            except Exception:
                err += 1
        print(f"  [{i}/{len(datos)}] {base}", end="\r")
    print(f"\n  Imagenes: {ok} bajadas, {err} con error   ->  {os.path.abspath(carpeta)}")


def elegir_fechas():
    if FECHAS_A_MANO:
        return FECHAS_A_MANO
    if not os.path.exists(RANKING):
        print('No hay ranking todavia: primero corre con MODO = "explorar".')
        return []
    with open(RANKING, encoding="utf-8") as fh:
        return [f["fecha"] for f in csv.DictReader(fh)][:CANTIDAD]


if __name__ == "__main__":
    if MODO == "explorar":
        explorar()
    elif MODO == "descargar":
        fechas = elegir_fechas()
        print("Dias a bajar:", ", ".join(fechas) or "(ninguno)")
        for fecha in fechas:
            descargar_dia(fecha)
        if fechas:
            print(f"\nListo. Comprimi la carpeta '{CARPETA_BASE}' y subila.")
    else:
        print('MODO tiene que ser "explorar" o "descargar"')

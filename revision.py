"""Revisión a ojo semanal: la forma de saber si los modelos miden bien en operación.

    python revision.py crear      # arma el issue de la semana con 20 fotos al azar (GitHub lo corre los lunes)
    python revision.py resumir    # lee los issues de revisión cerrados y escribe datos/panel/revision.json

Cada foto se marca "Bien" o "Mal" en el issue. Fotos donde el modelo midió: un "Mal" es un falso positivo
(dio un número equivocado). Fotos donde no midió: un "Mal" es un falso negativo (la foto se podía leer).
Usa la CLI de GitHub (gh) con GH_TOKEN; no necesita las librerías de los modelos.
"""
import csv, glob, json, os, random, re, subprocess, sys
from datetime import date, datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
BUCKET = "https://sam-240101.s3.sa-east-1.amazonaws.com"
ETIQUETA = "revision"
POR_CAMARA = {"top": 7, "left": 7, "amp": 6}       # 20 fotos por semana
PARTE_NO_MEDIDAS = 0.25                             # de cada cámara, ~1/4 son fotos donde el modelo no midió
# PROPUESTA a confirmar con el tutor: qué cuenta como "Bien" y qué acierto se exige para darlo por operativo.
TOLERANCIA = {"top": "±0,5 en la escala 0-10", "left": "±5 mm en cada pesa y ±3° en el ángulo", "amp": "±1 A en cada fase"}
OBJETIVO = 0.95


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def fotos_de(camara, dias):
    """{archivo: {"t", "filas"}} de las lecturas guardadas de esos días."""
    fotos = {}
    for d in dias:
        ruta = os.path.join(DATOS, "lecturas", camara, f"{d}.csv")
        if os.path.exists(ruta):
            for f in csv.DictReader(open(ruta, encoding="utf-8")):
                fotos.setdefault(f["archivo"], {"t": f["t"], "filas": []})["filas"].append(f)
    return fotos


def nombres_variables(dias):
    var = {}
    for d in dias:
        ruta = os.path.join(DATOS, "panel", f"{d}.json")
        if os.path.exists(ruta):
            var.update(json.load(open(ruta, encoding="utf-8"))["variables"])
    return var


def describir(foto, var, camara):
    partes = []
    for f in foto["filas"]:
        m = var.get(f"{camara}.{f['variable']}", {})
        nombre, unidad = m.get("nombre", f["variable"]), m.get("unidad", "")
        unidad = "en la escala 0-10" if unidad == "0-10" else unidad
        partes.append(f"{nombre}: **{round(float(f['valor']), 1)} {unidad}**" if f["valor"] != ""
                      else f"{nombre}: no midió ({f['estado'].replace('_', ' ')})")
    return " · ".join(partes)


def crear(hoy=None):
    hoy = hoy or date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    titulo = f"Revisión a ojo · semana del {lunes - timedelta(days=7)}"
    if any(i["title"] == titulo for i in json.loads(gh("issue", "list", "--label", ETIQUETA, "--state", "all",
                                                        "--limit", "100", "--json", "title"))):
        print("Ya existe:", titulo)
        return
    dias = [str(lunes - timedelta(days=i)) for i in range(7, 0, -1)]     # lunes a domingo de la semana pasada
    var, rnd = nombres_variables(dias), random.Random(titulo)            # misma semana -> misma muestra
    cuerpo = [f"Para cada foto, comparala con lo que leyó el modelo y marcá **una** casilla. Al terminar, cerrá el issue.\n",
              "**Bien** si el valor está dentro de la tolerancia, o si el modelo no midió y la foto de verdad no se puede leer. "
              "**Mal** si el número es incorrecto, o si no midió pero la foto se leía bien.\n",
              "Tolerancias (propuesta): " + "; ".join(f"{c}: {t}" for c, t in TOLERANCIA.items()) + ".\n"]
    n = 0
    for camara, cuantas in POR_CAMARA.items():
        fotos = fotos_de(camara, dias)
        midio = sorted(a for a, f in fotos.items() if any(x["valor"] != "" for x in f["filas"]))
        no_midio = sorted(set(fotos) - set(midio))
        k = min(len(no_midio), round(cuantas * PARTE_NO_MEDIDAS))
        elegidas = [(a, "no_midio") for a in rnd.sample(no_midio, k)]
        elegidas += [(a, "midio") for a in rnd.sample(midio, min(len(midio), cuantas - k))]
        for archivo, tipo in sorted(elegidas, key=lambda x: fotos[x[0]]["t"]):
            n += 1
            a, m, d = re.search(r"(\d{4})-(\d\d)-(\d\d)_", archivo).groups()
            cuerpo.append(f"### {n}. {camara} · {fotos[archivo]['t'][:16].replace('T', ' ')}\n"
                          f"<!-- foto:{camara}:{archivo}:{tipo} -->\n"
                          f"![{archivo}]({BUCKET}/{a}/{m}/{d}/{archivo})\n\n"
                          f"El modelo leyó: {describir(fotos[archivo], var, camara)}\n\n- [ ] Bien\n- [ ] Mal\n")
    if not n:
        print("No hay lecturas de esa semana")
        return
    gh("label", "create", ETIQUETA, "--color", "0E8A16", "--description", "Revisión a ojo semanal", "--force")
    print(gh("issue", "create", "--title", titulo, "--label", ETIQUETA, "--body", "\n".join(cuerpo)).strip())


def leer_marcas(cuerpo):
    """[(camara, archivo, tipo, "bien" | "mal" | None)] a partir del texto del issue."""
    marcas = []
    bloques = re.split(r"<!-- foto:", cuerpo)[1:]
    for b in bloques:
        camara, archivo, tipo = b.split(" -->", 1)[0].split(":")
        bien = re.search(r"- \[[xX]\] Bien", b) is not None
        mal = re.search(r"- \[[xX]\] Mal", b) is not None
        marcas.append((camara, archivo, tipo, "mal" if mal else "bien" if bien else None))
    return marcas


def resumir():
    issues = json.loads(gh("issue", "list", "--label", ETIQUETA, "--state", "all", "--limit", "200",
                           "--json", "number,title,url,state,body,closedAt"))
    camaras = {c: dict(revisadas=0, bien=0, falsos_positivos=0, falsos_negativos=0) for c in POR_CAMARA}
    semanas, pendiente = [], None
    for i in sorted(issues, key=lambda i: i["number"]):
        if i["state"] != "CLOSED":
            pendiente = {"titulo": i["title"], "url": i["url"]}
            continue
        malas = 0
        for camara, _, tipo, marca in leer_marcas(i["body"]):
            if marca is None or camara not in camaras:
                continue
            c = camaras[camara]
            c["revisadas"] += 1
            if marca == "bien":
                c["bien"] += 1
            else:
                malas += 1
                c["falsos_positivos" if tipo == "midio" else "falsos_negativos"] += 1
        semanas.append({"titulo": i["title"], "url": i["url"], "cerrada": i["closedAt"][:10], "malas": malas})
    for c in camaras.values():
        c["acierto"] = round(c["bien"] / c["revisadas"], 3) if c["revisadas"] else None
    salida = {"actualizado": datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="minutes"),
              "objetivo": OBJETIVO, "tolerancia": TOLERANCIA, "camaras": camaras,
              "semanas": semanas, "pendiente": pendiente}
    os.makedirs(os.path.join(DATOS, "panel"), exist_ok=True)
    with open(os.path.join(DATOS, "panel", "revision.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print({c: (v["bien"], v["revisadas"]) for c, v in camaras.items()}, "pendiente:", bool(pendiente))


if __name__ == "__main__":
    {"crear": crear, "resumir": resumir}[sys.argv[1]]()

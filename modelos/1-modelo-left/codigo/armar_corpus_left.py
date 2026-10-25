#!/usr/bin/env python3
"""
armar_corpus_left.py — Arma el corpus de fotos de la camara "left".

Idea: el campo `err` de Nexlab NO se usa como verdad de referencia. Se usa
unicamente como *buscador de casos dificiles*: donde su algoritmo falla es,
con alta probabilidad, donde la escena esta en una condicion rara. Eso nos
permite estratificar el muestreo sin etiquetar nada a mano.

Salida:
  corpus/
    ok/ falta_ficha_verde/ faltan_puntos_magenta/ tamano_fuera_de_rango/ otros/
    metadata.json   <- todos los registros crudos + la categoria asignada
    reporte.txt     <- distribucion de casos por dia y total
"""
import json, os, re, sys, urllib.request, collections
from concurrent.futures import ThreadPoolExecutor

BASE = "http://sam-analysis.nexlab.com.uy/data"   # OJO: http, el server no tiene https
OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "corpus_prueba" if "--prueba" in __import__("sys").argv else "corpus")

# Dias espaciados a proposito: distinta estacion, distinta suciedad de camara,
# distinta luz. No consecutivos.
import sys as _sys
DIAS = ["2026-08-03", "2026-08-17", "2026-09-01", "2026-09-10", "2026-09-15", "2026-09-19"]
# dias de PRUEBA INDEPENDIENTE: el algoritmo se calibro con los de arriba, asi
# que estos sirven para comprobar que no esta ajustado a medida de ellos.
DIAS_PRUEBA = ["2026-07-01", "2026-07-10", "2026-07-20", "2026-08-10",
               "2026-08-25", "2026-09-05", "2026-09-20"]
if "--prueba" in _sys.argv:
    DIAS = DIAS_PRUEBA

MAX_OK_POR_DIA = 40      # los casos normales abundan -> se muestrean
                         # los casos con error se bajan TODOS

CATEGORIAS = ["ok", "falta_ficha_verde", "faltan_puntos_magenta",
              "tamano_fuera_de_rango", "otros"]


def categorizar(err):
    """Traduce el mensaje de error de Nexlab a una categoria de escena."""
    if not err:
        return "ok"
    e = err.lower()
    if "bar_points" in e or "bar end contours" in e or "retracted" in e:
        return "falta_ficha_verde"
    if "ref_points" in e or "magenta" in e or "anchor" in e:
        return "faltan_puntos_magenta"
    if "invalid" in e and ("size" in e or "dist" in e):
        return "tamano_fuera_de_rango"
    return "otros"


def pedir_dia(fecha):
    url = f"{BASE}?date={fecha}&env=prod&name_filter=left"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def bajar(reg):
    destino = reg["_ruta_local"]
    if os.path.exists(destino) and os.path.getsize(destino) > 1000:
        return True
    try:
        urllib.request.urlretrieve(reg["input_img_path"], destino)
        return True
    except Exception as ex:
        print(f"  ! fallo {reg['filename']}: {ex}", file=sys.stderr)
        return False


def main():
    for c in CATEGORIAS:
        os.makedirs(os.path.join(OUT, c), exist_ok=True)

    seleccion, por_dia = [], {}

    for fecha in DIAS:
        try:
            regs = pedir_dia(fecha)
        except Exception as ex:
            print(f"{fecha}: ERROR al pedir datos ({ex})", file=sys.stderr)
            continue

        cuenta = collections.Counter()
        con_error, sin_error = [], []
        for r in regs:
            cat = categorizar(r.get("err"))
            r["_categoria"] = cat
            r["_fecha_dia"] = fecha
            cuenta[cat] += 1
            (sin_error if cat == "ok" else con_error).append(r)

        # muestreo uniforme a lo largo del dia para los 'ok' (cubre luz diurna y nocturna)
        if len(sin_error) > MAX_OK_POR_DIA:
            paso = len(sin_error) / MAX_OK_POR_DIA
            sin_error = [sin_error[int(i * paso)] for i in range(MAX_OK_POR_DIA)]

        elegidos = con_error + sin_error
        for r in elegidos:
            r["_ruta_local"] = os.path.join(OUT, r["_categoria"], r["filename"])
        seleccion += elegidos
        por_dia[fecha] = {"total_dia": len(regs), "elegidos": len(elegidos),
                          "distribucion": dict(cuenta)}
        print(f"{fecha}: {len(regs)} fotos, {sum(v for k,v in cuenta.items() if k!='ok')} con error "
              f"-> bajo {len(elegidos)}")

    print(f"\nDescargando {len(seleccion)} fotos...")
    with ThreadPoolExecutor(max_workers=12) as ex:
        ok = sum(ex.map(bajar, seleccion))
    print(f"Descargadas {ok}/{len(seleccion)}")

    with open(os.path.join(OUT, "metadata.json"), "w") as f:
        json.dump(seleccion, f, indent=1)

    total = collections.Counter(r["_categoria"] for r in seleccion)
    lineas = ["CORPUS 'left' — distribucion de casos", "=" * 45, ""]
    for fecha, info in por_dia.items():
        lineas.append(f"{fecha}  ({info['total_dia']} fotos en el dia, {info['elegidos']} bajadas)")
        for c in CATEGORIAS:
            if info["distribucion"].get(c):
                lineas.append(f"    {c:<26} {info['distribucion'][c]:>4}")
        lineas.append("")
    lineas += ["TOTAL BAJADO POR CATEGORIA", "-" * 45]
    for c in CATEGORIAS:
        lineas.append(f"  {c:<26} {total.get(c,0):>4}")
    lineas.append(f"  {'TOTAL':<26} {sum(total.values()):>4}")
    txt = "\n".join(lineas)
    with open(os.path.join(OUT, "reporte.txt"), "w") as f:
        f.write(txt + "\n")
    print("\n" + txt)


if __name__ == "__main__":
    main()

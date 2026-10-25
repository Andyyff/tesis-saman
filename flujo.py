"""Flujo completo: Nexlab -> algoritmos -> grilla de 10 min -> chequeos -> datos/panel/.

    python flujo.py                 # hoy y ayer (lo que corre GitHub cada hora)
    python flujo.py 2026-10-20      # un día puntual

Es incremental: solo baja y procesa las fotos que todavía no están en datos/lecturas/.
"""
import csv, json, math, os, re, sys
from datetime import datetime, timedelta, timezone

import algoritmos, chequeos, nexlab

UY = timezone(timedelta(hours=-3))           # Uruguay no tiene horario de verano desde 2015
GRILLA_MIN = 10
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
CACHE_FOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "fotos")
CAMPOS = ["t", "archivo", "variable", "valor", "estado", "detalle", "version", "nexlab"]


def hora_de_archivo(nombre):
    """'RIC-0001-TOP_2026-10-25_11-11-35.jpg' -> '2026-10-25T11:11:35-03:00' (el nombre va en hora de Uruguay)."""
    m = re.search(r"(\d{4}-\d\d-\d\d)_(\d\d)-(\d\d)-(\d\d)", nombre)
    return f"{m[1]}T{m[2]}:{m[3]}:{m[4]}-03:00" if m else None


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escribir_csv(ruta, filas, campos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, campos)
        w.writeheader()
        w.writerows(filas)


# ---------------------------------------------------------------- cámaras
def procesar_camara(camara, fecha, aviso):
    alg = algoritmos.cargar(camara)
    ruta = os.path.join(DATOS, "lecturas", camara, f"{fecha}.csv")
    previas = leer_csv(ruta)
    hechas = {f["archivo"] for f in previas}

    regs, vistos = [], set()
    for r in nexlab.registros_fotos(camara, fecha):
        if r.get("filename") and r["filename"] not in vistos:   # Nexlab a veces repite registros
            vistos.add(r["filename"])
            regs.append(r)
    nuevos = [r for r in regs if r["filename"] not in hechas and hora_de_archivo(r["filename"])]

    rutas, por_archivo = [], {}
    for r in nuevos:
        try:
            rutas.append(nexlab.bajar_foto(r["input_img_path"], os.path.join(CACHE_FOTOS, camara, fecha, r["filename"])))
            por_archivo[r["filename"]] = r
        except Exception as e:      # se reintenta en la próxima corrida
            aviso(f"{camara}: no se pudo bajar {r['filename']}: {e}")
    if not rutas:
        return previas

    try:
        salida = alg.leer(rutas)
    except Exception as e:          # un algoritmo roto no frena a los demás; se reintenta
        aviso(f"{camara}: el algoritmo falló ({e!r}); sus fotos nuevas quedan para la próxima corrida")
        return previas

    filas = []
    for s in salida:
        var = alg.VARIABLES[s["variable"]]
        valor, estado, detalle = _num(s["valor"]), s["estado"], s.get("detalle", "")
        lo, hi = var["rango"]
        if valor is not None and not lo <= valor <= hi:
            detalle = f"valor {valor} fuera de rango ({lo} a {hi}). {detalle}".strip()
            valor, estado = None, "fuera_de_rango"
        reg = por_archivo[s["archivo"]]
        ref = _num(reg.get(var["nexlab"])) if var.get("nexlab") and not reg.get("err") else None
        if ref is not None and not lo <= ref <= hi:      # Nexlab marca sus fallas con -1 (amp)
            ref = None
        filas.append(dict(t=hora_de_archivo(s["archivo"]), archivo=s["archivo"], variable=s["variable"],
                          valor="" if valor is None else round(valor, 3), estado=estado, detalle=detalle,
                          version=alg.VERSION, nexlab="" if ref is None else ref))
    todas = sorted(previas + filas, key=lambda f: (f["t"], f["variable"]))
    escribir_csv(ruta, todas, CAMPOS)
    for r in rutas:                 # ya quedó en lecturas/: la foto no se vuelve a usar
        os.remove(r)
    print(f"{fecha} {camara}: {len(filas)} lecturas nuevas ({len(rutas)} fotos)")
    return todas


# ---------------------------------------------------------------- clima
def procesar_clima(fecha):
    ini = datetime.fromisoformat(fecha).replace(tzinfo=UY).astimezone(timezone.utc)
    fin = ini + timedelta(days=1, seconds=-1)
    filas = []
    for sid, var in nexlab.CLIMA.items():
        for t_utc, valor in nexlab.lecturas_clima(sid, f"{ini:%Y-%m-%dT%H:%M:%SZ}", f"{fin:%Y-%m-%dT%H:%M:%SZ}"):
            t = datetime.fromisoformat(t_utc.replace("Z", "+00:00")).astimezone(UY)
            valor, (lo, hi) = _num(valor), var["rango"]
            ok = valor is not None and lo <= valor <= hi
            filas.append(dict(t=t.isoformat(timespec="seconds"), variable=var["variable"],
                              valor=valor if ok else "", estado="medida" if ok else "fuera_de_rango"))
    filas.sort(key=lambda f: (f["t"], f["variable"]))
    escribir_csv(os.path.join(DATOS, "lecturas", "clima", f"{fecha}.csv"), filas, ["t", "variable", "valor", "estado"])
    print(f"{fecha} clima: {len(filas)} lecturas")
    return filas


# ---------------------------------------------------------------- grilla
def casillero(t_iso):
    t = datetime.fromisoformat(t_iso)
    return t.replace(minute=t.minute - t.minute % GRILLA_MIN, second=0, microsecond=0).isoformat(timespec="minutes")


def armar_dia(fecha, lecturas_cam, lecturas_clima, ahora):
    """Grilla de 10 min, hora de Uruguay. Cámaras: última lectura válida del casillero.
    Clima: promedio del casillero. Sin lectura válida -> null y el motivo en "e"."""
    ini = datetime.fromisoformat(fecha).replace(tzinfo=UY)
    fin = min(ini + timedelta(days=1), ahora)
    slots = []
    t = ini
    while t < fin:
        slots.append(t.isoformat(timespec="minutes"))
        t += timedelta(minutes=GRILLA_MIN)

    variables, v, e = {}, {s: {} for s in slots}, {s: {} for s in slots}
    for camara, filas in lecturas_cam.items():
        alg = algoritmos.cargar(camara)
        for nombre, meta in alg.VARIABLES.items():
            vid = f"{camara}.{nombre}"
            variables[vid] = dict(nombre=meta["nombre"], unidad=meta["unidad"], fuente=camara,
                                  version=alg.VERSION, salto_max=meta.get("salto_max"))
            if meta.get("nexlab"):
                variables[vid + "_nexlab"] = dict(nombre=meta["nombre"] + " (Nexlab)", unidad=meta["unidad"],
                                                  fuente="nexlab", version="nexlab", salto_max=None)
            for f in filas:          # ya vienen ordenadas por hora: la última pisa
                s = casillero(f["t"])
                if f["variable"] != nombre or s not in v:
                    continue
                if f["valor"] != "":
                    v[s][vid] = float(f["valor"])
                    e[s].pop(vid, None)
                elif vid not in v[s]:
                    e[s][vid] = f["estado"]
                if f.get("nexlab", "") != "":
                    v[s][vid + "_nexlab"] = float(f["nexlab"])

    for meta in nexlab.CLIMA.values():
        vid = f"clima.{meta['variable']}"
        variables[vid] = dict(nombre=meta["nombre"], unidad=meta["unidad"], fuente="clima",
                              version="nexlab-sensores", salto_max=meta["salto_max"])
        suma = {}
        for f in lecturas_clima:
            s = casillero(f["t"])
            if f["variable"] == meta["variable"] and f["valor"] != "" and s in v:
                suma.setdefault(s, []).append(float(f["valor"]))
        for s, xs in suma.items():
            v[s][vid] = round(sum(xs) / len(xs), 2)

    filas = []
    for s in slots:
        for vid in variables:
            if vid not in v[s] and vid not in e[s] and not vid.endswith("_nexlab"):
                e[s][vid] = "sin_dato"
        filas.append({"t": s, "v": v[s], "e": e[s]})
    return {"fecha": fecha, "zona_horaria": "-03:00", "grilla_min": GRILLA_MIN,
            "generado": ahora.isoformat(timespec="seconds"), "variables": variables, "filas": filas}


def correr(fechas, ahora=None):
    ahora = ahora or datetime.now(UY)
    avisos = []
    aviso = lambda m: (avisos.append(m), print("AVISO:", m))
    for fecha in fechas:
        cam = {}
        for c in algoritmos.CAMARAS:
            try:
                cam[c] = procesar_camara(c, fecha, aviso)
            except Exception as e:
                aviso(f"{c}: no se pudo leer Nexlab ({e}); se usan las lecturas ya guardadas")
                cam[c] = leer_csv(os.path.join(DATOS, "lecturas", c, f"{fecha}.csv"))
        try:
            clima = procesar_clima(fecha)
        except Exception as e:
            aviso(f"clima: no se pudo leer Nexlab ({e}); se usan las lecturas ya guardadas")
            clima = leer_csv(os.path.join(DATOS, "lecturas", "clima", f"{fecha}.csv"))
        dia = armar_dia(fecha, cam, clima, ahora)
        dia["calidad"] = chequeos.revisar(dia, ahora, avisos)
        os.makedirs(os.path.join(DATOS, "panel"), exist_ok=True)
        with open(os.path.join(DATOS, "panel", f"{fecha}.json"), "w", encoding="utf-8") as f:
            json.dump(dia, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{fecha} panel: {len(dia['filas'])} casilleros, calidad {dia['calidad']['estado']}")
    publicar(ahora)


def publicar(ahora=None):
    """indice.json y tablas de Power BI a partir de todos los días que haya en datos/panel/."""
    ahora = ahora or datetime.now(UY)
    dias = sorted(n[:-5] for n in os.listdir(os.path.join(DATOS, "panel")) if re.fullmatch(r"\d{4}-\d\d-\d\d\.json", n))
    with open(os.path.join(DATOS, "panel", "indice.json"), "w", encoding="utf-8") as f:
        json.dump({"dias": dias, "actualizado": ahora.isoformat(timespec="seconds"),
                   "grilla_min": GRILLA_MIN}, f, ensure_ascii=False, indent=1)
    exportar_powerbi(dias)


# ---------------------------------------------------------------- Power BI
def exportar_powerbi(dias):
    """Tres tablas planas con todos los días, rehechas desde datos/panel/ en cada corrida.
    mediciones: una fila por casillero y variable (hora de Uruguay). variables: el diccionario. calidad: por día."""
    med, var, cal = [], {}, []
    for fecha in dias:
        with open(os.path.join(DATOS, "panel", f"{fecha}.json"), encoding="utf-8") as f:
            dia = json.load(f)
        q = dia["calidad"]["variables"]
        for vid, meta in dia["variables"].items():
            if not vid.endswith("_nexlab"):
                var[vid] = dict(variable=vid, nombre=meta["nombre"], unidad=meta["unidad"],
                                fuente=meta["fuente"], version=meta["version"])
        for fila in dia["filas"]:
            for vid in var:
                if vid not in dia["variables"]:
                    continue
                med.append(dict(fecha_hora=fila["t"][:16].replace("T", " "), variable=vid,
                                valor=fila["v"].get(vid, ""), valor_nexlab=fila["v"].get(vid + "_nexlab", ""),
                                motivo=fila["e"].get(vid, ""), salto=fila["t"] in q.get(vid, {}).get("saltos", [])))
        for vid, c in q.items():
            cal.append(dict(fecha=fecha, variable=vid, cobertura=c.get("cobertura", ""),
                            coincide_con_nexlab=c.get("coincide_con_nexlab", ""), saltos=len(c.get("saltos", [])),
                            estado_dia=dia["calidad"]["estado"]))
    carpeta = os.path.join(DATOS, "powerbi")
    escribir_csv(os.path.join(carpeta, "mediciones.csv"), med, ["fecha_hora", "variable", "valor", "valor_nexlab", "motivo", "salto"])
    escribir_csv(os.path.join(carpeta, "variables.csv"), list(var.values()), ["variable", "nombre", "unidad", "fuente", "version"])
    escribir_csv(os.path.join(carpeta, "calidad.csv"), cal, ["fecha", "variable", "cobertura", "coincide_con_nexlab", "saltos", "estado_dia"])
    print(f"Power BI: {len(med)} mediciones de {len(dias)} días")


if __name__ == "__main__":
    hoy = datetime.now(UY).date()
    correr(sys.argv[1:] or [str(hoy - timedelta(days=1)), str(hoy)])

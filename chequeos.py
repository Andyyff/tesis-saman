"""Chequeos de veracidad de un día ya armado. El resultado va en el JSON del día ("calidad")
para que el panel muestre si el dato es confiable, no solo el dato."""
from datetime import datetime

MAX_ATRASO_MIN = 90          # el flujo corre cada hora y Nexlab tarda ~10 min: más que esto es una falla
MIN_COBERTURA = 0.80         # menos del 80 % de casilleros con dato: revisar
TOL_NEXLAB = 0.5             # unidades de diferencia que todavía cuentan como "coincide con Nexlab"

def revisar(dia, ahora, avisos=()):
    filas, alertas, por_var = dia["filas"], list(avisos), {}
    ts = [f["t"] for f in filas]
    assert ts == sorted(ts) and len(ts) == len(set(ts)), "casilleros desordenados o repetidos"
    es_hoy = dia["fecha"] == ahora.date().isoformat()

    for vid, meta in dia["variables"].items():
        if vid.endswith("_nexlab"):
            continue
        serie = [(f["t"], f["v"].get(vid)) for f in filas]
        con = [(t, x) for t, x in serie if x is not None]
        motivos = {}
        for f in filas:
            if f["e"].get(vid):
                motivos[f["e"][vid]] = motivos.get(f["e"][vid], 0) + 1
        c = dict(cobertura=round(len(con) / len(serie), 3) if serie else 0.0, sin_valor=motivos)

        if con:
            atraso = (ahora - datetime.fromisoformat(con[-1][0])).total_seconds() / 60 - dia["grilla_min"]
            c["minutos_desde_ultimo_dato"] = max(0, round(atraso))
            if es_hoy and atraso > MAX_ATRASO_MIN:
                alertas.append(f"{vid}: sin datos nuevos hace {round(atraso)} min")
        elif serie:
            alertas.append(f"{vid}: ningún dato en el día")
        if serie and c["cobertura"] < MIN_COBERTURA:
            alertas.append(f"{vid}: solo {c['cobertura']:.0%} de los casilleros tiene dato")

        if meta.get("salto_max"):   # saltos bruscos: se marcan, no se borran (pueden ser reales)
            saltos = [t2 for (t1, a), (t2, b) in zip(serie, serie[1:])
                      if a is not None and b is not None and abs(b - a) > meta["salto_max"]]
            c["saltos"] = saltos
            if saltos:
                alertas.append(f"{vid}: {len(saltos)} salto(s) de más de {meta['salto_max']} {meta['unidad']}")

        if vid + "_nexlab" in dia["variables"]:
            pares = [(f["v"][vid], f["v"][vid + "_nexlab"]) for f in filas
                     if f["v"].get(vid) is not None and f["v"].get(vid + "_nexlab") is not None]
            if pares:
                c["coincide_con_nexlab"] = round(sum(abs(a - b) <= TOL_NEXLAB for a, b in pares) / len(pares), 3)
        por_var[vid] = c

    return {"estado": "revisar" if alertas else "ok", "alertas": alertas, "variables": por_var}

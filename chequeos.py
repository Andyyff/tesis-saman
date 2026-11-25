"""Chequeos de un día ya armado. El resultado va en el JSON del día ("calidad") para que el panel muestre si el
dato es confiable, y alimenta las alertas y los avisos por mail.

Las alertas nunca salen de una foto suelta: salen del volumen del día o de un patrón que se sostiene (pedido de
Latitud, reunión del 25/11/2026). Se separan en dos tipos:
  equipo: el sistema de toma de datos (cámaras que sacan pocas fotos, sensores sin datos, el flujo atrasado).
  datos:  patrones raros con la máquina encendida (muchas fotos con error, una fase de amperaje separada,
          diferencia de temperatura del arroz fuera de rango).
Con la máquina apagada no se evalúan patrones: es normal; solo se informa (tipo info).
"""
from datetime import datetime

MAX_ATRASO_MIN = 90          # el flujo corre cada hora y Nexlab tarda ~10 min: más que esto es una falla
FOTOS_DIA = 144              # una foto cada 10 min por cámara (sacan una cada ~7)
MIN_FOTOS = 0.5              # menos de la mitad de las fotos esperadas: falla la toma de datos
MAX_ERRORES = 0.30           # más del 30 % de las fotos (máquina encendida) sin poder leer una variable
MIN_FOTOS_PARA_ERRORES = 10
DESVIO_FASE_A = 15.0         # A: una fase separada de las otras dos (ej. 90 contra 120)
DIF_TEMP = (2.0, 9.0)        # °C: salida - entrada del arroz con la máquina encendida. Esperado ~5; medido oct-nov:
                             # mediana 5,8, el 98 % entre 0,3 y 8,2 (3-7 dejaba afuera el 23 % de la operación normal)
SOSTENIDO = 3                # casilleros seguidos (30 min) para que un patrón cuente
TOL_NEXLAB = 0.5             # unidades de diferencia que todavía cuentan como "coincide con Nexlab" (para la tesis)


def _alerta(tipo, origen, texto):
    return {"tipo": tipo, "origen": origen, "texto": texto}


def _tramos(filas, condicion):
    """Tramos de al menos SOSTENIDO casilleros seguidos, con la máquina encendida, donde se cumple la condición.
    Devuelve [(desde, hasta, [valores])]."""
    tramos, actual = [], []
    for f in filas:
        x = condicion(f) if f.get("m") == "encendida" else None
        if x is not None:
            actual.append((f["t"], x))
            continue
        if len(actual) >= SOSTENIDO:
            tramos.append(actual)
        actual = []
    if len(actual) >= SOSTENIDO:
        tramos.append(actual)
    return [(t[0][0][11:16], t[-1][0][11:16], [x for _, x in t]) for t in tramos]


def revisar(dia, ahora, avisos=()):
    filas, alertas, por_var = dia["filas"], [], {}
    ts = [f["t"] for f in filas]
    assert ts == sorted(ts) and len(ts) == len(set(ts)), "casilleros desordenados o repetidos"
    es_hoy = dia["fecha"] == ahora.date().isoformat()
    encendidos = [f for f in filas if f.get("m") == "encendida"]
    for a in avisos:
        alertas.append(_alerta("equipo", "flujo", a))

    # ---- máquina
    if filas and not encendidos:
        alertas.append(_alerta("info", "maquina", "máquina apagada todo el día"))
    elif filas:
        horas = len(encendidos) * dia["grilla_min"] / 60
        alertas.append(_alerta("info", "maquina", f"máquina encendida {horas:.1f} h"))

    # ---- equipo: volumen de fotos por cámara
    fraccion = len(filas) * dia["grilla_min"] / (24 * 60)
    for camara, c in dia.get("camaras", {}).items():
        esperadas = FOTOS_DIA * fraccion
        if c["fotos"] < MIN_FOTOS * esperadas:
            alertas.append(_alerta("equipo", camara, f"{camara}: solo {c['fotos']} fotos en el día "
                                   f"(se esperan unas {esperadas:.0f}): revisar la cámara o la subida de fotos"))
        if c["fotos_encendida"] >= MIN_FOTOS_PARA_ERRORES:
            for var, n in c["errores"].items():
                if n / c["fotos_encendida"] > MAX_ERRORES:
                    alertas.append(_alerta("datos", camara, f"{camara}.{var}: {n} de {c['fotos_encendida']} fotos "
                                           f"({n / c['fotos_encendida']:.0%}) sin poder leer, con la máquina encendida"))

    # ---- por variable: cobertura con la máquina encendida y atraso
    for vid, meta in dia["variables"].items():
        if vid.endswith("_nexlab"):
            continue
        con = [f for f in encendidos if f["v"].get(vid) is not None]
        motivos = {}
        for f in encendidos:
            if f["e"].get(vid):
                motivos[f["e"][vid]] = motivos.get(f["e"][vid], 0) + 1
        c = dict(cobertura=round(len(con) / len(encendidos), 3) if encendidos else None, sin_valor=motivos)
        todos = [f for f in filas if f["v"].get(vid) is not None]
        if todos:
            atraso = (ahora - datetime.fromisoformat(todos[-1]["t"])).total_seconds() / 60 - dia["grilla_min"]
            c["minutos_desde_ultimo_dato"] = max(0, round(atraso))
            if es_hoy and atraso > MAX_ATRASO_MIN:
                alertas.append(_alerta("equipo", vid.split(".")[0], f"{vid}: sin datos nuevos hace {round(atraso)} min"))
        if meta.get("salto_max"):   # saltos bruscos: se marcan en los datos, no son alerta
            serie = [(f["t"], f["v"].get(vid)) for f in encendidos]
            c["saltos"] = [t2 for (t1, a), (t2, b) in zip(serie, serie[1:])
                           if a is not None and b is not None and abs(b - a) > meta["salto_max"]]
        if vid + "_nexlab" in dia["variables"]:
            pares = [(f["v"][vid], f["v"][vid + "_nexlab"]) for f in filas
                     if f["v"].get(vid) is not None and f["v"].get(vid + "_nexlab") is not None]
            if pares:
                c["coincide_con_nexlab"] = round(sum(abs(a - b) <= TOL_NEXLAB for a, b in pares) / len(pares), 3)
        por_var[vid] = c

    # ---- equipo: sensores de temperatura del arroz
    for vid in ("clima.temp_entrada", "clima.temp_salida"):
        if vid in dia["variables"] and filas and sum(f["v"].get(vid) is not None for f in filas) < len(filas) / 2:
            alertas.append(_alerta("equipo", "clima", f"{dia['variables'][vid]['nombre']}: sin datos en más de la mitad del día"))

    # ---- datos: una fase de amperaje separada de las otras dos, sostenido
    def fase_separada(f):
        a = [f["v"].get(f"amp.f{i}") for i in (1, 2, 3)]
        if None in a:
            return None
        desv = [abs(a[i] - (sum(a) - a[i]) / 2) for i in range(3)]
        i = max(range(3), key=lambda k: desv[k])
        return f"F{i + 1}" if desv[i] > DESVIO_FASE_A else None
    for desde, hasta, fases in _tramos(filas, fase_separada):
        alertas.append(_alerta("datos", "amp", f"amperaje: la fase {max(set(fases), key=fases.count)} se separa más de "
                               f"{DESVIO_FASE_A:.0f} A de las otras dos entre {desde} y {hasta}"))

    # ---- datos: diferencia de temperatura del arroz fuera de rango, sostenido
    lo, hi = DIF_TEMP
    def temp_fuera(f):
        d = f["v"].get("clima.dif_temp")
        return d if d is not None and not lo <= d <= hi else None
    for desde, hasta, difs in _tramos(filas, temp_fuera):
        extra = " (la salida no está más caliente que la entrada)" if max(difs) <= 0 else ""
        alertas.append(_alerta("datos", "clima", f"temperatura del arroz: salida − entrada entre {min(difs):.1f} y "
                               f"{max(difs):.1f} °C de {desde} a {hasta} (esperado {lo:.0f} a {hi:.0f} °C){extra}"))

    problemas = [a for a in alertas if a["tipo"] != "info"]
    return {"estado": "revisar" if problemas else "ok", "alertas": alertas, "variables": por_var}

# -*- coding: utf-8 -*-
"""
Baja de Nexlab la temperatura y la humedad ambiente de la planta de Samán (una lectura por minuto).
Uso: pip install requests, cambiá DESDE/HASTA (hora de Uruguay) y corré: python descargar_clima.py
Genera en datos_clima/: clima_ancho.csv (fecha, temperatura, humedad), clima_largo.csv y actual.csv.
"""
import os, csv
from datetime import datetime, timedelta, timezone
import requests

DESDE = "2026-10-18"   # primer día, incluido
HASTA = "2026-10-25"   # último día, incluido
SENSORES = {1: "temperatura_c", 2: "humedad_pct"}   # id en Nexlab -> columna
CARPETA = "datos_clima"

BASE = "https://apis.nexlab.com.uy/control/a7b2c3d4/nodes/1/sensors"
UY = timezone(timedelta(hours=-3))


def a_uy(iso):
    """'2026-10-25T13:46:35.198073Z' -> '2026-10-25 10:46:35' (hora de Uruguay)."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UY).strftime("%Y-%m-%d %H:%M:%S")

assert a_uy("2026-10-25T13:46:35.198073Z") == "2026-10-25 10:46:35"


def main():
    os.makedirs(CARPETA, exist_ok=True)

    actual = requests.get(BASE, timeout=60); actual.raise_for_status()
    with open(f"{CARPETA}/actual.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sensor", "valor", "fecha_uy"])
        for s in actual.json():
            if s["id"] in SENSORES:
                w.writerow([SENSORES[s["id"]], s["last_value"], a_uy(s["last_date"])])
                print(f"Ahora: {s['name']} = {s['last_value']} {s['unit']}")

    filas = []   # (fecha_uy, columna, valor)
    dia, fin = datetime.fromisoformat(DESDE), datetime.fromisoformat(HASTA)
    while dia <= fin:
        ini = dia.replace(tzinfo=UY).astimezone(timezone.utc)
        rango = {"startDate": ini.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "endDate": (ini + timedelta(days=1, seconds=-1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for sid, col in SENSORES.items():
            r = requests.get(f"{BASE}/{sid}/history", params=rango, timeout=60); r.raise_for_status()
            datos = r.json()["data"]
            filas += [(a_uy(x["date"]), col, x["value"]) for x in datos]
            print(f"{dia:%Y-%m-%d}  {col:14s} {len(datos):5d} lecturas")
        dia += timedelta(days=1)
    filas.sort()

    with open(f"{CARPETA}/clima_largo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["fecha_uy", "sensor", "valor"]); w.writerows(filas)

    # temperatura y humedad llegan con segundos distintos: se juntan por minuto
    ancho = {}
    for fecha, col, valor in filas:
        ancho.setdefault(fecha[:16], {})[col] = valor
    with open(f"{CARPETA}/clima_ancho.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["fecha_uy", *SENSORES.values()])
        w.writerows([m, *(ancho[m].get(c, "") for c in SENSORES.values())] for m in sorted(ancho))

    print(f"\nListo: {len(filas)} lecturas en {os.path.abspath(CARPETA)}")


if __name__ == "__main__":
    main()

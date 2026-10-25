"""Las dos fuentes de Nexlab: registros de fotos por cámara y sensores de ambiente."""
import os
import requests

FOTOS_URL = "http://sam-analysis.nexlab.com.uy/data"
SENSORES_URL = "https://apis.nexlab.com.uy/control/a7b2c3d4/nodes/1/sensors"
CLIMA = {1: {"variable": "temperatura", "unidad": "°C", "nombre": "Temperatura ambiente",
             "rango": (-10, 50), "salto_max": 5},
         2: {"variable": "humedad", "unidad": "%", "nombre": "Humedad ambiente",
             "rango": (0, 100), "salto_max": 20}}


def registros_fotos(camara, fecha):
    """Lista de registros del día (filename, date, err, input_img_path y campos de Nexlab)."""
    r = requests.get(FOTOS_URL, params={"date": fecha, "env": "prod", "name_filter": camara}, timeout=60)
    r.raise_for_status()
    return r.json() or []


def bajar_foto(url, ruta):
    if not os.path.exists(ruta):
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as f:
            f.write(r.content)
    return ruta


def lecturas_clima(sensor_id, desde_utc, hasta_utc):
    """[(fecha_iso_utc, valor)] del sensor entre dos instantes 'AAAA-MM-DDTHH:MM:SSZ'."""
    r = requests.get(f"{SENSORES_URL}/{sensor_id}/history",
                     params={"startDate": desde_utc, "endDate": hasta_utc}, timeout=60)
    r.raise_for_status()
    return [(x["date"], x["value"]) for x in r.json()["data"]]

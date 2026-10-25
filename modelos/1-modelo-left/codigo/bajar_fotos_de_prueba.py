#!/usr/bin/env python3
"""Baja las fotos de prueba (las que usan los tests) desde el bucket publico de
la plataforma, y las deja en las mismas carpetas que se usaron al desarrollar.

    python3 bajar_fotos_de_prueba.py

La lista exacta esta en fotos_de_prueba.txt (una ruta por linea). Son 2.715
fotos, ~300 MB. Si se corta, se vuelve a correr y sigue donde quedo."""
import os, re, urllib.request
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
BUCKET = "https://sam-240101.s3.sa-east-1.amazonaws.com"

def url_de(nombre):
    m = re.search(r"_(\d{4})-(\d{2})-(\d{2})_", nombre)
    return f"{BUCKET}/{m.group(1)}/{m.group(2)}/{m.group(3)}/{nombre}"

def bajar(ruta):
    destino = os.path.join(AQUI, ruta)
    if os.path.exists(destino) and os.path.getsize(destino) > 1000:
        return "ya estaba"
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    try:
        urllib.request.urlretrieve(url_de(os.path.basename(ruta)), destino)
        return "ok"
    except Exception as e:
        return f"error: {e}"

if __name__ == "__main__":
    rutas = [l.strip() for l in open(os.path.join(AQUI, "fotos_de_prueba.txt")) if l.strip()]
    with ThreadPoolExecutor(max_workers=12) as ex:
        res = list(ex.map(bajar, rutas))
    print(f"{len(rutas)} fotos: {res.count('ok')} bajadas, {res.count('ya estaba')} ya estaban, "
          f"{sum(r.startswith('error') for r in res)} con error")

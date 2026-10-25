"""Pruebas sin internet. GitHub las corre antes de aceptar cualquier cambio.

    python probar.py

1) Cada algoritmo, contra sus fotos de ejemplo: mismo estado y mismo valor (±0,05).
2) El flujo de punta a punta con un Nexlab simulado: grilla, rangos, clima y chequeos.
"""
import csv, glob, json, os, shutil, tempfile
from datetime import datetime

import algoritmos, flujo, nexlab

AQUI = os.path.dirname(os.path.abspath(__file__))


def probar_algoritmos():
    for camara in algoritmos.CAMARAS:
        alg = algoritmos.cargar(camara)
        carpeta = os.path.join(AQUI, "algoritmos", camara, "ejemplos")
        esperado = {f["archivo"]: f for f in csv.DictReader(open(os.path.join(carpeta, "esperado.csv"), encoding="utf-8"))}
        fotos = sorted(glob.glob(os.path.join(carpeta, "*.jpg")))
        salida = alg.leer(fotos)
        assert {s["archivo"] for s in salida} == set(esperado), f"{camara}: no devolvió una fila por foto"
        for s in salida:
            assert set(s) >= {"archivo", "variable", "valor", "estado"}, f"{camara}: no cumple el contrato: {s}"
            assert s["variable"] in alg.VARIABLES, f"{camara}: variable no declarada {s['variable']}"
            e = esperado[s["archivo"]]
            ee = e.get(f"estado_{s['variable']}", e.get("estado"))      # varias variables: un estado por variable
            assert s["estado"] == ee, f"{camara} {s['archivo']} {s['variable']}: estado {s['estado']} (esperado {ee})"
            ve = e[s["variable"]]
            if ve == "":
                assert s["valor"] is None, f"{camara} {s['archivo']}: dio {s['valor']}, no debía medir"
            else:
                assert abs(float(s["valor"]) - float(ve)) <= 0.05, f"{camara} {s['archivo']}: {s['valor']} (esperado {ve})"
        print(f"OK algoritmo {camara} ({alg.VERSION}): {len(fotos)} fotos de ejemplo")


def probar_flujo():
    """Un día simulado con las fotos de ejemplo de top renombradas a la misma fecha."""
    tmp = tempfile.mkdtemp()
    fotos = sorted(glob.glob(os.path.join(AQUI, "algoritmos", "top", "ejemplos", "*.jpg")))
    horas = ["00-03-10", "00-09-50", "00-12-00", "00-24-30", "00-31-00", "00-44-00", "00-58-59"]
    regs = []
    for foto, h in zip(fotos, horas):
        nombre = f"RIC-0001-TOP_2026-10-25_{h}.jpg"
        shutil.copy(foto, os.path.join(tmp, nombre))
        regs.append({"filename": nombre, "input_img_path": os.path.join(tmp, nombre), "err": "", "opening": 5.0})
    regs.append(dict(regs[0]))                                   # registro repetido: se descarta
    regs[2]["err"] = "bar"                                        # Nexlab con error: sin referencia

    clima = {1: [("2026-10-25T03:01:00Z", 15.0), ("2026-10-25T03:02:00Z", 16.0), ("2026-10-25T03:15:00Z", 99.0)],
             2: [("2026-10-25T03:01:00Z", 70.0), ("2026-10-25T03:45:00Z", 150.0)]}
    viejo = (nexlab.registros_fotos, nexlab.bajar_foto, nexlab.lecturas_clima, flujo.DATOS, flujo.CACHE_FOTOS)
    nexlab.registros_fotos = lambda camara, fecha: [dict(r) for r in regs] if camara == "top" else []
    nexlab.bajar_foto = lambda url, ruta: url
    nexlab.lecturas_clima = lambda sid, a, b: clima[sid]
    flujo.DATOS, flujo.CACHE_FOTOS = os.path.join(tmp, "datos"), os.path.join(tmp, "cache")
    try:
        ahora = datetime.fromisoformat("2026-10-25T01:00:00-03:00")
        flujo.correr(["2026-10-25"], ahora)
        flujo.correr(["2026-10-25"], ahora)                     # segunda corrida: no reprocesa nada
        lect = flujo.leer_csv(os.path.join(flujo.DATOS, "lecturas", "top", "2026-10-25.csv"))
        assert len(lect) == 7, f"esperaba 7 lecturas sin duplicar, hay {len(lect)}"
        dia = json.load(open(os.path.join(flujo.DATOS, "panel", "2026-10-25.json"), encoding="utf-8"))
        f = {x["t"][11:16]: x for x in dia["filas"]}
        assert len(dia["filas"]) == 6, "una hora = 6 casilleros de 10 min"
        medido = {x["t"][11:19]: float(x["valor"]) for x in lect if x["valor"] != ""}   # la precisión la prueba probar_algoritmos
        assert f["00:00"]["v"]["top.apertura"] == medido["00:09:50"], "00:00 debe quedarse con la última lectura válida (00:09:50)"
        assert f["00:10"]["v"]["top.apertura"] == medido["00:12:00"] and "top.apertura_nexlab" not in f["00:10"]["v"]
        assert f["00:40"]["e"]["top.apertura"] == "color_inutilizable", "sin valor: queda vacío con el motivo"
        assert f["00:50"]["e"]["top.apertura"] == "mango_no_visible"
        assert f["00:00"]["v"]["clima.temperatura"] == 15.5, "promedio del casillero"
        assert "clima.temperatura" not in f["00:10"]["v"], "99 °C está fuera de rango y no llega al panel"
        assert f["00:40"]["e"]["clima.humedad"] == "sin_dato"
        assert dia["calidad"]["variables"]["top.apertura"]["cobertura"] == 0.667
        assert set(json.load(open(os.path.join(flujo.DATOS, "panel", "indice.json")))["dias"]) == {"2026-10-25"}
        est = json.load(open(os.path.join(flujo.DATOS, "panel", "estado.json"), encoding="utf-8"))
        assert est["camaras"]["top"] == {"nexlab": 7, "ultima_foto": "2026-10-25T00:58:59-03:00", "procesadas": 7}, est["camaras"]["top"]
        hist = json.load(open(os.path.join(flujo.DATOS, "panel", "historial.json"), encoding="utf-8"))["dias"]
        top = hist[0]["camaras"]["top"]
        assert top["fotos"] == 7 and top["variables"]["apertura"]["medidas"] == len(medido), top
        pbi = {(m["fecha_hora"], m["variable"]): m for m in flujo.leer_csv(os.path.join(flujo.DATOS, "powerbi", "mediciones.csv"))}
        assert float(pbi[("2026-10-25 00:00", "top.apertura")]["valor"]) == medido["00:09:50"], "Power BI: mismo valor que el panel"
        assert pbi[("2026-10-25 00:40", "top.apertura")]["motivo"] == "color_inutilizable"
        print(f"OK flujo de punta a punta: calidad {dia['calidad']['estado']}, alertas: {dia['calidad']['alertas']}")
    finally:
        nexlab.registros_fotos, nexlab.bajar_foto, nexlab.lecturas_clima, flujo.DATOS, flujo.CACHE_FOTOS = viejo
        shutil.rmtree(tmp)


if __name__ == "__main__":
    probar_algoritmos()
    probar_flujo()
    print("Todo OK")

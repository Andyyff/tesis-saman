"""Avisos por mail de las alertas, con los avisos (issues) de GitHub.

    python avisar.py             # después de flujo.py: avisa las alertas nuevas de hoy y de ayer
    python avisar.py --inicial   # marca todas las alertas actuales como ya avisadas, sin avisar (para arrancar)

Un aviso por día ("Alertas saman AAAA-MM-DD"): la primera alerta del día lo abre y las siguientes se agregan como
comentario. GitHub manda un mail por cada aviso o comentario a quienes siguen el repositorio (Watch). Solo se avisan
alertas de equipo y de datos; las informativas no. Lo ya avisado queda en datos/panel/avisadas.json.
Usa la CLI de GitHub (gh) con GH_TOKEN.
"""
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone

DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "panel")
AVISADAS = os.path.join(DATOS, "avisadas.json")
ETIQUETA = "alerta"
PAGINA = "https://andyyff.github.io/tesis-saman/monitoreo.html"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def alertas_del_dia(fecha):
    ruta = os.path.join(DATOS, f"{fecha}.json")
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as f:
        return [a for a in json.load(f)["calidad"]["alertas"] if a["tipo"] in ("equipo", "datos")]


def nuevas(fecha, avisadas):
    """Alertas del día cuya clave todavía no se avisó."""
    return [a for a in alertas_del_dia(fecha) if f"{fecha}|{a['clave']}" not in avisadas]


def texto(alertas):
    return "\n".join(f"- **{a['tipo']}** · {a['texto']}" for a in alertas)


def avisar(fecha, alertas):
    titulo = f"Alertas saman {fecha}"
    abiertos = json.loads(gh("issue", "list", "--label", ETIQUETA, "--state", "all", "--search", f'"{titulo}" in:title',
                             "--json", "number,title"))
    numero = next((i["number"] for i in abiertos if i["title"] == titulo), None)
    if numero is None:
        gh("label", "create", ETIQUETA, "--color", "D93F0B", "--description", "Alertas del flujo (equipo o datos)", "--force")
        cuerpo = (f"Alertas del {fecha}. **Equipo**: falla la toma de datos (cámaras, sensores, flujo). "
                  f"**Datos**: algo raro con la máquina encendida.\n\n{texto(alertas)}\n\nDetalle y fotos: {PAGINA}")
        print(gh("issue", "create", "--title", titulo, "--label", ETIQUETA, "--body", cuerpo).strip())
    else:
        gh("issue", "comment", str(numero), "--body", f"Nuevas alertas:\n\n{texto(alertas)}")
        print(f"comentario en #{numero}")


def main(inicial=False):
    avisadas = set(json.load(open(AVISADAS, encoding="utf-8"))) if os.path.exists(AVISADAS) else set()
    if inicial:
        fechas = sorted(n[:10] for n in os.listdir(DATOS) if n[:4].isdigit() and n.endswith(".json"))
    else:
        hoy = datetime.now(timezone(timedelta(hours=-3))).date()   # hora de Uruguay
        fechas = [str(hoy - timedelta(days=1)), str(hoy)]
    for fecha in fechas:
        lista = nuevas(fecha, avisadas)
        if lista and not inicial:
            avisar(fecha, lista)
        avisadas |= {f"{fecha}|{a['clave']}" for a in lista}
    with open(AVISADAS, "w", encoding="utf-8") as f:
        json.dump(sorted(avisadas), f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main("--inicial" in sys.argv)

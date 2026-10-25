# Flujo de datos para el panel — Samán / Latitud

Baja de Nexlab las fotos de las cámaras y el clima, corre nuestros algoritmos, alinea todo en una grilla de 10 minutos y deja archivos JSON que el panel lee. GitHub lo corre solo cada hora.

```
Nexlab fotos ─┐
              ├─► algoritmos/<cámara> ─► grilla 10 min ─► chequeos ─► datos/panel/AAAA-MM-DD.json
Nexlab clima ─┘
```

## Correrlo en tu compu

```
pip install -r requirements.txt
python probar.py                 # pruebas sin internet (deben dar "Todo OK")
python flujo.py                  # hoy y ayer
python flujo.py 2026-10-20       # un día puntual
```

## Para los que trabajan en los algoritmos

Cada cámara es una carpeta `algoritmos/<cámara>/` con su código y un `__init__.py` que cumple el contrato (ver `algoritmos/__init__.py`): `VERSION`, `VARIABLES` y `leer(rutas)`. Por dentro podés cambiar lo que quieras: el flujo y el panel solo ven el contrato.

- **Mejorar un algoritmo:** cambiá el código, subí `VERSION` y, si cambian los resultados esperados, actualizá `ejemplos/esperado.csv`. GitHub corre `probar.py` antes de aceptar el cambio.
- **Sumar una cámara:** creá su carpeta con el contrato y fotos de ejemplo, y agregala a `CAMARAS` en `algoritmos/__init__.py`.
- Si un algoritmo falla, el flujo sigue con los demás y reintenta sus fotos en la próxima corrida.

## Para los que arman el panel

Leé `datos/panel/indice.json` (días disponibles) y después `datos/panel/AAAA-MM-DD.json`:

```json
{
  "fecha": "2026-10-25", "zona_horaria": "-03:00", "grilla_min": 10, "generado": "...",
  "variables": { "top.apertura": {"nombre": "Apertura válvula", "unidad": "0-10", "fuente": "top", "version": "top-v3"},
                 "top.apertura_nexlab": {...}, "clima.temperatura": {...}, "clima.humedad": {...} },
  "filas": [ {"t": "2026-10-25T00:00-03:00",
              "v": {"top.apertura": 8.95, "top.apertura_nexlab": 9.0, "clima.temperatura": 15.5},
              "e": {"clima.humedad": "sin_dato"}} ],
  "calidad": {"estado": "ok | revisar", "alertas": ["..."],
              "variables": {"top.apertura": {"cobertura": 0.97, "minutos_desde_ultimo_dato": 12,
                                              "sin_valor": {"mango_no_visible": 3}, "saltos": [], "coincide_con_nexlab": 0.96}}}
}
```

- `v`: valor de cada variable en el casillero `[t, t+10 min)`. Si falta, no hay dato válido y `e` dice por qué. **Nunca rellenar ni interpolar huecos.**
- Armá los gráficos recorriendo `variables`, no con nombres fijos: así una variable nueva aparece sola.
- Mostrá `calidad.estado` y `calidad.alertas` en la página.

## Reglas de los datos

- **Grilla:** casilleros de 10 min en hora de Uruguay. Cámaras: última lectura válida del casillero. Clima (1 lectura por minuto): promedio del casillero.
- **Veracidad:** cada lectura guarda foto de origen, estado y versión del algoritmo (`datos/lecturas/<cámara>/AAAA-MM-DD.csv`). Un valor fuera del rango declarado no llega al panel. Los saltos bruscos se marcan, no se borran. El valor de Nexlab va al lado como referencia.
- **Frecuencia:** el flujo corre cada hora (minuto 17). La página puede tener hasta ~1 hora de atraso.

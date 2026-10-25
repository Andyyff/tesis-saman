# Tesis Samán — contexto para Claude Code

Tesis de grado UM (Ciencia de Datos para Negocios) con **Latitud (Fundación LATU)**: monitoreo por cámara del pulido por abrasión en el molino arrocero de **Samán, José Pedro Varela (Lavalleja)**. Equipo: Andrés Fernández (modelo top, flujo), Alfonso Valek (modelo left), Matías Cárpena (modelo amp). Tutor: Mateo Sere. Contacto en Latitud: Mauro.

**Nexlab** es la empresa que instaló las cámaras y da la plataforma de monitoreo actual. No es nuestro cliente: sus resultados son la referencia que nuestros modelos buscan superar.

Responder en castellano rioplatense, simple. Modo de trabajo preferido: cambios chicos y completos, sin código "por si acaso" (estilo ponytail).

## Qué hay en esta carpeta

| Ruta | Qué es |
|---|---|
| `flujo.py`, `nexlab.py`, `chequeos.py`, `probar.py`, `algoritmos/` | **El flujo hacia el panel** (top, left y amp). Ver README.md. Correr con `.venv\Scripts\python.exe` |
| `algoritmos/top/` | Copia del modelo top usada por el flujo. **Es la versión vigente para el flujo**; `modelos/2-modelo-top/` es la del entregable 2 (no editar las dos por separado) |
| `modelos/` | Entregable 2: los 3 modelos tal como se entregaron (left, top, amp), con su README y resultados |
| `scripts/descargar_top.py` | Baja fotos + JSON de Nexlab por cámara y día (modo explorar/descargar). Sirve para top/left/amp cambiando FILTRO |
| `scripts/descargar_clima.py` | Baja temperatura y humedad ambiente a CSV |
| `entregables/` | Entregable 1+2 (docx) y PDF del segundo entregable (versión casi final enviada) |
| `.github/workflows/` | `flujo.yml` (corre cada hora y commitea `datos/`), `pruebas.yml` (corre `probar.py` en cada cambio) |

## Fuentes de datos (verificadas el 25/10/2026)

- **Fotos:** `GET http://sam-analysis.nexlab.com.uy/data?date=AAAA-MM-DD&env=prod&name_filter={top|left|amp}` → lista de registros `{filename, date, err, input_img_path, output_img_path, + campos de Nexlab}`. Top: `opening`. Left: `angle`, `weight_dis_a/_b(_2,_3)`, `weight_size_*`, y muchos `analysis_*`. Las fotos están en S3 (`sam-240101.s3.sa-east-1.amazonaws.com/AAAA/MM/DD/...`).
- La hora del `filename` (`RIC-0001-TOP_2026-10-25_11-11-35.jpg`) es **hora de Uruguay (-03:00, sin horario de verano)**. Cada cámara saca una foto cada ~6,7 min, no sincronizadas entre sí. Nexlab publica con ~10 min de atraso.
- **Sensores:** `GET https://apis.nexlab.com.uy/control/a7b2c3d4/nodes/1/sensors` → 28 sensores con `last_value`, `last_date`, `mqtt_topic`. Histórico: `.../sensors/{id}/history?startDate=...Z&endDate=...Z` → `{"data":[{"date","value",...}]}` en **UTC**. Sin autenticación.
  - Temperatura ambiente = id 1 (`samanmaquina1/temperaturaAmbiente`, °C). Humedad ambiente = id 2 (%). Llegan **1 por minuto**, sin cortes largos en la semana revisada.
  - Otros: 3 Temp. salida arroz, 4 Temp. entrada arroz, 5 Amperaje, 26-28 Amperaje F1-F3, 6 Potencia, 7 Ángulo, 25 Apertura superior, 8 Peso total, 9-24 pesos (mm).
- Origen físico del clima: sensor publicado por MQTT desde la planta. Marca, ubicación y precisión **sin confirmar** (preguntar a Mauro/Nexlab).

## Los 3 modelos (visión por computadora clásica, OpenCV)

- **top** (`vision_top.py`, v3): apertura de válvula 0-10 ubicando el mango verde de la palanca sobre su curva. Alineación por similitud ORB+RANSAC (con alineación "prestada" de una foto vecina ≤3 h), balance de blancos, color+forma. Calibración `apertura = 0,02909·posicion_px + 8,9553`. Estados: medida / color_inutilizable / mango_no_visible / mango_no_encontrado / alineacion_fallida. Resultado: mide 98,9 % de 1.474 fotos (Nexlab 66,4 %), auditoría 90/90.
- **left** (Alfonso, `modelos/1-modelo-left/codigo/vision_left.py`): mm entre tapón verde y pesa contando hendiduras de la rosca (FFT, 10 mm cada una) + ángulo de palanca. 96 % de 2.715 fotos.
- **amp** (Matías, V10 congelada `modelos/3-modelo-amp/amp_v10.py` + `model/amp_v10_bundle.joblib`): lee displays F1/F2/F3 (HOG/SVM + 7 segmentos). `AMPV10().predict_image(ruta)` → 3 filas por foto. 93,4 % de 3.093 lecturas (Nexlab 76,6 %). Verificar con `python verify_v10.py` (9/9).

## El flujo al panel (decisiones tomadas)

- **Arquitectura:** GitHub + GitHub Actions (gratis). Corre cada hora, procesa solo fotos nuevas, escribe `datos/lecturas/<cámara>/AAAA-MM-DD.csv` (auditoría) y `datos/panel/AAAA-MM-DD.json` + `indice.json` (lo que lee la página). El panel se arma con Claude.
- **Contrato de algoritmo** (`algoritmos/__init__.py`): `VERSION`, `VARIABLES` (unidad, nombre, rango, salto_max, campo nexlab) y `leer(rutas) -> [{archivo, variable, valor, estado, detalle}]`. Cambiar un algoritmo no rompe el flujo ni la página.
- **Grilla común de 10 min** en hora de Uruguay. Cámaras: última lectura válida del casillero. Clima: promedio. Sin dato → null + motivo; **nunca interpolar**.
- **Veracidad:** fuera de rango no llega al panel; saltos se marcan; valor Nexlab al lado; `calidad` en cada JSON (cobertura, atraso, motivos, saltos, coincidencia con Nexlab).
- `python probar.py`: algoritmos contra `ejemplos/esperado.csv` + flujo simulado de punta a punta (sin internet). Debe dar "Todo OK".

## Operación (desde 25/10/2026)

- El flujo corre **en GitHub Actions** (repo público https://github.com/Andyyff/tesis-saman): `flujo.yml` cada hora, `historia.yml` para cargar días pasados en paralelo (a mano, con desde/hasta). Versiones de Python (3.12) y librerías fijadas igual que la PC: con OpenCV 5 left mide distinto.
- En la PC de Andrés, la tarea "Tesis Saman - flujo" (Programador de tareas, cada hora a los :05) solo hace `git pull` con `actualizar_datos.cmd` (log en `datos/actualizar.log`), para que OneDrive/Power BI tengan lo último. `correr_flujo.cmd` corre el flujo en la PC a mano.
- Salida para **Power BI**: `datos/powerbi/mediciones.csv`, `variables.csv`, `calidad.csv` (UTF-8, punto decimal). Está en OneDrive, así que Power BI la lee de ahí.
- Las fotos se borran de `.cache/` apenas se procesan.

## Pendientes

1. Correr `python flujo.py` contra Nexlab real por primera vez (solo se probó simulado).
2. Left y amp ya están en el flujo (25/10). Falta decidir si left se compara con Nexlab (`angle`, `weight_dis_a/_b`): no está confirmado que midan lo mismo. Nexlab marca sus fallas de amp con -1 (el flujo descarta referencias fuera de rango).
3. Decidir repo público o privado (público: el panel lee los JSON directo y sin límite de minutos, pero datos visibles; privado: entra en 2.000 min/mes, pero la página necesita otra forma de leer). Consultar con Mauro.
4. Páginas (GitHub Pages, https://andyyff.github.io/tesis-saman/): `index.html` = panel de datos; `monitoreo.html` = monitoreo de los modelos para el equipo y Latitud (salud del flujo con `datos/panel/estado.json`, alcance por día con `historial.json`, alertas, visor de fotos). Antes: panel (página estática que lee `datos/panel/`, se refresca cada 5 min). Prueba local: `python -m http.server 8000` en esta carpeta. Falta definir con Latitud en qué servidor se publica.
5. Riesgo conocido: top procesando de a una hora tiene menos fotos vecinas para prestar alineación → puede medir algo menos que procesando el día entero.
6. No hay prueba del caso "un algoritmo falla" (el flujo lo atrapa y reintenta, sin test).
7. Del entregable 2, abiertos: falta archivo GT de amp en el paquete; left le falta `vision_left_v2_25-09.py`; el diagrama de left dice "fichas magenta" (el código usa perilla); CSV de left con el ángulo viejo; la curva de top podría pasar a arco y expresarse en grados.

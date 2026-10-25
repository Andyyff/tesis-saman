# Algoritmo LEFT — código

| archivo | qué es |
|---|---|
| `vision_left.py` | **el algoritmo** (versión 3, 03/10/2026) |
| `medir_dia.py` | baja las fotos de un día desde la plataforma y arma un CSV |
| `referencia_left.jpg` | la foto patrón contra la que se alinean las demás (no borrar) |
| `fondo_fijo.npy` | máscara de los objetos de color que están siempre en el mismo lugar (no borrar) |
| `tests.py` | suite de 13 tests (`--rapido` para una versión corta) |
| `revisar.py` | dibuja el resultado de una foto, ampliado, para revisar a ojo |
| `muestra10.py` | dibuja los 10 casos de muestra |
| `antes_despues.py` | los 10 casos, versión vieja a la izquierda y nueva a la derecha |
| `vision_left_v2_25-09.py` | la versión anterior (25/09), para comparar |
| `armar_corpus_left.py` | baja fotos de varios días y las separa por tipo de caso |
| `comparar.py` | compara dos corridas sobre las mismas lecturas |
| `bajar_fotos_de_prueba.py` + `fotos_de_prueba.txt` | baja las fotos que usan los tests |

## Instalar y usar

```bash
pip install -r requirements.txt
python3 medir_dia.py 2026-09-19 --salida mediciones.csv
```

Columnas del CSV: `fecha_hora, archivo, barra, estado, distancia_pasos, distancia_mm, distancia_px, angulo_grados, confianza_distancia, confianza_angulo, color_pesa, detalle`.

- `estado`: `medida` · `sin_pesa` (la barra no tiene pesa; no es una falla) · `no_medida` (`detalle` dice por qué)
- `angulo_grados` es uno por foto y se repite en las dos filas (a y b).

## Tests

Necesitan las fotos de prueba. Se bajan con `python3 bajar_fotos_de_prueba.py` (2.715 fotos, ~300 MB; si se corta, se vuelve a correr y sigue).

```bash
python3 tests.py --rapido     # unos minutos
python3 tests.py              # completo, ~40 min
```

## Comparar antes y después

```bash
python3 antes_despues.py vision_left_v2_25-09.py salida/
```

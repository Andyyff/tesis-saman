# Modelo de la cámara "top" — versión 3

Modelo propio que mide la apertura de la válvula (escala 0 a 10) a partir de las fotos de la cámara "top", ubicando el mango verde de la palanca. Escrito desde cero en Python con OpenCV; no usa código de Nexlab.

**Resultado en 8 días (1.474 fotos):** mide el 98,9 % de las fotos (Nexlab: 66,4 %), auditoría visual al azar 90 de 90 correctas, y concuerda con Nexlab a ±0,3 unidades en el 97 % de las fotos donde miden los dos. El detalle está en el informe de avance.

## Cómo probarlo en 2 minutos (sin internet)

```
pip install opencv-python numpy matplotlib
cd codigo
python medir_dia_top.py ../fotos-ejemplo --salida prueba.csv
```

Compará `prueba.csv` con `fotos-ejemplo/resultado_esperado.csv`. Cada foto de ejemplo tiene en su nombre el caso que representa: válvula abierta, a media apertura (donde Nexlab dio error), cerrada (donde Nexlab dijo 8,6), foto verde, operario moviendo la palanca, color irrecuperable y mango tapado. En los dos últimos el modelo no mide e informa el motivo.

Para ver cómo analiza una foto, con flechas explicativas:

```
python explicar_foto_top.py "../fotos-ejemplo/2_media_6-3_nexlab_dio_error__RIC-0001-TOP_2026-08-18_05-57-04.jpg" explicacion.png
```

## Contenido

| Carpeta / archivo | Qué es |
| --- | --- |
| `codigo/vision_top.py` | El modelo: alineación, corrección de color, búsqueda del mango, medición y calibración. Comentado en castellano. |
| `codigo/medir_dia_top.py` | Herramienta de uso: una carpeta de fotos → un CSV con la apertura de cada foto. |
| `codigo/foto_referencia_top.jpg` | Foto de referencia (02/09/2026 00:04:53). Todas las fotos se alinean contra ella. |
| `codigo/descargar_top.py` | Baja fotos y valores de Nexlab del servidor (modo "explorar" para elegir días, modo "descargar" para bajarlos). |
| `codigo/comparar_nexlab_top.py` | Compara nuestra salida con los valores de Nexlab de un día: reporte y gráfico. |
| `codigo/calibrar_top.py` | Rehace la calibración 0-10 con varios días, validando con un día afuera por vez. |
| `codigo/errores_nexlab.py` | Resume, día por día, los errores declarados por Nexlab. |
| `codigo/explicar_foto_top.py` | Dibuja una foto con flechas que explican qué usa el modelo. |
| `resultados/` | Para cada uno de los 8 días: CSV con la medición de cada foto, reporte de comparación con Nexlab y gráfico. Además, los errores de Nexlab en 53 días. |
| `verificacion/` | La foto explicada con flechas, las hojas de la auditoría al azar (60 fotos) y la muestra de fotos donde Nexlab falló (30 fotos), con la medición dibujada. |
| `fotos-ejemplo/` | 7 fotos reales, una por tipo de caso, y el resultado esperado. |

## Columnas del CSV de salida

| Columna | Significado |
| --- | --- |
| `estado` | `medida`, `color_inutilizable`, `mango_no_visible`, `mango_no_encontrado` o `alineacion_fallida` |
| `apertura` | Escala 0-10 (vacía si no se midió) |
| `posicion_px` | Píxeles recorridos por el mango a lo largo de su curva, desde la foto de referencia |
| `confianza` | 1,0 = color y forma coinciden; menos si se usó la alineación de una foto vecina, si el color se corrigió o si la forma no confirma |
| `metodo` | `color+forma` o `color` |
| `tinte_camara` | Qué tan alterado está el color (1 = normal; más de 6 = irrecuperable) |
| `detalle` | Notas en castellano: por qué no se midió, qué corrección se aplicó |

## Calibración vigente

`apertura = 0,02909 × posicion_px + 8,9553` (1 unidad = 34,4 px). Ajustada contra Nexlab con 682 fotos de 4 días (21/08, 28/08, 02/09, 04/09). Vale para la cámara en su posición desde el 21/08; si la cámara se mueve, hace falta una referencia y una calibración nuevas (`calibrar_top.py`).

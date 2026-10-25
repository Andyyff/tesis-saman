# Entregable 2 — Modelos left, top y amp

Tesis UM, en conjunto con Latitud. Monitoreo por cámara del pulido por abrasión en el molino arrocero de José Pedro Varela.

Esta carpeta reúne los tres modelos propios de visión por computadora, uno por cámara. El informe general de avance se entrega por separado y explica cada modelo, sus resultados y sus límites.

## Qué hay en cada carpeta

**1-modelo-left/** — Distancia en milímetros entre el tapón verde y cada pesa, e inclinación de la palanca.
Contiene el informe del modelo (`README.md`), un esquema de cómo funciona, una medición real dibujada sobre la foto, los resultados sobre 508 fotos de 44 días (`resultados-508-fotos.csv`) y el código completo en `codigo/` (ver `codigo/LEEME.md`). Las 2.715 fotos de prueba no se incluyen por tamaño; se bajan con `codigo/bajar_fotos_de_prueba.py`.

**2-modelo-top/** — Apertura de la válvula, en la escala de 0 a 10.
Contiene el código completo, la foto de referencia, 7 fotos de ejemplo con su resultado esperado, los resultados de 8 días con la comparación contra Nexlab y las hojas de verificación visual. Se puede correr sin internet (ver `2-modelo-top/LEEME.md`):

```
pip install opencv-python numpy matplotlib
cd 2-modelo-top/codigo
python medir_dia_top.py ../fotos-ejemplo --salida prueba.csv
```

**3-modelo-amp/** — Lectura de los displays de corriente F1, F2 y F3 (versión V10).
Versión V10 congelada y lista para correr: el código de inferencia completo (`amp_v10.py`), todos los modelos ya entrenados (`model/amp_v10_bundle.joblib`), 3 fotos de ejemplo y los resultados del test de 3.093 lecturas. Para verificarla (ver `3-modelo-amp/README.md`):

```
cd 3-modelo-amp
pip install -r requirements.txt
python verify_v10.py      # debe informar 9/9 lecturas coincidentes
```

## Resultados principales

| Cámara | Respuestas del modelo propio | Respuestas de Nexlab |
| --- | --- | --- |
| left | 96 % (2.715 fotos, 44 días) | — |
| top | 98,9 % (1.474 fotos, 8 días) | 66,4 % |
| amp | 93,4 % (3.093 lecturas, 5 días) | 76,6 % |

En los tres modelos, cuando no se puede leer una foto, el resultado indica el motivo en lugar de devolver un número.

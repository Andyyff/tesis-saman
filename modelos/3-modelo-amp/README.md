# AMP V10 — modelo final reproducible

Esta carpeta contiene **la versión V10 congelada y ejecutable** del lector de amperímetro AMP. No incluye V1–V9 porque esas versiones fueron etapas de desarrollo; V10 integra las capas que quedaron vigentes.

## Qué recibe y qué devuelve

Entrada: fotografías originales AMP, equivalentes a `input_img_path`.

Salida: tres filas por fotografía:
- F1
- F2
- F3

Para cada fase devuelve un valor numérico o un estado `NO_VALIDO_*` si la lectura no supera los controles del modelo.

## Qué contiene V10

El pipeline integrado realiza, en este orden:

1. rotación de la foto original;
2. alineación geométrica ORB + RANSAC contra una referencia congelada;
3. extracción de F1/F2/F3 y de sus cuatro dígitos;
4. lector visual HOG/SVM;
5. evidencia física de los siete segmentos;
6. clasificador híbrido/meta;
7. lectores global y específico por posición;
8. rescates conservadores de V6/V8/V9;
9. detección **visual e independiente** del punto decimal;
10. especialista V10 para confusiones entre 5, 6, 8 y 9;
11. decisión final: valor o `NO_VALIDO`.

El punto decimal no se infiere por la magnitud del número.

## Archivos importantes

- `amp_v10.py`: implementación completa de inferencia V10.
- `run_v10.py`: ejecutable para una foto o una carpeta.
- `model/amp_v10_bundle.joblib`: **todos los modelos ya entrenados y congelados + imagen de referencia**. No hace falta disponer de los datasets de entrenamiento para ejecutar V10.
- `requirements.txt`: dependencias usadas para congelar el modelo.
- `verify_v10.py`: prueba de reproducción con tres fotografías incluidas.
- `examples/`: un caso normal, un caso donde actúa el especialista V10 y un caso rechazado por alineación.
- `resultados/`: evidencia del último test externo, sin las 1.031 fotos.

## Instalación

Con Python 3.11 o superior:

```bash
python -m pip install -r requirements.txt
```

## Uso

Una imagen:

```bash
python run_v10.py "ruta/foto.jpg" --out resultado.csv
```

Una carpeta completa:

```bash
python run_v10.py "ruta/carpeta_fotos" --out predicciones.csv
```

Para conservar columnas técnicas de diagnóstico:

```bash
python run_v10.py "ruta/carpeta_fotos" --out predicciones.csv --details
```

## Verificación de la entrega

```bash
python verify_v10.py
```

Debe informar `9/9` lecturas coincidentes con la salida congelada esperada. Los tres ejemplos cubren: lectura normal, corrección del especialista 5/6/8/9 y rechazo por alineación.

## Último test externo congelado

Se evaluó V10 sobre 5 días nuevos, 1.031 fotografías y 3.093 lecturas F1/F2/F3.

| Métrica | V10 | Nexlab |
|---|---:|---:|
| Respondidas | 2.888 | 2.368 |
| Correctas | 2.880 | 2.353 |
| Incorrectas | 8 | 15 |
| Rechazadas | 205 | 725 |
| Cobertura | 93,37% | 76,56% |
| Precisión cuando responde | 99,72% | 99,37% |

El ground truth de esa evaluación se construyó por inspección visual de las 3.093 lecturas. Las fotografías de `output_img_path` de Nexlab no se utilizaron como entrada de V10.

## Reproducibilidad

El archivo `.joblib` evita reentrenar al ejecutar. Es la forma correcta de entregar el modelo operativo: código de inferencia + pesos/modelos congelados + referencia geométrica. Para reproducir **el entrenamiento desde cero** sí serían necesarios los datasets de desarrollo, pero no son necesarios para usar la V10 entregada.

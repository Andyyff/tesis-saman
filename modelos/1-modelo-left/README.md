# Entregable 2 — Informe de avance · **Modelo LEFT**

**Tesis UM · Ciencia de Datos para Negocios · con Latitud (Fundación LATU)**
Monitoreo por cámara del pulido por abrasión — molino arrocero, José Pedro Varela.
Autor: Alfonso Valek · Estado al **06/10/2026**

> Esta carpeta cubre **uno de los tres modelos** (cámara *left*). Se combina con las carpetas
> de los otros dos modelos para armar el entregable completo.

---

## 1. Qué hace

La planta tiene una cámara fija que saca una foto cada ~6 minutos de **dos varillas con pesas**.
El modelo lee cada foto y devuelve, por varilla:

- **la distancia en milímetros** entre el tapón verde y la pesa;
- **el ángulo** de la palanca;
- un **estado** (medida / sin pesa / no se pudo, y por qué) y una **confianza** de 0 a 1.

Es **visión por computadora clásica**: no hay entrenamiento ni modelo estadístico. Son reglas
geométricas y de color calibradas a mano. Las fotos sirven para calibrar y para validar, no para
entrenar.

## 2. Cómo funciona, en simple

La varilla tiene una **rosca con una hendidura cada 10 mm**. Esa rosca es la regla del sistema.

1. **Alinear.** Cada foto se compara con una foto de referencia y se corrige si la cámara se
   corrió. Solo se permite correr y girar: la cámara está atornillada, no puede deformar la
   imagen. Una perilla roja de la máquina hace de testigo: después de alinear tiene que quedar
   en su lugar.
2. **Encontrar la varilla.** Se busca el patrón repetido de la rosca (transformada de Fourier).
   Donde ese patrón aparece, hay varilla.
3. **Ubicar los dos extremos.** El **tapón verde** por color, y la **pesa** por color y porque
   tapa la barra.
4. **Contar hendiduras.** Se cuentan las que hay entre el tapón y la pesa: **hendiduras × 10 = mm**.
   Como se cuenta sobre la propia varilla, el resultado **no depende de a qué distancia esté la
   cámara**.
5. **Decidir si se puede afirmar.** Si falta el tapón, el color está roto o algo tapa la barra,
   el modelo **se abstiene y explica por qué**, en vez de devolver un número inventado.

Ver `01-como-funciona.png` (el recorrido completo) y `02-ejemplo-medicion.png` (una medición
real dibujada sobre la foto: cruz = tapón, círculo = pesa, líneas verdes = el ángulo).

---

## 3. Resultados preliminares

Sobre **2.715 fotos** de 44 días. Las tres columnas miden cosas distintas y conviene no
mezclarlas.

| Qué | Pregunta que responde | Resultado |
|---|---|---|
| **Cobertura** | ¿da una respuesta? | **96 %** de las varillas da distancia o "sin pesa". El 4 % restante se abstiene **explicando el motivo** |
| **Precisión** (repetibilidad) | si mide dos veces seguidas, ¿repite? | **0,5 – 1,0 mm** entre fotos consecutivas. Ángulo: **0,1°** |
| **Exactitud de la escala** | ¿un milímetro es un milímetro? | **validada por debajo del 1 %** contra la ficha física de la varilla que entregó Latitud (+0,19 % y −0,88 % según la barra) |
| **Límites físicos** | ¿alguna medida imposible? | **0 de 999** lecturas fuera del largo real de la barra |
| **Robustez** | ¿aguanta condiciones malas? | mide de noche, con polvo en suspensión y con gente delante de la máquina; cuando no puede, baja la confianza y lo declara |

**El resultado más fuerte:** la escala está validada contra un objeto físico, con un método
independiente del que usa el algoritmo (contar las hendiduras una por una). O sea que el
milímetro que informa el modelo **es un milímetro**, con menos de 1 % de error.

---

## 4. Límites conocidos

Los decimos explícitamente porque son los que condicionan qué se puede afirmar en la tesis.

1. **La exactitud de la *posición* no está medida.** Sabemos que la escala es correcta, pero no
   hay una medición externa que confirme que el borde del tapón y el centro de la pesa caen
   exactamente donde el modelo dice. Lo único que hay es verificación visual.
2. **Los tests no detectan un error sistemático.** Se comprobó con una prueba de mutación: si se
   multiplican todas las medidas por 1,5, o se reemplazan por una constante, la batería de tests
   **sigue pasando**. Los tests miden cobertura y repetibilidad, y las dos son ciegas a un sesgo
   parejo.
3. **La confianza no predice el error.** Se midió la correlación entre la confianza y el error
   aproximado: da prácticamente cero. Hoy la confianza indica **por qué camino** se obtuvo la
   medida, no qué tan buena es. **No debe usarse para filtrar.**
4. **Trazabilidad de versión.** Los resultados guardados no se reproducen exactamente con el
   código actual: falta registrar con qué versión se generó cada salida.
5. **Convención de medición.** Se mide desde el **borde interno del tapón**. La ficha de Latitud
   mide desde el borde externo: hay un corrimiento fijo de ~20 mm que **hay que declarar** al
   comparar números. No es un error, es una definición.
6. **Casos no vistos:** la pesa amarilla nunca apareció en las fotos, y hay una pesa metálica sin
   pintar que no figura en la lista de Latitud.

## 5. Mejoras previstas

Ordenadas por relación esfuerzo / beneficio:

| Mejora | Por qué | Esfuerzo |
|---|---|---|
| Registrar versión del código en cada salida | sin eso los resultados no son reproducibles | bajo |
| Agregar tests que detecten un sesgo de escala | hoy el punto ciego más grande | medio |
| Renombrar o recalibrar la "confianza" | hoy el nombre promete más de lo que da | bajo / medio |
| Mostrar el ángulo en las imágenes de control | hoy no se puede verificar a ojo | bajo |
| Avisar cuando hay más de una pesa candidata | hoy elige una en silencio | bajo |
| Segundo estimador independiente como control cruzado | señala automáticamente los casos dudosos | medio |

---

## 6. Cronograma

El modelo **está funcionando y validado en escala**. No se pide ajuste de plazos.

| Etapa | Estado |
|---|---|
| Algoritmo de medición | ✅ terminado |
| Validación de cobertura, precisión y escala | ✅ terminada |
| Auditoría independiente del código | ✅ terminada (2 pasadas) |
| Documentación | ✅ al día |
| Exactitud de posición + calibrar confianza | 🔄 en curso, no bloquea la entrega |

---

## 7. Contenido de esta carpeta

| Archivo | Qué es |
|---|---|
| `README.md` | este informe |
| `01-como-funciona.png` | esquema del recorrido completo del algoritmo |
| `02-ejemplo-medicion.png` | una medición real dibujada sobre la foto |
| `resultados-508-fotos.csv` | salida del modelo sobre 508 fotos de 44 días (1.016 lecturas) |
| `codigo/` | **el algoritmo completo, listo para correr** |

**Cómo correrlo** (dentro de `codigo/`):

```bash
pip install -r requirements.txt
python3 bajar_fotos_de_prueba.py    # baja las 2.715 fotos de prueba, ~300 MB
python3 tests.py --rapido           # la batería de tests
python3 medir_dia.py 2026-09-19 --salida mediciones.csv
```

Una sola foto, desde Python:

```python
import numpy as np, vision_left as V
L = V.LectorLeft("referencia_left.jpg", np.load("fondo_fijo.npy"))
r = L.leer("foto.jpg")
print(r["varillas"]["a"]["distancia_mm"], r["angulo"]["angulo_grados"])
```

`vision_left.py` es el algoritmo; el resto son utilidades (medir un día, revisar imágenes de a
una, bajar las fotos). `fondo_fijo.npy` y `referencia_left.jpg` son necesarios para correrlo.

**Lo único que no va acá** son las 2.715 fotos de prueba (~300 MB, se bajan con el comando de
arriba) y la auditoría del código. Están en el repositorio del proyecto.

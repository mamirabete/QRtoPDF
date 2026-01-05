# Insert QR into PDF

## Descripción general

**Insert QR into PDF** es una herramienta desarrollada en **Python** que permite generar un **código QR a partir de una URL** e **insertarlo en un archivo PDF existente**, en una página y posición específicas.

El proyecto está orientado a escenarios donde se requiere **agregar códigos QR de forma automatizada** sobre documentos ya generados, tales como:

- Formularios administrativos  
- Documentación institucional  
- Certificados, constancias o reportes  
- Documentos académicos o técnicos  

El script trabaja directamente sobre el PDF original sin modificar su contenido base, superponiendo el código QR mediante un *overlay*.

---

## Características principales

- Generación de códigos QR desde una URL.
- Inserción del QR en:
  - Página específica del PDF.
  - Coordenadas definidas por el usuario.
- Soporte de unidades:
  - **cm**
  - **mm**
  - **puntos (pt)**
- Validación del tamaño de página:
  - **A4**
  - **Carta**
- Comparación con tolerancia configurable.
- Detección y advertencia de páginas con rotación (`/Rotate`).
- Modo de validación:
  - **warn**: advierte y continúa.
  - **strict**: aborta si el tamaño no es válido.
- Compatible con PDFs multipágina.

---

## Requisitos

- Python 3.10 o superior
- Dependencias:
  ```bash
  pip install qrcode[pil] pypdf reportlab pillow
  ```

---

## Uso básico

El script principal es:

```bash
insert_qr_pdf.py
```

### Ejemplo 1: Inserción básica en A4 (coordenadas en cm)

```bash
python insert_qr_pdf.py   --url "https://www.ejemplo.com"   --in-pdf "entrada.pdf"   --out-pdf "salida.pdf"   --page 1   --x 2 --y 3 --unit cm   --size 4 --size-unit cm
```

### Ejemplo 2: Coordenadas en mm y tamaño en puntos

```bash
python insert_qr_pdf.py   --url "https://www.ejemplo.com"   --in-pdf "entrada.pdf"   --out-pdf "salida.pdf"   --page 2   --x 15 --y 20 --unit mm   --size 120 --size-unit pt
```

---

## Validación de tamaño de papel

El script compara el tamaño de cada página contra los valores estándar en **puntos**:

| Papel  | Ancho (pt) | Alto (pt) |
|------|------------|-----------|
| A4   | 595.28     | 841.89    |
| Carta| 612.00     | 792.00    |

---

## Advertencias y fallas comunes

### 1) El PDF no es A4 ni Carta

**Síntoma**
- Se emite advertencia o error (según `--paper-check`).

**Causa**
- El PDF fue generado en otro formato (Legal/Oficio/personalizado) o con un MediaBox no estándar.

**Solución**
- Usar `--paper-check warn` para continuar o convertir el PDF a A4/Carta antes del proceso.

---

### 2) Página con rotación (`/Rotate`)

**Síntoma**
- Se informa una advertencia indicando la rotación detectada.

**Causa**
- El PDF tiene rotación lógica aplicada; las coordenadas PDF siguen el sistema estándar, lo que puede no coincidir con la vista “en pantalla”.

**Solución**
- Definir coordenadas considerando el origen PDF (abajo-izquierda) o incorporar una transformación automática de coordenadas (mejora futura).

---

### 3) QR fuera del área visible

**Síntoma**
- El proceso finaliza correctamente, pero el QR no aparece.

**Causas frecuentes**
- Coordenadas fuera del tamaño de página.
- Tamaño del QR demasiado grande.
- Confusión entre coordenadas “desde arriba” vs “desde abajo”.

**Solución**
- Verificar valores y unidades; recordar que el origen (0,0) está abajo-izquierda.

---

### 4) Página fuera de rango

**Síntoma**
- Error `page_number fuera de rango`.

**Causa**
- El número de página indicado no existe en el PDF.

**Solución**
- Verificar la cantidad real de páginas del PDF.

---

## Arquitectura del script

El script `insert_qr_pdf.py` fue diseñado de forma **modular**, separando responsabilidades para facilitar mantenimiento y extensiones (GUI, API, transformaciones por rotación, inserción múltiple, etc.).

---

## Consideraciones técnicas

- El QR se inserta mediante un **overlay PDF**, sin alterar el contenido original.
- El sistema de coordenadas es el estándar del formato PDF (origen abajo-izquierda).
- El script no reescala ni rota páginas automáticamente.
- Compatible con PDFs multipágina.

---

## Licencia

Este proyecto se distribuye bajo licencia **MIT**.

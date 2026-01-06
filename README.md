# Insert QR into PDF

## Descripción general

**Insert QR into PDF** es una herramienta desarrollada en **Python** que permite generar un **código QR a partir de una URL** e **insertarlo en un archivo PDF existente**, en una página y posición específicas.

El proyecto está orientado a escenarios donde se requiere **agregar códigos QR de forma automatizada o asistida visualmente** sobre documentos ya generados, tales como:

- Formularios administrativos  
- Documentación institucional  
- Certificados y constancias  
- Informes técnicos y académicos  
- Documentos legales o contractuales  

El sistema ofrece dos modos de trabajo complementarios:

- **Script CLI** (`insert_qr_pdf.py`) → automatización y ejecución por línea de comandos.  
- **Cliente gráfico (GUI)** (`gui_insert_qr.py`) → posicionamiento visual, previsualización y arrastre del QR.

---

## Componentes del proyecto

| Archivo | Descripción |
|------|------------|
| `.\src\insert_qr_pdf.py` | Script principal de inserción de QR en PDFs (CLI / backend). |
| `.\src\gui_insert_qr.py` | Cliente gráfico PySide6/Qt con previsualización y drag & drop. |
| `.\src\config.json` | Archivo de configuración con valores por defecto. |
| `.\src\insert-qr-web\app.py` | Implementación de un cliente web con Flask. |
| `.\src\insert-qr-web\static\styles.css` | Archivo que contiene código CSS (Cascading Style Sheets, Hojas de Estilo en Cascada). |
| `.\src\insert-qr-web\static\editor.js` | Lógica del editor (preview, zoom, mover y redimensionar). |
| `.\src\insert-qr-web\template\index.html` | Tmplate HTML para la pagina index.html donde se solicita la carga del PDF. |
| `.\src\insert-qr-web\template\result.html` | Archivo con el template HTML para la pagina result.html donde muestra el editor. |
| `requirements.txt` | Dependencias del proyecto. |
| `README.md` | Documentación del proyecto. |

---

## Características principales

### Funcionalidad general

- Generación de códigos QR desde una URL.
- Inserción del QR en:
  - Página específica del PDF.
  - Coordenadas definidas por el usuario.
- Soporte de unidades:
  - **cm**
  - **mm**
  - **puntos (pt)**
- Inserción no destructiva mediante **overlay PDF**.
- Compatible con PDFs multipágina.

### Validación de documento

- Validación del tamaño de página:
  - **A4**
  - **Carta**
- Comparación con **tolerancia configurable**.
- Detección de páginas con rotación (`/Rotate`).
- Modos de validación:
  - **warn**: emite advertencia y continúa.
  - **strict**: aborta el proceso si no cumple.

---

## Requisitos

### Entorno

- Python **3.10 o superior**

### Dependencias (requirements.txt)

```
blinker==1.9.0
certifi==2026.1.4
charset-normalizer==3.4.4
click==8.3.1
colorama==0.4.6
Flask==3.1.2
idna==3.11
itsdangerous==2.2.0
Jinja2==3.1.6
MarkupSafe==3.0.3
pillow==12.1.0
PyMuPDF==1.26.7
pypdf==6.5.0
PySide6==6.10.1
PySide6_Addons==6.10.1
PySide6_Essentials==6.10.1
qrcode==8.2
reportlab==4.4.7
requests==2.32.5
shiboken6==6.10.1
urllib3==2.6.2
Werkzeug==3.1.4
```

### Instalación

```bash
pip install -r requirements.txt
```

---

# Uso del script `insert_qr_pdf.py` (CLI)

### Ejemplo básico

```bash
python insert_qr_pdf.py   --url "https://www.ejemplo.com"   --in-pdf "entrada.pdf"   --out-pdf "salida.pdf"   --page 1   --x 2 --y 3 --unit cm   --size 4 --size-unit cm
```

## Uso del archivo de configuración (`config.json`)

### Descripción

El script `insert_qr_pdf.py` admite la definición de **valores por defecto** mediante un archivo de configuración en formato **JSON**, lo que permite ejecutar el programa sin necesidad de especificar todos los parámetros por línea de comandos.

El orden de prioridad de los valores es el siguiente:

1. **Argumentos por línea de comandos (CLI)**
2. **Archivo de configuración (`config.json`)**
3. **Valores por defecto internos (hard-defaults)**

Cualquier valor indicado por CLI **sobrescribe** al definido en el archivo de configuración.

---

### Ubicación y uso del archivo de configuración

Por defecto, el script busca un archivo llamado:

```
config.json
```

en el mismo directorio desde el cual se ejecuta el comando.

También es posible indicar explícitamente la ruta al archivo de configuración utilizando el parámetro:

```bash
--config ruta/al/config.json
```

Ejemplo:

```bash
python insert_qr_pdf.py   --config config.json   --url "https://www.ejemplo.com"   --in-pdf "entrada.pdf"   --out-pdf "salida.pdf"
```

---

### Estructura del archivo `config.json`

Ejemplo de estructura:

```json
{
  "defaults": {
    "page": 1,
    "x": 2.0,
    "y": 3.0,
    "unit": "cm",
    "size": 4.0,
    "size_unit": "cm"
  },
  "validation": {
    "tol_pt": 3.0,
    "paper_check": "warn",
    "check_all_pages": false,
    "paper_dim_mode": "visible"
  },
  "web_client": {
    "max_upload_mb": 20
  }
}
```

---

### Parámetros configurables – Sección `defaults`

| Clave        | Tipo   | Descripción |
|-------------|--------|-------------|
| `page`      | int    | Página destino del QR (1 = primera página). |
| `x`         | float  | Coordenada X del QR. |
| `y`         | float  | Coordenada Y del QR. |
| `unit`      | string | Unidad para `x` e `y` (`cm`, `mm`, `pt`). |
| `size`      | float  | Tamaño (lado) del código QR. |
| `size_unit` | string | Unidad del tamaño del QR (`cm`, `mm`, `pt`). |

---

### Parámetros configurables – Sección `validation`

| Clave              | Tipo   | Descripción |
|-------------------|--------|-------------|
| `tol_pt`          | float  | Tolerancia en puntos para comparar tamaños de página. |
| `paper_check`     | string | `warn` (advierte) o `strict` (aborta si no es A4/Carta). |
| `check_all_pages` | bool   | Si es `true`, valida todas las páginas del PDF. |
| `paper_dim_mode`  | string | `visible` (considera rotación) o `mediabox`. |

---

### Parámetros configurables – Sección `web_client` (sólo WEB)

| Clave              | Tipo   | Descripción |
|-------------------|--------|-------------|
| `max_upload_mb`   | int    | Tamaño máximo permitido en MB para el PDF subido. |
| `cleanup_enabled` | bool    | Activa/desactiva la limpieza. |
| `cleanup_interval_seconds`| int    | Cada cuánto corre el limpiador (ej. 900 = 15 min). |
| `cleanup_max_age_seconds` | int    | Borra archivos con antigüedad mayor a ese valor (ej. 86400 = 24 hs). |
| `admin_key`   | string | Clave simple para proteger /admin/cleanup. Agregar "VALOR" con una clave real. Para deshabilitar protección: vacío "" (no recomendado). |
| `admin_allowed_ips`   | array[string] | Lista blanca de IPs permitidas (por defecto: localhost IPv4 e IPv6). |
| `admin_trust_proxy_headers`   | bool | Si es true, se toma IP desde X-Forwarded-For (solo si estás detrás de proxy confiable). |

---

### Ejecución utilizando solo el archivo de configuración

```bash
python insert_qr_pdf.py   --url "https://www.ejemplo.com"   --in-pdf "entrada.pdf"   --out-pdf "salida.pdf"
```

En este caso, los valores de **página, posición, unidad y tamaño del QR** se toman desde `config.json`.

---

### Ejecución con sobrescritura parcial por CLI

```bash
python insert_qr_pdf.py   --url "https://www.ejemplo.com"   --in-pdf "entrada.pdf"   --out-pdf "salida.pdf"   --page 2   --x 1.5   --y 1.5
```

Los parámetros indicados por CLI sobrescriben los definidos en el archivo de configuración.

---

### Consideraciones finales

- El archivo `config.json` es **opcional**.
- Si no existe, el script utiliza valores por defecto internos.
- Este mecanismo facilita la automatización, la ejecución en lote y la integración en pipelines.

---

# Cliente gráfico `gui_insert_qr.py` (GUI)

### Descripción

El cliente gráfico permite trabajar de forma visual con el PDF, evitando el ensayo/error numérico y facilitando la ubicación precisa del QR.

### Características destacadas

- Previsualización real del PDF.
- Rectángulo del QR arrastrable.
- Coordenadas del cursor en tiempo real.
- Conversión automática entre coordenadas visuales y PDF.
- Integración completa con las validaciones del backend.

### Caso de uso típico

Un usuario administrativo necesita agregar un QR siempre en la misma posición de certificados ya emitidos.  
Mediante el GUI puede posicionar el QR visualmente, verificar el resultado y generar el PDF final sin cálculos manuales.

### Captura de pantalla del GUI (comentada)

![GUI Insert QR](docs/gui_insert_qr_preview.png)

> **Figura 1 – Interfaz gráfica `gui_insert_qr.py` con previsualización y posicionamiento visual del QR**

#### Referencias de la interfaz

1. **URL del código QR**
   Campo de texto donde se ingresa la URL que será codificada en el QR.

2. **Selección de PDF de entrada y salida**
   Permite elegir el documento original y definir el archivo PDF resultante.

3. **Página destino**
   Indica la página del PDF donde se insertará el QR (1 = primera página).

4. **Parámetros de posición y tamaño**

   * Coordenadas **X / Y**
   * Unidad de medida (**cm, mm, pt**)
   * Tamaño del QR (lado del cuadrado)

5. **Modo de coordenadas visuales**
   Al estar activado, las coordenadas se interpretan con origen **arriba-izquierda**, coincidiendo con la vista en pantalla.
   El sistema convierte automáticamente a coordenadas PDF internas.

6. **Validación del documento**
   Configuración de:

   * Tolerancia en puntos
   * Modo de validación (**warn / strict**)
   * Criterio de dimensiones (**visible / mediabox**)
   * Validación de todas las páginas

7. **Área de previsualización del PDF**
   Renderizado real del PDF con:

   * Zoom configurable
   * Visualización exacta “como se ve”
   * Soporte para páginas rotadas

8. **Rectángulo rojo del QR (arrastrable)**
   Representa la ubicación y tamaño final del QR.
   Puede moverse con el mouse para posicionamiento preciso.

9. **Coordenadas del cursor en tiempo real**
   Muestra la posición actual del mouse sobre el documento en la unidad seleccionada.

10. **Botones de acción**

    * **Actualizar previsualización**: refresca la vista según los parámetros actuales
    * **Insertar QR**: ejecuta el proceso definitivo sobre el PDF

11. **Área de log**
    Muestra:

    * Advertencias (formato de página, rotación, tolerancia)
    * Mensajes informativos
    * Errores de ejecución

## Cliente WEB: `insert-qr-web`

Esta versión incorpora una **interfaz web** basada en **Flask** para insertar un código QR en un PDF existente, reutilizando el backend del proyecto (`insert_qr_pdf.py`) y los **valores por defecto** definidos en `config.json`.

### Objetivo

El cliente WEB permite:

- Subir un PDF desde el navegador.
- Seleccionar la página destino.
- Renderizar una **previsualización** de la página seleccionada.
- **Ubicar el QR visualmente** mediante un rectángulo rojo superpuesto:
  - **Mover** el rectángulo (drag & drop).
  - **Redimensionar proporcionalmente (1:1)** desde las **esquinas** para ajustar el tamaño del QR manteniendo la forma cuadrada.
- Ajustar el **zoom** de la previsualización (+ / -) sin perder precisión en coordenadas.
- Generar y descargar el PDF resultante con el QR insertado.

---

### Estructura de directorios

Se asume la siguiente estructura (según la organización del proyecto):

```text
src/
├── config.json
├── insert_qr_pdf.py
└── insert-qr-web/
    ├── app.py
    ├── template/
    │   ├── index.html
    │   └── result.html
    ├── static/
    │   ├── styles.css
    │   └── editor.js
    └── storage/
        ├── uploads/    # PDFs subidos (temporales)
        ├── outputs/    # PDFs generados
        └── previews/   # PNGs de previsualización (cache)
```

> Nota: el directorio `storage/` se crea automáticamente al iniciar la aplicación.

---

### Ejecución

Desde el directorio `src/insert-qr-web/`:

```bash
python app.py
```

Por defecto se inicia en:

- `http://127.0.0.1:5000/`

---

### Uso (paso a paso)

1) Abrir el navegador en `http://127.0.0.1:5000/`.

2) **Subir PDF**:
   - Seleccionar un archivo `.pdf` y presionar “Subir y abrir editor”.

3) **Ingresar URL y seleccionar página**:
   - Ingresar la URL para el QR.
   - Indicar la página donde se insertará.

4) **Ubicar el QR visualmente**:
   - Sobre la previsualización, se muestra un rectángulo rojo “QR”.
   - **Mover**: arrastrar el rectángulo para posicionarlo.
   - **Cambiar tamaño (proporcional)**: arrastrar desde cualquiera de las **4 esquinas** (handles) para aumentar/disminuir el tamaño manteniendo forma cuadrada.
   - Los campos **X / Y / Tamaño** se actualizan automáticamente en la unidad seleccionada (cm/mm/pt) al soltar el mouse.

5) **Ajustar zoom**:
   - Usar los botones **+ / -** para aumentar/disminuir el zoom.
   - El sistema conserva coordenadas correctas al mover o redimensionar el rectángulo con zoom aplicado.

6) **Generar PDF**:
   - Presionar “Insertar QR y generar PDF”.
   - Se mostrará la página de resultado con el enlace de descarga.

---

### Cómo se interpretan las coordenadas

- En el cliente WEB, **X/Y se interpretan como coordenadas visuales** con origen **arriba-izquierda** (coinciden con lo que se ve en pantalla).
- Antes de llamar al backend, el servidor convierte a coordenadas PDF (origen abajo-izquierda) usando el alto de página en puntos:
  - `y_pdf = page_height_pt - y_top_pt - qr_size_pt`

Esto garantiza consistencia entre lo que se ve en la previsualización y el resultado final.

---

### Endpoints principales (referencia técnica)

- `GET /` : pantalla inicial (subida de PDF).
- `POST /upload` : recibe el PDF y redirige al editor.
- `GET /editor/<token>` : editor con previsualización.
- `GET /preview/<token>/<page>` : PNG de la página.
- `GET /pageinfo/<token>/<page>` : tamaño visible en puntos (pt).
- `POST /apply/<token>` : inserta el QR y produce el PDF final.
- `GET /download/<token>` : descarga del PDF generado.
- `GET /admin/cleanup?key=VALOR` : borra archivos. Devuelve JSON con las estadísticas de archivos borrados y mantenidos.

---

### Solución de problemas

- **No se ve la previsualización**:
  - Verificar instalación de `PyMuPDF` (import `fitz`).
- **Error 500 al generar PDF**:
  - Revisar consola del servidor Flask (traceback).
  - Confirmar que `insert_qr_pdf.py` y `config.json` estén en `src/` (un nivel superior).
- **Las coordenadas no coinciden**:
  - Confirmar que el zoom se aplica solo al contenedor (`transform: scale`) y que el overlay se mueve en coordenadas base.
  - Evitar modificar manualmente estilos del viewer sin ajustar el mapeo.

---

### Seguridad y limpieza (recomendación)

En entornos reales se recomienda:

- Limpiar periódicamente `storage/uploads`, `storage/previews` y `storage/outputs`.
- Ejecutar detrás de un servidor WSGI (Gunicorn/Waitress) en producción.

---

## Licencia

Este proyecto se distribuye bajo licencia **MIT**.

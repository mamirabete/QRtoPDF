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

### El PDF no es A4 ni Carta
- Se emite advertencia o error según el modo configurado.

### Página con rotación (`/Rotate`)
- El script informa la rotación detectada para evitar errores de posicionamiento.

### QR fuera del área visible
- Verificar coordenadas y tamaño del QR.

---

## Arquitectura del script

El script `insert_qr_pdf.py` sigue una arquitectura modular:

```mermaid
classDiagram
    direction LR

    class InsertQRParams {
        +str input_pdf
        +str output_pdf
        +str url
        +int page_number
        +float x_value
        +float y_value
        +str unit
        +float size_value
        +str size_unit
        +float tol_pt
        +str paper_check
        +bool check_all_pages
        +str paper_dim_mode
    }

    class CLI {
        +parse_args()
        +main()
    }

    class Units {
        +to_points(value, unit) float
    }

    class PageValidation {
        +PAPER_SIZES_PT
        +classify_page_size(w, h, tol) str?
        +validate_pdf_pages(reader, params)
    }

    class Rotation {
        +get_page_rotation_degrees(page) int
        +visible_dimensions(w, h, rot) tuple
    }

    class QRGenerator {
        +generate_qr_png_bytes(url, box_size, border) bytes
    }

    class OverlayBuilder {
        +build_overlay_pdf(page_w, page_h, qr_png, x, y, size) bytes
    }

    class PDFInserter {
        +insert_qr_into_pdf(params)
    }

    CLI --> InsertQRParams : construye
    CLI --> PDFInserter : invoca

    PDFInserter ..> PageValidation : valida tamaño
    PDFInserter ..> Rotation : lee /Rotate
    PDFInserter ..> Units : convierte unidades
    PDFInserter ..> QRGenerator : genera QR PNG
    PDFInserter ..> OverlayBuilder : crea overlay
    PDFInserter ..> "pypdf.PdfReader/PdfWriter" : lee/escribe
    OverlayBuilder ..> "reportlab.canvas" : dibuja QR
    QRGenerator ..> "qrcode + PIL" : genera imagen
    PageValidation ..> Rotation : (modo visible)
```

---

## Licencia

MIT License

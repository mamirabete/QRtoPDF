import io
import argparse
from dataclasses import dataclass

import qrcode
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ----------------------------
# Unidades y conversión
# ----------------------------
PT_PER_INCH = 72.0
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54

def to_points(value: float, unit: str) -> float:
    unit = unit.lower().strip()
    if unit in ("pt", "pts", "point", "points"):
        return float(value)
    if unit == "mm":
        return float(value) * (PT_PER_INCH / MM_PER_INCH)
    if unit == "cm":
        return float(value) * (PT_PER_INCH / CM_PER_INCH)
    raise ValueError(f"Unidad no soportada: {unit}. Use cm, mm o pt.")


# ----------------------------
# Tamaños estándar en puntos
# ----------------------------
PAPER_SIZES_PT = {
    "A4": (595.275590551, 841.88976378),   # 210x297 mm
    "LETTER": (612.0, 792.0),              # 8.5x11 in
}

def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol

def classify_page_size(width_pt: float, height_pt: float, tol_pt: float) -> str | None:
    """
    Devuelve "A4", "LETTER", "A4(rotated)", "LETTER(rotated)" o None.
    El sufijo "(rotated)" acá significa que el ancho/alto estaba intercambiado
    respecto del tamaño de referencia.
    """
    for name, (w_ref, h_ref) in PAPER_SIZES_PT.items():
        if _close(width_pt, w_ref, tol_pt) and _close(height_pt, h_ref, tol_pt):
            return name
        if _close(width_pt, h_ref, tol_pt) and _close(height_pt, w_ref, tol_pt):
            return f"{name}(rotated)"
    return None


# ----------------------------
# Rotación de página (Rotate)
# ----------------------------
def get_page_rotation_degrees(page) -> int:
    """
    Retorna 0/90/180/270. Si no hay /Rotate, retorna 0.
    Normaliza valores extraños (ej. 450 -> 90).
    """
    rot = page.get("/Rotate", 0)
    try:
        rot = int(rot)
    except Exception:
        rot = 0
    rot = rot % 360
    if rot not in (0, 90, 180, 270):
        # Normalización defensiva: aproximar al múltiplo de 90 más cercano
        rot = (round(rot / 90) * 90) % 360
    return rot

def visible_dimensions(width_pt: float, height_pt: float, rotation_deg: int) -> tuple[float, float]:
    """
    Si la página está rotada 90/270, el ancho/alto visibles se intercambian.
    """
    if rotation_deg in (90, 270):
        return (height_pt, width_pt)
    return (width_pt, height_pt)


# ----------------------------
# QR: generar PNG en memoria
# ----------------------------
def generate_qr_png_bytes(url: str, box_size: int = 10, border: int = 2) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ----------------------------
# Overlay PDF con ReportLab
# ----------------------------
def build_overlay_pdf(page_width_pt: float, page_height_pt: float, qr_png: bytes,
                      x_pt: float, y_pt: float, size_pt: float) -> bytes:
    """
    Crea un PDF de 1 página (mismo tamaño que la página objetivo) y dibuja el QR.
    Nota: el overlay se dibuja en el sistema de coordenadas PDF estándar
    (origen abajo-izquierda).
    """
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width_pt, page_height_pt))

    img_reader = ImageReader(io.BytesIO(qr_png))
    c.drawImage(img_reader, x_pt, y_pt, width=size_pt, height=size_pt, mask="auto")

    c.showPage()
    c.save()
    return packet.getvalue()


# ----------------------------
# Inserción en PDF existente
# ----------------------------
@dataclass
class InsertQRParams:
    input_pdf: str
    output_pdf: str
    url: str
    page_number: int          # 1-based
    x_value: float
    y_value: float
    unit: str                 # cm | mm | pt
    size_value: float         # lado del QR
    size_unit: str            # cm | mm | pt

    # Validación papel
    tol_pt: float             # tolerancia en puntos
    paper_check: str          # "warn" | "strict"
    check_all_pages: bool     # validar todas las páginas o solo la página destino
    paper_dim_mode: str       # "mediabox" | "visible" (considera Rotate)


def validate_pdf_pages(reader: PdfReader, params: InsertQRParams) -> None:
    """
    - Advierte si alguna página no coincide con A4/Carta (según tolerancia).
    - Advierte si la página tiene /Rotate != 0 (porque puede afectar cómo se interpretan coordenadas).
    - paper_dim_mode:
        * mediabox: usa width/height del mediabox tal cual.
        * visible: si rotate 90/270, intercambia width/height para comparar contra A4/Carta.
    """
    pages_to_check = range(1, len(reader.pages) + 1) if params.check_all_pages else [params.page_number]

    for pnum in pages_to_check:
        page = reader.pages[pnum - 1]

        w_mb = float(page.mediabox.width)
        h_mb = float(page.mediabox.height)

        rot = get_page_rotation_degrees(page)

        # Dimensiones para clasificación
        if params.paper_dim_mode == "visible":
            w_chk, h_chk = visible_dimensions(w_mb, h_mb, rot)
        else:
            w_chk, h_chk = (w_mb, h_mb)

        classification = classify_page_size(w_chk, h_chk, params.tol_pt)

        # Advertir rotación
        if rot != 0:
            print(
                f"[ADVERTENCIA] Página {pnum}: /Rotate={rot}°. "
                f"El origen (0,0) y el sentido visual pueden no coincidir con tu intuición "
                f"si tomás coordenadas “como se ve en pantalla”."
            )

        # Informar clasificación
        if classification is None:
            msg = (
                f"[ADVERTENCIA] Página {pnum}: tamaño chequeado {w_chk:.2f} x {h_chk:.2f} pt "
                f"(MediaBox {w_mb:.2f} x {h_mb:.2f} pt, Rotate {rot}°, modo={params.paper_dim_mode}) "
                f"no coincide con A4 ni Carta (tolerancia ±{params.tol_pt:.2f} pt)."
            )
            if params.paper_check == "strict":
                raise ValueError(msg.replace("[ADVERTENCIA]", "[ERROR]"))
            else:
                print(msg)
        else:
            print(
                f"[INFO] Página {pnum}: detectado {classification} "
                f"(chequeado {w_chk:.2f} x {h_chk:.2f} pt, "
                f"MediaBox {w_mb:.2f} x {h_mb:.2f} pt, Rotate {rot}°, modo={params.paper_dim_mode}, "
                f"tol ±{params.tol_pt:.2f} pt)."
            )


def insert_qr_into_pdf(params: InsertQRParams) -> None:
    reader = PdfReader(params.input_pdf)
    writer = PdfWriter()

    if params.page_number < 1 or params.page_number > len(reader.pages):
        raise ValueError(
            f"page_number fuera de rango. El PDF tiene {len(reader.pages)} páginas."
        )

    # Validación de tamaño (A4/Carta) y rotación
    validate_pdf_pages(reader, params)

    # Convertir a puntos
    x_pt = to_points(params.x_value, params.unit)
    y_pt = to_points(params.y_value, params.unit)
    size_pt = to_points(params.size_value, params.size_unit)

    # Generar QR
    qr_png = generate_qr_png_bytes(params.url)

    # Recorrer páginas y mergear solo la indicada
    for idx, page in enumerate(reader.pages, start=1):
        if idx == params.page_number:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            overlay_pdf = build_overlay_pdf(w, h, qr_png, x_pt, y_pt, size_pt)
            overlay_reader = PdfReader(io.BytesIO(overlay_pdf))
            overlay_page = overlay_reader.pages[0]

            page.merge_page(overlay_page)

        writer.add_page(page)

    with open(params.output_pdf, "wb") as f:
        writer.write(f)


def parse_args():
    p = argparse.ArgumentParser(
        description="Genera un QR desde una URL y lo inserta en un PDF existente (validación A4/Carta + rotación)."
    )
    p.add_argument("--url", required=True, help="URL para codificar en el QR.")
    p.add_argument("--in-pdf", required=True, help="Ruta al PDF existente de entrada.")
    p.add_argument("--out-pdf", required=True, help="Ruta al PDF de salida.")

    p.add_argument("--page", type=int, required=True, help="Página destino (1 = primera).")

    p.add_argument("--x", type=float, required=True, help="Coordenada X.")
    p.add_argument("--y", type=float, required=True, help="Coordenada Y.")
    p.add_argument("--unit", default="cm", choices=["cm", "mm", "pt"],
                   help="Unidad para X e Y (cm, mm o pt).")

    p.add_argument("--size", type=float, required=True, help="Tamaño (lado) del QR.")
    p.add_argument("--size-unit", default="cm", choices=["cm", "mm", "pt"],
                   help="Unidad del tamaño (cm, mm o pt).")

    # Validación papel
    p.add_argument("--tol-pt", type=float, default=3.0,
                   help="Tolerancia en puntos para comparar tamaños (default: 3.0 pt).")
    p.add_argument("--paper-check", choices=["warn", "strict"], default="warn",
                   help="warn: advierte y continúa. strict: aborta si no es A4/Carta.")
    p.add_argument("--check-all-pages", action="store_true",
                   help="Si se indica, valida todas las páginas; si no, solo la página destino.")
    p.add_argument("--paper-dim-mode", choices=["visible", "mediabox"], default="visible",
                   help="visible: considera Rotate (swap w/h en 90/270). mediabox: usa mediabox tal cual.")

    return p.parse_args()


def main():
    a = parse_args()
    params = InsertQRParams(
        input_pdf=a.in_pdf,
        output_pdf=a.out_pdf,
        url=a.url,
        page_number=a.page,
        x_value=a.x,
        y_value=a.y,
        unit=a.unit,
        size_value=a.size,
        size_unit=a.size_unit,
        tol_pt=a.tol_pt,
        paper_check=a.paper_check,
        check_all_pages=a.check_all_pages,
        paper_dim_mode=a.paper_dim_mode,
    )
    insert_qr_into_pdf(params)
    print(f"OK: generado {params.output_pdf}")


if __name__ == "__main__":
    main()

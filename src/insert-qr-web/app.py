import uuid
import json
import io
import contextlib
from pathlib import Path

from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify, abort

import fitz  # PyMuPDF

# app.py está en: src/insert-qr-web/app.py
# insert_qr_pdf.py y config.json están en: src/
SRC_DIR = Path(__file__).resolve().parents[1]   # .../src
BACKEND_PATH = SRC_DIR / "insert_qr_pdf.py"
CONFIG_PATH = SRC_DIR / "config.json"

# Import dinámico del backend (insert_qr_pdf.py)
import importlib.util
spec = importlib.util.spec_from_file_location("insert_qr_pdf", str(BACKEND_PATH))
insert_qr_pdf = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(insert_qr_pdf)

InsertQRParams = insert_qr_pdf.InsertQRParams
insert_qr_into_pdf = insert_qr_pdf.insert_qr_into_pdf
to_points = insert_qr_pdf.to_points


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


app = Flask(
    __name__,
    template_folder="template",
    static_folder="static",
    static_url_path="/static",
)

# Storage
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
PREVIEWS_DIR = STORAGE_DIR / "previews"

for d in (STORAGE_DIR, UPLOADS_DIR, OUTPUTS_DIR, PREVIEWS_DIR):
    d.mkdir(parents=True, exist_ok=True)

CONFIG = load_config(CONFIG_PATH)
DEFAULTS = CONFIG.get("defaults", {})
VALIDATION = CONFIG.get("validation", {})


def safe_int(x, default=1):
    try:
        return int(x)
    except Exception:
        return default


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def get_pdf_page_count(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    n = doc.page_count
    doc.close()
    return n


def get_page_visible_size_pt(pdf_path: Path, page_1based: int) -> tuple[float, float]:
    doc = fitz.open(str(pdf_path))
    page = doc.load_page(page_1based - 1)
    rect = page.rect
    doc.close()
    return float(rect.width), float(rect.height)


def render_preview_png(pdf_path: Path, token: str, page_1based: int, base_zoom: float = 2.0) -> Path:
    out_path = PREVIEWS_DIR / f"{token}_p{page_1based}_z{base_zoom:.2f}.png"
    if out_path.exists():
        return out_path

    doc = fitz.open(str(pdf_path))
    if page_1based < 1 or page_1based > doc.page_count:
        doc.close()
        raise ValueError("Página fuera de rango.")

    page = doc.load_page(page_1based - 1)
    mat = fitz.Matrix(base_zoom, base_zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(str(out_path))
    doc.close()
    return out_path


@app.get("/")
def index():
    return render_template(
        "index.html",
        token=None,
        pages=None,
        defaults={
            "page": DEFAULTS.get("page", 1),
            "x": DEFAULTS.get("x", 2.0),
            "y": DEFAULTS.get("y", 3.0),
            "unit": DEFAULTS.get("unit", "cm"),
            "size": DEFAULTS.get("size", 4.0),
            "size_unit": DEFAULTS.get("size_unit", "cm"),
        },
        validation={
            "tol_pt": VALIDATION.get("tol_pt", 3.0),
            "paper_check": VALIDATION.get("paper_check", "warn"),
            "check_all_pages": VALIDATION.get("check_all_pages", False),
            "paper_dim_mode": VALIDATION.get("paper_dim_mode", "visible"),
        },
        has_config=bool(CONFIG),
        config_path=str(CONFIG_PATH),
    )


@app.post("/upload")
def upload():
    if "pdf" not in request.files:
        abort(400, "Falta archivo PDF.")
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        abort(400, "El archivo debe ser PDF.")

    token = uuid.uuid4().hex
    pdf_path = UPLOADS_DIR / f"{token}.pdf"
    f.save(str(pdf_path))

    return redirect(url_for("editor", token=token))


@app.get("/editor/<token>")
def editor(token):
    pdf_path = UPLOADS_DIR / f"{token}.pdf"
    if not pdf_path.exists():
        abort(404)

    n_pages = get_pdf_page_count(pdf_path)

    return render_template(
        "index.html",
        token=token,
        pages=n_pages,
        defaults={
            "page": min(DEFAULTS.get("page", 1), n_pages),
            "x": DEFAULTS.get("x", 2.0),
            "y": DEFAULTS.get("y", 3.0),
            "unit": DEFAULTS.get("unit", "cm"),
            "size": DEFAULTS.get("size", 4.0),
            "size_unit": DEFAULTS.get("size_unit", "cm"),
        },
        validation={
            "tol_pt": VALIDATION.get("tol_pt", 3.0),
            "paper_check": VALIDATION.get("paper_check", "warn"),
            "check_all_pages": VALIDATION.get("check_all_pages", False),
            "paper_dim_mode": VALIDATION.get("paper_dim_mode", "visible"),
        },
        has_config=bool(CONFIG),
        config_path=str(CONFIG_PATH),
    )


@app.get("/preview/<token>/<int:page>")
def preview(token, page):
    pdf_path = UPLOADS_DIR / f"{token}.pdf"
    if not pdf_path.exists():
        abort(404)
    png_path = render_preview_png(pdf_path, token=token, page_1based=page, base_zoom=2.0)
    return send_file(str(png_path), mimetype="image/png", as_attachment=False)


@app.get("/pageinfo/<token>/<int:page>")
def pageinfo(token, page):
    pdf_path = UPLOADS_DIR / f"{token}.pdf"
    if not pdf_path.exists():
        abort(404)
    w_pt, h_pt = get_page_visible_size_pt(pdf_path, page)
    return jsonify({"page": page, "width_pt": w_pt, "height_pt": h_pt})


@app.post("/apply/<token>")
def apply(token):
    pdf_path = UPLOADS_DIR / f"{token}.pdf"
    if not pdf_path.exists():
        abort(404)

    url = (request.form.get("url") or "").strip()
    if not url:
        abort(400, "Falta URL.")

    page = safe_int(request.form.get("page"), 1)

    # Recibimos coordenadas VISUALES (arriba-izquierda)
    x = safe_float(request.form.get("x"), DEFAULTS.get("x", 2.0))
    y = safe_float(request.form.get("y"), DEFAULTS.get("y", 3.0))
    unit = (request.form.get("unit") or DEFAULTS.get("unit", "cm")).strip().lower()

    size = safe_float(request.form.get("size"), DEFAULTS.get("size", 4.0))
    size_unit = (request.form.get("size_unit") or DEFAULTS.get("size_unit", "cm")).strip().lower()

    # Validación
    tol_pt = safe_float(request.form.get("tol_pt"), VALIDATION.get("tol_pt", 3.0))
    paper_check = (request.form.get("paper_check") or VALIDATION.get("paper_check", "warn")).strip().lower()
    paper_dim_mode = (request.form.get("paper_dim_mode") or VALIDATION.get("paper_dim_mode", "visible")).strip().lower()
    check_all_pages = bool(request.form.get("check_all_pages") == "on")

    # Convertir visual -> PDF
    page_w_pt, page_h_pt = get_page_visible_size_pt(pdf_path, page)
    x_pt = to_points(x, unit)
    y_top_pt = to_points(y, unit)
    size_pt = to_points(size, size_unit)

    y_bottom_pt = page_h_pt - y_top_pt - size_pt

    out_path = OUTPUTS_DIR / f"{token}_out.pdf"

    params = InsertQRParams(
        input_pdf=str(pdf_path),
        output_pdf=str(out_path),
        url=url,
        page_number=page,
        x_value=x_pt,
        y_value=y_bottom_pt,
        unit="pt",
        size_value=size_pt,
        size_unit="pt",
        tol_pt=tol_pt,
        paper_check=paper_check,
        check_all_pages=check_all_pages,
        paper_dim_mode=paper_dim_mode,
    )

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            insert_qr_into_pdf(params)
        log = buf.getvalue()
    except Exception as e:
        log = buf.getvalue()
        return render_template(
            "result.html",
            ok=False,
            token=token,
            output_url=None,
            log=log,
            error=f"{type(e).__name__}: {e}",
        ), 400

    return render_template(
        "result.html",
        ok=True,
        token=token,
        output_url=url_for("download", token=token),
        log=log,
        error=None,
    )


@app.get("/download/<token>")
def download(token):
    out_path = OUTPUTS_DIR / f"{token}_out.pdf"
    if not out_path.exists():
        abort(404)
    return send_file(
        str(out_path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{token}_con_qr.pdf",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

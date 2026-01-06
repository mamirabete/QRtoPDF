import uuid
import json
import io
import contextlib
import time
import threading
from pathlib import Path

from flask import (
    Flask, render_template, request, send_file, redirect, url_for,
    jsonify, abort, after_this_request
)
from werkzeug.exceptions import RequestEntityTooLarge

import fitz  # PyMuPDF

# -------------------------
# Paths (según tu estructura)
# -------------------------
SRC_DIR = Path(__file__).resolve().parents[1]   # .../src
BACKEND_PATH = SRC_DIR / "insert_qr_pdf.py"
CONFIG_PATH = SRC_DIR / "config.json"

# -------------------------
# Import dinámico del backend (insert_qr_pdf.py)
# -------------------------
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


def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def safe_bool(x, default=False):
    if isinstance(x, bool):
        return x
    if x is None:
        return default
    s = str(x).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


app = Flask(
    __name__,
    template_folder="template",
    static_folder="static",
    static_url_path="/static",
)

# -------------------------
# Storage
# -------------------------
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
PREVIEWS_DIR = STORAGE_DIR / "previews"

for d in (STORAGE_DIR, UPLOADS_DIR, OUTPUTS_DIR, PREVIEWS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# -------------------------
# Config defaults + límites + limpieza + admin
# -------------------------
CONFIG = load_config(CONFIG_PATH)
DEFAULTS = CONFIG.get("defaults", {})
VALIDATION = CONFIG.get("validation", {})
WEB_CLIENT = CONFIG.get("web_client", {})

# Límite de upload
MAX_UPLOAD_MB = safe_int(WEB_CLIENT.get("max_upload_mb", 20), 20)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# Limpieza periódica por antigüedad
CLEANUP_ENABLED = safe_bool(WEB_CLIENT.get("cleanup_enabled", True), True)
CLEANUP_INTERVAL_SECONDS = safe_int(WEB_CLIENT.get("cleanup_interval_seconds", 900), 900)
CLEANUP_MAX_AGE_SECONDS = safe_int(WEB_CLIENT.get("cleanup_max_age_seconds", 86400), 86400)

# Admin (key + allowlist IP)
ADMIN_KEY = str(WEB_CLIENT.get("admin_key", "")).strip()

ADMIN_ALLOWED_IPS = WEB_CLIENT.get("admin_allowed_ips", ["127.0.0.1", "::1"])
ADMIN_TRUST_PROXY_HEADERS = safe_bool(WEB_CLIENT.get("admin_trust_proxy_headers", False), False)

if not isinstance(ADMIN_ALLOWED_IPS, list):
    ADMIN_ALLOWED_IPS = ["127.0.0.1", "::1"]
ADMIN_ALLOWED_IPS = {str(x).strip() for x in ADMIN_ALLOWED_IPS if str(x).strip()}


# -------------------------
# Limpieza: helpers
# -------------------------
def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def cleanup_dir(dir_path: Path, max_age_seconds: int) -> dict:
    """
    Borra archivos regulares con mtime más viejo que max_age_seconds.
    """
    now = time.time()
    deleted = 0
    kept = 0
    errors = 0

    if not dir_path.exists():
        return {"dir": str(dir_path), "deleted": 0, "kept": 0, "errors": 0}

    for p in dir_path.iterdir():
        try:
            if not p.is_file():
                continue
            age = now - p.stat().st_mtime
            if age > max_age_seconds:
                if _safe_unlink(p):
                    deleted += 1
                else:
                    errors += 1
            else:
                kept += 1
        except Exception:
            errors += 1

    return {"dir": str(dir_path), "deleted": deleted, "kept": kept, "errors": errors}


def cleanup_storage_once() -> dict:
    """
    Limpia uploads/previews/outputs por antigüedad.
    """
    return {
        "uploads": cleanup_dir(UPLOADS_DIR, CLEANUP_MAX_AGE_SECONDS),
        "previews": cleanup_dir(PREVIEWS_DIR, CLEANUP_MAX_AGE_SECONDS),
        "outputs": cleanup_dir(OUTPUTS_DIR, CLEANUP_MAX_AGE_SECONDS),
        "max_age_seconds": CLEANUP_MAX_AGE_SECONDS,
    }


def cleanup_token_artifacts(token: str) -> dict:
    """
    Limpieza por token: borra previews y outputs asociados al token.
    - outputs: <token>_out.pdf
    - previews: archivos que empiezan con "<token>_" en PREVIEWS_DIR
    """
    deleted_outputs = 0
    deleted_previews = 0
    errors = 0

    out_pdf = OUTPUTS_DIR / f"{token}_out.pdf"
    try:
        if out_pdf.exists() and out_pdf.is_file():
            if _safe_unlink(out_pdf):
                deleted_outputs += 1
            else:
                errors += 1
    except Exception:
        errors += 1

    try:
        if PREVIEWS_DIR.exists():
            prefix = f"{token}_"
            for p in PREVIEWS_DIR.iterdir():
                try:
                    if p.is_file() and p.name.startswith(prefix):
                        if _safe_unlink(p):
                            deleted_previews += 1
                        else:
                            errors += 1
                except Exception:
                    errors += 1
    except Exception:
        errors += 1

    return {
        "token": token,
        "deleted_outputs": deleted_outputs,
        "deleted_previews": deleted_previews,
        "errors": errors,
    }


def _cleanup_worker(stop_event: threading.Event):
    time.sleep(2)
    while not stop_event.is_set():
        try:
            cleanup_storage_once()
        except Exception:
            pass
        stop_event.wait(CLEANUP_INTERVAL_SECONDS)


_stop_cleanup_event = threading.Event()
_cleanup_thread = None


def start_cleanup_thread():
    global _cleanup_thread
    if not CLEANUP_ENABLED:
        return
    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return

    _cleanup_thread = threading.Thread(
        target=_cleanup_worker,
        args=(_stop_cleanup_event,),
        daemon=True,
        name="storage-cleanup-worker",
    )
    _cleanup_thread.start()


if CLEANUP_ENABLED:
    cleanup_storage_once()
    start_cleanup_thread()


# -------------------------
# Admin: IP + key
# -------------------------
def get_client_ip() -> str:
    """
    Obtiene IP del cliente.
    - Por defecto usa request.remote_addr (seguro si Flask recibe tráfico directo).
    - Si admin_trust_proxy_headers=True, usa X-Forwarded-For / X-Real-IP.
      (Solo habilitar si estás detrás de un proxy confiable).
    """
    if ADMIN_TRUST_PROXY_HEADERS:
        xff = request.headers.get("X-Forwarded-For", "").strip()
        if xff:
            return xff.split(",")[0].strip()

        xri = request.headers.get("X-Real-IP", "").strip()
        if xri:
            return xri

    return (request.remote_addr or "").strip()


def require_admin():
    """
    Protección del endpoint admin:
    1) Restricción por IP (allowlist)
    2) Clave admin (admin_key) por header/query/form
    """
    # 1) IP allowlist
    client_ip = get_client_ip()
    if ADMIN_ALLOWED_IPS and client_ip not in ADMIN_ALLOWED_IPS:
        abort(403, "Forbidden (IP not allowed)")

    # 2) Admin key
    if not ADMIN_KEY:
        # Si está vacío, no se valida la key (NO recomendado)
        return

    provided = (
        request.headers.get("X-Admin-Key")
        or request.args.get("key")
        or request.form.get("key")
        or ""
    ).strip()

    if provided != ADMIN_KEY:
        abort(403, "Forbidden (bad admin key)")


# -------------------------
# Error 413 “lindo”
# -------------------------
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
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
        max_upload_mb=MAX_UPLOAD_MB,
        error_message=f"El archivo excede el límite permitido ({MAX_UPLOAD_MB} MB).",
    ), 413


# -------------------------
# PDF helpers
# -------------------------
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


# -------------------------
# Routes
# -------------------------
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
        max_upload_mb=MAX_UPLOAD_MB,
        error_message=None,
    )


@app.post("/upload")
def upload():
    # 1) Pre-check si viene Content-Length
    if request.content_length is not None and request.content_length > MAX_UPLOAD_BYTES:
        abort(413)

    if "pdf" not in request.files:
        abort(400, "Falta archivo PDF.")
    f = request.files["pdf"]
    if not f or not f.filename:
        abort(400, "Archivo inválido.")
    if not f.filename.lower().endswith(".pdf"):
        abort(400, "El archivo debe ser PDF.")

    token = uuid.uuid4().hex
    pdf_path = UPLOADS_DIR / f"{token}.pdf"
    f.save(str(pdf_path))

    # 2) Post-check por si Content-Length no vino / no es confiable
    try:
        size_bytes = pdf_path.stat().st_size
    except FileNotFoundError:
        abort(400, "No se pudo guardar el archivo.")

    if size_bytes > MAX_UPLOAD_BYTES:
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass
        abort(413)

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
        max_upload_mb=MAX_UPLOAD_MB,
        error_message=None,
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

    x = safe_float(request.form.get("x"), DEFAULTS.get("x", 2.0))
    y = safe_float(request.form.get("y"), DEFAULTS.get("y", 3.0))
    unit = (request.form.get("unit") or DEFAULTS.get("unit", "cm")).strip().lower()

    size = safe_float(request.form.get("size"), DEFAULTS.get("size", 4.0))
    size_unit = (request.form.get("size_unit") or DEFAULTS.get("size_unit", "cm")).strip().lower()

    tol_pt = safe_float(request.form.get("tol_pt"), VALIDATION.get("tol_pt", 3.0))
    paper_check = (request.form.get("paper_check") or VALIDATION.get("paper_check", "warn")).strip().lower()
    paper_dim_mode = (request.form.get("paper_dim_mode") or VALIDATION.get("paper_dim_mode", "visible")).strip().lower()
    check_all_pages = bool(request.form.get("check_all_pages") == "on")

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

    # Limpieza por token DESPUÉS de enviar el archivo
    @after_this_request
    def _cleanup_after_download(response):
        try:
            cleanup_token_artifacts(token)
        except Exception:
            pass
        return response

    return send_file(
        str(out_path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{token}_con_qr.pdf",
    )


# -------------------------
# Admin endpoints
# -------------------------
@app.get("/admin/cleanup")
def admin_cleanup_get():
    require_admin()
    stats = cleanup_storage_once()
    return jsonify({
        "ok": True,
        "stats": stats,
        "client_ip": get_client_ip(),
        "allowed_ips": sorted(list(ADMIN_ALLOWED_IPS)),
        "trust_proxy_headers": ADMIN_TRUST_PROXY_HEADERS,
    })


@app.post("/admin/cleanup")
def admin_cleanup_post():
    require_admin()
    stats = cleanup_storage_once()
    return jsonify({
        "ok": True,
        "stats": stats,
        "client_ip": get_client_ip(),
        "allowed_ips": sorted(list(ADMIN_ALLOWED_IPS)),
        "trust_proxy_headers": ADMIN_TRUST_PROXY_HEADERS,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

import os
import sys
import io
import contextlib

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPixmap, QImage, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QFileDialog, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QTextEdit, QGridLayout, QHBoxLayout, QMessageBox, QGroupBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
)

from insert_qr_pdf import InsertQRParams, insert_qr_into_pdf, to_points

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


# ----------------------------
# Inversa de to_points (para mostrar/actualizar campos)
# ----------------------------
PT_PER_INCH = 72.0
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54

def from_points(value_pt: float, unit: str) -> float:
    unit = unit.lower().strip()
    if unit == "pt":
        return float(value_pt)
    if unit == "mm":
        return float(value_pt) * (MM_PER_INCH / PT_PER_INCH)
    if unit == "cm":
        return float(value_pt) * (CM_PER_INCH / PT_PER_INCH)
    raise ValueError(f"Unidad no soportada: {unit}")


class DraggableRectItem(QGraphicsRectItem):
    """
    Rectángulo arrastrable que llama a un callback cuando cambia su posición.
    """
    def __init__(self, rect: QRectF, on_moved=None):
        super().__init__(rect)
        self._on_moved = on_moved

        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
        self.setZValue(10)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionHasChanged and callable(self._on_moved):
            r = self.rect()
            rect_scene = QRectF(self.pos().x(), self.pos().y(), r.width(), r.height())
            self._on_moved(rect_scene)  # callback
        return super().itemChange(change, value)

class PreviewGraphicsView(QGraphicsView):
    mouseMoved = Signal(QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        # Qt6: usar position() en lugar de pos()
        sp = self.mapToScene(event.position().toPoint())
        self.mouseMoved.emit(sp)
        super().mouseMoveEvent(event)


class PdfPreviewWidget(QWidget):
    """
    Visor de página PDF renderizada con:
    - zoom
    - overlay del QR arrastrable
    - coordenadas en vivo
    """
    rectMoved = Signal(QRectF)     # rect en pixeles (escena)
    mousePosChanged = Signal(QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.view = PreviewGraphicsView()
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%"])
        self.zoom_combo.setCurrentText("50%")
        self.zoom_combo.currentTextChanged.connect(self.apply_zoom)

        self.refresh_btn = QPushButton("Actualizar vista")

        self.cursor_label = QLabel("Cursor: —")
        self.cursor_label.setMinimumWidth(260)

        top = QHBoxLayout()
        top.addWidget(QLabel("Zoom:"))
        top.addWidget(self.zoom_combo)
        top.addSpacing(16)
        top.addWidget(self.cursor_label)
        top.addStretch(1)
        top.addWidget(self.refresh_btn)

        layout = QGridLayout(self)
        layout.addLayout(top, 0, 0)
        layout.addWidget(self.view, 1, 0)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._rect_item: DraggableRectItem | None = None

        self.view.mouseMoved.connect(self.mousePosChanged.emit)

    def clear(self):
        self.scene.clear()
        self._pixmap_item = None
        self._rect_item = None

    def set_cursor_text(self, text: str):
        self.cursor_label.setText(text)

    def set_image(self, qimage: QImage):
        self.clear()
        pix = QPixmap.fromImage(qimage)
        self._pixmap_item = self.scene.addPixmap(pix)
        self.scene.setSceneRect(QRectF(pix.rect()))
        self.apply_zoom()

    def set_or_update_rect(self, rect_scene: QRectF):
        # rect_scene en coordenadas de escena (pixeles)
        if self._rect_item is None:
            pen = QPen(Qt.red)
            pen.setWidth(2)

            item = DraggableRectItem(
                QRectF(0, 0, rect_scene.width(), rect_scene.height()),
                on_moved=self.rectMoved.emit  # <-- el emit lo hace el widget (QObject)
            )
            item.setPen(pen)
            item.setPos(rect_scene.x(), rect_scene.y())

            self.scene.addItem(item)
            self._rect_item = item
        else:
            # mantener tamaño, mover posición
            self._rect_item.setRect(QRectF(0, 0, rect_scene.width(), rect_scene.height()))
            self._rect_item.setPos(rect_scene.x(), rect_scene.y())

    def apply_zoom(self):
        if self._pixmap_item is None:
            return
        text = self.zoom_combo.currentText().replace("%", "").strip()
        try:
            zoom = float(text) / 100.0
        except Exception:
            zoom = 1.25
        self.view.resetTransform()
        self.view.scale(zoom, zoom)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Insertar QR en PDF (DGC - AREF)")

        root = QWidget()
        self.setCentralWidget(root)

        layout = QGridLayout(root)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 2)

        self._preview_base_zoom = 2.0  # debe coincidir con render (para mapear pt<->px)
        self._page_w_pt_visible = None
        self._page_h_pt_visible = None
        self._pix_w = None
        self._pix_h = None
        self._syncing_from_rect = False  # evita loops

        row = 0

        # URL
        layout.addWidget(QLabel("URL:"), row, 0)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://...")
        layout.addWidget(self.url_edit, row, 1, 1, 2)
        row += 1

        # PDF Entrada
        layout.addWidget(QLabel("PDF de entrada:"), row, 0)
        self.in_pdf_edit = QLineEdit()
        layout.addWidget(self.in_pdf_edit, row, 1)
        self.in_browse_btn = QPushButton("Examinar…")
        self.in_browse_btn.clicked.connect(self.browse_in_pdf)
        layout.addWidget(self.in_browse_btn, row, 2)
        row += 1

        # PDF Salida
        layout.addWidget(QLabel("PDF de salida:"), row, 0)
        self.out_pdf_edit = QLineEdit()
        layout.addWidget(self.out_pdf_edit, row, 1)
        self.out_browse_btn = QPushButton("Examinar…")
        self.out_browse_btn.clicked.connect(self.browse_out_pdf)
        layout.addWidget(self.out_browse_btn, row, 2)
        row += 1

        # Página
        layout.addWidget(QLabel("Página (1 = primera):"), row, 0)
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 999999)
        self.page_spin.setValue(1)
        self.page_spin.valueChanged.connect(lambda _: self.refresh_preview())
        layout.addWidget(self.page_spin, row, 1, 1, 2)
        row += 1

        # Coordenadas + tamaño
        coords_group = QGroupBox("Posición del QR")
        coords_layout = QGridLayout(coords_group)

        coords_layout.addWidget(QLabel("X:"), 0, 0)
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-1e6, 1e6)
        self.x_spin.setDecimals(3)
        self.x_spin.setValue(2.0)
        self.x_spin.valueChanged.connect(lambda _: self._refresh_rect_only())
        coords_layout.addWidget(self.x_spin, 0, 1)

        coords_layout.addWidget(QLabel("Y:"), 0, 2)
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-1e6, 1e6)
        self.y_spin.setDecimals(3)
        self.y_spin.setValue(3.0)
        self.y_spin.valueChanged.connect(lambda _: self._refresh_rect_only())
        coords_layout.addWidget(self.y_spin, 0, 3)

        coords_layout.addWidget(QLabel("Unidad:"), 0, 4)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["cm", "mm", "pt"])
        self.unit_combo.setCurrentText("cm")
        self.unit_combo.currentTextChanged.connect(lambda _: self._refresh_rect_only())
        coords_layout.addWidget(self.unit_combo, 0, 5)

        coords_layout.addWidget(QLabel("Tamaño (lado):"), 1, 0)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(0.1, 1e6)
        self.size_spin.setDecimals(3)
        self.size_spin.setValue(4.0)
        self.size_spin.valueChanged.connect(lambda _: self._refresh_rect_only())
        coords_layout.addWidget(self.size_spin, 1, 1)

        coords_layout.addWidget(QLabel("Unidad tamaño:"), 1, 2)
        self.size_unit_combo = QComboBox()
        self.size_unit_combo.addItems(["cm", "mm", "pt"])
        self.size_unit_combo.setCurrentText("cm")
        self.size_unit_combo.currentTextChanged.connect(lambda _: self._refresh_rect_only())
        coords_layout.addWidget(self.size_unit_combo, 1, 3)

        self.visual_coords_chk = QCheckBox("Coordenadas visuales (origen arriba-izquierda)")
        self.visual_coords_chk.setChecked(True)
        self.visual_coords_chk.stateChanged.connect(lambda _: self._refresh_rect_only())
        coords_layout.addWidget(self.visual_coords_chk, 1, 4, 1, 2)

        layout.addWidget(coords_group, row, 0, 1, 3)
        row += 1

        # Validación
        validate_group = QGroupBox("Validación de tamaño y rotación")
        vlayout = QGridLayout(validate_group)

        vlayout.addWidget(QLabel("Tolerancia (pt):"), 0, 0)
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.0, 100.0)
        self.tol_spin.setDecimals(2)
        self.tol_spin.setValue(3.0)
        vlayout.addWidget(self.tol_spin, 0, 1)

        vlayout.addWidget(QLabel("paper_check:"), 0, 2)
        self.paper_check_combo = QComboBox()
        self.paper_check_combo.addItems(["warn", "strict"])
        self.paper_check_combo.setCurrentText("warn")
        vlayout.addWidget(self.paper_check_combo, 0, 3)

        vlayout.addWidget(QLabel("paper_dim_mode:"), 1, 0)
        self.paper_dim_mode_combo = QComboBox()
        self.paper_dim_mode_combo.addItems(["visible", "mediabox"])
        self.paper_dim_mode_combo.setCurrentText("visible")
        vlayout.addWidget(self.paper_dim_mode_combo, 1, 1)

        self.check_all_pages_chk = QCheckBox("Validar todas las páginas")
        self.check_all_pages_chk.setChecked(False)
        vlayout.addWidget(self.check_all_pages_chk, 1, 2, 1, 2)

        layout.addWidget(validate_group, row, 0, 1, 3)
        row += 1

        # Acciones
        btn_row = QHBoxLayout()
        self.preview_btn = QPushButton("Actualizar previsualización")
        self.preview_btn.clicked.connect(self.refresh_preview)

        self.run_btn = QPushButton("Insertar QR")
        self.run_btn.clicked.connect(self.run_insert)

        btn_row.addWidget(self.preview_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.run_btn)
        layout.addLayout(btn_row, row, 0, 1, 3)
        row += 1

        # Log
        layout.addWidget(QLabel("Log:"), row, 0, Qt.AlignTop)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Advertencias, info y errores…")
        layout.addWidget(self.log_text, row, 1, 1, 2)
        row += 1

        # Preview
        self.preview = PdfPreviewWidget()
        self.preview.refresh_btn.clicked.connect(self.refresh_preview)
        self.preview.rectMoved.connect(self.on_rect_moved)
        self.preview.mousePosChanged.connect(self.on_mouse_moved)

        layout.addWidget(QLabel("Previsualización:"), 0, 3, Qt.AlignTop)
        layout.addWidget(self.preview, 1, 3, row - 1, 1)

        self.resize(1300, 750)

        if fitz is None:
            self.append_log("[ADVERTENCIA] PyMuPDF no está instalado. La previsualización no funcionará.")
            self.preview_btn.setEnabled(False)
            self.preview.refresh_btn.setEnabled(False)

    # -------------------------
    # Helpers
    # -------------------------
    def append_log(self, text: str):
        self.log_text.append(text.rstrip("\n"))

    def browse_in_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar PDF de entrada", "", "PDF (*.pdf)")
        if path:
            self.in_pdf_edit.setText(path)
            if not self.out_pdf_edit.text().strip():
                base, ext = os.path.splitext(path)
                self.out_pdf_edit.setText(f"{base}_qr{ext}")
            self.refresh_preview()

    def browse_out_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Seleccionar PDF de salida", "", "PDF (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.out_pdf_edit.setText(path)

    def validate_inputs_basic(self) -> tuple[bool, str]:
        url = self.url_edit.text().strip()
        in_pdf = self.in_pdf_edit.text().strip()
        out_pdf = self.out_pdf_edit.text().strip()

        if not url:
            return False, "Debe ingresarse una URL."
        if not in_pdf or not os.path.isfile(in_pdf):
            return False, "Debe seleccionarse un PDF de entrada existente."
        if not out_pdf:
            return False, "Debe seleccionarse una ruta de salida."
        try:
            if os.path.abspath(in_pdf) == os.path.abspath(out_pdf):
                return False, "El PDF de salida no puede ser el mismo que el de entrada."
        except Exception:
            pass
        return True, ""

    def make_params(self) -> InsertQRParams:
        return InsertQRParams(
            input_pdf=self.in_pdf_edit.text().strip(),
            output_pdf=self.out_pdf_edit.text().strip(),
            url=self.url_edit.text().strip(),
            page_number=int(self.page_spin.value()),
            x_value=float(self.x_spin.value()),
            y_value=float(self.y_spin.value()),
            unit=self.unit_combo.currentText(),
            size_value=float(self.size_spin.value()),
            size_unit=self.size_unit_combo.currentText(),
            tol_pt=float(self.tol_spin.value()),
            paper_check=self.paper_check_combo.currentText(),
            check_all_pages=bool(self.check_all_pages_chk.isChecked()),
            paper_dim_mode=self.paper_dim_mode_combo.currentText(),
        )

    # -------------------------
    # Preview rendering
    # -------------------------
    def refresh_preview(self):
        if fitz is None:
            return

        in_pdf = self.in_pdf_edit.text().strip()
        if not in_pdf or not os.path.isfile(in_pdf):
            self.preview.clear()
            self._page_w_pt_visible = self._page_h_pt_visible = None
            self._pix_w = self._pix_h = None
            return

        page_num = int(self.page_spin.value())
        try:
            doc = fitz.open(in_pdf)
            if page_num < 1 or page_num > doc.page_count:
                self.append_log(f"[ADVERTENCIA] Página {page_num} fuera de rango (PDF tiene {doc.page_count}).")
                self.preview.clear()
                doc.close()
                return

            page = doc.load_page(page_num - 1)

            base_zoom = self._preview_base_zoom
            mat = fitz.Matrix(base_zoom, base_zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            self.preview.set_image(img)

            rect = page.rect  # tamaño visible en puntos
            self._page_w_pt_visible = rect.width
            self._page_h_pt_visible = rect.height
            self._pix_w = pix.width
            self._pix_h = pix.height

            doc.close()

            # Dibujar rectángulo del QR según campos
            self._refresh_rect_only()

        except Exception as e:
            self.append_log(f"[ERROR] Preview: {type(e).__name__}: {e}")
            self.preview.clear()
            self._page_w_pt_visible = self._page_h_pt_visible = None
            self._pix_w = self._pix_h = None

    def _refresh_rect_only(self):
        """
        Actualiza el rectángulo rojo sin rerender de PDF.
        """
        if self._page_w_pt_visible is None or self._page_h_pt_visible is None:
            return
        if self._pix_w is None or self._pix_h is None:
            return
        if self._syncing_from_rect:
            return

        try:
            page_w_pt = float(self._page_w_pt_visible)
            page_h_pt = float(self._page_h_pt_visible)

            x_pt = to_points(float(self.x_spin.value()), self.unit_combo.currentText())
            y_pt = to_points(float(self.y_spin.value()), self.unit_combo.currentText())
            size_pt = to_points(float(self.size_spin.value()), self.size_unit_combo.currentText())

            # Para dibujar en preview (origen arriba-izquierda)
            if self.visual_coords_chk.isChecked():
                x_vis_pt = x_pt
                y_vis_pt = y_pt
            else:
                # si el usuario usa coords PDF (abajo-izquierda), convertir a coords visuales para pintar
                x_vis_pt = x_pt
                y_vis_pt = page_h_pt - y_pt - size_pt

            sx = float(self._pix_w) / page_w_pt
            sy = float(self._pix_h) / page_h_pt

            x_px = x_vis_pt * sx
            y_px = y_vis_pt * sy
            w_px = size_pt * sx
            h_px = size_pt * sy

            self.preview.set_or_update_rect(QRectF(x_px, y_px, w_px, h_px))
        except Exception as e:
            self.append_log(f"[ADVERTENCIA] No se pudo actualizar rectángulo: {type(e).__name__}: {e}")

    # -------------------------
    # Mouse tracking (coords en vivo)
    # -------------------------
    def on_mouse_moved(self, scene_pos: QPointF):
        if self._page_w_pt_visible is None or self._page_h_pt_visible is None:
            self.preview.set_cursor_text("Cursor: —")
            return
        if self._pix_w is None or self._pix_h is None:
            self.preview.set_cursor_text("Cursor: —")
            return

        x_px = scene_pos.x()
        y_px = scene_pos.y()

        # Clamp al área de la imagen
        x_px = max(0.0, min(float(self._pix_w), x_px))
        y_px = max(0.0, min(float(self._pix_h), y_px))

        page_w_pt = float(self._page_w_pt_visible)
        page_h_pt = float(self._page_h_pt_visible)

        # px -> pt (visual)
        x_vis_pt = x_px * (page_w_pt / float(self._pix_w))
        y_vis_pt = y_px * (page_h_pt / float(self._pix_h))

        # Convertir a la unidad elegida para mostrar
        unit = self.unit_combo.currentText()
        x_unit = from_points(x_vis_pt, unit)
        y_unit = from_points(y_vis_pt, unit)

        self.preview.set_cursor_text(f"Cursor: x={x_unit:.2f} {unit}, y={y_unit:.2f} {unit} (visual)")

    # -------------------------
    # Drag: rect moved -> actualizar campos X/Y
    # -------------------------
    def on_rect_moved(self, rect_scene: QRectF):
        """
        rect_scene está en pixeles (escena), origen arriba-izquierda del preview.
        Convertimos esa posición a pt (visual) y actualizamos los campos.
        """
        if self._page_w_pt_visible is None or self._page_h_pt_visible is None:
            return
        if self._pix_w is None or self._pix_h is None:
            return

        # Evitar loops: mover rect -> cambia spin -> refresh rect
        self._syncing_from_rect = True
        try:
            page_w_pt = float(self._page_w_pt_visible)
            page_h_pt = float(self._page_h_pt_visible)

            # pix -> pt (visual)
            x_vis_pt = rect_scene.x() * (page_w_pt / float(self._pix_w))
            y_vis_pt = rect_scene.y() * (page_h_pt / float(self._pix_h))

            # Si el usuario trabaja en visual, los campos X/Y representan visual
            if self.visual_coords_chk.isChecked():
                x_field_pt = x_vis_pt
                y_field_pt = y_vis_pt
            else:
                # si los campos están en coords PDF (abajo-izq), convertir:
                # y_pdf = page_h - y_visual - size
                size_pt = to_points(float(self.size_spin.value()), self.size_unit_combo.currentText())
                x_field_pt = x_vis_pt
                y_field_pt = page_h_pt - y_vis_pt - size_pt

            unit = self.unit_combo.currentText()
            self.x_spin.setValue(from_points(x_field_pt, unit))
            self.y_spin.setValue(from_points(y_field_pt, unit))
        finally:
            self._syncing_from_rect = False

    # -------------------------
    # Inserción
    # -------------------------
    def run_insert(self):
        ok, msg = self.validate_inputs_basic()
        if not ok:
            QMessageBox.warning(self, "Validación", msg)
            return

        self.log_text.clear()
        params = self.make_params()

        # Si el usuario ingresó coordenadas visuales, convertir a coordenadas PDF (abajo-izquierda)
        if self.visual_coords_chk.isChecked():
            try:
                if self._page_h_pt_visible is None:
                    # intentar obtenerlo desde PyMuPDF
                    if fitz is not None:
                        doc = fitz.open(params.input_pdf)
                        page = doc.load_page(params.page_number - 1)
                        self._page_h_pt_visible = page.rect.height
                        doc.close()

                if self._page_h_pt_visible is not None:
                    page_h_pt = float(self._page_h_pt_visible)
                    x_pt = to_points(params.x_value, params.unit)
                    y_pt = to_points(params.y_value, params.unit)
                    size_pt = to_points(params.size_value, params.size_unit)
                    y_bottom_pt = page_h_pt - y_pt - size_pt

                    params.unit = "pt"
                    params.x_value = x_pt
                    params.y_value = y_bottom_pt
                else:
                    self.append_log("[ADVERTENCIA] No se pudo convertir coordenadas visuales (alto de página desconocido).")
            except Exception as e:
                self.append_log(f"[ADVERTENCIA] Conversión coords visuales falló: {type(e).__name__}: {e}")

        stdout_buf = io.StringIO()
        try:
            self.run_btn.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)

            with contextlib.redirect_stdout(stdout_buf):
                insert_qr_into_pdf(params)

            out_text = stdout_buf.getvalue().strip()
            if out_text:
                self.append_log(out_text)

            self.append_log(f"\nOK: generado {params.output_pdf}")
            QMessageBox.information(self, "Éxito", "QR insertado correctamente.")
        except Exception as e:
            out_text = stdout_buf.getvalue().strip()
            if out_text:
                self.append_log(out_text)
            self.append_log(f"\n[ERROR] {type(e).__name__}: {e}")
            QMessageBox.critical(self, "Error", f"{type(e).__name__}: {e}")
        finally:
            QApplication.restoreOverrideCursor()
            self.run_btn.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

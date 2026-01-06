(() => {
  const dataEl = document.getElementById("appData");
  if (!dataEl) return; // en pantalla de upload no hay editor

  const token = dataEl.dataset.token;
  const pages = parseInt(dataEl.dataset.pages || "1", 10);

  // Inputs
  const pageInput = document.getElementById("page");
  const xInput = document.getElementById("x");
  const yInput = document.getElementById("y");
  const unitSel = document.getElementById("unit");
  const sizeInput = document.getElementById("size");
  const sizeUnitSel = document.getElementById("size_unit");

  // Preview
  const pageImg = document.getElementById("pageImg");
  const viewer = document.getElementById("viewer");
  const overlay = document.getElementById("qrOverlay");
  const cursorInfo = document.getElementById("cursorInfo");
  const pageMeta = document.getElementById("pageMeta");

  const zoomLabel = document.getElementById("zoomLabel");
  const btnReload = document.getElementById("btnReload");
  const zoomInBtn = document.getElementById("zoomIn");
  const zoomOutBtn = document.getElementById("zoomOut");

  // Estado
  let zoom = 1.0;
  let pageWpt = 0;
  let pageHpt = 0;

  const MIN_SIZE_PX = 20;

  // Utils
  function clamp(v, a, b) { return Math.max(a, Math.min(v, b)); }

  function ptToUnit(pt, unit) {
    unit = (unit || "").toLowerCase();
    if (unit === "pt") return pt;
    if (unit === "mm") return pt * (25.4 / 72.0);
    if (unit === "cm") return pt * (2.54 / 72.0);
    return pt;
  }

  function unitToPt(val, unit) {
    unit = (unit || "").toLowerCase();
    if (unit === "pt") return val;
    if (unit === "mm") return val * (72.0 / 25.4);
    if (unit === "cm") return val * (72.0 / 2.54);
    return val;
  }

  // Zoom
  function setZoom(z) {
    zoom = clamp(z, 0.25, 4.0);
    viewer.style.transform = `scale(${zoom})`;
    zoomLabel.textContent = `Zoom: ${Math.round(zoom * 100)}%`;
  }

  // Cargar preview + info pt
  async function loadPage() {
    const p = clamp(parseInt(pageInput.value || "1", 10), 1, pages);
    pageInput.value = p;

    pageImg.src = `/preview/${token}/${p}?t=${Date.now()}`;
    await pageImg.decode().catch(() => {});

    // Importante: sistema de coordenadas BASE = natural size
    pageImg.style.width = pageImg.naturalWidth + "px";
    pageImg.style.height = pageImg.naturalHeight + "px";

    const info = await fetch(`/pageinfo/${token}/${p}`).then(r => r.json());
    pageWpt = info.width_pt;
    pageHpt = info.height_pt;

    pageMeta.textContent = `Página ${p} — tamaño visible: ${pageWpt.toFixed(2)} x ${pageHpt.toFixed(2)} pt`;

    applyInputsToOverlay();
  }

  // Inputs -> overlay (BASE)
  function applyInputsToOverlay() {
    if (!pageImg.naturalWidth || !pageImg.naturalHeight || !pageWpt || !pageHpt) return;

    const x = parseFloat(xInput.value || "0");
    const y = parseFloat(yInput.value || "0");
    const u = unitSel.value;

    const s = parseFloat(sizeInput.value || "0");
    const su = sizeUnitSel.value;

    const xPt = unitToPt(x, u);
    const yPt = unitToPt(y, u);
    const sizePt = unitToPt(s, su);

    const sx = pageImg.naturalWidth / pageWpt;
    const sy = pageImg.naturalHeight / pageHpt;

    const leftPx = xPt * sx;
    const topPx = yPt * sy;
    const sizePx = sizePt * sx; // cuadrado

    // Clamp
    const maxLeft = pageImg.naturalWidth - sizePx;
    const maxTop = pageImg.naturalHeight - sizePx;

    overlay.style.left = `${clamp(leftPx, 0, maxLeft)}px`;
    overlay.style.top = `${clamp(topPx, 0, maxTop)}px`;
    overlay.style.width = `${Math.max(MIN_SIZE_PX, sizePx)}px`;
    overlay.style.height = `${Math.max(MIN_SIZE_PX, sizePx)}px`;
  }

  // Overlay -> inputs (BASE, independiente de zoom)
  function applyOverlayToInputs() {
    if (!pageImg.naturalWidth || !pageImg.naturalHeight || !pageWpt || !pageHpt) return;

    const leftPx = overlay.offsetLeft;
    const topPx = overlay.offsetTop;
    const wPx = overlay.offsetWidth;

    const xPt = leftPx * (pageWpt / pageImg.naturalWidth);
    const yPt = topPx * (pageHpt / pageImg.naturalHeight);
    const sizePt = wPx * (pageWpt / pageImg.naturalWidth);

    const u = unitSel.value;
    const su = sizeUnitSel.value;

    xInput.value = ptToUnit(xPt, u).toFixed(3);
    yInput.value = ptToUnit(yPt, u).toFixed(3);
    sizeInput.value = ptToUnit(sizePt, su).toFixed(3);
  }

  // Cursor coords (visual)
  function updateCursorInfo(e) {
    if (!pageImg.naturalWidth || !pageWpt || !pageHpt) {
      cursorInfo.textContent = "Cursor: —";
      return;
    }

    const imgRect = pageImg.getBoundingClientRect();
    const inside =
      e.clientX >= imgRect.left && e.clientX <= imgRect.right &&
      e.clientY >= imgRect.top && e.clientY <= imgRect.bottom;

    if (!inside) {
      cursorInfo.textContent = "Cursor: —";
      return;
    }

    // px base: (distancia en pantalla) / zoom
    const pxBase = (e.clientX - imgRect.left) / zoom;
    const pyBase = (e.clientY - imgRect.top) / zoom;

    const xPt = pxBase * (pageWpt / pageImg.naturalWidth);
    const yPt = pyBase * (pageHpt / pageImg.naturalHeight);

    const u = unitSel.value;
    cursorInfo.textContent = `Cursor: x=${ptToUnit(xPt, u).toFixed(2)} ${u}, y=${ptToUnit(yPt, u).toFixed(2)} ${u}`;
  }

  // Drag & Resize (proporcional 1:1 desde esquinas)
  let mode = null;        // "move" | "resize"
  let handle = null;      // "tl"|"tr"|"bl"|"br"
  let startMouseX = 0;
  let startMouseY = 0;

  let startLeft = 0;
  let startTop = 0;
  let startSize = 0;

  overlay.addEventListener("mousedown", (e) => {
    const h = e.target.closest(".handle");
    mode = h ? "resize" : "move";
    handle = h ? h.dataset.handle : null;

    startMouseX = e.clientX;
    startMouseY = e.clientY;

    startLeft = overlay.offsetLeft;
    startTop = overlay.offsetTop;
    startSize = overlay.offsetWidth;

    e.preventDefault();
  });

  document.addEventListener("mouseup", () => {
    if (!mode) return;
    mode = null;
    handle = null;
    applyOverlayToInputs();
  });

  document.addEventListener("mousemove", (e) => {
    updateCursorInfo(e);
    if (!mode) return;

    const imgW = pageImg.naturalWidth || 0;
    const imgH = pageImg.naturalHeight || 0;
    if (!imgW || !imgH) return;

    // delta mouse -> base
    const dx = (e.clientX - startMouseX) / zoom;
    const dy = (e.clientY - startMouseY) / zoom;

    if (mode === "move") {
      const maxLeft = imgW - overlay.offsetWidth;
      const maxTop = imgH - overlay.offsetHeight;

      overlay.style.left = `${clamp(startLeft + dx, 0, maxLeft)}px`;
      overlay.style.top = `${clamp(startTop + dy, 0, maxTop)}px`;
      return;
    }

    // Resize proporcional
    const delta = Math.max(Math.abs(dx), Math.abs(dy));

    let newLeft = startLeft;
    let newTop = startTop;
    let newSize = startSize;

    // Signo por esquina: se interpreta para que el resize sea "intuitivo"
    if (handle === "br") {
      // derecha/abajo
      newSize = startSize + ((dx >= 0 || dy >= 0) ? delta : -delta);
    } else if (handle === "tl") {
      // izquierda/arriba
      newSize = startSize + ((dx <= 0 || dy <= 0) ? delta : -delta);
      newLeft = startLeft + (startSize - newSize);
      newTop = startTop + (startSize - newSize);
    } else if (handle === "tr") {
      // derecha/arriba
      newSize = startSize + ((dx >= 0 || dy <= 0) ? delta : -delta);
      newTop = startTop + (startSize - newSize);
    } else if (handle === "bl") {
      // izquierda/abajo
      newSize = startSize + ((dx <= 0 || dy >= 0) ? delta : -delta);
      newLeft = startLeft + (startSize - newSize);
    }

    newSize = Math.max(MIN_SIZE_PX, newSize);

    // Clamp a bordes (mantener dentro del PNG)
    newLeft = clamp(newLeft, 0, imgW - newSize);
    newTop = clamp(newTop, 0, imgH - newSize);

    // Ajuste final por bounds
    const maxSizeByBounds = Math.min(imgW - newLeft, imgH - newTop);
    newSize = Math.min(newSize, maxSizeByBounds);

    overlay.style.left = `${newLeft}px`;
    overlay.style.top = `${newTop}px`;
    overlay.style.width = `${newSize}px`;
    overlay.style.height = `${newSize}px`;
  });

  // Eventos UI
  btnReload.addEventListener("click", loadPage);
  zoomInBtn.addEventListener("click", () => setZoom(zoom + 0.1));
  zoomOutBtn.addEventListener("click", () => setZoom(zoom - 0.1));

  pageInput.addEventListener("change", loadPage);
  [xInput, yInput, unitSel, sizeInput, sizeUnitSel].forEach(el =>
    el.addEventListener("input", applyInputsToOverlay)
  );

  // Init
  setZoom(1.0);
  loadPage();

  // Si el mouse se mueve sin arrastrar, igualmente actualizamos cursor info
  document.addEventListener("mousemove", (e) => {
    if (!mode) updateCursorInfo(e);
  });
})();

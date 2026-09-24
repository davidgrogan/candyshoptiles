/*
 * Tile wall designer.
 *
 * The wall is a sparse set of placed tiles keyed by "row,col" -- there's no
 * fixed grid size. The visible grid is the bounding box of what's placed;
 * while a tile is being dragged, a ring of empty drop slots appears one cell
 * out on every side so the wall can grow in any direction. Coordinates are
 * re-normalized after every change so the top-left occupied cell is 0,0.
 *
 * Drag and drop uses pointer events (not the HTML5 drag API) so it works the
 * same with a mouse, a trackpad and a touchscreen.
 *
 * Config comes from the <script id="designer-config"> JSON block (built by
 * app/catalog.py's designer_config()). mode is "customer" (public designer,
 * remembers the design in localStorage) or "admin" (sample-set editor,
 * writes the layout into the #set-layout hidden field instead).
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("designer-config");
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);

  var MAX_SPAN = 12;
  var STORAGE_KEY = "candyshoptiles:design:v1";
  var pricing = cfg.pricing;
  var images = new Map(cfg.images.map(function (i) { return [i.id, i]; }));
  var cells = new Map(); // "r,c" -> image id
  var spacingCfg = cfg.spacing;
  var spacing = spacingCfg.default; // inches between tiles, part of the design

  var gridEl = document.getElementById("grid");
  var canvasEl = document.getElementById("board-canvas");
  var paletteEl = document.getElementById("palette-list");
  var filtersEl = document.getElementById("palette-filters");
  var dimsEl = document.getElementById("board-dims");
  var clearBtn = document.getElementById("clear-board");
  var boardEl = canvasEl.closest(".board");
  var spacingInput = document.getElementById("spacing-input");
  var spacingOut = document.getElementById("spacing-value");

  var drag = null;
  var suppressClick = false;
  var activeCategory = null;

  // --- model -----------------------------------------------------------------

  function key(r, c) { return r + "," + c; }
  function unkey(k) { return k.split(",").map(Number); }

  function bounds() {
    if (!cells.size) return null;
    var b = { minR: Infinity, maxR: -Infinity, minC: Infinity, maxC: -Infinity };
    cells.forEach(function (_, k) {
      var rc = unkey(k);
      b.minR = Math.min(b.minR, rc[0]); b.maxR = Math.max(b.maxR, rc[0]);
      b.minC = Math.min(b.minC, rc[1]); b.maxC = Math.max(b.maxC, rc[1]);
    });
    b.rows = b.maxR - b.minR + 1;
    b.cols = b.maxC - b.minC + 1;
    return b;
  }

  function normalize() {
    var b = bounds();
    if (!b || (b.minR === 0 && b.minC === 0)) return;
    var shifted = new Map();
    cells.forEach(function (id, k) {
      var rc = unkey(k);
      shifted.set(key(rc[0] - b.minR, rc[1] - b.minC), id);
    });
    cells = shifted;
  }

  function withinLimits() {
    var b = bounds();
    return !b || (b.rows <= MAX_SPAN && b.cols <= MAX_SPAN);
  }

  // Where a tapped thumbnail goes: fill any gap first (reading order), then
  // grow toward a square -- add a column while the wall is taller than or
  // as tall as it is wide, otherwise start a new row.
  function nextSlot() {
    var b = bounds();
    if (!b) return [0, 0];
    for (var r = 0; r < b.rows; r++) {
      for (var c = 0; c < b.cols; c++) {
        if (!cells.has(key(r, c))) return [r, c];
      }
    }
    if (b.cols <= b.rows && b.cols < MAX_SPAN) return [0, b.cols];
    if (b.rows < MAX_SPAN) return [b.rows, 0];
    return null;
  }

  function layout() {
    var out = [];
    cells.forEach(function (id, k) {
      var rc = unkey(k);
      out.push({ r: rc[0], c: rc[1], image_id: id });
    });
    out.sort(function (a, b) { return a.r - b.r || a.c - b.c; });
    return out;
  }

  function clampSpacing(v) {
    v = Number(v);
    if (!isFinite(v)) return spacingCfg.default;
    v = Math.min(spacingCfg.max, Math.max(0, v));
    return Math.round(v / spacingCfg.step) * spacingCfg.step;
  }

  // 24.5 -> "24½″" (quarter-inch precision), matching layout.format_inches().
  function inches(v) {
    var q = Math.round(v * 4), whole = Math.floor(q / 4), frac = ["", "¼", "½", "¾"][q % 4];
    return (whole === 0 && frac ? frac : whole + frac) + "″";
  }

  function wallSize(b) {
    return {
      w: b.cols * pricing.tileWidthIn + (b.cols - 1) * spacing,
      h: b.rows * pricing.tileHeightIn + (b.rows - 1) * spacing,
    };
  }

  function load(items) {
    cells = new Map();
    (items || []).forEach(function (t) {
      if (images.has(t.image_id)) cells.set(key(t.r, t.c), t.image_id);
    });
    normalize();
  }

  function addImage(id) {
    var slot = nextSlot();
    if (!slot) return;
    cells.set(key(slot[0], slot[1]), id);
    changed();
    var el = gridEl.querySelector('[data-k="' + key(slot[0], slot[1]) + '"]');
    if (el) {
      el.classList.add("just-added");
      setTimeout(function () { el.classList.remove("just-added"); }, 400);
    }
  }

  function removeAt(k) {
    cells.delete(k);
    normalize();
    changed();
  }

  // --- rendering -------------------------------------------------------------

  function money(cents) {
    var d = Math.floor(cents / 100), rem = cents % 100;
    var s = "$" + d.toLocaleString("en-US");
    return rem ? s + "." + String(rem).padStart(2, "0") : s;
  }

  function quote(n) {
    var unit = n === 1 ? pricing.singleCents : pricing.multiCents;
    return { unit: unit, total: unit * n };
  }

  function sizeCells(rows, cols) {
    // Size as though the drop ring is always there, so tiles don't jump
    // when a drag starts and the ring appears.
    // Gaps are drawn to scale: the chosen spacing relative to a tile's
    // real width, so 1" between 8" tiles looks like 1/8 of a tile.
    var r = rows + 2, c = cols + 2;
    var k = spacing / pricing.tileWidthIn;             // gap as a fraction of cell width
    var aspect = pricing.tileHeightIn / pricing.tileWidthIn;
    var availW = canvasEl.clientWidth - 26;            // canvas padding + border
    var availH = Math.max(280, Math.min(window.innerHeight * 0.66, 720));
    var w = Math.min(150, availW / (c + (c - 1) * k), availH / (r * aspect + (r - 1) * k));
    // No artificial minimum: the grid must always fit the canvas width,
    // never push the page into horizontal scrolling.
    w = Math.max(8, Math.floor(w));
    var gap = Math.floor(w * k);
    var h = Math.round(w * aspect);
    gridEl.style.setProperty("--cell-w", w + "px");
    gridEl.style.setProperty("--cell-h", h + "px");
    gridEl.style.gap = gap + "px";
    canvasEl.style.minHeight = (r * h + (r - 1) * gap + 24) + "px";
  }

  function render() {
    var b = bounds();
    var r0 = 0, r1 = 0, c0 = 0, c1 = 0;
    if (b) {
      r0 = 0; r1 = b.rows - 1; c0 = 0; c1 = b.cols - 1;
      if (drag && drag.started) {
        if (b.rows < MAX_SPAN) { r0 -= 1; r1 += 1; }
        if (b.cols < MAX_SPAN) { c0 -= 1; c1 += 1; }
      }
    }
    sizeCells(b ? b.rows : 1, b ? b.cols : 1);
    gridEl.style.gridTemplateColumns = "repeat(" + (c1 - c0 + 1) + ", var(--cell-w))";
    gridEl.textContent = "";

    for (var r = r0; r <= r1; r++) {
      for (var c = c0; c <= c1; c++) {
        var k = key(r, c);
        var cell = document.createElement("div");
        cell.className = "cell";
        cell.dataset.k = k;
        var inside = b && r >= 0 && c >= 0 && r < b.rows && c < b.cols;
        if (cells.has(k)) {
          var img = images.get(cells.get(k));
          cell.classList.add("filled");
          if (drag && drag.started && drag.fromKey === k) cell.classList.add("drag-source");
          var pic = document.createElement("img");
          pic.src = img.thumb;
          pic.alt = img.title;
          pic.draggable = false;
          cell.appendChild(pic);
          cell.title = img.title;
          var rm = document.createElement("button");
          rm.type = "button";
          rm.className = "cell-remove";
          rm.setAttribute("aria-label", "Remove " + img.title);
          rm.textContent = "×";
          rm.addEventListener("click", removeAt.bind(null, k));
          cell.appendChild(rm);
          cell.addEventListener("pointerdown", startPointer.bind(null, { source: "cell", fromKey: k, imageId: cells.get(k) }));
        } else if (!b) {
          cell.classList.add("empty", "start");
          cell.innerHTML = "<span>Drop a tile here<br>or tap one to start</span>";
        } else {
          cell.classList.add(inside ? "empty" : "ring");
        }
        gridEl.appendChild(cell);
      }
    }
  }

  function renderSummary() {
    var n = cells.size;
    var b = bounds();
    var size = b ? wallSize(b) : null;
    var sizeText = size ? inches(size.w) + " wide × " + inches(size.h) + " tall" : "--";
    if (dimsEl) {
      dimsEl.textContent = b
        ? n + " tile" + (n === 1 ? "" : "s") + " · " + b.cols + " across × " + b.rows + " down · " + sizeText
        : "No tiles yet";
    }
    if (clearBtn) clearBtn.disabled = n === 0;

    var q = quote(n);
    setText("sum-count", String(n));
    setText("sum-unit", n ? money(q.unit) : "--");
    setText("sum-size", sizeText);
    setText("sum-total", money(n ? q.total : 0));
    var note = document.getElementById("sum-note");
    if (note) {
      if (n === 1) {
        note.textContent = "Add one more and every tile drops to " + money(pricing.multiCents) +
          " (2 tiles: " + money(2 * pricing.multiCents) + ").";
      } else if (n > 1) {
        note.textContent = "You're getting the multi-tile price of " + money(pricing.multiCents) +
          " each (saving " + money(n * (pricing.singleCents - pricing.multiCents)) + ").";
      } else {
        note.textContent = "One tile is " + money(pricing.singleCents) + ". Order two or more and they're all " +
          money(pricing.multiCents) + " each.";
      }
    }
    ["btn-order", "btn-wall", "btn-share"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.disabled = n === 0;
    });
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function persist() {
    var json = JSON.stringify(layout());
    if (cfg.mode === "admin") {
      var input = document.getElementById("set-layout");
      if (input) input.value = json;
      var sp = document.getElementById("set-spacing");
      if (sp) sp.value = String(spacing);
      return;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ layout: layout(), spacing: spacing }));
    } catch (e) { /* private mode etc. */ }
  }

  function setSpacing(v) {
    spacing = clampSpacing(v);
    if (spacingInput) spacingInput.value = String(spacing);
    if (spacingOut) spacingOut.textContent = inches(spacing);
  }

  function changed() {
    render();
    renderSummary();
    persist();
    var share = document.getElementById("share-box");
    if (share) share.hidden = true; // an old link no longer matches
  }

  // --- palette ---------------------------------------------------------------

  function renderFilters() {
    if (!filtersEl) return;
    filtersEl.textContent = "";
    if (!cfg.categories.length) { filtersEl.hidden = true; return; }
    [{ id: null, name: "All" }].concat(cfg.categories).forEach(function (cat) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "pill" + (activeCategory === cat.id ? " active" : "");
      b.textContent = cat.name;
      b.setAttribute("aria-pressed", activeCategory === cat.id ? "true" : "false");
      b.addEventListener("click", function () {
        activeCategory = cat.id;
        renderFilters();
        renderPalette();
      });
      filtersEl.appendChild(b);
    });
  }

  function renderPalette() {
    paletteEl.textContent = "";
    var shown = cfg.images.filter(function (img) {
      return activeCategory === null || img.categories.indexOf(activeCategory) !== -1;
    });
    if (!cfg.images.length) {
      paletteEl.innerHTML = '<p class="hint">No tile designs yet.</p>';
      return;
    }
    shown.forEach(function (img) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "thumb";
      b.title = "Add “" + img.title + "”";
      var pic = document.createElement("img");
      pic.src = img.thumb;
      pic.alt = "";
      pic.draggable = false;
      pic.loading = "lazy";
      var cap = document.createElement("span");
      cap.textContent = img.title;
      b.appendChild(pic);
      b.appendChild(cap);
      b.addEventListener("pointerdown", startPointer.bind(null, { source: "palette", imageId: img.id }));
      b.addEventListener("click", function () {
        if (suppressClick) { suppressClick = false; return; }
        addImage(img.id);
      });
      paletteEl.appendChild(b);
    });
  }

  // --- drag and drop ---------------------------------------------------------

  function startPointer(info, e) {
    if (e.button !== 0 || drag) return;
    if (e.target.closest(".cell-remove")) return;
    drag = {
      source: info.source, fromKey: info.fromKey, imageId: info.imageId,
      startX: e.clientX, startY: e.clientY, pointerId: e.pointerId, started: false, target: null,
    };
    window.addEventListener("pointermove", onPointerMove, { passive: false });
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);
  }

  function beginDrag() {
    drag.started = true;
    var img = images.get(drag.imageId);
    var ghost = document.createElement("img");
    ghost.className = "drag-ghost";
    ghost.src = img.thumb;
    ghost.alt = "";
    var w = parseInt(gridEl.style.getPropertyValue("--cell-w"), 10) || 100;
    ghost.style.width = w + "px";
    ghost.style.height = Math.round(w * pricing.tileHeightIn / pricing.tileWidthIn) + "px";
    document.body.appendChild(ghost);
    drag.ghost = ghost;
    document.body.classList.add("is-dragging");
    render();
  }

  function onPointerMove(e) {
    if (!drag || e.pointerId !== drag.pointerId) return;
    if (!drag.started) {
      if (Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 6) return;
      beginDrag();
    }
    e.preventDefault();
    var g = drag.ghost;
    g.style.transform = "translate(" + (e.clientX - g.offsetWidth / 2) + "px," + (e.clientY - g.offsetHeight / 2) + "px) rotate(-3deg)";
    var target = cellAt(e.clientX, e.clientY);
    if (target !== drag.target) {
      if (drag.target) drag.target.classList.remove("drop-target");
      if (target) target.classList.add("drop-target");
      drag.target = target;
    }
    if (drag.source === "cell") {
      boardEl.classList.toggle("will-remove", !target && !overBoard(e.clientX, e.clientY));
    }
  }

  function cellAt(x, y) {
    var el = document.elementFromPoint(x, y);
    var cell = el && el.closest ? el.closest(".cell") : null;
    return cell && gridEl.contains(cell) ? cell : null;
  }

  function overBoard(x, y) {
    var r = canvasEl.getBoundingClientRect();
    return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  }

  function onPointerUp(e) {
    if (!drag || e.pointerId !== drag.pointerId) return;
    var d = drag;
    if (d.started) {
      suppressClick = true;
      setTimeout(function () { suppressClick = false; }, 0);
      var target = cellAt(e.clientX, e.clientY);
      if (target) {
        drop(d, target.dataset.k);
      } else if (d.source === "cell" && !overBoard(e.clientX, e.clientY)) {
        cells.delete(d.fromKey); // dragged off the wall
        normalize();
      }
    }
    endDrag();
    if (d.started) changed();
  }

  function onPointerCancel(e) {
    if (!drag || e.pointerId !== drag.pointerId) return;
    var started = drag.started;
    endDrag();
    if (started) render();
  }

  function endDrag() {
    if (drag && drag.ghost) drag.ghost.remove();
    drag = null;
    document.body.classList.remove("is-dragging");
    boardEl.classList.remove("will-remove");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerCancel);
  }

  function drop(d, targetKey) {
    var before = new Map(cells);
    if (d.source === "palette") {
      cells.set(targetKey, d.imageId);
    } else if (d.fromKey !== targetKey) {
      var existing = cells.get(targetKey);
      cells.set(targetKey, d.imageId);
      if (existing !== undefined) cells.set(d.fromKey, existing); // swap
      else cells.delete(d.fromKey);
    }
    if (!withinLimits()) cells = before;
    normalize();
  }

  // --- actions ---------------------------------------------------------------

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : "";
  }

  function bind(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("click", fn);
  }

  bind("clear-board", function () {
    if (cells.size && window.confirm("Remove all tiles from the wall?")) {
      cells = new Map();
      changed();
    }
  });

  bind("btn-order", function () {
    document.getElementById("order-layout").value = JSON.stringify(layout());
    document.getElementById("order-spacing").value = String(spacing);
    document.getElementById("order-form").submit();
  });

  bind("btn-wall", function () {
    if (window.CSTWall) window.CSTWall.open(layout(), images, pricing, spacing);
  });

  bind("btn-share", function () {
    var btn = document.getElementById("btn-share");
    btn.disabled = true;
    btn.textContent = "Making link…";
    fetch(cfg.urls.share, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify({ layout: layout(), spacing: spacing }),
      credentials: "same-origin",
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.body.error || "Couldn't make a link.");
        document.getElementById("share-url").value = res.body.url;
        document.getElementById("share-box").hidden = false;
      })
      .catch(function (err) { window.alert(err.message || "Couldn't make a link -- please try again."); })
      .finally(function () {
        btn.textContent = "Get a share link";
        btn.disabled = cells.size === 0;
      });
  });

  bind("share-copy", function () {
    var input = document.getElementById("share-url");
    var btn = document.getElementById("share-copy");
    var done = function () { btn.textContent = "Copied!"; setTimeout(function () { btn.textContent = "Copy"; }, 1500); };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(input.value).then(done, function () { input.select(); });
    } else {
      input.select();
      document.execCommand("copy");
      done();
    }
  });

  if (spacingInput) {
    spacingInput.min = "0";
    spacingInput.max = String(spacingCfg.max);
    spacingInput.step = String(spacingCfg.step);
    spacingInput.addEventListener("input", function () {
      setSpacing(spacingInput.value);
      // Same tiles, new gaps: re-measure rather than rebuild the board.
      resizeBoard();
      renderSummary();
      persist();
      var share = document.getElementById("share-box");
      if (share) share.hidden = true;
    });
  }

  var setForm = document.getElementById("set-form");
  if (setForm) {
    setForm.addEventListener("submit", function (e) {
      persist();
      if (!cells.size) {
        e.preventDefault();
        window.alert("Add at least one tile to the set first.");
      }
    });
  }

  // --- resizable palette -------------------------------------------------------
  //
  // The panel's width is user-adjustable (drag the handle on its right edge,
  // arrow keys when it's focused, double-click to reset) and remembered in
  // localStorage. Thumbnails wrap into as many columns as fit (CSS
  // auto-fill), so the palette never scrolls sideways. On phones the panel
  // sits above the board at full width and the handle is hidden.

  var WIDTH_KEY = "candyshoptiles:paletteWidth";
  var DEFAULT_PALETTE = 250, MIN_PALETTE = 180, MIN_BOARD = 320;
  var designerEl = document.getElementById("designer");
  var paletteBox = paletteEl.closest(".palette");
  var resizer = document.getElementById("palette-resizer");

  function maxPaletteWidth() {
    return Math.max(MIN_PALETTE, designerEl.clientWidth - MIN_BOARD);
  }

  function setPaletteWidth(w, save) {
    w = Math.round(Math.min(maxPaletteWidth(), Math.max(MIN_PALETTE, w)));
    designerEl.style.setProperty("--palette-w", w + "px");
    if (resizer) {
      resizer.setAttribute("aria-valuenow", String(w));
      resizer.setAttribute("aria-valuemax", String(Math.round(maxPaletteWidth())));
    }
    if (save) {
      try { localStorage.setItem(WIDTH_KEY, String(w)); } catch (e) { /* ignore */ }
    }
    resizeBoard();
  }

  // Width changes only need the cells re-measured, not rebuilt -- rebuilding
  // on every frame of a drag makes the tile images flicker.
  function resizeBoard() {
    var b = bounds();
    sizeCells(b ? b.rows : 1, b ? b.cols : 1);
  }

  if (resizer) {
    resizer.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      resizer.setPointerCapture(e.pointerId);
      var startX = e.clientX;
      var startW = paletteBox.getBoundingClientRect().width;
      var pending = null;
      document.body.classList.add("is-resizing");
      function move(ev) {
        pending = startW + ev.clientX - startX;
        requestAnimationFrame(function () {
          if (pending !== null) { setPaletteWidth(pending, false); pending = null; }
        });
      }
      function up() {
        resizer.removeEventListener("pointermove", move);
        resizer.removeEventListener("pointerup", up);
        resizer.removeEventListener("pointercancel", up);
        document.body.classList.remove("is-resizing");
        setPaletteWidth(paletteBox.getBoundingClientRect().width, true);
      }
      resizer.addEventListener("pointermove", move);
      resizer.addEventListener("pointerup", up);
      resizer.addEventListener("pointercancel", up);
    });
    resizer.addEventListener("keydown", function (e) {
      var w = paletteBox.getBoundingClientRect().width;
      var step = e.shiftKey ? 60 : 20;
      if (e.key === "ArrowLeft") w -= step;
      else if (e.key === "ArrowRight") w += step;
      else if (e.key === "Home") w = MIN_PALETTE;
      else if (e.key === "End") w = maxPaletteWidth();
      else return;
      e.preventDefault();
      setPaletteWidth(w, true);
    });
    resizer.addEventListener("dblclick", function () { setPaletteWidth(DEFAULT_PALETTE, true); });
  }

  // --- start -----------------------------------------------------------------

  var initial = cfg.initialLayout;
  var initialSpacing = cfg.initialSpacing;
  if (initial == null && cfg.mode === "customer") {
    try {
      var stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      // Older saves were a bare layout array, before spacing existed.
      if (Array.isArray(stored)) {
        initial = stored;
      } else {
        initial = stored.layout || [];
        if (initialSpacing == null) initialSpacing = stored.spacing;
      }
    } catch (e) { initial = []; }
  }
  setSpacing(initialSpacing == null ? spacingCfg.default : initialSpacing);
  load(initial);
  renderFilters();
  renderPalette();
  changed();

  var savedWidth = DEFAULT_PALETTE;
  try { savedWidth = Number(localStorage.getItem(WIDTH_KEY)) || DEFAULT_PALETTE; } catch (e) { /* ignore */ }
  setPaletteWidth(savedWidth, false);

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      // Re-clamp against the new window size (also re-measures the board).
      setPaletteWidth(paletteBox.getBoundingClientRect().width, false);
    }, 120);
  });


  window.CSTDesigner = { layout: layout, images: images, pricing: pricing, inches: inches };
})();

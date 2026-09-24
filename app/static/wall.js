/*
 * "View on a wall" preview.
 *
 * Built-in walls know how many inches wide the picture is (data-inches), so
 * the tiles are drawn true to scale at 100%. For the customer's own photo
 * there's no way to know the scale, so it starts at a sensible size and the
 * slider + drag let them fit it to their wall.
 *
 * The customer's photo is read with URL.createObjectURL and never leaves
 * their browser -- nothing here uploads anything.
 */
(function () {
  "use strict";

  var dialog = document.getElementById("wall-dialog");
  if (!dialog) return;

  var stage = document.getElementById("wall-stage");
  var bg = document.getElementById("wall-bg");
  var gridEl = document.getElementById("wall-grid");
  var scaleInput = document.getElementById("wall-scale");
  var scaleLabel = document.getElementById("wall-scale-label");
  var hint = document.getElementById("wall-hint");
  var photoInput = document.getElementById("wall-photo");
  var choices = Array.prototype.slice.call(dialog.querySelectorAll(".wall-choice"));
  var sizeEl = document.getElementById("wall-size");
  var dimW = document.getElementById("wall-dim-w");
  var dimH = document.getElementById("wall-dim-h");
  var showDims = document.getElementById("wall-show-dims");
  var DIM_OFFSET = 14; // px between the tiles and a measurement line

  var state = { layout: [], images: null, pricing: null, spacing: 0.5, wall: null, x: 0.5, y: 0.4, photoUrl: null };

  function scale() { return Number(scaleInput.value) / 100; }

  // Same formatting as the designer's readouts (24.5 -> "24½″").
  function inches(v) {
    return window.CSTDesigner && window.CSTDesigner.inches ? window.CSTDesigner.inches(v) : v + "″";
  }

  // Real-world size of the tile pattern -- gaps between tiles count, the
  // wall around them doesn't.
  function realSize(d) {
    var p = state.pricing;
    return {
      w: d.cols * p.tileWidthIn + Math.max(d.cols - 1, 0) * state.spacing,
      h: d.rows * p.tileHeightIn + Math.max(d.rows - 1, 0) * state.spacing,
    };
  }

  // Dimension lines, like on a floor plan: width below the tiles, height to
  // their right -- each flipped to the other side when it would run off the
  // picture. They follow the tiles as they're dragged and resized.
  function placeDims(left, top, gw, gh, frameW, frameH) {
    var on = showDims.checked;
    dimW.hidden = dimH.hidden = !on;
    if (!on) return;
    var d = dims(), size = realSize(d);
    var below = top + gh + DIM_OFFSET + 16 <= frameH;
    dimW.style.left = left + "px";
    dimW.style.width = gw + "px";
    dimW.style.top = (below ? top + gh + DIM_OFFSET : top - DIM_OFFSET) + "px";
    dimW.firstChild.textContent = inches(size.w);
    var right = left + gw + DIM_OFFSET + 40 <= frameW;
    dimH.style.top = top + "px";
    dimH.style.height = gh + "px";
    dimH.style.left = (right ? left + gw + DIM_OFFSET : left - DIM_OFFSET) + "px";
    dimH.firstChild.textContent = inches(size.h);
  }

  function dims() {
    var rows = 0, cols = 0;
    state.layout.forEach(function (t) { rows = Math.max(rows, t.r + 1); cols = Math.max(cols, t.c + 1); });
    return { rows: rows, cols: cols };
  }

  function buildTiles() {
    gridEl.textContent = "";
    state.layout.forEach(function (t) {
      var img = state.images.get(t.image_id);
      if (!img) return;
      var el = document.createElement("img");
      el.src = img.full;
      el.alt = img.title;
      el.draggable = false;
      el.dataset.r = t.r;
      el.dataset.c = t.c;
      gridEl.appendChild(el);
    });
  }

  function place() {
    var w = bg.clientWidth, h = bg.clientHeight;
    if (!w || !h || !state.wall) return;
    var p = state.pricing, d = dims();
    var ppi;
    if (state.wall.photo) {
      // Start the grid at ~40% of the photo's width, then let them adjust.
      var gridInches = d.cols * p.tileWidthIn + (d.cols - 1) * state.spacing;
      ppi = (0.4 * w) / Math.max(gridInches, p.tileWidthIn);
    } else {
      ppi = w / state.wall.inches;
    }
    ppi *= scale();
    var tw = p.tileWidthIn * ppi, th = p.tileHeightIn * ppi, gap = state.spacing * ppi;
    var gw = d.cols * tw + (d.cols - 1) * gap;
    var gh = d.rows * th + (d.rows - 1) * gap;
    gridEl.style.width = gw + "px";
    gridEl.style.height = gh + "px";
    var left = state.x * w - gw / 2, top = state.y * h - gh / 2;
    gridEl.style.left = left + "px";
    gridEl.style.top = top + "px";
    placeDims(left, top, gw, gh, w, h);
    Array.prototype.forEach.call(gridEl.children, function (el) {
      el.style.width = tw + "px";
      el.style.height = th + "px";
      el.style.left = (el.dataset.c * (tw + gap)) + "px";
      el.style.top = (el.dataset.r * (th + gap)) + "px";
    });
    var pct = Number(scaleInput.value);
    scaleLabel.textContent = state.wall.photo ? pct + "%" : (pct === 100 ? "True to scale" : pct + "% of real size");
  }

  function select(choice, wall) {
    choices.forEach(function (c) { c.setAttribute("aria-checked", c === choice ? "true" : "false"); });
    state.wall = wall;
    state.x = 0.5;
    state.y = wall.y;
    scaleInput.value = 100;
    hint.textContent = "";
    hint.classList.toggle("wall-instruction", !!wall.photo);
    if (wall.photo) {
      // There's no way to know a photo's real scale, so the customer has to
      // set it -- lead with that.
      var lead = document.createElement("strong");
      lead.textContent = "Adjust the scale to accurately reflect the space on the image of your wall.";
      hint.appendChild(lead);
      hint.appendChild(document.createTextNode(
        " Use the Size slider until the measurements match something you know, like a door (about 80″ tall)" +
        " or a light switch plate (about 4½″ tall), then drag the tiles into place." +
        " Your photo stays on your device -- it isn't uploaded."
      ));
    } else {
      hint.textContent = "Drag the tiles to move them. At 100% this wall is drawn true to scale.";
    }
    if (bg.getAttribute("src") === wall.src && bg.complete) {
      place();
    } else {
      bg.src = wall.src;
    }
  }

  choices.forEach(function (choice) {
    if (!choice.dataset.wall) return; // the upload label is handled below
    choice.addEventListener("click", function () {
      select(choice, { src: choice.dataset.src, inches: Number(choice.dataset.inches), y: Number(choice.dataset.y) });
    });
  });

  photoInput.addEventListener("change", function () {
    var file = photoInput.files && photoInput.files[0];
    if (!file) return;
    if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
    state.photoUrl = URL.createObjectURL(file);
    select(photoInput.closest(".wall-choice"), { src: state.photoUrl, photo: true, y: 0.4 });
    photoInput.value = "";
  });

  bg.addEventListener("load", place);
  showDims.addEventListener("change", place);
  scaleInput.addEventListener("input", place);
  document.getElementById("wall-reset").addEventListener("click", function () {
    if (!state.wall) return;
    state.x = 0.5;
    state.y = state.wall.y;
    scaleInput.value = 100;
    place();
  });

  // Drag the whole grid around the wall.
  var move = null;
  gridEl.addEventListener("pointerdown", function (e) {
    if (e.button !== 0) return;
    gridEl.setPointerCapture(e.pointerId);
    move = { id: e.pointerId, sx: e.clientX, sy: e.clientY, x: state.x, y: state.y };
    gridEl.classList.add("moving");
  });
  gridEl.addEventListener("pointermove", function (e) {
    if (!move || e.pointerId !== move.id) return;
    state.x = Math.min(1, Math.max(0, move.x + (e.clientX - move.sx) / bg.clientWidth));
    state.y = Math.min(1, Math.max(0, move.y + (e.clientY - move.sy) / bg.clientHeight));
    place();
  });
  function endMove(e) {
    if (!move || e.pointerId !== move.id) return;
    move = null;
    gridEl.classList.remove("moving");
  }
  gridEl.addEventListener("pointerup", endMove);
  gridEl.addEventListener("pointercancel", endMove);

  if (window.ResizeObserver) new ResizeObserver(place).observe(stage);
  else window.addEventListener("resize", place);

  document.getElementById("wall-close").addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });

  window.CSTWall = {
    open: function (layout, images, pricing, spacing) {
      state.layout = layout;
      state.spacing = spacing == null ? 0.5 : spacing;
      state.images = images;
      state.pricing = pricing;
      buildTiles();
      var size = realSize(dims());
      sizeEl.textContent = inches(size.w) + " wide × " + inches(size.h) + " tall" +
        (state.layout.length > 1 ? " · " + inches(state.spacing) + " between tiles" : "");
      dialog.showModal();
      if (!state.wall) choices[0].click();
      else place();
    },
  };
})();

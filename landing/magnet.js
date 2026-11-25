// Interactive dot grid behind the hero stage and the setup board: dots lean toward the pointer and spring back.
(() => {
  const STEP = 16, DOT = 0.9, BIG = 1.6, RADIUS = 150, PULL = 0.28, EASE = 0.18;
  const BASE_ALPHA = 0.35, NEAR_ALPHA = 0.7, RGB = "84, 123, 77";
  const still = matchMedia("(prefers-reduced-motion: reduce), (hover: none)").matches;

  function setup(host) {
    const canvas = document.createElement("canvas");
    canvas.className = "magnet";
    canvas.setAttribute("aria-hidden", "true");
    host.prepend(canvas);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = 0, h = 0, cols = 0, rows = 0;
    let ox, oy, ot; // current offset and "nearness" per dot
    let pointer = null;
    let visible = true;
    let frame = 0;

    function resize() {
      const dpr = window.devicePixelRatio || 1;
      w = host.clientWidth; h = host.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(w / STEP); rows = Math.ceil(h / STEP);
      ox = new Float32Array(cols * rows); oy = new Float32Array(cols * rows); ot = new Float32Array(cols * rows);
      draw();
    }

    // Moves every dot one easing step toward its target and paints; returns true while anything still moves.
    function draw() {
      ctx.clearRect(0, 0, w, h);
      let moving = false;
      ctx.fillStyle = `rgba(${RGB}, ${BASE_ALPHA})`;
      ctx.beginPath();
      const lifted = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const i = r * cols + c;
          const x = c * STEP + STEP / 2, y = r * STEP + STEP / 2;
          let tx = 0, ty = 0, tn = 0;
          if (pointer) {
            const dx = pointer.x - x, dy = pointer.y - y, d = Math.hypot(dx, dy);
            if (d < RADIUS) {
              const f = 1 - d / RADIUS;
              tx = dx * PULL * f * f; ty = dy * PULL * f * f; tn = f;
            }
          }
          ox[i] += (tx - ox[i]) * EASE; oy[i] += (ty - oy[i]) * EASE; ot[i] += (tn - ot[i]) * EASE;
          const settled = Math.abs(ox[i]) < 0.02 && Math.abs(oy[i]) < 0.02 && ot[i] < 0.01;
          if (!settled || tn > 0) moving = true;
          if (settled) { ox[i] = oy[i] = ot[i] = 0; ctx.moveTo(x + DOT, y); ctx.arc(x, y, DOT, 0, 6.2832); }
          else lifted.push(i, x, y);
        }
      }
      ctx.fill();
      for (let k = 0; k < lifted.length; k += 3) {
        const i = lifted[k], t = ot[i];
        ctx.fillStyle = `rgba(${RGB}, ${BASE_ALPHA + (NEAR_ALPHA - BASE_ALPHA) * t})`;
        ctx.beginPath();
        ctx.arc(lifted[k + 1] + ox[i], lifted[k + 2] + oy[i], DOT + (BIG - DOT) * t, 0, 6.2832);
        ctx.fill();
      }
      return moving;
    }

    function tick() {
      frame = 0;
      if (draw() && visible) frame = requestAnimationFrame(tick);
    }
    const kick = () => { if (!frame && visible) frame = requestAnimationFrame(tick); };

    new ResizeObserver(resize).observe(host);
    resize();
    if (still) return; // static grid, drawn once

    host.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") return;
      const box = canvas.getBoundingClientRect();
      pointer = { x: e.clientX - box.left, y: e.clientY - box.top };
      kick();
    });
    host.addEventListener("pointerleave", () => { pointer = null; kick(); });
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (!visible) { cancelAnimationFrame(frame); frame = 0; } else kick();
    }).observe(host);
  }

  document.querySelectorAll(".canvas-stage, .setup-board").forEach(setup);
})();

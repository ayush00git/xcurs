// xcurs touchpad: turns touches into mouse messages, and draws them in light.
(() => {
  "use strict";

  // ---- settings ----------------------------------------------------------
  // localStorage can be missing or throw (private mode), so every access is
  // guarded and the defaults always work.
  const store = {
    get(k, d) {
      try { const v = localStorage.getItem("xcurs." + k); return v === null ? d : JSON.parse(v); }
      catch (_) { return d; }
    },
    set(k, v) { try { localStorage.setItem("xcurs." + k, JSON.stringify(v)); } catch (_) {} },
  };
  const DEFAULTS = { sens: 1.4, accel: 0.8, scroll: 1, natural: true, haptics: true };
  const settings = { ...DEFAULTS, ...store.get("settings", {}) };

  // ---- tuning ------------------------------------------------------------
  const PX_PER_NOTCH = 36;     // finger travel for one scroll notch, at scroll speed 1
  const TAP_MS = 230;          // a touch shorter than this...
  const TAP_SLOP = 10;         // ...that moved less than this (px) is a tap
  const DOUBLE_TAP_MS = 300;   // tap, then touch again within this -> drag
  const DOUBLE_TAP_SLOP = 48;

  // ---- connection --------------------------------------------------------
  const statusEl = document.getElementById("status");
  const statusLabel = statusEl.querySelector(".label");
  let ws = null;
  let retryMs = 400;

  // The QR code's URL carries the pairing token after "#t=". Keep it, then
  // tidy it out of the address bar.
  const fromUrl = location.hash.match(/[#&]t=([\w-]+)/);
  const token = fromUrl ? fromUrl[1] : store.get("token", "");
  if (fromUrl) {
    store.set("token", token);
    history.replaceState(null, "", location.pathname);
  }
  const q = `?t=${encodeURIComponent(token)}`;
  // Scanning the QR again while this page is already open only changes the
  // "#", which doesn't reload. Reload so the new token is picked up.
  window.addEventListener("hashchange", () => location.reload());

  function setStatus(state, label) {
    statusEl.classList.toggle("live", state === "live");
    statusEl.classList.toggle("unpaired", state === "unpaired");
    statusLabel.textContent = label;
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let opened = false;
    ws = new WebSocket(`${proto}://${location.host}/ws${q}`);
    ws.onopen = () => {
      opened = true;
      retryMs = 400;
      setStatus("live", "connected");
    };
    ws.onclose = async () => {
      let delay = retryMs;
      retryMs = Math.min(retryMs * 2, 4000);
      setStatus("", "connecting");
      if (!opened) {
        // Refused before it opened: ask the laptop whether it's our token.
        try {
          const r = await fetch(`/check${q}`, { cache: "no-store" });
          if (r.status === 401) { setStatus("unpaired", "scan the qr to pair"); delay = 4000; }
        } catch (_) {}
      }
      setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
  }
  connect();

  // Motion is summed and sent once per animation frame (~60 Hz), so a burst
  // of touchmove events becomes one small packet. Clicks go out right away,
  // after any motion still waiting, so the order is never scrambled.
  let moveX = 0, moveY = 0, scrollX = 0, scrollY = 0;

  function flush(extra) {
    const batch = [];
    if (moveX || moveY) batch.push(["m", round2(moveX), round2(moveY)]);
    if (scrollX || scrollY) batch.push(["s", round2(scrollX), round2(scrollY)]);
    if (extra) batch.push(extra);
    moveX = moveY = scrollX = scrollY = 0;
    if (batch.length && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(batch));
    }
  }
  const round2 = (v) => Math.round(v * 100) / 100;
  const buzz = (ms) => {
    if (!settings.haptics) return;
    try { navigator.vibrate && navigator.vibrate(ms); } catch (_) {}
  };

  // ---- gestures ----------------------------------------------------------
  const touches = new Map();   // id -> {x, y}
  let gesture = null;          // the current run of touches, first down to last up
  let lastTap = null;          // {t, x, y} of the last one-finger tap
  let dragging = false;
  let lastMoveT = 0;

  // Pointer acceleration: slow fingers get exactly the base sensitivity, for
  // precision; fast flicks get extra gain, so one swipe can cross the screen.
  function gainFor(dist, dt) {
    const speed = dist / Math.max(dt, 1);              // px per ms
    const boost = Math.max(0, Math.min(speed, 3) - 0.15);
    return settings.sens * (1 + settings.accel * boost);
  }

  function onStart(e) {
    e.preventDefault();
    document.body.classList.add("touching", "used");
    const now = performance.now();
    lastMoveT = now;

    for (const t of e.changedTouches) {
      if (touches.size === 0) {
        gesture = { t0: now, max: 0, travel: 0, x: t.clientX, y: t.clientY };
        const near = lastTap && Math.hypot(t.clientX - lastTap.x, t.clientY - lastTap.y) < DOUBLE_TAP_SLOP;
        if (near && now - lastTap.t < DOUBLE_TAP_MS) {
          dragging = true;
          flush(["d", "left"]);
          fx.dragStart(t.identifier);
          buzz(12);
        }
      }
      touches.set(t.identifier, { x: t.clientX, y: t.clientY });
      fx.down(t.identifier, t.clientX, t.clientY);
    }
    gesture.max = Math.max(gesture.max, touches.size);
  }

  function onMove(e) {
    e.preventDefault();
    let sx = 0, sy = 0, n = 0;
    for (const t of e.changedTouches) {
      const prev = touches.get(t.identifier);
      if (!prev) continue;
      const dx = t.clientX - prev.x, dy = t.clientY - prev.y;
      prev.x = t.clientX; prev.y = t.clientY;
      sx += dx; sy += dy; n++;
      gesture.travel += Math.hypot(dx, dy);
      fx.move(t.identifier, t.clientX, t.clientY);
    }
    if (!n) return;

    const now = performance.now();
    const dt = now - lastMoveT;
    lastMoveT = now;

    if (touches.size >= 2) {
      // Two fingers: scroll by their average motion. "Natural" means the
      // content follows the fingers. Kernel signs: +y is up, +x is right.
      const k = (settings.natural ? 1 : -1) * settings.scroll / PX_PER_NOTCH;
      scrollY += (sy / n) * k;
      scrollX -= (sx / n) * k;
      fx.scroll(sy / n);
    } else if (gesture.max === 1 || dragging) {
      // One finger moves the cursor, but only if this gesture never had a
      // second finger: lifting one finger of a scroll shouldn't jerk the cursor.
      const g = gainFor(Math.hypot(sx, sy), dt);
      moveX += sx * g;
      moveY += sy * g;
    }
  }

  function onEnd(e) {
    e.preventDefault();
    const now = performance.now();
    let last = null;
    for (const t of e.changedTouches) {
      touches.delete(t.identifier);
      fx.up(t.identifier);
      last = t;
    }
    if (touches.size > 0 || !gesture) return;

    document.body.classList.remove("touching");
    const isTap = now - gesture.t0 < TAP_MS && gesture.travel < TAP_SLOP;

    if (dragging) {
      dragging = false;
      flush(["u", "left"]);
      lastTap = null;
      if (isTap) fx.ripple(last.clientX, last.clientY, 1); // tap, tap = double click
    } else if (isTap) {
      const button = ["left", "right", "middle"][Math.min(gesture.max, 3) - 1];
      flush(["c", button]);
      fx.ripple(gesture.x, gesture.y, Math.min(gesture.max, 3));
      buzz(8);
      lastTap = gesture.max === 1 ? { t: now, x: gesture.x, y: gesture.y } : null;
    } else {
      lastTap = null;
    }
    gesture = null;
  }

  const pad = document.getElementById("pad");
  pad.addEventListener("touchstart", onStart, { passive: false });
  pad.addEventListener("touchmove", onMove, { passive: false });
  pad.addEventListener("touchend", onEnd, { passive: false });
  pad.addEventListener("touchcancel", onEnd, { passive: false });
  document.addEventListener("gesturestart", (e) => e.preventDefault()); // iOS pinch-zoom
  document.addEventListener("contextmenu", (e) => e.preventDefault());

  // ---- settings sheet ----------------------------------------------------
  const sheet = document.getElementById("sheet");
  const menu = document.getElementById("menu");

  function openSheet(open) {
    sheet.classList.toggle("open", open);
    sheet.setAttribute("aria-hidden", String(!open));
    menu.setAttribute("aria-expanded", String(open));
  }
  menu.addEventListener("click", () => openSheet(!sheet.classList.contains("open")));
  sheet.addEventListener("click", (e) => { if (e.target === sheet) openSheet(false); });
  document.getElementById("done").addEventListener("click", () => openSheet(false));

  for (const input of sheet.querySelectorAll("[data-key]")) {
    const key = input.dataset.key;
    const out = sheet.querySelector(`[data-out="${key}"]`);
    const show = () => { if (out) out.textContent = Number(settings[key]).toFixed(1); };
    if (input.type === "checkbox") input.checked = settings[key];
    else input.value = settings[key];
    show();
    input.addEventListener("input", () => {
      settings[key] = input.type === "checkbox" ? input.checked : Number(input.value);
      store.set("settings", settings);
      show();
    });
  }
  document.getElementById("reset").addEventListener("click", () => {
    Object.assign(settings, DEFAULTS);
    store.set("settings", settings);
    for (const input of sheet.querySelectorAll("[data-key]")) {
      if (input.type === "checkbox") input.checked = settings[input.dataset.key];
      else input.value = settings[input.dataset.key];
      input.dispatchEvent(new Event("input"));
    }
  });

  // ---- light -------------------------------------------------------------
  // Everything is drawn on one canvas: a soft glow under each finger, a
  // fading comet trail behind it, and rings that bloom out on a tap.
  const fx = (() => {
    const ctx = pad.getContext("2d");
    let w = 0, h = 0, dpr = 1;
    const fingers = new Map(); // id -> {x, y, gx, gy, life, trail: [{x, y, t}], drag}
    const ripples = [];        // {x, y, t0, delay}
    let scrollPulse = 0, scrollOffset = 0;

    const TRAIL_MS = 380;
    const easeOut = (t) => 1 - Math.pow(1 - t, 3);

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 3);
      w = window.innerWidth; h = window.innerHeight;
      pad.width = Math.round(w * dpr);
      pad.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    window.addEventListener("resize", resize);
    resize();

    function down(id, x, y) {
      fingers.set(id, { x, y, gx: x, gy: y, life: 0, alive: true, trail: [{ x, y, t: performance.now() }], drag: false });
    }
    function move(id, x, y) {
      const f = fingers.get(id);
      if (!f) return;
      f.x = x; f.y = y;
      f.trail.push({ x, y, t: performance.now() });
    }
    function up(id) {
      const f = fingers.get(id);
      if (f) f.alive = false;
    }
    function dragStart(id) {
      const f = fingers.get(id);
      if (f) f.drag = true;
    }
    function ripple(x, y, rings) {
      const t0 = performance.now();
      for (let i = 0; i < rings; i++) ripples.push({ x, y, t0, delay: i * 90 });
    }
    function scroll(dy) {
      scrollPulse = 1;
      scrollOffset += dy;
    }

    function drawTrail(f, now) {
      const pts = f.trail;
      while (pts.length && now - pts[0].t > TRAIL_MS) pts.shift();
      if (pts.length < 2) return;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      // Smooth through midpoints with quadratic curves; older segments are
      // thinner and dimmer, so the trail tapers like a comet's tail.
      for (let i = 1; i < pts.length - 1; i++) {
        const a = pts[i - 1], b = pts[i], c = pts[i + 1];
        const k = 1 - (now - b.t) / TRAIL_MS;
        ctx.strokeStyle = `rgba(255,255,255,${0.55 * k * k})`;
        ctx.lineWidth = 1 + 9 * k * k;
        ctx.beginPath();
        ctx.moveTo((a.x + b.x) / 2, (a.y + b.y) / 2);
        ctx.quadraticCurveTo(b.x, b.y, (b.x + c.x) / 2, (b.y + c.y) / 2);
        ctx.stroke();
      }
    }

    function drawFinger(f) {
      // Glow eases toward the finger, so it feels liquid rather than stuck on.
      f.gx += (f.x - f.gx) * 0.45;
      f.gy += (f.y - f.gy) * 0.45;
      f.life += ((f.alive ? 1 : 0) - f.life) * (f.alive ? 0.22 : 0.12);
      const a = f.life;
      const r = 34 + 10 * a;

      const g = ctx.createRadialGradient(f.gx, f.gy, 0, f.gx, f.gy, r * 2.2);
      g.addColorStop(0, `rgba(255,255,255,${0.30 * a})`);
      g.addColorStop(0.35, `rgba(255,255,255,${0.10 * a})`);
      g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(f.gx, f.gy, r * 2.2, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = `rgba(255,255,255,${0.75 * a})`;
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      ctx.arc(f.gx, f.gy, r * (f.drag ? 0.8 : 0.62), 0, Math.PI * 2);
      ctx.stroke();

      if (f.drag) {
        // Holding a drag: a solid core that slowly breathes.
        const breathe = 0.5 + 0.5 * Math.sin(performance.now() / 260);
        ctx.fillStyle = `rgba(255,255,255,${(0.75 + 0.2 * breathe) * a})`;
        ctx.beginPath();
        ctx.arc(f.gx, f.gy, 7 + 2 * breathe, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillStyle = `rgba(255,255,255,${0.9 * a})`;
        ctx.beginPath();
        ctx.arc(f.gx, f.gy, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function drawRipples(now) {
      for (let i = ripples.length - 1; i >= 0; i--) {
        const rp = ripples[i];
        const t = (now - rp.t0 - rp.delay) / 620;
        if (t < 0) continue;
        if (t >= 1) { ripples.splice(i, 1); continue; }
        const e = easeOut(t);
        ctx.strokeStyle = `rgba(255,255,255,${0.85 * (1 - e)})`;
        ctx.lineWidth = 1.5 * (1 - e) + 0.5;
        ctx.beginPath();
        ctx.arc(rp.x, rp.y, 12 + 78 * e, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    function drawScrollRail() {
      // A slim rail on the right edge, with ticks that slide as you scroll.
      if (scrollPulse < 0.01) return;
      const x = w - 14, top = h * 0.25, len = h * 0.5, gap = 22;
      ctx.strokeStyle = `rgba(255,255,255,${0.12 * scrollPulse})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + len);
      ctx.stroke();
      const off = ((scrollOffset % gap) + gap) % gap;
      for (let y = top + off; y < top + len; y += gap) {
        const edge = Math.min(y - top, top + len - y) / 40; // fade at the ends
        ctx.fillStyle = `rgba(255,255,255,${0.7 * scrollPulse * Math.min(1, edge)})`;
        ctx.fillRect(x - 3, y, 6, 1.5);
      }
      scrollPulse *= 0.94;
    }

    function frame() {
      const now = performance.now();
      ctx.clearRect(0, 0, w, h);
      for (const [id, f] of fingers) {
        drawTrail(f, now);
        drawFinger(f);
        if (!f.alive && f.life < 0.02 && f.trail.length < 2) fingers.delete(id);
      }
      drawRipples(now);
      drawScrollRail();
      flush();
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    return { down, move, up, dragStart, ripple, scroll };
  })();
})();

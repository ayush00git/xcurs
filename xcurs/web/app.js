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
  const DOUBLE_TAP_MS = 250;   // tap, then touch again within this -> drag
  const DOUBLE_TAP_SLOP = 48;
  const PX_TO_MM = 0.18;       // phone css px -> mm on the virtual touchpad (3/4-finger swipes)

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
  let swipeFingers = 0, swipeX = 0, swipeY = 0;   // a 3/4-finger desktop gesture

  function flush(extra) {
    const batch = [];
    if (moveX || moveY) batch.push(["m", round2(moveX), round2(moveY)]);
    if (scrollX || scrollY) batch.push(["s", round2(scrollX), round2(scrollY)]);
    if (swipeFingers && (swipeX || swipeY)) batch.push(["t", swipeFingers, round2(swipeX), round2(swipeY)]);
    if (extra) batch.push(extra);
    moveX = moveY = scrollX = scrollY = swipeX = swipeY = 0;
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
  let pendingClick = null;     // that tap's click, held back in case it becomes a drag
  let dragging = false;
  let lastMoveT = 0;

  // Pointer acceleration: slow fingers get exactly the base sensitivity, for
  // precision; fast flicks get extra gain, so one swipe can cross the screen.
  function gainFor(dist, dt) {
    const speed = dist / Math.max(dt, 1);              // px per ms
    const boost = Math.max(0, Math.min(speed, 3) - 0.15);
    return settings.sens * (1 + settings.accel * boost);
  }

  // A single tap's click waits DOUBLE_TAP_MS before it's sent, like on a
  // laptop touchpad. If a finger comes back in that time, the tap was the
  // start of a drag ("tap, then touch and hold"), so nothing gets clicked.
  function holdClick() {
    pendingClick = setTimeout(() => {
      pendingClick = null;
      flush(["c", "left"]);
    }, DOUBLE_TAP_MS);
  }

  function sendPendingClickNow() {
    if (!pendingClick) return;
    clearTimeout(pendingClick);
    pendingClick = null;
    flush(["c", "left"]);
  }

  function endSwipe() {
    if (!swipeFingers) return;
    flush();
    swipeFingers = 0;
    flush(["t", 0, 0, 0]);
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
        if (near && pendingClick && now - lastTap.t < DOUBLE_TAP_MS) {
          // Tap, then touch again: a drag. The held-back click is dropped.
          clearTimeout(pendingClick);
          pendingClick = null;
          dragging = true;
          flush(["d", "left"]);
          fx.dragStart(t.identifier);
          buzz(12);
        } else {
          sendPendingClickNow(); // some other gesture: let the earlier tap click first
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

    if (touches.size >= 3 && !dragging) {
      // Three or four fingers: a desktop gesture (switch workspace, overview,
      // ...). Once they've clearly moved, play the swipe on the laptop's
      // virtual touchpad and let the desktop decide what it means.
      const fingers = Math.min(touches.size, 4);
      if (fingers !== swipeFingers && gesture.travel > TAP_SLOP * fingers) {
        endSwipe();
        swipeFingers = fingers;
      }
      if (swipeFingers) {
        swipeX += (sx / n) * PX_TO_MM;
        swipeY += (sy / n) * PX_TO_MM;
      }
    } else if (touches.size === 2 && gesture.max < 3) {
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
    // Lifting below three fingers ends a desktop gesture.
    if (swipeFingers && touches.size < 3) endSwipe();
    if (touches.size > 0 || !gesture) return;

    document.body.classList.remove("touching");
    const isTap = now - gesture.t0 < TAP_MS && gesture.travel < TAP_SLOP;

    if (dragging) {
      dragging = false;
      flush(["u", "left"]);
      lastTap = null;
      if (isTap) {
        // Tap, tap: the press and release above were the first click; add the
        // second one, and it's a double click.
        flush(["c", "left"]);
        fx.ripple(last.clientX, last.clientY, 1);
      }
    } else if (isTap) {
      const fingers = Math.min(gesture.max, 3);
      if (fingers === 1) {
        holdClick();
      } else {
        flush(["c", fingers === 2 ? "right" : "middle"]);
      }
      fx.ripple(gesture.x, gesture.y, fingers);
      buzz(8);
      lastTap = fingers === 1 ? { t: now, x: gesture.x, y: gesture.y } : null;
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
  // Nothing here has an edge. Everything is drawn by stamping one soft,
  // pre-rendered glow sprite, added together ("lighter") so blobs that meet
  // melt into each other like drops of liquid light.
  //   finger  a droplet on a spring: it lags, overshoots and stretches with speed
  //   ink     particles shed along the path that drift, swell and dissolve
  //   tap     a soft wave that spreads out like a ripple on water
  const fx = (() => {
    const ctx = pad.getContext("2d");
    let w = 0, h = 0, dpr = 1;

    function makeSprite(stop) {
      const size = 256, c = document.createElement("canvas");
      c.width = c.height = size;
      const s = c.getContext("2d");
      const g = s.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
      for (let i = 0; i <= 24; i++) {
        const t = i / 24;
        g.addColorStop(t, `rgba(255,255,255,${stop(t).toFixed(4)})`);
      }
      s.fillStyle = g;
      s.fillRect(0, 0, size, size);
      return c;
    }
    // A gaussian dot, and a gaussian ring (for ripples). Both reach exactly
    // zero before the sprite's border, so no edge can ever show.
    const DOT = makeSprite((t) => Math.exp(-t * t * 5) * (1 - t * t));
    const RING = makeSprite((t) => Math.exp(-Math.pow((t - 0.72) / 0.11, 2)) * (1 - t * t));

    function stamp(img, x, y, r, a, angle = 0, stretch = 1) {
      if (a < 0.004 || r < 0.5) return;
      ctx.globalAlpha = Math.min(a, 1);
      if (stretch === 1) {
        ctx.drawImage(img, x - r, y - r, r * 2, r * 2);
        return;
      }
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(angle);
      ctx.scale(stretch, 1 / Math.sqrt(stretch)); // a drop thins as it stretches
      ctx.drawImage(img, -r, -r, r * 2, r * 2);
      ctx.restore();
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 3);
      w = window.innerWidth; h = window.innerHeight;
      pad.width = Math.round(w * dpr);
      pad.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    window.addEventListener("resize", resize);
    resize();

    const fingers = new Map(); // id -> droplet
    const ink = [];            // shed particles
    const waves = [];          // tap ripples
    const MAX_INK = 520;
    let scrollEnergy = 0, scrollOffset = 0;

    const easeOut = (t) => 1 - Math.pow(1 - t, 3);
    const rand = (a, b) => a + Math.random() * (b - a);

    function down(id, x, y) {
      fingers.set(id, {
        tx: x, ty: y, x, y, vx: 0, vy: 0,
        ex: x, ey: y,          // where ink was last shed
        life: 0, alive: true, drag: false, born: performance.now(),
      });
      // A soft bloom where the finger lands.
      waves.push({ x, y, t0: performance.now(), delay: 0, size: 46, dur: 520, a: 0.22 });
    }

    function move(id, x, y) {
      const f = fingers.get(id);
      if (!f) return;
      const dx = x - f.tx, dy = y - f.ty;
      f.tx = x; f.ty = y;
      // Shed ink every 4px along the path, drifting the way the finger went.
      const dist = Math.hypot(x - f.ex, y - f.ey);
      const steps = Math.floor(dist / 4);
      for (let i = 1; i <= steps && ink.length < MAX_INK; i++) {
        const k = i / steps;
        ink.push({
          x: f.ex + (x - f.ex) * k + rand(-2, 2),
          y: f.ey + (y - f.ey) * k + rand(-2, 2),
          vx: dx * 0.05 + rand(-0.25, 0.25),
          vy: dy * 0.05 + rand(-0.25, 0.25),
          r0: rand(7, 12), grow: rand(22, 40),
          a: rand(0.07, 0.11) * (f.drag ? 1.5 : 1),
          t0: performance.now(), dur: rand(650, 1050),
        });
      }
      if (steps) { f.ex = x; f.ey = y; }
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
      for (let i = 0; i < rings; i++) {
        waves.push({ x, y, t0, delay: i * 120, size: 120 + i * 18, dur: 950, a: 0.5 });
      }
    }

    function scroll(dy) {
      scrollEnergy = Math.min(1, scrollEnergy + Math.abs(dy) / 30);
      scrollOffset += dy;
    }

    function drawFinger(f, now, step) {
      // Spring toward the real touch point: soft lag, a hint of overshoot.
      f.vx += (f.tx - f.x) * 0.3 * step;
      f.vy += (f.ty - f.y) * 0.3 * step;
      const damp = Math.pow(0.58, step);
      f.vx *= damp; f.vy *= damp;
      f.x += f.vx * step; f.y += f.vy * step;

      f.life += ((f.alive ? 1 : 0) - f.life) * (1 - Math.pow(f.alive ? 0.8 : 0.9, step));
      const a = f.life;
      const speed = Math.hypot(f.vx, f.vy);
      const angle = Math.atan2(f.vy, f.vx);
      const stretch = 1 + Math.min(speed / 22, 0.9);
      const breathe = 0.5 + 0.5 * Math.sin((now - f.born) / (f.drag ? 230 : 900));

      // Wide, faint halo; the droplet body; a hot, soft centre.
      stamp(DOT, f.x, f.y, 150 + 12 * breathe, 0.10 * a);
      stamp(DOT, f.x, f.y, (f.drag ? 64 : 50) + 4 * breathe, (f.drag ? 0.6 : 0.42) * a, angle, stretch);
      stamp(DOT, f.x, f.y, f.drag ? 22 : 14, (f.drag ? 0.75 : 0.55) * a, angle, 1 + (stretch - 1) * 0.5);
    }

    function drawInk(now, step) {
      for (let i = ink.length - 1; i >= 0; i--) {
        const p = ink[i];
        const t = (now - p.t0) / p.dur;
        if (t >= 1) { ink.splice(i, 1); continue; }
        const drag = Math.pow(0.95, step);
        p.vx *= drag; p.vy *= drag;
        p.x += p.vx * step; p.y += p.vy * step;
        stamp(DOT, p.x, p.y, p.r0 + p.grow * easeOut(t), p.a * Math.pow(1 - t, 1.7));
      }
    }

    function drawWaves(now) {
      for (let i = waves.length - 1; i >= 0; i--) {
        const wv = waves[i];
        const t = (now - wv.t0 - wv.delay) / wv.dur;
        if (t < 0) continue;
        if (t >= 1) { waves.splice(i, 1); continue; }
        const e = easeOut(t);
        stamp(RING, wv.x, wv.y, 18 + wv.size * e, wv.a * Math.pow(1 - t, 1.5));
        if (wv.delay === 0) stamp(DOT, wv.x, wv.y, 30 + 20 * e, wv.a * 0.6 * Math.pow(1 - t, 3));
      }
    }

    function drawScrollGlow(step) {
      // Soft beads of light down the right edge that slide as you scroll.
      if (scrollEnergy < 0.01) return;
      const x = w - 12, top = h * 0.22, len = h * 0.56, gap = 26;
      const off = ((scrollOffset % gap) + gap) % gap;
      for (let y = top + off; y < top + len; y += gap) {
        const edge = Math.sin(((y - top) / len) * Math.PI); // fades to 0 at both ends
        stamp(DOT, x, y, 9, 0.55 * scrollEnergy * edge, Math.PI / 2, 1.8);
      }
      scrollEnergy *= Math.pow(0.95, step);
    }

    let last = performance.now();
    function frame(now) {
      // Physics is scaled by frame time, so 60 Hz and 120 Hz phones feel the same.
      const step = Math.min((now - last) / 16.667, 3);
      last = now;
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
      drawInk(now, step);
      drawWaves(now);
      for (const [id, f] of fingers) {
        drawFinger(f, now, step);
        if (!f.alive && f.life < 0.01) fingers.delete(id);
      }
      drawScrollGlow(step);
      flush();
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    return { down, move, up, dragStart, ripple, scroll };
  })();
})();

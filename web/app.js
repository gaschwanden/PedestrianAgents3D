(function () {
  const STR = window.PEDSIM_STRINGS;
  const TOOLS = [
    { id: "path", label: "P", tip: "tipPath", group: "analysis" },
    { id: "facade", label: "F", tip: "tipFacade", group: "analysis" },
    { id: "facadeO", label: "Fx", tip: "tipFacadeO", group: "analysis" },
    { id: "traces", label: "TR", tip: "tipTraces", group: "analysis" },
    { id: "tracesO", label: "TRx", tip: "tipTracesO", group: "analysis" },
    { id: "odAdd", label: "OD+", tip: "tipOdAdd", group: "mode" },
    { id: "odDelete", label: "OD-", tip: "tipOdDelete", group: "mode" },
    { id: "odWeight", label: "+/-", tip: "tipOdWeight", group: "mode" },
    { id: "odSave", label: "save", tip: "tipOdSave", group: "action" },
    { id: "odLoad", label: "open", tip: "tipOdLoad", group: "action" },
    { id: "bdCircle", label: "B○", tip: "tipBdCircle", group: "mode" },
    { id: "bdRect", label: "B▭", tip: "tipBdRect", group: "mode" },
    { id: "run", label: "▶", tip: "tipRun", group: "action" },
    { id: "pause", label: "❚❚", tip: "tipPause", group: "action" },
    { id: "record", label: "REC", tip: "tipRecord", group: "toggle" },
    { id: "gpx", label: "GPX", tip: "tipGpx", group: "action" },
    { id: "hub", label: "HUB", tip: "tipHub", group: "action" },
    { id: "top", label: "2D", tip: "tipTop", group: "action" },
    { id: "tilt45", label: "3D", tip: "tipTilt45", group: "action" },
    { id: "iso", label: "Iso", tip: "tipIso", group: "toggle" },
    { id: "reset", label: "X", tip: "tipReset", group: "action" },
  ];

  const state = {
    lang: localStorage.getItem("pedsim-lang") || "en",
    scene: null,
    scenes: {},
    scale: "cluster",
    rows: null,
    active: [],
    overrides: {},
    playing: false,
    timer: null,
    displayTimer: null,
    lastFrame: 0,
    fps: 0,
    agentFrom: [],
    agentTo: [],
    agentShown: [],
    lerpStart: 0,
    // Packed steps advance slowly; display lerps between them at ~30 Hz.
    playStepMs: 320,
    playStepMsLow: 700,
    lerpMs: 320,
    analysis: "path",
    mode: null,
    recording: false,
    watch: null,
    track: { id: "t" + Date.now(), points: [] },
    customOds: [],
    customBuildings: [],
    template: null, // {shape, a, b}
    odWeight: 1,
    showIso: false,
    low: false,
  };

  const worker = new Worker("worker.js");
  const canvas = document.createElement("canvas");
  let map = null;

  function t(key) {
    return (STR[state.lang] && STR[state.lang][key]) || STR.en[key] || key;
  }

  function applyLanguage() {
    document.documentElement.lang = state.lang === "de" ? "de" : "en";
    document.querySelectorAll("[data-i18n]").forEach(function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    document.title = t("title");
    document.getElementById("lang").value = state.lang;
    localStorage.setItem("pedsim-lang", state.lang);
    buildToolbar();
    setNet();
  }

  function setStatus(text) {
    document.getElementById("status").textContent = text;
  }

  function setNet() {
    const online = navigator.onLine;
    document.getElementById("net").textContent = online ? t("online") : t("offline");
    const select = document.getElementById("basemap");
    Array.prototype.forEach.call(select.options, function (option) {
      if (option.value === "none") {
        option.disabled = false;
        return;
      }
      option.disabled = !online;
    });
    if (!online && select.value !== "none") {
      select.value = "none";
      setBasemap("none");
    }
  }

  function db() {
    return new Promise(function (resolve, reject) {
      const request = indexedDB.open("pedsim-field", 3);
      request.onupgradeneeded = function () {
        const base = request.result;
        if (!base.objectStoreNames.contains("notes")) base.createObjectStore("notes", { keyPath: "id" });
        if (!base.objectStoreNames.contains("tracks")) base.createObjectStore("tracks", { keyPath: "id" });
        if (!base.objectStoreNames.contains("ods")) base.createObjectStore("ods", { keyPath: "id" });
        if (!base.objectStoreNames.contains("buildings")) base.createObjectStore("buildings", { keyPath: "id" });
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function put(store, value) {
    return db().then(function (base) {
      return new Promise(function (resolve, reject) {
        const tx = base.transaction(store, "readwrite");
        tx.objectStore(store).put(value);
        tx.oncomplete = function () { resolve(value); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function all(store) {
    return db().then(function (base) {
      return new Promise(function (resolve, reject) {
        const tx = base.transaction(store, "readonly");
        const request = tx.objectStore(store).getAll();
        request.onsuccess = function () { resolve(request.result || []); };
        request.onerror = function () { reject(request.error); };
      });
    });
  }

  function clearStore(store) {
    return db().then(function (base) {
      return new Promise(function (resolve, reject) {
        const tx = base.transaction(store, "readwrite");
        tx.objectStore(store).clear();
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function toolTipText(tool) {
    return t(tool.tip);
  }

  function showToolTip(button, text) {
    const tip = document.getElementById("tool-tip");
    const stage = document.getElementById("stage").getBoundingClientRect();
    const box = button.getBoundingClientRect();
    tip.textContent = text;
    tip.hidden = false;
    tip.setAttribute("aria-hidden", "false");
    tip.style.left = Math.round(box.left - stage.left + box.width / 2) + "px";
    tip.style.top = Math.round(box.bottom - stage.top + 8) + "px";
    setStatus(text);
  }

  function hideToolTip() {
    const tip = document.getElementById("tool-tip");
    tip.hidden = true;
    tip.setAttribute("aria-hidden", "true");
    tip.textContent = "";
  }

  function buildToolbar() {
    const bar = document.getElementById("toolbar");
    bar.innerHTML = "";
    TOOLS.forEach(function (tool) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "java-btn";
      button.dataset.id = tool.id;
      button.setAttribute("aria-label", toolTipText(tool));
      button.textContent = tool.label;
      button.addEventListener("mouseenter", function () {
        button.classList.add("over");
        showToolTip(button, toolTipText(tool));
      });
      button.addEventListener("mouseleave", function () {
        button.classList.remove("over");
        hideToolTip();
      });
      button.addEventListener("focus", function () {
        showToolTip(button, toolTipText(tool));
      });
      button.addEventListener("blur", hideToolTip);
      button.addEventListener("click", function () { onTool(tool.id); });
      bar.appendChild(button);
    });
    paintToolbar();
  }

  function mapEditLocked() {
    return state.mode === "bdCircle" || state.mode === "bdRect"
      || state.mode === "odAdd" || state.mode === "odDelete" || state.mode === "odWeight"
      || state.recording;
  }

  function updateMapInteraction() {
    if (!map) return;
    if (mapEditLocked()) {
      map.dragPan.disable();
      map.dragRotate.disable();
      map.touchPitch.disable();
      map.getCanvas().style.cursor = "crosshair";
    } else {
      map.dragPan.enable();
      map.dragRotate.enable();
      map.touchPitch.enable();
      map.getCanvas().style.cursor = "";
    }
  }

  function paintToolbar() {
    document.querySelectorAll(".java-btn").forEach(function (button) {
      const id = button.dataset.id;
      let on = false;
      if (id === state.analysis) on = true;
      if (id === state.mode) on = true;
      if ((id === "bdCircle" || id === "bdRect") && state.mode === id) on = true;
      if (id === "record" && state.recording) on = true;
      if (id === "iso" && state.showIso) on = true;
      if (id === "run" && state.playing) on = true;
      if (id === "pause" && !state.playing) on = true;
      button.classList.toggle("active", on);
      button.classList.toggle("down", on);
    });
  }

  function chronologyWindow() {
    let startBc = Number(document.getElementById("start").value);
    let endBc = Number(document.getElementById("end").value);
    if (startBc < endBc) {
      const swap = startBc;
      startBc = endBc;
      endBc = swap;
    }
    document.getElementById("start-out").textContent = String(startBc);
    document.getElementById("end-out").textContent = String(endBc);
    return { startBc: startBc, endBc: endBc };
  }

  function sendToggles() {
    const phases = {};
    document.querySelectorAll("#phases input").forEach(function (box) {
      phases[box.value] = box.checked;
    });
    const window = chronologyWindow();
    worker.postMessage({
      type: "setToggles",
      toggles: {
        chronology: document.getElementById("chrono").checked,
        startBc: window.startBc,
        endBc: window.endBc,
        season: document.getElementById("season").value,
        phases: phases,
        overrides: state.overrides,
      },
    });
  }

  function ramp(amount) {
    const stops = [
      [68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37],
    ];
    const x = Math.max(0, Math.min(0.999, amount)) * (stops.length - 1);
    const i = Math.floor(x);
    const f = x - i;
    const a = stops[i];
    const b = stops[i + 1];
    return [
      Math.round(a[0] + (b[0] - a[0]) * f),
      Math.round(a[1] + (b[1] - a[1]) * f),
      Math.round(a[2] + (b[2] - a[2]) * f),
    ];
  }

  function paint() {
    const rows = state.rows;
    if (!rows || !rows.length || !map || !map.getLayer("density")) return;
    if (state.analysis !== "path" && state.analysis !== "traces" && state.analysis !== "tracesO") {
      map.setPaintProperty("density", "raster-opacity", 0);
      return;
    }
    const ny = rows.length;
    const nx = rows[0].length;
    if (canvas.width !== nx || canvas.height !== ny) {
      canvas.width = nx;
      canvas.height = ny;
    }
    const ctx = canvas.getContext("2d");
    const image = ctx.createImageData(nx, ny);
    let max = 0;
    rows.forEach(function (row) {
      row.forEach(function (value) { if (value > max) max = value; });
    });
    const cutoff = Number(document.getElementById("cutoff").value) * max;
    const useLog = document.getElementById("log").checked;
    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) {
        let value = rows[y][x];
        if (value < cutoff) value = 0;
        let tone = max > 0 ? value / max : 0;
        if (useLog && tone > 0) tone = Math.log1p(tone * 9) / Math.log(10);
        const pixel = (y * nx + x) * 4;
        if (tone <= 0) {
          image.data[pixel + 3] = 0;
          continue;
        }
        const rgb = ramp(tone);
        image.data[pixel] = rgb[0];
        image.data[pixel + 1] = rgb[1];
        image.data[pixel + 2] = rgb[2];
        image.data[pixel + 3] = 210;
      }
    }
    ctx.putImageData(image, 0, 0);
    map.setPaintProperty("density", "raster-opacity", Number(document.getElementById("opacity").value));
    map.triggerRepaint();
  }

  function featurePoint(coords, props) {
    return {
      type: "Feature",
      properties: props || {},
      geometry: { type: "Point", coordinates: coords },
    };
  }

  function syncAgents(points) {
    if (!map || !map.getSource("agents")) return;
    state.agentShown = points || [];
    map.getSource("agents").setData({
      type: "FeatureCollection",
      features: state.agentShown.map(function (pair) {
        return featurePoint(pair, { kind: "agent" });
      }),
    });
  }

  function lerpAgents(now) {
    const from = state.agentFrom;
    const to = state.agentTo;
    if (!to.length) {
      syncAgents([]);
      return;
    }
    if (!from.length) {
      syncAgents(to);
      return;
    }
    const span = Math.max(1, state.lerpMs);
    const t = Math.min(1, Math.max(0, (now - state.lerpStart) / span));
    const n = Math.max(from.length, to.length);
    const out = [];
    for (let i = 0; i < n; i++) {
      const a = from[i] || to[i];
      const b = to[i] || from[i];
      if (!a || !b) continue;
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
    }
    syncAgents(out);
  }

  function stopDisplayLoop() {
    if (state.displayTimer !== null) {
      cancelAnimationFrame(state.displayTimer);
      state.displayTimer = null;
    }
  }

  function startDisplayLoop() {
    stopDisplayLoop();
    const tick = function (now) {
      if (!state.playing) {
        state.displayTimer = null;
        return;
      }
      lerpAgents(now);
      state.displayTimer = requestAnimationFrame(tick);
    };
    state.displayTimer = requestAnimationFrame(tick);
  }

  function metresPerDegree(lat) {
    return {
      lat: 111320,
      lon: 111320 * Math.cos((lat * Math.PI) / 180),
    };
  }

  function distMetres(a, b) {
    const m = metresPerDegree(a[1]);
    return Math.hypot((b[0] - a[0]) * m.lon, (b[1] - a[1]) * m.lat);
  }

  function circleRing(center, radiusM, n) {
    n = Math.max(8, n || 24);
    const m = metresPerDegree(center[1]);
    const ring = [];
    for (let i = 0; i < n; i++) {
      const angle = (2 * Math.PI * i) / n;
      ring.push([
        center[0] + (radiusM * Math.cos(angle)) / m.lon,
        center[1] + (radiusM * Math.sin(angle)) / m.lat,
      ]);
    }
    ring.push(ring[0]);
    return ring;
  }

  function rectRing(a, b) {
    const west = Math.min(a[0], b[0]);
    const east = Math.max(a[0], b[0]);
    const south = Math.min(a[1], b[1]);
    const north = Math.max(a[1], b[1]);
    return [[west, south], [east, south], [east, north], [west, north], [west, south]];
  }

  function entranceFromDoor(ring, door) {
    let best = null;
    let bestD = Infinity;
    for (let i = 0; i < ring.length - 1; i++) {
      const a = ring[i];
      const b = ring[i + 1];
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const L2 = dx * dx + dy * dy;
      const t = L2 <= 0 ? 0 : Math.max(0, Math.min(1, ((door[0] - a[0]) * dx + (door[1] - a[1]) * dy) / L2));
      const proj = [a[0] + t * dx, a[1] + t * dy];
      const d = Math.hypot(door[0] - proj[0], door[1] - proj[1]);
      if (d < bestD) {
        bestD = d;
        const len = Math.sqrt(L2);
        best = { proj: proj, dx: dx, dy: dy, len: len };
      }
    }
    if (!best || best.len <= 0) return door;
    const m = metresPerDegree(best.proj[1]);
    const nx = -best.dy / best.len;
    const ny = best.dx / best.len;
    const offsetLon = (3 * nx) / m.lon;
    const offsetLat = (3 * ny) / m.lat;
    return [best.proj[0] + offsetLon, best.proj[1] + offsetLat];
  }

  function syncBuildings() {
    if (!map || !map.getSource("buildings")) return;
    const active = {};
    state.active.forEach(function (id) { active[id] = true; });
    const packed = (state.scene.buildings || []).filter(function (building) {
      if (!building.phase_ids || !building.phase_ids.length) return true;
      return building.phase_ids.some(function (id) { return active[id]; });
    }).map(function (building) {
      return {
        type: "Feature",
        properties: {
          colour: "#9aa3ad",
          name: building.name,
          height: 3,
        },
        geometry: { type: "Polygon", coordinates: [building.ring] },
      };
    });
    const custom = state.customBuildings.filter(function (building) {
      return !building.scale || building.scale === state.scale;
    }).map(function (building) {
      return {
        type: "Feature",
        properties: {
          colour: "#9aa3ad",
          name: building.name || building.shape,
          height: 3,
        },
        geometry: { type: "Polygon", coordinates: [building.ring] },
      };
    });
    map.getSource("buildings").setData({
      type: "FeatureCollection",
      features: packed.concat(custom),
    });
  }

  function syncSites() {
    if (!map || !map.getSource("sites")) return;
    map.getSource("sites").setData({
      type: "FeatureCollection",
      features: (state.scene.sites || []).map(function (site) {
        return featurePoint(site.coordinates, {
          name: site.name,
          official: site.official ? 1 : 0,
          period: site.period || "",
        });
      }),
    });
  }

  function allOds() {
    const packed = (state.scene.ods || []).map(function (od, index) {
      return {
        id: "pack-" + index,
        name: od.name,
        kind: od.kind || "site",
        coordinates: od.coordinates,
        custom: false,
        weight: od.dest_weight || 1,
      };
    });
    return packed.concat(state.customOds);
  }

  function syncOds() {
    if (!map || !map.getSource("ods")) return;
    map.getSource("ods").setData({
      type: "FeatureCollection",
      features: allOds().map(function (od) {
        return featurePoint(od.coordinates, {
          name: od.name,
          kind: od.kind,
          custom: od.custom ? 1 : 0,
          weight: od.weight || 1,
        });
      }),
    });
  }

  function syncLinks() {
    if (!map || !map.getSource("links")) return;
    map.getSource("links").setData({
      type: "FeatureCollection",
      features: (state.scene.links || []).map(function (link) {
        return {
          type: "Feature",
          properties: { from: link.from, to: link.to },
          geometry: { type: "LineString", coordinates: link.coordinates },
        };
      }),
    });
  }

  function syncTrack() {
    if (!map || !map.getSource("track")) return;
    const points = state.track.points || [];
    map.getSource("track").setData({
      type: "FeatureCollection",
      features: points.length < 2 ? points.map(function (point) {
        return featurePoint([point.lon, point.lat], { t: point.t || "" });
      }) : [{
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: points.map(function (point) { return [point.lon, point.lat]; }),
        },
      }],
    });
  }

  function syncIso(center) {
    if (!map || !map.getSource("iso")) return;
    if (!state.showIso || !center) {
      map.getSource("iso").setData({ type: "FeatureCollection", features: [] });
      return;
    }
    const ring = [];
    for (let i = 0; i <= 32; i++) {
      const angle = (i / 32) * Math.PI * 2;
      ring.push([
        center[0] + 0.002 * Math.cos(angle),
        center[1] + 0.0016 * Math.sin(angle),
      ]);
    }
    map.getSource("iso").setData({
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [ring] },
      }],
    });
  }

  function showMetrics(message) {
    const season = document.getElementById("season").value;
    const lines = [
      (state.scene.scale || state.scale) + " · " + (state.scene.name || ""),
      "phases: " + (state.active.join(", ") || "none"),
      "season: " + season + (message.daylight != null ? (" · " + message.daylight + " min day") : ""),
      "ODs: " + allOds().length + " · custom " + state.customOds.length,
      "step " + (message.step || 0) + " · peak " + (message.max || 0).toFixed(3),
      "playback " + state.fps.toFixed(1) + " frames/s",
    ];
    document.getElementById("metrics").textContent = lines.join("\n");
    document.getElementById("scale-label").textContent =
      state.scale === "cluster" ? t("cluster") : t("village");
    document.querySelectorAll("#phases input").forEach(function (box) {
      if (!Object.prototype.hasOwnProperty.call(state.overrides, box.value)) {
        box.checked = state.active.indexOf(box.value) >= 0;
      }
    });
  }

  worker.onmessage = function (event) {
    const message = event.data || {};
    if (message.type !== "frame") return;
    const now = performance.now();
    if (state.lastFrame) {
      const dt = now - state.lastFrame;
      if (dt > 0) state.fps = state.fps ? state.fps * 0.7 + (1000 / dt) * 0.3 : 1000 / dt;
    }
    state.lastFrame = now;
    state.rows = message.rows;
    state.active = message.active || [];
    paint();
    const next = message.agents || [];
    state.agentFrom = state.agentShown.length ? state.agentShown.slice() : (state.agentTo.slice());
    state.agentTo = next;
    state.lerpStart = now;
    if (!state.playing) syncAgents(next);
    syncBuildings();
    syncSites();
    syncOds();
    syncLinks();
    syncTrack();
    showMetrics(message);
  };

  // Proxied through pedsim.serve so WebGL gets CORS. Direct Google/Esri URLs
  // return images without Access-Control-Allow-Origin and stay blank in MapLibre.
  function tileUrl(kind) {
    return window.location.origin + "/tiles/" + kind + "/{z}/{x}/{y}.jpg";
  }

  const TILES = {
    streets: {
      tiles: [window.location.origin + "/tiles/streets/{z}/{x}/{y}.png"],
      attribution: "© OpenStreetMap",
    },
    satellite: {
      tiles: [tileUrl("satellite")],
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
    google: {
      tiles: [tileUrl("google")],
      attribution: "© Google",
    },
    "google-hybrid": {
      tiles: [tileUrl("google-hybrid")],
      attribution: "© Google",
    },
  };

  function setBasemap(kind) {
    if (!map || !map.isStyleLoaded()) return;
    if (map.getLayer("basemap")) map.removeLayer("basemap");
    if (map.getSource("basemap")) map.removeSource("basemap");
    if (!TILES[kind] || !navigator.onLine) return;
    map.addSource("basemap", {
      type: "raster",
      tiles: TILES[kind].tiles,
      tileSize: 256,
      attribution: TILES[kind].attribution,
      maxzoom: 20,
    });
    // Keep imagery under the density / site overlays.
    const before = map.getLayer("density") ? "density"
      : (map.getLayer("links") ? "links" : undefined);
    map.addLayer({
      id: "basemap",
      type: "raster",
      source: "basemap",
      paint: { "raster-opacity": 1, "raster-fade-duration": 0 },
    }, before);
    window.__pedsimMap = map;
  }

  function ensureMap() {
    if (map) return;
    map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        sources: {},
        layers: [{ id: "background", type: "background", paint: { "background-color": "#111111" } }],
      },
      center: [38.85, 37.15],
      zoom: 9.5,
      pitch: 45,
      bearing: -20,
      attributionControl: false,
      maxPitch: 70,
    });
    window.__pedsimMap = map;
    map.on("error", function (event) {
      window.__lastErr = (event && event.error && event.error.message) || String(event);
      setStatus("map: " + window.__lastErr);
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-right");
    map.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution: "pedsim playback · Java-style tools · Google/Esri tiles online only, not cached",
    }));
    map.on("load", function () {
      try {
        // Imagery first so a later overlay failure cannot leave a black map.
        setBasemap(document.getElementById("basemap").value);
        const empty = { type: "FeatureCollection", features: [] };
        const bounds = (state.scene && state.scene.bounds) || {
          west: 38.4, south: 36.8, east: 39.3, north: 37.5,
        };
        map.addSource("density", {
          type: "canvas",
          canvas: canvas,
          coordinates: [
            [bounds.west, bounds.north],
            [bounds.east, bounds.north],
            [bounds.east, bounds.south],
            [bounds.west, bounds.south],
          ],
          animate: true,
        });
        map.addLayer({
          id: "density", type: "raster", source: "density",
          paint: { "raster-opacity": Number(document.getElementById("opacity").value) },
        });
        map.addSource("links", { type: "geojson", data: empty });
        map.addLayer({
          id: "links", type: "line", source: "links",
          paint: { "line-color": "#ff5555", "line-width": 1.2, "line-opacity": 0.45 },
        });
        map.addSource("buildings", { type: "geojson", data: empty });
        // Standardised prism height; flat top (no modelled roof).
        map.addLayer({
          id: "buildings-fill", type: "fill-extrusion", source: "buildings",
          paint: {
            "fill-extrusion-color": "#9aa3ad",
            "fill-extrusion-height": ["coalesce", ["get", "height"], 3],
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.88,
            "fill-extrusion-vertical-gradient": true,
          },
        });
        map.addSource("sites", { type: "geojson", data: empty });
        map.addLayer({
          id: "sites", type: "circle", source: "sites",
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              8, ["case", ["==", ["get", "official"], 1], 4, 3],
              14, ["case", ["==", ["get", "official"], 1], 6, 4.5],
              17, ["case", ["==", ["get", "official"], 1], 8, 6],
            ],
            "circle-color": ["case", ["==", ["get", "official"], 1], "#ff2222", "#ffaa00"],
            "circle-stroke-width": 1,
            "circle-stroke-color": "#ffffff",
          },
        });
        map.addLayer({
          id: "sites-label", type: "symbol", source: "sites",
          layout: {
            "text-field": ["get", "name"],
            "text-size": 11,
            "text-offset": [0, 1.2],
            "text-anchor": "top",
          },
          paint: {
            "text-color": "#ffffff",
            "text-halo-color": "#000000",
            "text-halo-width": 1.2,
          },
        });
        map.addSource("ods", { type: "geojson", data: empty });
        map.addLayer({
          id: "ods", type: "circle", source: "ods",
          paint: {
            // ODs stay clearly larger than agents, smaller than site markers.
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              8, ["+", 2.2, ["*", 0.6, ["coalesce", ["get", "weight"], 1]]],
              14, ["+", 3.2, ["*", 0.8, ["coalesce", ["get", "weight"], 1]]],
              17, ["+", 4.5, ["*", 1.0, ["coalesce", ["get", "weight"], 1]]],
            ],
            "circle-color": [
              "case",
              ["==", ["get", "custom"], 1], "#00ff66",
              ["==", ["get", "kind"], "water"], "#44aaff",
              ["==", ["get", "kind"], "house"], "#ffcc00",
              "#ff0000",
            ],
            "circle-stroke-width": 1,
            "circle-stroke-color": "#ffffff",
          },
        });
        map.addLayer({
          id: "ods-label", type: "symbol", source: "ods",
          layout: {
            "text-field": ["get", "name"],
            "text-size": 10,
            "text-offset": [0, 1.1],
            "text-anchor": "top",
          },
          paint: { "text-color": "#fff", "text-halo-color": "#000", "text-halo-width": 1 },
        });
        map.addSource("agents", { type: "geojson", data: empty });
        map.addLayer({
          id: "agents", type: "circle", source: "agents",
          paint: {
            // Keep walkers as pinpricks next to buildings and OD discs.
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              8, 0.8,
              12, 1.2,
              15, 1.8,
              17, 2.4,
            ],
            "circle-color": "#ffffff",
            "circle-stroke-width": 0.6,
            "circle-stroke-color": "#cc0000",
            "circle-opacity": 0.9,
          },
        });
        map.addSource("track", { type: "geojson", data: empty });
        map.addLayer({
          id: "track-line", type: "line", source: "track",
          paint: { "line-color": "#00ffaa", "line-width": 3 },
        });
        map.addLayer({
          id: "track-points", type: "circle", source: "track",
          filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 4, "circle-color": "#00ffaa" },
        });
        map.addSource("iso", { type: "geojson", data: empty });
        map.addLayer({
          id: "iso", type: "fill", source: "iso",
          paint: { "fill-color": "#ffffff", "fill-opacity": 0.12 },
        });
        map.on("click", onMapClick);
        applySceneToMap();
        updateMapInteraction();
      } catch (error) {
        window.__lastErr = String(error && error.message ? error.message : error);
        setStatus("map setup: " + window.__lastErr);
      }
    });
  }

  function applySceneToMap() {
    if (!map || !state.scene) return;
    const bounds = state.scene.bounds;
    if (map.getSource("density")) {
      map.getSource("density").setCoordinates([
        [bounds.west, bounds.north],
        [bounds.east, bounds.north],
        [bounds.east, bounds.south],
        [bounds.west, bounds.south],
      ]);
    }
    if (state.scene.center) {
      map.easeTo({
        center: state.scene.center,
        zoom: state.scene.zoom || (state.scale === "cluster" ? 9.5 : 16),
        duration: 600,
      });
    }
    syncBuildings();
    syncSites();
    syncOds();
    syncLinks();
    syncTrack();
    paint();
  }

  function fillSceneControls() {
    const season = document.getElementById("season");
    season.innerHTML = "";
    (state.scene.seasons || []).forEach(function (item) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name;
      if (item.id === "dry") option.selected = true;
      season.appendChild(option);
    });
    const phases = document.getElementById("phases");
    phases.innerHTML = "";
    state.overrides = {};
    (state.scene.phases || []).forEach(function (phase) {
      const label = document.createElement("label");
      label.className = "row check";
      label.innerHTML = "<input type='checkbox' value='" + phase.id + "' checked> "
        + phase.name + " (" + phase.start_bc + "–" + phase.end_bc + ")";
      phases.appendChild(label);
      label.querySelector("input").addEventListener("change", function (event) {
        state.overrides[phase.id] = event.target.checked;
        sendToggles();
      });
    });
    document.getElementById("scale-cluster").classList.toggle("active", state.scale === "cluster");
    document.getElementById("scale-village").classList.toggle("active", state.scale === "village");
  }

  function loadScene(scale) {
    const scene = state.scenes[scale];
    if (!scene) {
      setStatus("scene pack missing — run python -m pedsim pack");
      return;
    }
    state.scale = scale;
    state.scene = scene;
    state.playing = false;
    if (state.timer) clearTimeout(state.timer);
    stopDisplayLoop();
    state.agentFrom = [];
    state.agentTo = [];
    state.agentShown = [];
    // Village / settlement packs carry denser frames; cluster stays coarser.
    if (scale === "village") {
      state.playStepMs = 320;
      state.lerpMs = 320;
    } else {
      state.playStepMs = 420;
      state.lerpMs = 420;
    }
    fillSceneControls();
    ensureMap();
    applySceneToMap();
    worker.postMessage({ type: "loadScene", scene: scene });
    sendToggles();
    paintToolbar();
  }

  function play() {
    if (state.playing) return;
    state.playing = true;
    paintToolbar();
    setStatus(t("playing"));
    const stepMs = state.low ? state.playStepMsLow : state.playStepMs;
    state.lerpMs = stepMs;
    const tick = function () {
      if (!state.playing) return;
      worker.postMessage({ type: "step", n: 1 });
      state.timer = setTimeout(tick, stepMs);
    };
    tick();
    startDisplayLoop();
  }

  function pause() {
    state.playing = false;
    if (state.timer) clearTimeout(state.timer);
    stopDisplayLoop();
    if (state.agentTo.length) syncAgents(state.agentTo);
    paintToolbar();
    setStatus(t("paused"));
  }

  function gpxText(points, name) {
    const rows = points.map(function (point) {
      const time = point.t ? "<time>" + point.t + "</time>" : "";
      return "<trkpt lat=\"" + point.lat + "\" lon=\"" + point.lon + "\">" + time + "</trkpt>";
    }).join("");
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
      + "<gpx version=\"1.1\" creator=\"pedsim\"><trk><name>" + name
      + "</name><trkseg>" + rows + "</trkseg></trk></gpx>";
  }

  function download(name, blob) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  }

  function addTrackPoint(lat, lon, source) {
    state.track.points.push({
      lat: lat,
      lon: lon,
      t: new Date().toISOString(),
      source: source || "map",
    });
    put("tracks", state.track);
    syncTrack();
    setStatus(t("recorded") + " (" + state.track.points.length + ")");
  }

  function startRecord() {
    state.recording = true;
    state.track = { id: "t" + Date.now(), points: [], name: "field" };
    paintToolbar();
    updateMapInteraction();
    setStatus(t("recordStart") + " — " + t("recording"));
    if (!navigator.geolocation) {
      setStatus(t("noGeo"));
      return;
    }
    state.watch = navigator.geolocation.watchPosition(function (pos) {
      addTrackPoint(pos.coords.latitude, pos.coords.longitude, "gps");
    }, function () {
      setStatus(t("noGeo"));
    }, {
      enableHighAccuracy: true,
      maximumAge: 2000,
      timeout: 10000,
    });
  }

  function stopRecord() {
    state.recording = false;
    if (state.watch !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(state.watch);
    }
    state.watch = null;
    paintToolbar();
    updateMapInteraction();
    setStatus(t("recordStop"));
  }

  function nearestCustomOd(lngLat) {
    let best = null;
    let bestDist = Infinity;
    state.customOds.forEach(function (od, index) {
      const dx = od.coordinates[0] - lngLat.lng;
      const dy = od.coordinates[1] - lngLat.lat;
      const dist = dx * dx + dy * dy;
      if (dist < bestDist) {
        bestDist = dist;
        best = index;
      }
    });
    return bestDist < 0.0004 ? best : -1;
  }

  function finishTemplate(doorLngLat) {
    const draft = state.template;
    if (!draft || !draft.a || !draft.b) return;
    let ring;
    if (draft.shape === "circle") {
      const radius = distMetres(draft.a, draft.b);
      if (radius < 1) {
        setStatus(t("bdTooSmall"));
        state.template = null;
        return;
      }
      ring = circleRing(draft.a, radius, 24);
    } else {
      if (Math.abs(draft.a[0] - draft.b[0]) < 1e-7 || Math.abs(draft.a[1] - draft.b[1]) < 1e-7) {
        setStatus(t("bdTooSmall"));
        state.template = null;
        return;
      }
      ring = rectRing(draft.a, draft.b);
    }
    const door = [doorLngLat.lng, doorLngLat.lat];
    const entrance = entranceFromDoor(ring, door);
    const building = {
      id: "b-" + Date.now(),
      name: draft.shape + " " + (state.customBuildings.length + 1),
      shape: draft.shape,
      function: "domestic",
      height: 3,
      ring: ring,
      door: door,
      scale: state.scale,
      custom: true,
    };
    const od = {
      id: "od-door-" + Date.now(),
      name: "entrance " + building.name,
      kind: "house",
      coordinates: entrance,
      custom: true,
      weight: 1,
      scale: state.scale,
      tags: ["entrance", "door", draft.shape],
      building_id: building.id,
    };
    state.customBuildings.push(building);
    state.customOds.push(od);
    put("buildings", building);
    put("ods", od);
    state.template = { shape: draft.shape };
    syncBuildings();
    syncOds();
    setStatus(t("bdAdded") + ": " + building.name);
    paintToolbar();
  }

  function onMapClick(event) {
    const lngLat = event.lngLat;
    if (state.recording) {
      addTrackPoint(lngLat.lat, lngLat.lng, "map");
      return;
    }
    if (state.mode === "bdCircle" || state.mode === "bdRect") {
      const shape = state.mode === "bdCircle" ? "circle" : "rect";
      if (!state.template || state.template.shape !== shape || state.template.done) {
        state.template = { shape: shape, a: [lngLat.lng, lngLat.lat] };
        setStatus(shape === "circle" ? t("bdCircleRim") : t("bdRectCorner"));
        return;
      }
      if (!state.template.b) {
        state.template.b = [lngLat.lng, lngLat.lat];
        setStatus(t("bdDoor"));
        return;
      }
      finishTemplate(lngLat);
      return;
    }
    if (state.mode === "odAdd") {
      const od = {
        id: "od-" + Date.now(),
        name: "OD " + (state.customOds.length + 1),
        kind: "destination",
        coordinates: [lngLat.lng, lngLat.lat],
        custom: true,
        weight: state.odWeight,
        scale: state.scale,
      };
      state.customOds.push(od);
      put("ods", od);
      syncOds();
      setStatus(t("odAdded") + ": " + od.name);
      return;
    }
    if (state.mode === "odDelete") {
      const index = nearestCustomOd(lngLat);
      if (index < 0) return;
      const removed = state.customOds.splice(index, 1)[0];
      db().then(function (base) {
        const tx = base.transaction("ods", "readwrite");
        tx.objectStore("ods").delete(removed.id);
      });
      syncOds();
      setStatus(t("odDeleted"));
      return;
    }
    if (state.mode === "odWeight") {
      const index = nearestCustomOd(lngLat);
      if (index < 0) return;
      state.customOds[index].weight = Math.min(5, (state.customOds[index].weight || 1) + 0.5);
      put("ods", state.customOds[index]);
      syncOds();
      setStatus("+/- " + state.customOds[index].name + " → " + state.customOds[index].weight);
      return;
    }
    if (state.showIso) syncIso([lngLat.lng, lngLat.lat]);
  }

  function onTool(id) {
    if (id === "path" || id === "facade" || id === "facadeO" || id === "traces" || id === "tracesO") {
      state.analysis = id;
      paint();
      paintToolbar();
      return;
    }
    if (id === "odAdd" || id === "odDelete" || id === "odWeight" || id === "bdCircle" || id === "bdRect") {
      state.mode = state.mode === id ? null : id;
      state.template = null;
      paintToolbar();
      updateMapInteraction();
      if (state.mode === "odAdd") setStatus(t("odMode"));
      if (state.mode === "bdCircle") setStatus(t("bdCircleStart"));
      if (state.mode === "bdRect") setStatus(t("bdRectStart"));
      return;
    }
    if (id === "odSave") {
      Promise.all(state.customOds.map(function (od) { return put("ods", od); })).then(function () {
        setStatus(t("saved") + " (" + state.customOds.length + " OD)");
      });
      return;
    }
    if (id === "odLoad") {
      all("ods").then(function (rows) {
        state.customOds = rows.filter(function (od) {
          return !od.scale || od.scale === state.scale;
        });
        syncOds();
        setStatus(t("saved") + " · " + state.customOds.length + " OD");
      });
      return;
    }
    if (id === "run") { play(); return; }
    if (id === "pause") { pause(); return; }
    if (id === "record") {
      if (state.recording) stopRecord();
      else startRecord();
      return;
    }
    if (id === "gpx") {
      const blob = new Blob([gpxText(state.track.points, state.track.id)], { type: "application/gpx+xml" });
      download(state.track.id + ".gpx", blob);
      setStatus(t("gpxOut"));
      return;
    }
    if (id === "hub") {
      setStatus(t("hubWait"));
      fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seeds: 4, steps: 8, agents: 12 }),
      }).then(function (response) {
        if (!response.ok) throw new Error("status");
        return response.json();
      }).then(function (body) {
        setStatus(t("hubOk") + " " + body.mean_max.toFixed(3));
      }).catch(function () { setStatus(t("hubFail")); });
      return;
    }
    if (id === "top") {
      document.getElementById("tilt").value = "0";
      if (map) map.easeTo({ pitch: 0, bearing: 0, duration: 400 });
      return;
    }
    if (id === "tilt45") {
      document.getElementById("tilt").value = "45";
      if (map) map.easeTo({ pitch: 45, bearing: -20, duration: 400 });
      return;
    }
    if (id === "iso") {
      state.showIso = !state.showIso;
      if (!state.showIso) syncIso(null);
      paintToolbar();
      return;
    }
    if (id === "reset") {
      pause();
      worker.postMessage({ type: "reset" });
      if (state.recording) stopRecord();
      state.customOds = [];
      state.customBuildings = [];
      state.template = null;
      state.mode = null;
      state.track = { id: "t" + Date.now(), points: [], name: "field" };
      clearStore("ods");
      clearStore("buildings");
      clearStore("tracks");
      syncOds();
      syncBuildings();
      syncTrack();
      setStatus(t("reset"));
      paintToolbar();
      updateMapInteraction();
    }
  }

  document.getElementById("lang").addEventListener("change", function (event) {
    state.lang = event.target.value;
    applyLanguage();
  });
  document.getElementById("scale-cluster").addEventListener("click", function () { loadScene("cluster"); });
  document.getElementById("scale-village").addEventListener("click", function () { loadScene("village"); });
  ["chrono", "start", "end", "season", "opacity", "log", "cutoff"].forEach(function (id) {
    const notify = function () {
      if (id === "start" || id === "end") chronologyWindow();
      if (id === "opacity" || id === "log" || id === "cutoff") paint();
      else sendToggles();
    };
    document.getElementById(id).addEventListener("input", notify);
    document.getElementById(id).addEventListener("change", notify);
  });
  document.getElementById("tilt").addEventListener("input", function (event) {
    if (map) map.setPitch(Number(event.target.value));
  });
  document.getElementById("basemap").addEventListener("change", function (event) {
    setBasemap(event.target.value);
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) pause();
  });
  window.addEventListener("online", setNet);
  window.addEventListener("offline", setNet);

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(function () {});
  }
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist();

  applyLanguage();
  chronologyWindow();

  Promise.all([
    fetch("packs/goebekli/cluster.json").then(function (r) { return r.ok ? r.json() : null; }),
    fetch("packs/goebekli/scene.json").then(function (r) { return r.ok ? r.json() : null; }),
    all("ods"),
    all("tracks"),
    all("buildings"),
  ]).then(function (found) {
    if (found[0]) state.scenes.cluster = found[0];
    if (found[1]) state.scenes.village = found[1];
    state.customOds = found[2] || [];
    if ((found[3] || []).length) state.track = found[3][found[3].length - 1];
    state.customBuildings = found[4] || [];
    loadScene(state.scenes.cluster ? "cluster" : "village");
  }).catch(function () {
    setStatus("scene pack missing — run python -m pedsim pack");
  });
}());

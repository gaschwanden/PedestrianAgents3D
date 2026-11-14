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
    { id: "export", label: "file", tip: "tipExport", group: "action" },
    { id: "bdCircle", label: "B○", tip: "tipBdCircle", group: "mode" },
    { id: "bdRect", label: "B▭", tip: "tipBdRect", group: "mode" },
    { id: "bdDelete", label: "B-", tip: "tipBdDelete", group: "mode" },
    { id: "run", label: "▶", tip: "tipRun", group: "action" },
    { id: "pause", label: "❚❚", tip: "tipPause", group: "action" },
    { id: "speed", label: "⏩", tip: "tipSpeed", group: "action" },
    { id: "restart", label: "↺", tip: "tipRestart", group: "action" },
    { id: "record", label: "REC", tip: "tipRecord", group: "toggle" },
    { id: "gpx", label: "GPX", tip: "tipGpx", group: "action" },
    { id: "hub", label: "HUB", tip: "tipHub", group: "action" },
    { id: "top", label: "2D", tip: "tipTop", group: "action" },
    { id: "tilt45", label: "3D", tip: "tipTilt45", group: "action" },
    { id: "iso", label: "Iso", tip: "tipIso", group: "toggle" },
    { id: "reset", label: "X", tip: "tipReset", group: "action" },
  ];

  const PACK = "packs/goebekli/";
  // Must match sw.js: the offline download writes into the same cache.
  const CACHE = "pedsim-field-v18";
  const ENGINE_FILES = [
    "vendor/pedsim.zip",
    "vendor/pyodide/pyodide.js",
    "vendor/pyodide/pyodide.asm.js",
    "vendor/pyodide/pyodide.asm.wasm",
    "vendor/pyodide/python_stdlib.zip",
    "vendor/pyodide/pyodide-lock.json",
    "vendor/pyodide/numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl",
    "vendor/pyodide/pyyaml-6.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl",
    "vendor/fonts/Noto Sans Regular/0-255.pbf",
    "vendor/fonts/Noto Sans Regular/256-511.pbf",
    "vendor/fonts/Noto Sans Regular/8192-8447.pbf",
  ];

  const state = {
    lang: localStorage.getItem("pedsim-lang") || "en",
    index: null,          // packs/<area>/index.json
    sceneId: "",
    meta: null,           // packed scene description (inputs of the Simulation)
    desc: null,           // what the engine says is there now: ODs, buildings, sites
    frame: null,          // last engine snapshot
    engine: "boot",
    awaiting: false,
    overrides: {},
    playing: false,
    timer: null,
    displayTimer: null,
    stepMs: 0,
    stepsPerTick: 2,
    agentFrom: new Map(),
    agentTo: new Map(),
    agentShown: [],
    lerpStart: 0,
    playStepMs: 300,
    lerpMs: 300,
    analysis: "path",
    mode: null,
    recording: false,
    watch: null,
    track: { id: "t" + Date.now(), points: [] },
    template: null, // {shape, a, b}
    showIso: false,
    hadTraces: false,
    low: false,
    autosave: true,
    pulses: [],           // walkers that just set out again: [lon, lat, group, t0]
    lastSteps: 1,
    draft: null,          // building being drawn: {shape, a, b, dragging}
    proxy: false,         // true when pedsim serve is behind this page (tiles, hub)
    mapReady: false,
  };

  // Same number as in index.html and sw.js: bump all three together so a
  // browser never mixes files from two versions.
  const worker = new Worker("worker.js?v=18");
  const canvas = document.createElement("canvas");
  // walls read from a plan (one pixel per cell, phase colours)
  const wallCanvas = document.createElement("canvas");
  wallCanvas.width = 1;
  wallCanvas.height = 1;
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
      // Relief is in the pack; every other basemap is fetched tile by tile
      // through the laptop's tile proxy, which a static host does not have.
      const kind = option.value;
      if (kind === "auto" || kind === "relief" || kind === "none") option.disabled = false;
      else if (kind === "sat") option.disabled = !satelliteFor(state.sceneId);
      else if (kind === "esri") option.disabled = !online;      // direct, any host
      else option.disabled = !(online && state.proxy);          // through the laptop
    });
    if (select.selectedOptions[0] && select.selectedOptions[0].disabled) select.value = "auto";
    setBasemap(select.value);
  }

  function db() {
    return new Promise(function (resolve, reject) {
      const request = indexedDB.open("pedsim-field", 4);
      request.onupgradeneeded = function () {
        const base = request.result;
        if (!base.objectStoreNames.contains("notes")) base.createObjectStore("notes", { keyPath: "id" });
        if (!base.objectStoreNames.contains("tracks")) base.createObjectStore("tracks", { keyPath: "id" });
        if (!base.objectStoreNames.contains("ods")) base.createObjectStore("ods", { keyPath: "id" });
        if (!base.objectStoreNames.contains("buildings")) base.createObjectStore("buildings", { keyPath: "id" });
        // one saved geometry per scene id, in the desktop save format
        if (!base.objectStoreNames.contains("saves")) base.createObjectStore("saves", { keyPath: "id" });
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
    return state.mode === "bdCircle" || state.mode === "bdRect" || state.mode === "bdDelete"
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

  const HINTS = {
    bdCircle: "hintCircle", bdRect: "hintRect", bdDelete: "hintDelete",
    odAdd: "hintOdAdd", odDelete: "hintOdDelete", odWeight: "hintOdWeight",
  };

  function showHint(text) {
    const bar = document.getElementById("hint");
    let line = text || "";
    if (!line) {
      if (state.recording) line = t("hintRecord");
      else if (state.mode && HINTS[state.mode]) line = t(HINTS[state.mode]);
      else if (state.showIso) line = t("hintIso");
    }
    bar.textContent = line;
    bar.hidden = !line;
  }

  function paintToolbar() {
    showHint();
    const run = document.getElementById("btn-run");
    if (run) {
      run.textContent = state.playing ? t("btnPause") : t("btnRun");
      run.classList.toggle("active", state.playing);
    }
    document.querySelectorAll(".java-btn").forEach(function (button) {
      const id = button.dataset.id;
      let on = false;
      if (id === state.analysis) on = true;
      if (id === state.mode) on = true;
      if (id === "record" && state.recording) on = true;
      if (id === "iso" && state.showIso) on = true;
      if (id === "run" && state.playing) on = true;
      if (id === "pause" && !state.playing) on = true;
      button.classList.toggle("active", on);
      button.classList.toggle("down", on);
    });
  }

  function chronologyWindow() {
    // The two handles hold minus the year BC, so older is on the left. Either
    // handle may be dragged past the other: the window is whatever lies between.
    const first = document.getElementById("start");
    const second = document.getElementById("end");
    const a = -Number(first.value);
    const b = -Number(second.value);
    const startBc = Math.max(a, b);
    const endBc = Math.min(a, b);
    const lo = -Number(first.min);
    const hi = -Number(first.max);
    const fill = document.getElementById("dual-fill");
    fill.style.left = (100 * (lo - startBc) / (lo - hi)) + "%";
    fill.style.right = (100 * (endBc - hi) / (lo - hi)) + "%";
    document.getElementById("window-out").textContent =
      startBc + "–" + endBc + " BC (" + (startBc - endBc) + " yrs)";
    return { startBc: startBc, endBc: endBc };
  }

  function currentToggles() {
    const phases = {};
    document.querySelectorAll("#phases input").forEach(function (box) {
      phases[box.value] = box.checked;
    });
    const window = chronologyWindow();
    return {
      chronology: document.getElementById("chrono").checked,
      startBc: window.startBc,
      endBc: window.endBc,
      season: document.getElementById("season").value || "normal",
      phases: phases,
      overrides: state.overrides,
      analysis: state.analysis,
      agents: Number(document.getElementById("agents").value),
      undated: document.getElementById("undated").value,
      terrainWeight: Number(document.getElementById("terrain-weight").value),
      riverWeight: Number(document.getElementById("river-weight").value),
    };
  }

  // Slider drags fire many events; the engine only needs the last one.
  let toggleTimer = null;
  function sendToggles() {
    if (toggleTimer) clearTimeout(toggleTimer);
    toggleTimer = setTimeout(function () {
      toggleTimer = null;
      worker.postMessage({ type: "setToggles", toggles: currentToggles() });
    }, 120);
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
    const frame = state.frame;
    if (!frame || !map || !map.getLayer("density")) return;
    const nx = frame.nx;
    const ny = frame.ny;
    const field = frame.field;
    const channels = frame.channels || 1;
    if (canvas.width !== nx || canvas.height !== ny) {
      canvas.width = nx;
      canvas.height = ny;
    }
    const ctx = canvas.getContext("2d");
    const image = ctx.createImageData(nx, ny);
    const max = frame.max || 0;
    const cutoff = Number(document.getElementById("cutoff").value) * max;
    const useLog = document.getElementById("log").checked;
    const size = nx * ny;
    const tone = function (value) {
      if (value < cutoff || max <= 0) return 0;
      let amount = value / max;
      if (useLog && amount > 0) amount = Math.log1p(amount * 9) / Math.log(10);
      return amount;
    };
    for (let k = 0; k < size; k++) {
      const pixel = k * 4;
      if (channels === 1) {
        const amount = tone(field[k]);
        if (amount <= 0) continue;
        const rgb = ramp(amount);
        image.data[pixel] = rgb[0];
        image.data[pixel + 1] = rgb[1];
        image.data[pixel + 2] = rgb[2];
        image.data[pixel + 3] = 210;
      } else {
        // one colour per origin group: red, green, blue, as in the Java tool
        const r = tone(field[k]);
        const g = tone(field[size + k]);
        const b = channels > 2 ? tone(field[2 * size + k]) : 0;
        const top = Math.max(r, g, b);
        if (top <= 0) continue;
        image.data[pixel] = Math.round(255 * r / top);
        image.data[pixel + 1] = Math.round(255 * g / top);
        image.data[pixel + 2] = Math.round(255 * b / top);
        image.data[pixel + 3] = Math.round(90 + 150 * top);
      }
    }
    ctx.putImageData(image, 0, 0);
    map.setPaintProperty("density", "raster-opacity", Number(document.getElementById("opacity").value));
    map.triggerRepaint();
  }

  function paintWalls(frame) {
    const nx = frame.walls ? frame.walls_nx : 1;
    const ny = frame.walls ? frame.walls_ny : 1;
    wallCanvas.width = nx;
    wallCanvas.height = ny;
    const ctx = wallCanvas.getContext("2d");
    ctx.clearRect(0, 0, nx, ny);
    if (frame.walls) ctx.putImageData(new ImageData(frame.walls, nx, ny), 0, 0);
    if (map) map.triggerRepaint();
  }

  function featurePoint(coords, props) {
    return {
      type: "Feature",
      properties: props || {},
      geometry: { type: "Point", coordinates: coords },
    };
  }

  const GROUP_COLOURS = ["#ff5a4d", "#4ddc6a", "#5aa2ff"];

  function syncAgents(points) {
    if (!map || !map.getSource("agents")) return;
    state.agentShown = points || [];
    map.getSource("agents").setData({
      type: "FeatureCollection",
      features: state.agentShown.map(function (item) {
        return featurePoint([item[0], item[1]], { group: item[2] });
      }),
    });
  }

  function agentsFromFrame(frame) {
    const out = new Map();
    const n = frame.n_agents || 0;
    for (let i = 0; i < n; i++) {
      out.set(frame.ids[i],
        [frame.agents[2 * i], frame.agents[2 * i + 1], frame.groups[i], frame.ages[i]]);
    }
    return out;
  }

  function lerpAgents(now) {
    const to = state.agentTo;
    const from = state.agentFrom;
    const span = Math.max(1, state.lerpMs);
    const amount = Math.min(1, Math.max(0, (now - state.lerpStart) / span));
    const out = [];
    to.forEach(function (b, id) {
      // A walker that has just set out again is at its origin now. Its last
      // position was the destination it reached, so tweening would drag it
      // across the map: it appears at the origin instead.
      const a = (b[3] <= state.lastSteps + 1 ? null : from.get(id)) || b;
      out.push([a[0] + (b[0] - a[0]) * amount, a[1] + (b[1] - a[1]) * amount, b[2]]);
    });
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
      drawPulses(now);
      state.displayTimer = requestAnimationFrame(tick);
    };
    state.displayTimer = requestAnimationFrame(tick);
  }

  // A ring that opens and fades where a walker sets out again, so arrivals
  // turning into departures can be seen rather than inferred.
  const PULSE_MS = 900;

  function notePulses(now) {
    state.agentTo.forEach(function (b) {
      if (b[3] <= state.lastSteps + 1) state.pulses.push([b[0], b[1], b[2], now]);
    });
    if (state.pulses.length > 400) state.pulses.splice(0, state.pulses.length - 400);
  }

  function drawPulses(now) {
    if (!state.pulses.length && !state.hadPulses) return;
    state.pulses = state.pulses.filter(function (p) { return now - p[3] < PULSE_MS; });
    state.hadPulses = state.pulses.length > 0;
    setData("spawns", state.pulses.map(function (p) {
      const age = (now - p[3]) / PULSE_MS;
      return featurePoint([p[0], p[1]], { r: 3 + 13 * age, o: 0.9 * (1 - age), group: p[2] });
    }));
    if (state.hadPulses && !state.playing) {
      requestAnimationFrame(function (next) { drawPulses(next); });
    }
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
      const s = L2 <= 0 ? 0 : Math.max(0, Math.min(1, ((door[0] - a[0]) * dx + (door[1] - a[1]) * dy) / L2));
      const proj = [a[0] + s * dx, a[1] + s * dy];
      const d = Math.hypot(door[0] - proj[0], door[1] - proj[1]);
      if (d < bestD) {
        bestD = d;
        best = { proj: proj };
      }
    }
    if (!best) return door;
    // Step out from the facade, away from the footprint's centre, by a few
    // cells so the entrance lands on walkable ground whatever the winding.
    let cx = 0;
    let cy = 0;
    for (let i = 0; i < ring.length - 1; i++) { cx += ring[i][0]; cy += ring[i][1]; }
    cx /= ring.length - 1;
    cy /= ring.length - 1;
    const m = metresPerDegree(best.proj[1]);
    const ox = (best.proj[0] - cx) * m.lon;
    const oy = (best.proj[1] - cy) * m.lat;
    const len = Math.hypot(ox, oy) || 1;
    const out = Math.max(3, 2 * ((state.desc && state.desc.grid.gridsize) || 2));
    return [best.proj[0] + (out * ox / len) / m.lon, best.proj[1] + (out * oy / len) / m.lat];
  }

  function setData(source, features) {
    if (!map || !map.getSource(source)) return;
    map.getSource(source).setData({ type: "FeatureCollection", features: features });
  }

  function syncBuildings() {
    const desc = state.desc;
    if (!desc) return;
    const phaseColour = {};
    (desc.phases || []).forEach(function (phase) { phaseColour[phase.id] = phase.colour; });
    setData("buildings", (desc.buildings || []).filter(function (building) {
      return building.active && building.state !== "backfilled";
    }).map(function (building) {
      const first = (building.phase_ids || [])[0];
      return {
        type: "Feature",
        properties: {
          colour: (first && phaseColour[first]) || "#9aa3ad",
          name: building.name,
          height: building.height || 3,
        },
        // a hollow building is drawn as its wall: outline with the room cut out
        geometry: {
          type: "Polygon",
          coordinates: building.inner ? [building.ring, building.inner] : [building.ring],
        },
      };
    }));
    setData("doors", (desc.buildings || []).filter(function (building) {
      return building.active && building.door;
    }).map(function (building) { return featurePoint(building.door, {}); }));
    setData("obstacles", (desc.obstacles || []).map(function (item) {
      return {
        type: "Feature", properties: { layer: item.layer },
        geometry: { type: "Polygon", coordinates: [item.ring] },
      };
    }));
  }

  function villageFor(siteName) {
    const scenes = (state.index && state.index.scenes) || [];
    for (let i = 0; i < scenes.length; i++) {
      if (scenes[i].scale === "village" && scenes[i].site === siteName) return scenes[i];
    }
    return null;
  }

  function syncSites() {
    const desc = state.desc;
    if (!desc) return;
    setData("sites", (desc.sites || []).map(function (site) {
      return featurePoint(site.coordinates, {
        name: site.name,
        official: site.official ? 1 : 0,
        active: site.walking ? 1 : 0,
        flagged: site.flagged ? 1 : 0,
        usable: site.uncertain ? 0 : 1,
        village: villageFor(site.name) ? 1 : 0,
        label: site.name + (site.uncertain ? " ?" : ""),
      });
    }));
  }

  function syncOds() {
    const desc = state.desc;
    if (!desc) return;
    // At cluster scale every OD is a site and the site marker already shows it.
    const show = (desc.ods || []).filter(function (od) {
      return desc.scale !== "cluster" || od.kind !== "site";
    });
    setData("ods", show.map(function (od) {
      return featurePoint(od.coordinates, {
        name: od.name,
        kind: od.kind,
        active: od.active ? 1 : 0,
        weight: od.dest_weight,
      });
    }));
  }

  function syncRivers() {
    const desc = state.desc;
    if (!desc) return;
    setData("rivers", (desc.rivers || []).map(function (river) {
      return {
        type: "Feature",
        properties: { name: river.name, perennial: river.perennial ? 1 : 0 },
        geometry: { type: "LineString", coordinates: river.coordinates },
      };
    }));
  }

  function syncTraces(frame) {
    const byGroup = frame.analysis === "tracesO";
    setData("traces", (frame.traces || []).map(function (trace) {
      return {
        type: "Feature",
        properties: { colour: byGroup ? GROUP_COLOURS[trace.group % 3] : "#3c78ff" },
        geometry: { type: "LineString", coordinates: trace.coordinates },
      };
    }));
  }

  function syncTrack() {
    const points = state.track.points || [];
    setData("track", points.length < 2 ? points.map(function (point) {
      return featurePoint([point.lon, point.lat], { t: point.t || "" });
    }) : [{
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates: points.map(function (point) { return [point.lon, point.lat]; }),
      },
    }]);
  }

  function syncIso(ring) {
    setData("iso", state.showIso && ring && ring.length > 3 ? [{
      type: "Feature", properties: {},
      geometry: { type: "Polygon", coordinates: [ring] },
    }] : []);
  }

  function showMetrics(frame) {
    const desc = state.desc;
    if (!desc) return;
    const lines = [desc.name + " · " + desc.grid.nx + "×" + desc.grid.ny + " cells of " + desc.grid.gridsize + " m"];
    if (desc.note) lines.push(desc.note);
    (desc.hud || []).forEach(function (line) { lines.push(line); });
    lines.push("season: " + frame.season + (frame.daylight ? " · " + frame.daylight + " min daylight" : ""));
    const idle = (desc.sites || []).filter(function (site) { return !site.walking; });
    if (desc.scale === "cluster" && idle.length) {
      lines.push(t("idleSites") + " (" + idle.length + "):");
      idle.forEach(function (site) { lines.push("  " + site.name + " — " + site.reason); });
    }
    lines.push("places: " + (desc.ods || []).length + " · buildings: " + (desc.buildings || []).length
      + (desc.edited ? " · edited" : ""));
    if (frame.live) {
      lines.push("step " + frame.step + " · " + frame.n_agents + " walkers · peak " + (frame.max || 0).toFixed(2));
      if (state.stepMs) {
        lines.push(t("engineLive") + " · " + (1000 / state.stepMs).toFixed(1) + " steps/s");
      } else {
        lines.push(t("engineLive"));
      }
    } else {
      lines.push(t("engineOff") + (frame.reason ? ": " + frame.reason : ""));
    }
    document.getElementById("metrics").textContent = lines.join("\n");
    document.getElementById("scale-label").textContent = desc.scale === "cluster" ? t("cluster") : desc.name;
    const active = {};
    (desc.active || []).forEach(function (id) { active[id] = true; });
    document.querySelectorAll("#phases input").forEach(function (box) {
      if (!Object.prototype.hasOwnProperty.call(state.overrides, box.value)) {
        box.checked = Boolean(active[box.value]);
      }
    });
  }

  function applyDescribe(desc) {
    const first = !state.desc || state.desc.id !== desc.id;
    state.desc = desc;
    if (first) {
      fillSceneControls();
      applySceneToMap();
    } else {
      syncBuildings();
      syncSites();
      syncOds();
      syncRivers();
    }
    if (desc.edited && state.autosave) {
      worker.postMessage({ type: "export", purpose: "autosave" });
    }
  }

  worker.onmessage = function (event) {
    const message = event.data || {};
    if (message.type === "status") {
      state.engine = message.phase;
      if (message.phase === "boot") setStatus(t("engineBoot") + " (" + message.text + ")");
      if (message.phase === "scene") setStatus(t("sceneLoading") + " " + message.text);
      if (message.phase === "loaded") setStatus(message.text);
      if (message.phase === "failed") setStatus(t("engineOff") + ": " + message.text);
      return;
    }
    if (message.type === "error") {
      state.awaiting = false;
      setStatus("engine: " + message.text);
      return;
    }
    if (message.type === "geometry") {
      const record = { id: message.data.scene.id, saved: new Date().toISOString(), geometry: message.data };
      put("saves", record);
      if (message.purpose === "download") {
        download(record.id + ".geometry.json",
          new Blob([JSON.stringify(message.data)], { type: "application/json" }));
        setStatus(t("exported"));
      } else if (message.purpose === "save") {
        setStatus(t("saved"));
      }
      return;
    }
    if (message.type !== "frame") return;
    state.awaiting = false;
    if (message.scene !== state.sceneId) return;   // a late frame from the previous scene
    const now = performance.now();
    if (message.steps) {
      const per = message.ms / message.steps;
      state.stepMs = state.stepMs ? state.stepMs * 0.7 + per * 0.3 : per;
    }
    if (message.describe) {
      applyDescribe(message.describe);
      paintWalls(message);      // walls change only when the scene does
    }
    state.frame = message;
    paint();
    state.agentFrom = state.agentTo;
    state.agentTo = agentsFromFrame(message);
    state.lastSteps = message.steps || 1;
    if (message.steps) notePulses(now);
    state.lerpStart = now;
    state.lerpMs = Math.max(state.playStepMs, message.ms || 0);
    if (!state.playing) {
      lerpAgents(now + state.lerpMs);
      drawPulses(now);
    }
    if (message.traces || state.hadTraces) syncTraces(message);
    state.hadTraces = Boolean(message.traces);
    syncIso(message.isovist);
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
    // Esri sends cross-origin headers, so this one needs no laptop behind the
    // page. Its terms allow display with credit, not storing: the service
    // worker leaves other origins alone.
    esri: {
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
      // level 19 is a "map data not yet available" placeholder out here;
      // 18 is the deepest real imagery, and the map stretches it beyond that
      maxzoom: 18,
    },
  };

  function firstOverlay() {
    // Basemap layers go under everything pedsim draws, roads included.
    if (map.getLayer("osm-roads")) return "osm-roads";
    return map.getLayer("density") ? "density" : undefined;
  }

  function satelliteFor(id) {
    const maps = state.index && state.index.maps;
    return (maps && maps.satellite && maps.satellite[id]) || null;
  }

  function addImage(id, entry) {
    map.addSource(id, {
      type: "image",
      url: PACK + entry.file + "?v=" + state.index.build,
      coordinates: entry.corners,
    });
    map.addLayer({
      id: id, type: "raster", source: id,
      paint: { "raster-opacity": 1, "raster-fade-duration": 0 },
    }, firstOverlay());
  }

  function setBasemap(kind) {
    // Not isStyleLoaded(): that is false while any source is still loading,
    // which would silently drop the basemap chosen during start-up.
    if (!map || !state.styleReady) return;
    ["basemap", "relief", "sat", "satwide"].forEach(function (id) {
      if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(id)) map.removeSource(id);
    });
    if (kind === "none") return;
    const online = navigator.onLine;
    const relief = state.index && state.index.basemap;
    const near = satelliteFor(state.sceneId);
    const wide = satelliteFor("cluster");
    let use = kind;
    if (use === "auto") use = online ? "esri" : (near || wide ? "sat" : "relief");
    // The packed image goes down first. Online tiles are drawn over it, so a
    // tile that does not arrive in the field leaves the packed map showing.
    if (use === "relief" || !(near || wide)) {
      if (relief && relief.file) addImage("relief", relief);
    } else {
      if (wide && wide !== near) addImage("satwide", wide);
      if (near) addImage("sat", near);
    }
    if (!TILES[use] || !online) return;
    map.addSource("basemap", {
      type: "raster",
      tiles: TILES[use].tiles,
      tileSize: 256,
      attribution: TILES[use].attribution,
      maxzoom: TILES[use].maxzoom || 20,
    });
    map.addLayer({
      id: "basemap",
      type: "raster",
      source: "basemap",
      paint: { "raster-opacity": 1, "raster-fade-duration": 0 },
    }, firstOverlay());
  }

  function syncOsm() {
    if (!map || !state.mapReady || !state.index) return;
    const maps = state.index.maps || {};
    const entry = (maps.osm || {})[state.sceneId] || (maps.osm || {}).cluster;
    const show = document.getElementById("roads").checked && entry;
    map.getSource("osm").setData(show
      ? PACK + entry.file + "?v=" + state.index.build
      : { type: "FeatureCollection", features: [] });
  }

  const LABEL_FONT = ["Noto Sans Regular"];

  function ensureMap() {
    if (map) return;
    map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        // Label glyphs ship with the app, so place names also draw offline.
        glyphs: new URL("vendor/fonts/", window.location.href).href + "{fontstack}/{range}.pbf",
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
      const text = (event && event.error && event.error.message) || String(event);
      window.__lastErr = text;
      // A missing glyph or tile while offline is expected, not worth the status line.
      if (navigator.onLine) setStatus("map: " + text);
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-right");
    map.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution: "pedsim live · relief © Copernicus DEM (DLR / Airbus, EU, ESA) · Google/Esri tiles online only, not cached",
    }));
    map.on("load", function () {
      try {
        const empty = { type: "FeatureCollection", features: [] };
        state.styleReady = true;
        map.addSource("osm", { type: "geojson", data: empty });
        map.addLayer({
          id: "osm-roads", type: "line", source: "osm",
          filter: ["==", ["get", "kind"], "road"],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#ffffff",
            "line-opacity": ["match", ["get", "rank"], 1, 0.75, 2, 0.6, 3, 0.45, 0.35],
            "line-width": [
              "interpolate", ["linear"], ["zoom"],
              9, ["match", ["get", "rank"], 1, 1.4, 2, 0.8, 0.4],
              15, ["match", ["get", "rank"], 1, 4, 2, 3, 3, 2, 1.2],
            ],
          },
        });
        map.addSource("density", {
          type: "canvas",
          canvas: canvas,
          coordinates: [[38.4, 37.5], [39.3, 37.5], [39.3, 36.8], [38.4, 36.8]],
          animate: true,
        });
        map.addLayer({
          id: "density", type: "raster", source: "density",
          paint: {
            "raster-opacity": Number(document.getElementById("opacity").value),
            "raster-resampling": "nearest",
            "raster-fade-duration": 0,
          },
        });
        map.addSource("walls", {
          type: "canvas", canvas: wallCanvas, animate: true,
          coordinates: [[38.4, 37.5], [39.3, 37.5], [39.3, 36.8], [38.4, 36.8]],
        });
        map.addLayer({
          id: "walls", type: "raster", source: "walls",
          paint: { "raster-opacity": 0.92, "raster-resampling": "nearest", "raster-fade-duration": 0 },
        });
        map.addSource("rivers", { type: "geojson", data: empty });
        map.addLayer({
          id: "rivers", type: "line", source: "rivers",
          paint: {
            "line-color": "#4aa3ff",
            "line-width": ["case", ["==", ["get", "perennial"], 1], 2.2, 1.2],
            "line-opacity": 0.75,
          },
        });
        map.addSource("traces", { type: "geojson", data: empty });
        map.addLayer({
          id: "traces", type: "line", source: "traces",
          paint: { "line-color": ["get", "colour"], "line-width": 1.2, "line-opacity": 0.7 },
        });
        map.addSource("obstacles", { type: "geojson", data: empty });
        map.addLayer({
          id: "obstacles", type: "fill", source: "obstacles",
          paint: { "fill-color": "#6f7780", "fill-opacity": 0.6 },
        });
        map.addSource("buildings", { type: "geojson", data: empty });
        // Standardised prism height; flat top (no modelled roof).
        map.addLayer({
          id: "buildings-fill", type: "fill-extrusion", source: "buildings",
          paint: {
            "fill-extrusion-color": ["coalesce", ["get", "colour"], "#9aa3ad"],
            "fill-extrusion-height": ["coalesce", ["get", "height"], 3],
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.88,
            "fill-extrusion-vertical-gradient": true,
          },
        });
        map.addSource("doors", { type: "geojson", data: empty });
        map.addLayer({
          id: "doors", type: "circle", source: "doors",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 14, 2, 18, 5],
            "circle-color": "#00ff66", "circle-stroke-width": 1, "circle-stroke-color": "#003311",
          },
        });
        map.addSource("sites", { type: "geojson", data: empty });
        map.addLayer({
          id: "sites", type: "circle", source: "sites",
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              8, ["case", ["==", ["get", "official"], 1], 5, 4],
              14, ["case", ["==", ["get", "official"], 1], 7, 5.5],
              17, ["case", ["==", ["get", "official"], 1], 9, 7],
            ],
            // Sites outside the time window stay on the map, greyed out.
            // an uncertain position (conflicting or search area) is drawn
            // hollow-looking: dark fill, and a "?" after its name
            "circle-color": [
              "case",
              ["==", ["get", "active"], 0], "#5a5a5a",
              ["==", ["get", "usable"], 0], "#7a3b00",
              ["==", ["get", "official"], 1], "#ff2222",
              "#ffaa00",
            ],
            "circle-stroke-width": ["case", ["==", ["get", "village"], 1], 2, 1],
            // an undated site that is included anyway wears a yellow ring
            "circle-stroke-color": ["case", ["==", ["get", "flagged"], 1], "#ffe14d", "#ffffff"],
            "circle-opacity": ["case", ["==", ["get", "active"], 0], 0.6, 1],
          },
        });
        map.addLayer({
          id: "sites-label", type: "symbol", source: "sites",
          layout: {
            "text-field": ["get", "label"],
            "text-font": LABEL_FONT,
            "text-size": 11,
            "text-offset": [0, 1.2],
            "text-anchor": "top",
            "text-optional": true,
          },
          paint: {
            "text-color": ["case", ["==", ["get", "active"], 0], "#9a9a9a", "#ffffff"],
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
              8, ["+", 2.2, ["*", 1.5, ["coalesce", ["get", "weight"], 1]]],
              14, ["+", 3.2, ["*", 2.5, ["coalesce", ["get", "weight"], 1]]],
              17, ["+", 4.5, ["*", 3.5, ["coalesce", ["get", "weight"], 1]]],
            ],
            "circle-color": [
              "case",
              ["==", ["get", "active"], 0], "#5a5a5a",
              ["==", ["get", "kind"], "water"], "#44aaff",
              ["==", ["get", "kind"], "house"], "#ffcc00",
              ["==", ["get", "kind"], "destination"], "#00ff66",
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
            "text-font": LABEL_FONT,
            "text-size": 10,
            "text-offset": [0, 1.1],
            "text-anchor": "top",
            "text-optional": true,
          },
          paint: { "text-color": "#fff", "text-halo-color": "#000", "text-halo-width": 1 },
        });
        map.addLayer({
          id: "osm-places", type: "symbol", source: "osm",
          // village names only once zoomed in, or they bury the cluster map
          filter: ["all", ["==", ["get", "kind"], "place"],
            ["any", ["in", ["get", "place"], ["literal", ["city", "town"]]], [">=", ["zoom"], 11.5]]],
          layout: {
            "text-field": ["get", "name"],
            "text-font": LABEL_FONT,
            "text-size": ["match", ["get", "place"], "city", 14, "town", 12, 10],
            "text-optional": true,
          },
          paint: { "text-color": "#ffe9a8", "text-halo-color": "#000000", "text-halo-width": 1.2 },
        }, "sites");
        map.addSource("spawns", { type: "geojson", data: empty });
        map.addLayer({
          id: "spawns", type: "circle", source: "spawns",
          paint: {
            "circle-radius": ["get", "r"],
            "circle-color": "rgba(0,0,0,0)",
            "circle-stroke-width": 2,
            "circle-stroke-color": [
              "match", ["get", "group"], 0, GROUP_COLOURS[0], 1, GROUP_COLOURS[1], 2, GROUP_COLOURS[2], "#ffffff",
            ],
            "circle-stroke-opacity": ["get", "o"],
          },
        });
        map.addSource("draft", { type: "geojson", data: empty });
        map.addLayer({
          id: "draft-fill", type: "fill", source: "draft",
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": "#ffcc00", "fill-opacity": 0.35 },
        });
        map.addLayer({
          id: "draft-line", type: "line", source: "draft",
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "line-color": "#ffcc00", "line-width": 2.5 },
        });
        map.addLayer({
          id: "draft-point", type: "circle", source: "draft",
          filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 5, "circle-color": "#ffcc00", "circle-stroke-width": 1.5, "circle-stroke-color": "#000000" },
        });
        map.addSource("agents", { type: "geojson", data: empty });
        map.addLayer({
          id: "agents", type: "circle", source: "agents",
          paint: {
            // Keep walkers as pinpricks next to buildings and OD discs.
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              8, 1.2,
              12, 1.6,
              15, 2.2,
              17, 2.8,
            ],
            // sized on the screen, not on the ground: in the tilted view every
            // walker is the same size, near or far
            "circle-pitch-scale": "viewport",
            "circle-pitch-alignment": "viewport",
            "circle-color": "#ffffff",
            "circle-stroke-width": 0.8,
            "circle-stroke-color": [
              "match", ["get", "group"], 0, GROUP_COLOURS[0], 1, GROUP_COLOURS[1], 2, GROUP_COLOURS[2], "#cc0000",
            ],
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
          paint: { "fill-color": "#ffffff", "fill-opacity": 0.22, "fill-outline-color": "#ffffff" },
        });
        map.on("click", onMapClick);
        ["mousedown", "touchstart"].forEach(function (name) { map.on(name, draftDown); });
        ["mousemove", "touchmove"].forEach(function (name) { map.on(name, draftMove); });
        ["mouseup", "touchend"].forEach(function (name) { map.on(name, draftUp); });
        map.on("contextmenu", function (event) {
          if (!state.draft) return;
          event.preventDefault();
          cancelDraft();
        });
        state.mapReady = true;
        setBasemap(document.getElementById("basemap").value);
        syncOsm();
        applySceneToMap();
        updateMapInteraction();
      } catch (error) {
        window.__lastErr = String(error && error.message ? error.message : error);
        setStatus("map setup: " + window.__lastErr);
      }
    });
  }

  function applySceneToMap() {
    const desc = state.desc;
    if (!map || !state.mapReady || !desc) return;
    map.getSource("density").setCoordinates(desc.corners);
    map.getSource("walls").setCoordinates(desc.corners);
    map.easeTo({
      center: desc.center,
      zoom: desc.zoom || (desc.scale === "cluster" ? 9.5 : 16),
      duration: 600,
    });
    syncBuildings();
    syncSites();
    syncOds();
    syncRivers();
    syncTrack();
    paint();
  }

  function fillSceneControls() {
    const desc = state.desc;
    const season = document.getElementById("season");
    const meta = state.meta || {};
    const keep = season.value || desc.season;
    season.innerHTML = "";
    (meta.seasons || []).forEach(function (item) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name;
      if (item.id === keep) option.selected = true;
      season.appendChild(option);
    });
    const phases = document.getElementById("phases");
    phases.innerHTML = "";
    state.overrides = {};
    (desc.phases || []).forEach(function (phase) {
      const label = document.createElement("label");
      label.className = "row check";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = phase.id;
      box.checked = phase.active;
      label.appendChild(box);
      label.appendChild(document.createTextNode(
        " " + phase.name + " (" + phase.start_bc + "–" + phase.end_bc + ")"));
      phases.appendChild(label);
      box.addEventListener("change", function (event) {
        state.overrides[phase.id] = event.target.checked;
        sendToggles();
      });
    });
    phases.parentNode.hidden = !(desc.phases || []).length;
    document.getElementById("undated").value = desc.undated || "exclude";
    ["terrain", "river"].forEach(function (key) {
      const value = desc[key + "_weight"] == null ? 1 : desc[key + "_weight"];
      document.getElementById(key + "-weight").value = String(value);
      document.getElementById(key + "-weight-out").textContent = "×" + value;
    });
    document.getElementById("river-weight").disabled = !(desc.rivers || []).length;
    document.getElementById("agents").value = String(desc.num_agents);
    document.getElementById("agents-out").textContent = String(desc.num_agents);
    document.getElementById("scale-cluster").classList.toggle("active", desc.scale === "cluster");
    document.getElementById("site").value = desc.scale === "cluster" ? "" : desc.id;
    document.getElementById("blurb").textContent = t("packed");
  }

  function sceneRow(id) {
    const scenes = (state.index && state.index.scenes) || [];
    for (let i = 0; i < scenes.length; i++) if (scenes[i].id === id) return scenes[i];
    return null;
  }

  function packUrl(file) {
    return PACK + file + "?v=" + state.index.build;
  }

  function loadScene(id) {
    const row = sceneRow(id);
    if (!row) {
      setStatus(t("packMissing"));
      return;
    }
    pause();
    state.sceneId = id;
    state.draft = null;
    state.pulses = [];
    setNet();              // the packed satellite image is per scene
    syncOsm();
    state.agentFrom = new Map();
    state.agentTo = new Map();
    state.stepMs = 0;
    state.playStepMs = row.scale === "village" ? 200 : 300;
    setStatus(t("sceneLoading") + " " + row.label);
    ensureMap();
    Promise.all([
      fetch(packUrl(row.file)).then(function (r) {
        if (!r.ok) throw new Error(row.file);
        return r.json();
      }),
      all("saves").catch(function () { return []; }),
    ]).then(function (found) {
      const meta = found[0];
      const saved = (found[1] || []).filter(function (item) { return item.id === id; })[0];
      state.meta = meta;
      // Draw the packed description at once; the engine's own follows.
      state.desc = null;
      paintWalls({});
      applyDescribe(meta.display);
      const toggles = currentToggles();
      toggles.agents = state.low ? Math.min(meta.display.num_agents, 80) : meta.display.num_agents;
      worker.postMessage({
        type: "loadScene", meta: meta, blobUrl: packUrl(row.blob),
        geometry: saved && state.autosave ? saved.geometry : null,
        toggles: toggles,
      });
    }).catch(function (error) {
      setStatus(t("packMissing") + " (" + (error && error.message) + ")");
    });
    paintToolbar();
  }

  function play() {
    if (state.playing) return;
    state.playing = true;
    paintToolbar();
    setStatus(t("playing"));
    const tick = function () {
      if (!state.playing) return;
      // Never queue steps the engine has not answered: a slow phone would fall
      // further and further behind.
      if (!state.awaiting) {
        state.awaiting = true;
        worker.postMessage({ type: "step", n: state.low ? 1 : state.stepsPerTick });
      }
      state.timer = setTimeout(tick, state.low ? state.playStepMs * 2 : state.playStepMs);
    };
    tick();
    startDisplayLoop();
  }

  function pause() {
    const was = state.playing;
    state.playing = false;
    if (state.timer) clearTimeout(state.timer);
    stopDisplayLoop();
    if (state.agentTo && state.agentTo.size) lerpAgents(performance.now() + 1e6);
    paintToolbar();
    if (was) setStatus(t("paused"));
  }

  function gpxText(points, name) {
    const rows = points.map(function (point) {
      const time = point.t ? "<time>" + point.t + "</time>" : "";
      const ele = point.alt != null ? "<ele>" + point.alt + "</ele>" : "";
      const acc = point.acc != null ? "<hdop>" + (point.acc / 5).toFixed(1) + "</hdop>" : "";
      return "<trkpt lat=\"" + point.lat + "\" lon=\"" + point.lon + "\">" + ele + time + acc + "</trkpt>";
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

  function addTrackPoint(lat, lon, source, extra) {
    const point = { lat: lat, lon: lon, t: new Date().toISOString(), source: source || "map" };
    if (extra && extra.accuracy != null) point.acc = Math.round(extra.accuracy * 10) / 10;
    if (extra && extra.altitude != null) point.alt = Math.round(extra.altitude * 10) / 10;
    state.track.points.push(point);
    put("tracks", state.track);
    syncTrack();
    setStatus(t("recorded") + " (" + state.track.points.length + ")"
      + (point.acc != null ? " ±" + point.acc + " m" : ""));
  }

  let wakeLock = null;
  function holdScreen(on) {
    // The browser stops GPS when the screen sleeps, so keep it awake while recording.
    if (!navigator.wakeLock) return;
    if (on) {
      navigator.wakeLock.request("screen").then(function (lock) { wakeLock = lock; }).catch(function () {});
    } else if (wakeLock) {
      wakeLock.release().catch(function () {});
      wakeLock = null;
    }
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
    holdScreen(true);
    state.watch = navigator.geolocation.watchPosition(function (pos) {
      addTrackPoint(pos.coords.latitude, pos.coords.longitude, "gps", pos.coords);
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
    holdScreen(false);
    paintToolbar();
    updateMapInteraction();
    setStatus(t("recordStop"));
  }

  function edit(name, payload) {
    if (state.engine === "failed") {
      setStatus(t("engineOff"));
      return;
    }
    // A wall edit re-solves every route, which takes a while on a phone.
    if (name === "addBuilding" || name === "deleteBuilding" || name === "applyGeometry" || name === "reset") {
      setStatus(t("working"));
    }
    worker.postMessage({ type: "command", name: name, payload: payload });
  }

  // ------------------------------------------------------ drawing a building
  // Press, drag, release: the outline follows the finger. A plain tap also
  // works (tap the start, tap the end). The entrance is placed by the page, on
  // the wall facing the nearest place, so there is no third step to remember.
  function drawingBuilding() {
    return state.mode === "bdCircle" || state.mode === "bdRect";
  }

  function draftRing(draft) {
    if (!draft || !draft.a || !draft.b) return null;
    if (draft.shape === "circle") {
      const radius = distMetres(draft.a, draft.b);
      return radius > 0 ? circleRing(draft.a, radius, 24) : null;
    }
    if (draft.a[0] === draft.b[0] || draft.a[1] === draft.b[1]) return null;
    return rectRing(draft.a, draft.b);
  }

  function draftSize(draft) {
    if (draft.shape === "circle") return "Ø " + (2 * distMetres(draft.a, draft.b)).toFixed(1) + " m";
    const w = distMetres(draft.a, [draft.b[0], draft.a[1]]);
    const h = distMetres(draft.a, [draft.a[0], draft.b[1]]);
    return w.toFixed(1) + " × " + h.toFixed(1) + " m";
  }

  function drawDraft() {
    const draft = state.draft;
    if (!draft) {
      setData("draft", []);
      return;
    }
    const ring = draftRing(draft);
    const features = [featurePoint(draft.a, {})];
    if (ring) features.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } });
    setData("draft", features);
    showHint((ring ? draftSize(draft) + " — " : "") + t("hintSecond") + " · " + t("hintRight"));
  }

  function cancelDraft() {
    state.draft = null;
    setData("draft", []);
    showHint();
  }

  function nearestPlace(point) {
    let best = null;
    let bestD = Infinity;
    ((state.desc && state.desc.ods) || []).forEach(function (od) {
      const d = distMetres(point, od.coordinates);
      if (od.active && d < bestD) {
        bestD = d;
        best = od;
      }
    });
    return best;
  }

  function finishDraft() {
    const draft = state.draft;
    const ring = draftRing(draft);
    const cell = (state.desc && state.desc.grid.gridsize) || 2;
    const small = !ring || (draft.shape === "circle"
      ? distMetres(draft.a, draft.b) < cell
      : Math.min(distMetres(draft.a, [draft.b[0], draft.a[1]]),
        distMetres(draft.a, [draft.a[0], draft.b[1]])) < cell);
    if (small) {
      cancelDraft();
      setStatus(t("bdTooSmall"));
      return;
    }
    const box = state.desc.bounds;
    const outside = ring.some(function (p) {
      return p[0] < box.west || p[0] > box.east || p[1] < box.south || p[1] > box.north;
    });
    if (outside) {
      cancelDraft();
      setStatus(t("bdOutside"));
      return;
    }
    let cx = 0;
    let cy = 0;
    for (let i = 0; i < ring.length - 1; i++) { cx += ring[i][0]; cy += ring[i][1]; }
    const centre = [cx / (ring.length - 1), cy / (ring.length - 1)];
    const toward = nearestPlace(centre);
    const door = entranceFromDoor(ring, toward ? toward.coordinates : [centre[0], centre[1] - 1e-4]);
    edit("addBuilding", { ring: ring, door: door, function: "domestic", height: 3 });
    cancelDraft();
    setStatus(t("bdEntrance") + " " + (toward ? toward.name : "south"));
  }

  function draftDown(event) {
    if (!drawingBuilding() || state.recording) return;
    if (event.originalEvent && event.originalEvent.button) return;   // left button only
    if (event.originalEvent && event.originalEvent.touches && event.originalEvent.touches.length > 1) {
      cancelDraft();          // two fingers: the user is zooming, not drawing
      return;
    }
    event.preventDefault();
    const here = [event.lngLat.lng, event.lngLat.lat];
    if (state.draft && state.draft.waiting) {
      state.draft.b = here;
      finishDraft();
      return;
    }
    state.draft = {
      shape: state.mode === "bdCircle" ? "circle" : "rect",
      a: here, b: here, down: event.point, dragging: true, waiting: false,
    };
    drawDraft();
  }

  function draftMove(event) {
    const draft = state.draft;
    if (!draft || !drawingBuilding()) return;
    if (!draft.dragging && !draft.waiting) return;
    draft.b = [event.lngLat.lng, event.lngLat.lat];
    drawDraft();
  }

  function draftUp(event) {
    const draft = state.draft;
    if (!draft || !draft.dragging) return;
    draft.dragging = false;
    const moved = Math.hypot(event.point.x - draft.down.x, event.point.y - draft.down.y);
    if (moved > 8) {
      draft.b = [event.lngLat.lng, event.lngLat.lat];
      finishDraft();
    } else {
      // a tap, not a drag: the next tap sets the far side
      draft.waiting = true;
      drawDraft();
    }
  }

  function siteAt(point) {
    if (!map.getLayer("sites")) return null;
    const hits = map.queryRenderedFeatures(
      [[point.x - 10, point.y - 10], [point.x + 10, point.y + 10]], { layers: ["sites"] });
    return hits.length ? hits[0].properties.name : null;
  }

  function onMapClick(event) {
    const lngLat = event.lngLat;
    const where = { lon: lngLat.lng, lat: lngLat.lat };
    if (state.recording) {
      addTrackPoint(lngLat.lat, lngLat.lng, "map");
      return;
    }
    if (drawingBuilding()) return;      // drawn with press-drag-release
    if (state.mode === "bdDelete") {
      edit("deleteBuilding", where);
      return;
    }
    if (state.mode === "odAdd") {
      edit("addOd", { lon: where.lon, lat: where.lat, weight: 1, kind: "destination" });
      setStatus(t("odAdded"));
      return;
    }
    if (state.mode === "odDelete") {
      edit("deleteOd", where);
      setStatus(t("odDeleted"));
      return;
    }
    if (state.mode === "odWeight") {
      edit("weightOd", where);
      return;
    }
    if (state.showIso) {
      edit("isovist", where);
      return;
    }
    if (state.desc && state.desc.scale === "cluster") {
      const name = siteAt(event.point);
      const row = name && villageFor(name);
      if (row) loadScene(row.id);
      else if (name) setStatus(name + ": " + t("noVillage"));
    }
  }

  function onTool(id) {
    if (id === "path" || id === "facade" || id === "facadeO" || id === "traces" || id === "tracesO") {
      state.analysis = id;
      sendToggles();
      paintToolbar();
      return;
    }
    if (id === "odAdd" || id === "odDelete" || id === "odWeight"
        || id === "bdCircle" || id === "bdRect" || id === "bdDelete") {
      state.mode = state.mode === id ? null : id;
      cancelDraft();
      paintToolbar();
      updateMapInteraction();
      return;
    }
    if (id === "odSave") {
      worker.postMessage({ type: "export", purpose: "save" });
      return;
    }
    if (id === "export") {
      worker.postMessage({ type: "export", purpose: "download" });
      return;
    }
    if (id === "odLoad") {
      all("saves").then(function (rows) {
        const saved = rows.filter(function (item) { return item.id === state.sceneId; })[0];
        if (!saved) {
          setStatus(t("noSave"));
          return;
        }
        edit("applyGeometry", { geometry: saved.geometry });
        setStatus(t("opened") + " " + saved.saved.slice(0, 16).replace("T", " "));
      });
      return;
    }
    if (id === "speed") {
      const steps = [1, 2, 5, 10];
      const next = steps[(steps.indexOf(state.stepsPerTick) + 1) % steps.length];
      setSpeed(next);
      return;
    }
    if (id === "restart") {
      state.pulses = [];
      edit("restart", {});
      setStatus(t("restarted"));
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
      if (!state.showIso) {
        syncIso(null);
        worker.postMessage({ type: "setToggles", toggles: { isovist: false } });
      } else {
        setStatus(t("isoMode"));
      }
      paintToolbar();
      return;
    }
    if (id === "reset") {
      // X: back to the scene as packed. Edits saved with "save" stay stored.
      pause();
      if (state.recording) stopRecord();
        state.mode = null;
      state.showIso = false;
      syncIso(null);
      db().then(function (base) {
        base.transaction("saves", "readwrite").objectStore("saves").delete(state.sceneId);
      });
      edit("reset", {});
      setStatus(t("reset"));
      paintToolbar();
      updateMapInteraction();
    }
  }

  // ------------------------------------------------------------ offline pack
  function packFiles() {
    const files = ["index.json"];
    const index = state.index;
    if (index.basemap && index.basemap.file) files.push(index.basemap.file + "?v=" + index.build);
    index.scenes.forEach(function (row) {
      files.push(row.file + "?v=" + index.build);
      files.push(row.blob + "?v=" + index.build);
    });
    ["satellite", "osm"].forEach(function (kind) {
      const entries = (index.maps && index.maps[kind]) || {};
      Object.keys(entries).forEach(function (id) {
        files.push(entries[id].file + "?v=" + index.build);
      });
    });
    return files.map(function (name) { return PACK + name; });
  }

  function offlineState() {
    if (!window.caches || !state.index) return Promise.resolve(null);
    const urls = packFiles().concat(ENGINE_FILES);
    return caches.open(CACHE).then(function (cache) {
      return Promise.all(urls.map(function (url) { return cache.match(url); }));
    }).then(function (hits) {
      return { have: hits.filter(Boolean).length, total: urls.length };
    });
  }

  function showOffline() {
    offlineState().then(function (info) {
      const node = document.getElementById("offline-state");
      if (!info) {
        node.textContent = t("offlineNoCache");
        return;
      }
      node.textContent = info.have >= info.total
        ? t("offlineReady") + " (" + info.total + ")"
        : t("offlinePartial") + " " + info.have + " / " + info.total;
    });
  }

  function downloadAll() {
    if (!window.caches) {
      setStatus(t("offlineNoCache"));
      return;
    }
    const urls = packFiles().concat(ENGINE_FILES);
    const button = document.getElementById("offline-get");
    button.disabled = true;
    let done = 0;
    let failed = 0;
    caches.open(CACHE).then(function (cache) {
      // One at a time: a phone on a hotspot drops parallel 25 MB downloads.
      return urls.reduce(function (chain, url) {
        return chain.then(function () {
          return cache.match(url).then(function (hit) {
            if (hit) return null;
            return fetch(url).then(function (response) {
              if (!response.ok) throw new Error(url);
              return cache.put(url, response);
            });
          }).catch(function () { failed += 1; }).then(function () {
            done += 1;
            document.getElementById("offline-state").textContent =
              t("offlinePartial") + " " + done + " / " + urls.length;
          });
        });
      }, Promise.resolve());
    }).then(function () {
      button.disabled = false;
      if (failed) setStatus(t("offlineFailed") + " (" + failed + ")");
      showOffline();
    });
  }

  document.getElementById("lang").addEventListener("change", function (event) {
    state.lang = event.target.value;
    applyLanguage();
    if (state.desc) document.getElementById("blurb").textContent = t("packed");
    showOffline();
  });
  document.getElementById("scale-cluster").addEventListener("click", function () { loadScene("cluster"); });
  document.getElementById("site").addEventListener("change", function (event) {
    loadScene(event.target.value || "cluster");
  });
  ["chrono", "start", "end", "season", "opacity", "log", "cutoff"].forEach(function (id) {
    const notify = function () {
      if (id === "start" || id === "end") chronologyWindow();
      if (id === "opacity" || id === "log" || id === "cutoff") paint();
      else sendToggles();
    };
    document.getElementById(id).addEventListener("input", notify);
    document.getElementById(id).addEventListener("change", notify);
  });
  document.getElementById("agents").addEventListener("input", function (event) {
    document.getElementById("agents-out").textContent = event.target.value;
  });
  document.getElementById("agents").addEventListener("change", sendToggles);
  document.getElementById("undated").addEventListener("change", sendToggles);
  ["terrain-weight", "river-weight"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", function (event) {
      document.getElementById(id + "-out").textContent = "×" + event.target.value;
    });
    // every route is solved again, so only when the slider is let go
    document.getElementById(id).addEventListener("change", function () {
      setStatus(t("working"));
      sendToggles();
    });
  });
  document.getElementById("roads").addEventListener("change", syncOsm);
  function setSpeed(steps) {
    state.stepsPerTick = steps;
    document.getElementById("speed").value = String(steps);
    document.getElementById("speed-out").textContent = "×" + steps;
    document.getElementById("btn-speed").textContent = "⏩ ×" + steps;
  }
  document.getElementById("speed").addEventListener("input", function (event) {
    setSpeed(Number(event.target.value));
  });
  document.getElementById("panel-toggle").addEventListener("click", function (event) {
    const folded = document.getElementById("panel").classList.toggle("folded");
    event.currentTarget.setAttribute("aria-expanded", String(!folded));
    event.currentTarget.classList.toggle("active", !folded);
  });
  document.getElementById("btn-run").addEventListener("click", function () {
    if (state.playing) pause(); else play();
  });
  document.getElementById("btn-speed").addEventListener("click", function () { onTool("speed"); });
  document.getElementById("btn-reset").addEventListener("click", function () { onTool("restart"); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && state.draft) cancelDraft();
  });
  document.getElementById("low").addEventListener("change", function (event) {
    state.low = event.target.checked;
    if (state.playing) { pause(); play(); }
  });
  document.getElementById("tilt").addEventListener("input", function (event) {
    if (map) map.setPitch(Number(event.target.value));
  });
  document.getElementById("basemap").addEventListener("change", function (event) {
    setBasemap(event.target.value);
  });
  document.getElementById("offline-get").addEventListener("click", downloadAll);
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
  worker.postMessage({ type: "boot" });
  if (navigator.onLine) {
    fetch(window.location.origin + "/tiles/streets/0/0/0.png").then(function (response) {
      state.proxy = response.ok;
      setNet();
    }).catch(function () {});
  }

  Promise.all([
    // no-cache: always ask the server whether the pack changed (offline, the
    // service worker answers from its stored copy)
    fetch(PACK + "index.json", { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("index");
      return r.json();
    }),
    all("tracks").catch(function () { return []; }),
  ]).then(function (found) {
    state.index = found[0];
    if ((found[1] || []).length) state.track = found[1][found[1].length - 1];
    const select = document.getElementById("site");
    state.index.scenes.filter(function (row) { return row.scale === "village"; }).forEach(function (row) {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.label + (row.confidence && row.confidence !== "published" ? " (~)" : "");
      select.appendChild(option);
    });
    setNet();
    showOffline();
    loadScene(state.index.default || "cluster");
  }).catch(function () {
    setStatus(t("packMissing"));
  });
}());

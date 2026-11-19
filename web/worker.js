/* Runs pedsim itself on the device. The Python package is loaded into Pyodide
   and pedsim.live.LiveEngine rebuilds each packed scene as a real Simulation,
   then steps and edits it. Nothing in this file models an agent.

   If the runtime cannot start (very old browser, no memory) the worker says so
   and only hands back the packed description, so the map still shows the scene. */
let pyodide = null;
let command = null;      // Python: (name, json) -> snapshot dict
let loadScene = null;    // Python: (meta json, blob path) -> None
let exportGeometry = null;
let bootError = "";
let booted = null;
let meta = null;
let queue = Promise.resolve();

function status(phase, text) {
  self.postMessage({ type: "status", phase: phase, text: text || "" });
}

// Everything the model needs before it can start, about 17 MB. Each file is
// fetched here first, with retries, because a phone on a weak connection often
// drops one large download; Pyodide's own loader would give up on the first
// failure with nothing more than "Load failed". Once a file has arrived it is
// in the offline cache (or the browser cache), and Pyodide gets it from there.
const RUNTIME = "vendor/pyodide/";
const RUNTIME_FILES = [
  "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json",
  "numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl",
  "pyyaml-6.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl",
];

function wait(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function fetchWithRetry(url, options, label, tries) {
  let last = null;
  for (let attempt = 1; attempt <= tries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (response.ok) return response;
      last = new Error("HTTP " + response.status);
      if (response.status === 404) break;          // will not appear by waiting
    } catch (error) {
      last = error;
    }
    if (attempt < tries) {
      status("boot", label + " — retry " + attempt + " of " + (tries - 1));
      await wait(2000 * attempt);
    }
  }
  const reason = last && last.message ? last.message : String(last);
  throw new Error("could not download " + label + " (" + reason + ")");
}

function boot() {
  if (booted) return booted;
  booted = (async function () {
    for (let i = 0; i < RUNTIME_FILES.length; i++) {
      const name = RUNTIME_FILES[i];
      status("boot", "download " + (i + 1) + "/" + (RUNTIME_FILES.length + 1) + ": " + name);
      const response = await fetchWithRetry(RUNTIME + name, {}, name, 4);
      await response.arrayBuffer();               // read it to the end, so it is complete
    }
    status("boot", "Python runtime");
    importScripts(RUNTIME + "pyodide.js");
    pyodide = await loadPyodide({
      indexURL: new URL(RUNTIME, self.location.href).href,
    });
    status("boot", "numpy");
    await pyodide.loadPackage(["numpy", "pyyaml"]);
    status("boot", "pedsim");
    // The model code changes with every pack build, so it must never come from
    // an old copy: its address carries the page version, and the request asks
    // the server to confirm it is current.
    const version = new URL(self.location.href).searchParams.get("v") || "0";
    const response = await fetchWithRetry("vendor/pedsim.zip?v=" + version,
      { cache: "no-cache" }, "pedsim.zip", 4);
    pyodide.FS.mkdirTree("/app");
    pyodide.unpackArchive(await response.arrayBuffer(), "zip", { extractDir: "/app" });
    pyodide.runPython([
      "import sys, json",
      "sys.path.insert(0, '/app')",
      "from pedsim import live",
      "_engine = live.LiveEngine()",
      "def _load(meta_json, path, geometry_json, toggles_json):",
      "    blob = None",
      "    if path:",
      "        with open(path, 'rb') as fh:",
      "            blob = fh.read()",
      "    _engine.load(json.loads(meta_json), blob)",
      "    if geometry_json:",
      "        _engine.apply_geometry(json.loads(geometry_json))",
      "    if toggles_json:",
      "        _engine.set_toggles(json.loads(toggles_json))",
      "def _command(name, payload_json):",
      "    return _engine.command(name, json.loads(payload_json) if payload_json else None)",
      "def _export():",
      "    return json.dumps(_engine.export_geometry())",
    ].join("\n"));
    loadScene = pyodide.globals.get("_load");
    command = pyodide.globals.get("_command");
    exportGeometry = pyodide.globals.get("_export");
    status("ready", pyodide.version);
  }()).catch(function (error) {
    bootError = String(error && error.message ? error.message : error);
    status("failed", bootError);
  });
  return booted;
}

function sendFrame(snapshot, ms, steps) {
  const frame = snapshot.toJs({ dict_converter: Object.fromEntries });
  snapshot.destroy();
  // bytes arrive as Uint8Array views into copies; re-wrap with the right type
  const agents = new Float64Array(frame.agents.slice().buffer);
  const groups = frame.groups.slice();
  const ids = new Uint16Array(frame.ids.slice().buffer);
  const ages = new Uint16Array(frame.ages.slice().buffer);
  const field = new Float32Array(frame.field.slice().buffer);
  frame.agents = agents;
  frame.groups = groups;
  if (frame.walls) frame.walls = new Uint8ClampedArray(frame.walls.slice().buffer);
  if (frame.patches) {
    // fine patches of a nested scene, each with its own picture
    frame.patches.forEach(function (patch) {
      patch.field = new Float32Array(patch.field.slice().buffer);
    });
  }
  frame.ids = ids;
  frame.ages = ages;
  frame.field = field;
  frame.ms = ms;
  frame.steps = steps || 0;
  frame.live = true;
  self.postMessage(frame, [agents.buffer, groups.buffer, ids.buffer, ages.buffer, field.buffer]);
}

function fallbackFrame() {
  if (!meta) return;
  self.postMessage({
    type: "frame", live: false, scene: meta.id, step: 0, n_agents: 0,
    agents: new Float64Array(0), groups: new Uint8Array(0), ids: new Uint16Array(0), ages: new Uint16Array(0),
    field: new Float32Array(1), nx: 1, ny: 1, channels: 1, max: 0,
    analysis: "path", season: (meta.display && meta.display.season) || "normal",
    describe: meta.display, reason: bootError,
  });
}

function run(name, payload, steps) {
  if (!command) { fallbackFrame(); return; }
  const start = performance.now();
  const snapshot = command(name, payload ? JSON.stringify(payload) : "");
  sendFrame(snapshot, performance.now() - start, steps);
}

async function handle(msg) {
  if (msg.type === "boot") { await boot(); return; }
  if (msg.type === "loadScene") {
    meta = msg.meta;
    await boot();
    if (!command) { fallbackFrame(); return; }
    status("scene", meta.name);
    let path = "";
    if (msg.blobUrl) {
      const response = await fetch(msg.blobUrl);
      if (!response.ok) throw new Error("scene data missing: " + msg.blobUrl);
      path = "/tmp/scene.bin";
      pyodide.FS.writeFile(path, new Uint8Array(await response.arrayBuffer()));
    }
    const start = performance.now();
    loadScene(JSON.stringify(meta), path,
      msg.geometry ? JSON.stringify(msg.geometry) : "",
      msg.toggles ? JSON.stringify(msg.toggles) : "");
    if (path) pyodide.FS.unlink(path);
    status("loaded", meta.name + " · " + Math.round(performance.now() - start) + " ms");
    run("snapshot");
    return;
  }
  if (msg.type === "export") {
    if (!exportGeometry) return;
    self.postMessage({ type: "geometry", purpose: msg.purpose, data: JSON.parse(exportGeometry()) });
    return;
  }
  if (msg.type === "step") { run("step", { n: msg.n || 1 }, msg.n || 1); return; }
  if (msg.type === "setToggles") { run("toggles", msg.toggles || {}); return; }
  if (msg.type === "command") { run(msg.name, msg.payload || {}); return; }
}

self.onmessage = function (event) {
  const msg = event.data || {};
  queue = queue.then(function () { return handle(msg); }).catch(function (error) {
    self.postMessage({
      type: "error", text: String(error && error.message ? error.message : error),
    });
  });
};

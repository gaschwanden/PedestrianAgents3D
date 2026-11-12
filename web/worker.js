/* Playback of a pedsim pack. Season, chronology and phase choices select or
   reweight bands the Python model already wrote. Nothing here steps an agent. */
let scene = null;
const toggles = {
  chronology: true,
  startBc: 9500,
  endBc: 8000,
  season: "dry",
  phases: {},
  overrides: {},
  klass: "",
  task: "",
  stepIndex: 0,
};

function overlaps(phase) {
  return phase.end_bc <= toggles.startBc && phase.start_bc >= toggles.endBc;
}

function phaseOn(phase) {
  if (!toggles.chronology) return toggles.phases[phase.id] !== false;
  if (Object.prototype.hasOwnProperty.call(toggles.overrides, phase.id)) {
    return toggles.overrides[phase.id] === true;
  }
  return overlaps(phase);
}

function bandKey() {
  if (!scene || !scene.density) return "";
  const on = (scene.phases || []).filter(phaseOn).map(function (phase) { return phase.id; });
  if (on.length === 1 && scene.density[on[0]]) return on[0];
  if (scene.density.both) return "both";
  if (scene.density.cluster) return "cluster";
  const keys = Object.keys(scene.density);
  return keys.length ? keys[0] : "";
}

function seasonFactor() {
  const season = (scene.seasons || []).find(function (item) {
    return item.id === toggles.season || item.name === toggles.season;
  });
  return season ? season.event_factor : 1;
}

function seasonInfo() {
  return (scene.seasons || []).find(function (item) {
    return item.id === toggles.season || item.name === toggles.season;
  }) || null;
}

function snapshot() {
  if (!scene) return;
  const key = bandKey();
  const source = (key && scene.density[key]) || scene.density.both || [[0]];
  const factor = seasonFactor();
  const unsplit = Boolean(toggles.klass || toggles.task);
  const scale = factor * (unsplit ? 0.35 : 1);
  const rows = source.map(function (row) {
    return row.map(function (value) { return value * scale; });
  });
  const frames = (scene.frames && (scene.frames[key] || scene.frames.both || scene.frames.cluster)) || [];
  const frame = frames.length ? frames[toggles.stepIndex % frames.length] : [];
  let max = 0;
  rows.forEach(function (row) {
    row.forEach(function (value) { if (value > max) max = value; });
  });
  const season = seasonInfo();
  self.postMessage({
    type: "frame",
    rows: rows,
    agents: frame,
    step: toggles.stepIndex,
    max: max,
    key: key || "none",
    active: (scene.phases || []).filter(phaseOn).map(function (phase) { return phase.id; }),
    unsplit: unsplit,
    season: toggles.season,
    daylight: season ? season.daylight_minutes : null,
  });
}

self.onmessage = function (event) {
  const msg = event.data || {};
  if (msg.type === "loadScene") {
    scene = msg.scene;
    toggles.phases = {};
    toggles.stepIndex = 0;
    (scene.phases || []).forEach(function (phase) { toggles.phases[phase.id] = true; });
    if ((scene.seasons || []).length) toggles.season = scene.seasons[0].id;
    snapshot();
    return;
  }
  if (msg.type === "setToggles") {
    const next = msg.toggles || {};
    ["chronology", "startBc", "endBc", "season", "klass", "task", "phases", "overrides"]
      .forEach(function (key) {
        if (next[key] !== undefined) toggles[key] = next[key];
      });
    snapshot();
    return;
  }
  if (msg.type === "step") {
    toggles.stepIndex += msg.n || 1;
    snapshot();
    return;
  }
  if (msg.type === "reset") {
    toggles.stepIndex = 0;
    snapshot();
    return;
  }
  if (msg.type === "getDensity" || msg.type === "getAgents") snapshot();
};

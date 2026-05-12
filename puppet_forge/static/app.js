const state = {
  characters: [],
  scenes: [],
  providers: [],
  performances: [],
  renders: [],
  selectedCharacters: new Set(),
  selectedCharacterId: null,
  activePerformance: null,
  activeAudio: null,
  stage: null,
  busy: false,
};

const $ = (id) => document.getElementById(id);
const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

function setBusy(value) {
  state.busy = value;
  ["runShowButton", "generateButton", "voiceButton", "renderButton", "saveCharacterButton", "saveSettingsButton"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = value;
  });
}

async function loadState() {
  const data = await api("/api/state");
  Object.assign(state, {
    characters: data.characters,
    scenes: data.scenes,
    providers: data.providers,
    performances: data.performances,
    renders: data.renders,
  });
  if (!state.selectedCharacterId && state.characters[0]) state.selectedCharacterId = state.characters[0].id;
  if (state.selectedCharacters.size === 0) state.characters.slice(0, 2).forEach((character) => state.selectedCharacters.add(character.id));
  if (!state.activePerformance && state.performances[0]) state.activePerformance = state.performances[0];
  renderAll(data);
}

function renderAll(data = {}) {
  ensureStage();
  renderDoctor(data.doctor);
  renderProviders();
  renderCharacters();
  renderScenes();
  renderInspector();
  renderPlayback();
  renderTimeline();
  renderExports();
  syncStage();
}

function renderDoctor(doctor) {
  const info = doctor || {};
  $("healthText").textContent = `Python ${info.python || "ready"} | data local`;
  $("offlinePill").textContent = info.providers?.ollama_model ? `Local model: ${info.providers.ollama_model}` : "Local ready";
  $("ffmpegPill").textContent = info.ffmpeg ? "MP4 ready" : "Bundle export";
  $("doctorOutput").textContent = JSON.stringify(info, null, 2);
}

function renderProviders() {
  const providerSelect = $("providerSelect");
  const current = providerSelect.value;
  providerSelect.innerHTML = state.providers
    .map((provider) => `<option value="${provider.id}" ${provider.disabled ? "disabled" : ""}>${provider.name}</option>`)
    .join("");
  providerSelect.value = current || "local";
  const provider = state.providers.find((item) => item.id === providerSelect.value) || state.providers[0];
  $("modelInput").value = $("modelInput").value || provider?.models?.[0] || "local-scriptwright";
}

function renderCharacters() {
  $("characterList").innerHTML = state.characters
    .map((character) => {
      const active = character.id === state.selectedCharacterId ? "active" : "";
      const checked = state.selectedCharacters.has(character.id) ? "checked" : "";
      const body = character.rig?.body_color || "#b85f37";
      return `
        <div class="character-row ${active}" data-character="${character.id}">
          <div class="avatar-dot" style="background:${body}"></div>
          <div>
            <strong><input type="checkbox" ${checked} data-cast="${character.id}" aria-label="Use ${escapeHtml(character.name)}"> ${escapeHtml(character.name)}</strong>
            <span>${escapeHtml(character.role || "original performer")}</span>
          </div>
        </div>`;
    })
    .join("");
  document.querySelectorAll("[data-character]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.matches("input")) return;
      state.selectedCharacterId = row.dataset.character;
      renderInspector();
      renderCharacters();
      syncStage();
    });
  });
  document.querySelectorAll("[data-cast]").forEach((box) => {
    box.addEventListener("change", () => {
      if (box.checked) state.selectedCharacters.add(box.dataset.cast);
      else state.selectedCharacters.delete(box.dataset.cast);
      syncStage();
    });
  });
}

function renderScenes() {
  const select = $("sceneSelect");
  const current = select.value;
  select.innerHTML = state.scenes.map((scene) => `<option value="${scene.id}">${escapeHtml(scene.name)}</option>`).join("");
  if (current) select.value = current;
  const scene = selectedScene();
  $("sceneNotes").value = scene ? `${scene.setting}\n${scene.mood}\n${scene.lighting}` : "";
}

function renderInspector() {
  const character = state.characters.find((item) => item.id === state.selectedCharacterId);
  if (!character) return;
  $("charName").value = character.name || "";
  $("charRole").value = character.role || "";
  $("charLore").value = character.lore || "";
  $("charStyle").value = character.speech_style || "";
  $("charKindness").value = character.kindness ?? 0.65;
  $("charChaos").value = character.chaos ?? 0.25;
  $("voicePitch").value = character.voice?.base_frequency ?? 170;
  $("voicePace").value = character.voice?.pace ?? 1;
  $("voiceBrightness").value = character.voice?.brightness ?? 0.5;
  $("voiceGrit").value = character.voice?.grit ?? 0.12;
  $("voiceWarmth").value = character.voice?.warmth ?? 0.42;
  $("bodyColor").value = character.rig?.body_color || "#b85f37";
  $("accentColor").value = character.rig?.accent_color || "#ffd166";
}

function renderPlayback() {
  const audio = $("showAudio");
  const source = state.activeAudio?.wav_url || "";
  if (source && !audio.src.endsWith(source)) {
    audio.src = source;
    audio.load();
  } else if (!source) {
    audio.removeAttribute("src");
    audio.load();
  }
  $("activeCue").textContent = state.activeAudio ? "Ready to perform" : "Voice not generated yet";
}

function renderTimeline() {
  const perf = state.activePerformance;
  $("performanceTitle").textContent = perf ? perf.title : "No show generated yet";
  $("stageStatus").textContent = perf ? `${perf.provider} / ${perf.model}` : "Write a prompt, pick a cast, then run the show.";
  $("timelineMeta").textContent = perf ? `${perf.lines.length} lines` : "No lines yet";
  $("scriptLines").innerHTML = perf
    ? perf.lines
        .map(
          (line, index) =>
            `<div class="script-line" data-line-index="${index}"><strong>${escapeHtml(line.character_name)}</strong><span>${escapeHtml(line.text)}</span></div>`,
        )
        .join("")
    : "";
  renderWaveform();
}

function renderWaveform() {
  const words = state.activeAudio?.word_cues || [];
  const lines = state.activePerformance?.lines || [];
  const bars = words.length ? Math.min(90, Math.max(28, words.length)) : Math.max(24, lines.length * 12 || 28);
  $("waveform").innerHTML = Array.from({ length: bars }, (_, index) => {
    const word = words[index % Math.max(1, words.length)];
    const span = word ? Math.max(0.04, word.end - word.start) : 0.08 + ((index * 11) % 10) / 100;
    const h = Math.round(14 + clamp(span * 120, 4, 34) + ((index * 17) % 10));
    return `<div class="bar" data-wave-index="${index}" style="height:${h}px"></div>`;
  }).join("");
}

function renderExports() {
  const items = state.renders || [];
  $("exportList").innerHTML = items.length
    ? items
        .map((render) => {
          const links = [
            render.html_url ? `<a href="${render.html_url}" target="_blank">Preview</a>` : "",
            render.wav_url ? `<a href="${render.wav_url}" target="_blank">WAV</a>` : "",
            render.mp4_url ? `<a href="${render.mp4_url}" target="_blank">MP4</a>` : "",
            render.preview_svg_url ? `<a href="${render.preview_svg_url}" target="_blank">Stage SVG</a>` : "",
            render.manifest_url ? `<a href="${render.manifest_url}" target="_blank">Manifest</a>` : "",
            render.package_url ? `<a href="${render.package_url}" target="_blank">ZIP</a>` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `<div class="export-item"><strong>${escapeHtml(render.status)}</strong><span>${escapeHtml(render.message || "")}</span><div>${links}</div></div>`;
        })
        .join("")
    : `<p class="quiet">Rendered shows will appear here.</p>`;
}

function activeCast() {
  const selected = state.characters.filter((character) => state.selectedCharacters.has(character.id));
  return selected.length ? selected : state.characters.slice(0, 2);
}

function selectedScene() {
  return state.scenes.find((scene) => scene.id === $("sceneSelect").value) || state.scenes[0] || {};
}

function selectedSceneId() {
  return $("sceneSelect").value || state.scenes[0]?.id;
}

function ensureStage() {
  if (state.stage || !window.PuppetStage) return;
  const audio = $("showAudio");
  state.stage = window.PuppetStage.create($("stageCanvas"), { onFrame: updateActiveFrame });
  state.stage.setAudioElement(audio);
  audio.addEventListener("play", () => state.stage?.draw());
  audio.addEventListener("seeked", () => state.stage?.draw());
}

function showPayload() {
  return {
    characters: state.activePerformance ? state.characters : activeCast(),
    scene: selectedScene(),
    performance: state.activePerformance,
    audio: state.activeAudio,
  };
}

function syncStage() {
  ensureStage();
  state.stage?.setShow(showPayload());
}

function updateActiveFrame(frame) {
  const activeIndex = frame?.activeLine?.index;
  document.querySelectorAll(".script-line").forEach((line) => {
    line.classList.toggle("active", activeIndex !== undefined && Number(line.dataset.lineIndex) === activeIndex);
  });
  if (frame?.activeWord) {
    $("activeCue").textContent = `${frame.activeWord.character_name}: ${frame.activeWord.word}`;
  } else if (frame?.activeLine) {
    $("activeCue").textContent = `${frame.activeLine.character_name}`;
  } else if (state.activeAudio) {
    $("activeCue").textContent = "Ready to perform";
  }
}

async function generatePerformance() {
  toast("Forging script...");
  const data = await api("/api/performances/generate", {
    method: "POST",
    body: JSON.stringify({
      prompt: $("promptInput").value,
      character_ids: [...state.selectedCharacters],
      scene_id: selectedSceneId(),
      provider: $("providerSelect").value,
      model: $("modelInput").value,
      temperature: Number($("temperatureInput").value),
      fallback_local: true,
    }),
  });
  state.activePerformance = data.performance;
  state.performances.unshift(data.performance);
  state.activeAudio = null;
  renderPlayback();
  renderTimeline();
  syncStage();
  toast("Script forged.");
  return data.performance;
}

async function makeVoice() {
  if (!state.activePerformance) await generatePerformance();
  toast("Synthesizing local voice...");
  const data = await api("/api/audio", {
    method: "POST",
    body: JSON.stringify({ performance_id: state.activePerformance.id }),
  });
  state.activeAudio = data.audio;
  renderPlayback();
  renderTimeline();
  syncStage();
  toast("Voice ready.");
  return data.audio;
}

async function renderShow() {
  if (!state.activePerformance) await generatePerformance();
  if (!state.activeAudio) await makeVoice();
  toast("Rendering local show bundle...");
  const data = await api("/api/render", {
    method: "POST",
    body: JSON.stringify({ performance_id: state.activePerformance.id, fps: 8 }),
  });
  state.renders.unshift(data.render);
  renderExports();
  toast(data.render.mp4_url ? "MP4 ready." : "Render bundle ready.");
  return data.render;
}

async function runShow() {
  setBusy(true);
  try {
    await generatePerformance();
    await makeVoice();
    await $("showAudio").play().catch(() => undefined);
    await renderShow();
  } finally {
    setBusy(false);
  }
}

async function guarded(action) {
  setBusy(true);
  try {
    await action();
  } finally {
    setBusy(false);
  }
}

async function saveCharacter() {
  const current = state.characters.find((character) => character.id === state.selectedCharacterId) || {};
  const payload = {
    ...current,
    name: $("charName").value,
    role: $("charRole").value,
    lore: $("charLore").value,
    speech_style: $("charStyle").value,
    kindness: Number($("charKindness").value),
    chaos: Number($("charChaos").value),
    traits: current.traits || ["original"],
    emotional_range: current.emotional_range || 0.7,
    voice: {
      ...(current.voice || {}),
      id: current.voice?.id || `voice-${crypto.randomUUID()}`,
      name: current.voice?.name || `${$("charName").value} Voice`,
      base_frequency: Number($("voicePitch").value),
      pace: Number($("voicePace").value),
      brightness: Number($("voiceBrightness").value),
      grit: Number($("voiceGrit").value),
      warmth: Number($("voiceWarmth").value),
      formality: current.voice?.formality ?? 0.5,
    },
    rig: {
      ...(current.rig || {}),
      id: current.rig?.id || `rig-${crypto.randomUUID()}`,
      name: current.rig?.name || `${$("charName").value} Rig`,
      body_color: $("bodyColor").value,
      accent_color: $("accentColor").value,
      eye_color: current.rig?.eye_color || "#f7fbff",
      mouth_color: current.rig?.mouth_color || "#171219",
      silhouette: current.rig?.silhouette || "rounded",
      scale: current.rig?.scale || 1,
    },
  };
  const data = await api("/api/characters", { method: "POST", body: JSON.stringify(payload) });
  const index = state.characters.findIndex((character) => character.id === data.character.id);
  if (index >= 0) state.characters[index] = data.character;
  else state.characters.push(data.character);
  state.selectedCharacterId = data.character.id;
  state.selectedCharacters.add(data.character.id);
  renderAll();
  toast("Character saved.");
}

async function saveSettings() {
  const payload = {
    OPENAI_API_KEY: $("openaiKey").value,
    ANTHROPIC_API_KEY: $("anthropicKey").value,
    GEMINI_API_KEY: $("geminiKey").value,
    OLLAMA_HOST: $("ollamaHost").value,
    OLLAMA_MODEL: $("ollamaModel").value,
  };
  const data = await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
  renderDoctor(data.doctor);
  toast("Settings saved locally.");
}

function newCharacter() {
  state.selectedCharacterId = null;
  $("charName").value = "New Performer";
  $("charRole").value = "original puppet performer";
  $("charLore").value = "A new character built inside Punch or Judy Studios.";
  $("charStyle").value = "clear, vivid, performable";
  $("charKindness").value = 0.65;
  $("charChaos").value = 0.25;
  $("voicePitch").value = 175;
  $("voicePace").value = 1;
  $("voiceBrightness").value = 0.5;
  $("voiceGrit").value = 0.12;
  $("voiceWarmth").value = 0.42;
  $("bodyColor").value = "#b85f37";
  $("accentColor").value = "#ffd166";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bind() {
  $("runShowButton").addEventListener("click", () => runShow().catch((error) => toast(error.message)));
  $("generateButton").addEventListener("click", () => guarded(generatePerformance).catch((error) => toast(error.message)));
  $("voiceButton").addEventListener("click", () => guarded(makeVoice).catch((error) => toast(error.message)));
  $("renderButton").addEventListener("click", () => guarded(renderShow).catch((error) => toast(error.message)));
  $("saveCharacterButton").addEventListener("click", () => guarded(saveCharacter).catch((error) => toast(error.message)));
  $("saveSettingsButton").addEventListener("click", () => guarded(saveSettings).catch((error) => toast(error.message)));
  $("newCharacterButton").addEventListener("click", newCharacter);
  $("providerSelect").addEventListener("change", () => {
    const provider = state.providers.find((item) => item.id === $("providerSelect").value);
    $("modelInput").value = provider?.models?.[0] || "";
  });
  $("sceneSelect").addEventListener("change", () => {
    renderScenes();
    syncStage();
  });
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".inspector-tab").forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      $(`${tab.dataset.tab}Tab`).classList.add("active");
    });
  });
}

bind();
loadState().catch((error) => toast(error.message));

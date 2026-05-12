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
  startedAt: performance.now(),
  animationStarted: false,
};

const $ = (id) => document.getElementById(id);

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
  if (state.selectedCharacters.size === 0) state.characters.slice(0, 2).forEach((c) => state.selectedCharacters.add(c.id));
  if (!state.activePerformance && state.performances[0]) state.activePerformance = state.performances[0];
  renderAll(data);
}

function renderAll(data = {}) {
  renderDoctor(data.doctor);
  renderProviders();
  renderCharacters();
  renderScenes();
  renderInspector();
  renderTimeline();
  renderExports();
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
  providerSelect.innerHTML = state.providers
    .map((p) => `<option value="${p.id}" ${p.disabled ? "disabled" : ""}>${p.name}</option>`)
    .join("");
  providerSelect.value = providerSelect.value || "local";
  const provider = state.providers.find((p) => p.id === providerSelect.value) || state.providers[0];
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
      renderAll();
    });
  });
  document.querySelectorAll("[data-cast]").forEach((box) => {
    box.addEventListener("change", () => {
      if (box.checked) state.selectedCharacters.add(box.dataset.cast);
      else state.selectedCharacters.delete(box.dataset.cast);
      drawStage();
    });
  });
}

function renderScenes() {
  const select = $("sceneSelect");
  const current = select.value;
  select.innerHTML = state.scenes.map((scene) => `<option value="${scene.id}">${escapeHtml(scene.name)}</option>`).join("");
  if (current) select.value = current;
  const scene = state.scenes.find((s) => s.id === select.value) || state.scenes[0];
  $("sceneNotes").value = scene ? `${scene.setting}\n${scene.mood}\n${scene.lighting}` : "";
}

function renderInspector() {
  const character = state.characters.find((c) => c.id === state.selectedCharacterId);
  if (!character) return;
  $("charName").value = character.name || "";
  $("charRole").value = character.role || "";
  $("charLore").value = character.lore || "";
  $("charStyle").value = character.speech_style || "";
  $("charKindness").value = character.kindness ?? 0.65;
  $("charChaos").value = character.chaos ?? 0.25;
  $("voicePitch").value = character.voice?.base_frequency ?? 170;
  $("voicePace").value = character.voice?.pace ?? 1;
  $("bodyColor").value = character.rig?.body_color || "#b85f37";
  $("accentColor").value = character.rig?.accent_color || "#ffd166";
}

function renderTimeline() {
  const perf = state.activePerformance;
  $("performanceTitle").textContent = perf ? perf.title : "No show generated yet";
  $("stageStatus").textContent = perf ? `${perf.provider} / ${perf.model}` : "Write a prompt, pick a cast, then forge the scene.";
  $("timelineMeta").textContent = perf ? `${perf.lines.length} lines` : "No lines yet";
  $("scriptLines").innerHTML = perf
    ? perf.lines
        .map(
          (line) =>
            `<div class="script-line"><strong>${escapeHtml(line.character_name)}</strong><span>${escapeHtml(line.text)}</span></div>`,
        )
        .join("")
    : "";
  const bars = perf ? Math.max(24, perf.lines.length * 12) : 28;
  $("waveform").innerHTML = Array.from({ length: bars }, (_, i) => {
    const h = perf ? 18 + ((i * 17 + perf.lines.length * 9) % 26) : 8 + ((i * 11) % 12);
    return `<div class="bar" style="height:${h}px"></div>`;
  }).join("");
  drawStage();
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
  const selected = state.characters.filter((c) => state.selectedCharacters.has(c.id));
  return selected.length ? selected : state.characters.slice(0, 2);
}

function drawStage() {
  if (state.animationStarted) return;
  state.animationStarted = true;
  animateStage();
}

function animateStage() {
  const canvas = $("stageCanvas");
  const ctx = canvas.getContext("2d");
  const time = (performance.now() - state.startedAt) / 1000;
  const scene = state.scenes.find((s) => s.id === $("sceneSelect").value) || state.scenes[0] || {};
  const night = /night|quiet/i.test(scene.mood || "");
  const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
  grad.addColorStop(0, night ? "#121d35" : "#23212a");
  grad.addColorStop(1, night ? "#33293b" : "#563825");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  spot(ctx, 300, 230, 210, "rgba(255,214,142,.14)");
  spot(ctx, 660, 230, 210, "rgba(104,195,192,.11)");
  ctx.fillStyle = "#5a3928";
  ctx.fillRect(0, 388, canvas.width, 152);
  ctx.fillStyle = "rgba(0,0,0,.25)";
  ctx.fillRect(0, 388, canvas.width, 16);
  const cast = activeCast().slice(0, 3);
  const positions = [
    [330, 318],
    [630, 318],
    [480, 334],
  ];
  cast.forEach((character, index) => {
    const viseme = currentViseme(character.id, time);
    drawPuppet(ctx, character, positions[index][0], positions[index][1], index < 2 ? 0.86 : 0.72, time, viseme, index);
  });
  requestAnimationFrame(animateStage);
}

function currentViseme(characterId, time) {
  const events = state.activeAudio?.visemes || [];
  const duration = state.activeAudio?.duration_seconds || 0;
  const t = duration ? time % duration : time % 2;
  const hit = events.find((e) => e.character_id === characterId && e.start <= t && e.end >= t);
  return hit?.viseme || "rest";
}

function spot(ctx, x, y, r, color) {
  const g = ctx.createRadialGradient(x, y, 20, x, y, r);
  g.addColorStop(0, color);
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(x - r, y - r, r * 2, r * 2);
}

function drawPuppet(ctx, character, x, y, scale, time, viseme, side) {
  const rig = character.rig || {};
  const body = rig.body_color || "#b85f37";
  const accent = rig.accent_color || "#ffd166";
  const mouth = rig.mouth_color || "#171219";
  const bob = Math.sin(time * 4 + side) * 6;
  const sway = Math.sin(time * 2.2 + side) * 8;
  x += sway;
  y += bob;
  const s = scale;
  ctx.save();
  ctx.lineCap = "round";
  ctx.fillStyle = "rgba(0,0,0,.35)";
  ellipse(ctx, x, y + 142 * s, 82 * s, 18 * s);
  ctx.strokeStyle = accent;
  ctx.globalAlpha = 0.58;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(x, 42);
  ctx.lineTo(x, y - 78 * s);
  ctx.stroke();
  ctx.globalAlpha = 1;
  ctx.fillStyle = body;
  ellipse(ctx, x, y + 80 * s, 74 * s, 98 * s);
  ellipse(ctx, x, y - 38 * s, 72 * s, 66 * s);
  ctx.fillStyle = accent;
  ellipse(ctx, x - 20 * s, y - 78 * s, 24 * s, 16 * s);
  ellipse(ctx, x + 20 * s, y - 78 * s, 24 * s, 16 * s);
  ctx.fillStyle = "#f8fbff";
  ellipse(ctx, x - 24 * s, y - 48 * s, 12 * s, 16 * s);
  ellipse(ctx, x + 24 * s, y - 48 * s, 12 * s, 16 * s);
  ctx.fillStyle = "#0c0e14";
  const look = Math.sin(time * 3) * 3;
  ellipse(ctx, x - 24 * s + look, y - 46 * s, 5 * s, 7 * s);
  ellipse(ctx, x + 24 * s + look, y - 46 * s, 5 * s, 7 * s);
  ctx.fillStyle = mouth;
  if (viseme === "closed") rect(ctx, x - 22 * s, y - 12 * s, 44 * s, 6 * s);
  else if (viseme === "wide") ellipse(ctx, x, y - 8 * s, 34 * s, 10 * s);
  else if (viseme === "round") ellipse(ctx, x, y - 8 * s, 17 * s, 22 * s);
  else if (viseme === "open") ellipse(ctx, x, y - 8 * s, 25 * s, 28 * s);
  else if (viseme === "teeth") {
    ellipse(ctx, x, y - 8 * s, 28 * s, 13 * s);
    ctx.fillStyle = "#f5eedc";
    rect(ctx, x - 20 * s, y - 14 * s, 40 * s, 6 * s);
  } else ellipse(ctx, x, y - 8 * s, 22 * s, 6 * s);
  ctx.fillStyle = body;
  ellipse(ctx, x - 78 * s, y + 36 * s, 22 * s, 48 * s);
  ellipse(ctx, x + 78 * s, y + 36 * s, 22 * s, 48 * s);
  ctx.fillStyle = accent;
  ellipse(ctx, x - 82 * s, y + 82 * s, 18 * s, 16 * s);
  ellipse(ctx, x + 82 * s, y + 82 * s, 18 * s, 16 * s);
  ctx.fillStyle = "#fff5dd";
  ctx.font = `700 ${24 * s}px Segoe UI, Arial`;
  ctx.textAlign = "center";
  ctx.fillText(character.name, x, y + 190 * s);
  ctx.restore();
}

function ellipse(ctx, x, y, rx, ry) {
  ctx.beginPath();
  ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
}

function rect(ctx, x, y, w, h) {
  ctx.fillRect(x, y, w, h);
}

function selectedSceneId() {
  return $("sceneSelect").value || state.scenes[0]?.id;
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
  renderAll();
  toast("Script forged.");
}

async function makeVoice() {
  if (!state.activePerformance) await generatePerformance();
  toast("Synthesizing local voice...");
  const data = await api("/api/audio", {
    method: "POST",
    body: JSON.stringify({ performance_id: state.activePerformance.id }),
  });
  state.activeAudio = data.audio;
  renderTimeline();
  toast("Voice ready.");
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
}

async function saveCharacter() {
  const current = state.characters.find((c) => c.id === state.selectedCharacterId) || {};
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
      brightness: current.voice?.brightness ?? 0.5,
      grit: current.voice?.grit ?? 0.12,
      warmth: current.voice?.warmth ?? 0.42,
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
  const index = state.characters.findIndex((c) => c.id === data.character.id);
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
  $("charLore").value = "A new character built inside Puppet Forge.";
  $("charStyle").value = "clear, vivid, performable";
  $("charKindness").value = 0.65;
  $("charChaos").value = 0.25;
  $("voicePitch").value = 175;
  $("voicePace").value = 1;
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
  $("generateButton").addEventListener("click", () => generatePerformance().catch((e) => toast(e.message)));
  $("voiceButton").addEventListener("click", () => makeVoice().catch((e) => toast(e.message)));
  $("renderButton").addEventListener("click", () => renderShow().catch((e) => toast(e.message)));
  $("saveCharacterButton").addEventListener("click", () => saveCharacter().catch((e) => toast(e.message)));
  $("saveSettingsButton").addEventListener("click", () => saveSettings().catch((e) => toast(e.message)));
  $("newCharacterButton").addEventListener("click", newCharacter);
  $("providerSelect").addEventListener("change", () => {
    const provider = state.providers.find((p) => p.id === $("providerSelect").value);
    $("modelInput").value = provider?.models?.[0] || "";
  });
  $("sceneSelect").addEventListener("change", renderScenes);
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
loadState().catch((e) => toast(e.message));

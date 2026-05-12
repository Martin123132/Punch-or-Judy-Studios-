(function () {
  const BASE_WIDTH = 960;
  const BASE_HEIGHT = 540;
  const DEFAULT_RIG = {
    body_color: "#b85f37",
    accent_color: "#ffd166",
    eye_color: "#f7fbff",
    mouth_color: "#171219",
    silhouette: "rounded",
    scale: 1,
  };

  function clamp(value, lo, hi) {
    return Math.max(lo, Math.min(hi, value));
  }

  function ellipse(ctx, x, y, rx, ry, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  function rect(ctx, x, y, w, h, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
  }

  function line(ctx, x1, y1, x2, y2, color, width, alpha = 1) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }

  function spot(ctx, x, y, rx, ry, color, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;
    const g = ctx.createRadialGradient(x, y, 20, x, y, Math.max(rx, ry));
    g.addColorStop(0, color);
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function activeLine(audio, t) {
    return (audio?.line_cues || []).find((cue) => cue.start <= t && cue.end >= t) || null;
  }

  function activeWord(audio, t, characterId) {
    return (
      (audio?.word_cues || []).find((cue) => cue.character_id === characterId && cue.start <= t && cue.end >= t) ||
      null
    );
  }

  function activeViseme(audio, t, characterId) {
    const hit = (audio?.visemes || []).find((event) => event.character_id === characterId && event.start <= t && event.end >= t);
    return hit?.viseme || "rest";
  }

  function castFor(show) {
    const characters = show.characters || [];
    const byId = new Map(characters.map((character) => [character.id, character]));
    const ids = [];
    for (const lineItem of show.performance?.lines || []) {
      if (!ids.includes(lineItem.character_id)) ids.push(lineItem.character_id);
    }
    if (!ids.length) characters.slice(0, 3).forEach((character) => ids.push(character.id));
    return ids.slice(0, 3).map((id) => {
      const fallbackLine = (show.performance?.lines || []).find((lineItem) => lineItem.character_id === id);
      return byId.get(id) || {
        id,
        name: fallbackLine?.character_name || "Performer",
        rig: DEFAULT_RIG,
        voice: {},
      };
    });
  }

  function positionFor(index, count) {
    if (count === 1) return [480, 326];
    if (count === 2) return index === 0 ? [340, 320] : [620, 320];
    return [
      [290, 322],
      [670, 322],
      [480, 340],
    ][index];
  }

  function emotionMotion(emotion) {
    const value = String(emotion || "steady").toLowerCase();
    if (value === "playful") return { bounce: 1.35, sway: 1.25, gesture: 1.35 };
    if (value === "bright") return { bounce: 1.22, sway: 1.0, gesture: 1.18 };
    if (value === "careful") return { bounce: 0.62, sway: 0.7, gesture: 0.64 };
    if (value === "curious") return { bounce: 0.9, sway: 1.15, gesture: 0.92 };
    if (value === "bold") return { bounce: 1.0, sway: 0.82, gesture: 1.5 };
    if (value === "gentle") return { bounce: 0.72, sway: 0.72, gesture: 0.72 };
    return { bounce: 1, sway: 1, gesture: 1 };
  }

  function drawArm(ctx, x, y, s, side, body, accent, gesture, active) {
    const dir = side < 0 ? -1 : 1;
    const angle = dir * (0.32 + gesture * 0.52 + (active ? 0.12 : 0));
    const shoulderX = x + dir * 62 * s;
    const shoulderY = y + 36 * s;
    ctx.save();
    ctx.translate(shoulderX, shoulderY);
    ctx.rotate(angle);
    ellipse(ctx, dir * 18 * s, 30 * s, 17 * s, 48 * s, body);
    ellipse(ctx, dir * 24 * s, 76 * s, 16 * s, 15 * s, accent);
    ctx.restore();
  }

  function drawMouth(ctx, x, y, s, viseme, mouth) {
    if (viseme === "closed") rect(ctx, x - 22 * s, y - 12 * s, 44 * s, 6 * s, mouth);
    else if (viseme === "wide") ellipse(ctx, x, y - 8 * s, 34 * s, 10 * s, mouth);
    else if (viseme === "round") ellipse(ctx, x, y - 8 * s, 17 * s, 22 * s, mouth);
    else if (viseme === "open") ellipse(ctx, x, y - 8 * s, 25 * s, 28 * s, mouth);
    else if (viseme === "teeth") {
      ellipse(ctx, x, y - 8 * s, 28 * s, 13 * s, mouth);
      rect(ctx, x - 20 * s, y - 14 * s, 40 * s, 6 * s, "#f5eedc");
    } else {
      ellipse(ctx, x, y - 8 * s, 22 * s, 6 * s, mouth);
    }
  }

  function drawEyes(ctx, x, y, s, rig, time, active, side) {
    const blinkPhase = (time * 0.72 + side * 0.19) % 4.8;
    const blinking = blinkPhase > 4.65;
    const look = active ? 0 : Math.sin(time * 2.4 + side) * 4;
    const eye = rig.eye_color || "#f7fbff";
    if (blinking) {
      line(ctx, x - 36 * s, y - 48 * s, x - 14 * s, y - 48 * s, "#10141d", 4 * s);
      line(ctx, x + 14 * s, y - 48 * s, x + 36 * s, y - 48 * s, "#10141d", 4 * s);
      return;
    }
    ellipse(ctx, x - 24 * s, y - 48 * s, 12 * s, 16 * s, eye);
    ellipse(ctx, x + 24 * s, y - 48 * s, 12 * s, 16 * s, eye);
    ellipse(ctx, x - 24 * s + look, y - 46 * s, 5 * s, 7 * s, "#0c0e14");
    ellipse(ctx, x + 24 * s + look, y - 46 * s, 5 * s, 7 * s, "#0c0e14");
  }

  function drawPuppet(ctx, character, index, count, show, t, activeCue) {
    const rig = { ...DEFAULT_RIG, ...(character.rig || {}) };
    const [baseX, baseY] = positionFor(index, count);
    const isActive = activeCue?.character_id === character.id;
    const emotion = isActive ? activeCue?.emotion : "steady";
    const motion = emotionMotion(emotion);
    const word = activeWord(show.audio, t, character.id);
    const wordProgress = word ? clamp((t - word.start) / Math.max(0.001, word.end - word.start), 0, 1) : 0;
    const wordPulse = word ? Math.sin(wordProgress * Math.PI) : 0;
    const activeLift = isActive ? 16 : 0;
    const s = (index < 2 ? 0.9 : 0.78) * (rig.scale || 1) * (isActive ? 1.06 : 1);
    const x = baseX + Math.sin(t * 2.1 + index) * 8 * motion.sway;
    const y = baseY + Math.sin(t * 4.0 + index) * 6 * motion.bounce - activeLift;
    const body = rig.body_color || DEFAULT_RIG.body_color;
    const accent = rig.accent_color || DEFAULT_RIG.accent_color;
    const mouth = rig.mouth_color || DEFAULT_RIG.mouth_color;
    const viseme = activeViseme(show.audio, t, character.id);
    const gesture = wordPulse * motion.gesture;

    ellipse(ctx, x, y + 142 * s, 84 * s, 18 * s, "rgba(0,0,0,.35)");
    line(ctx, x - 28 * s, 42, x - 22 * s, y - 74 * s, accent, 3, 0.52);
    line(ctx, x + 28 * s, 42, x + 22 * s, y - 74 * s, accent, 3, 0.52);
    line(ctx, x, 34, x, y - 92 * s, accent, 4, 0.62);
    ellipse(ctx, x, y + 80 * s, 74 * s, 98 * s, body);
    ellipse(ctx, x, y - 38 * s, 72 * s, 66 * s, body);
    ellipse(ctx, x - 20 * s, y - 78 * s, 24 * s, 16 * s, accent);
    ellipse(ctx, x + 20 * s, y - 78 * s, 24 * s, 16 * s, accent);
    drawEyes(ctx, x, y, s, rig, t, isActive, index);
    drawMouth(ctx, x, y, s, viseme, mouth);
    drawArm(ctx, x, y, s, -1, body, accent, gesture, isActive);
    drawArm(ctx, x, y, s, 1, body, accent, gesture * 0.7, isActive);
    ctx.save();
    ctx.fillStyle = isActive ? "#fff7df" : "#dfe5ef";
    ctx.font = `700 ${Math.round(22 * s)}px Segoe UI, Arial`;
    ctx.textAlign = "center";
    ctx.shadowColor = "rgba(0,0,0,.55)";
    ctx.shadowBlur = 7;
    ctx.fillText(character.name, x, y + 190 * s);
    ctx.restore();
  }

  function drawStage(ctx, show, t) {
    const scene = show.scene || {};
    const activeCue = activeLine(show.audio, t);
    const night = /night|quiet|moon/i.test(`${scene.mood || ""} ${scene.lighting || ""}`);
    const grad = ctx.createLinearGradient(0, 0, 0, BASE_HEIGHT);
    grad.addColorStop(0, night ? "#111b33" : "#23212a");
    grad.addColorStop(0.62, night ? "#25243a" : "#382b28");
    grad.addColorStop(1, night ? "#352a3f" : "#5a3928");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, BASE_WIDTH, BASE_HEIGHT);
    const emotion = activeCue?.emotion || "steady";
    const warmAlpha = emotion === "bright" || emotion === "playful" ? 0.19 : 0.13;
    const coolAlpha = emotion === "careful" || emotion === "curious" ? 0.15 : 0.1;
    spot(ctx, 290, 230, 230, 320, "#ffd68e", warmAlpha);
    spot(ctx, 670, 230, 230, 320, "#78c9e8", coolAlpha);
    if (activeCue) {
      const cast = castFor(show);
      const activeIndex = cast.findIndex((character) => character.id === activeCue.character_id);
      if (activeIndex >= 0) {
        const [x] = positionFor(activeIndex, cast.length);
        spot(ctx, x, 260, 180, 280, "#fff3c5", 0.14);
      }
    }
    rect(ctx, 0, 388, BASE_WIDTH, 152, "#5a3928");
    rect(ctx, 0, 388, BASE_WIDTH, 16, "rgba(0,0,0,.25)");
    for (let y = 408; y < 540; y += 28) {
      line(ctx, 0, y, BASE_WIDTH, y - 18, "rgba(255,255,255,.035)", 1);
    }
    const cast = castFor(show);
    cast.forEach((character, index) => drawPuppet(ctx, character, index, cast.length, show, t, activeCue));
    return {
      activeLine: activeCue,
      activeWord: activeCue ? activeWord(show.audio, t, activeCue.character_id) : null,
      time: t,
    };
  }

  class StageController {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.options = options;
      this.show = { characters: [], scene: {}, performance: null, audio: null };
      this.audioElement = null;
      this.startedAt = performance.now();
      this.running = false;
      this.lastFrame = null;
    }

    setShow(show) {
      this.show = {
        characters: show.characters || [],
        scene: show.scene || {},
        performance: show.performance || null,
        audio: show.audio || null,
      };
      this.draw();
    }

    setAudioElement(audioElement) {
      this.audioElement = audioElement;
    }

    currentTime() {
      const duration = Number(this.show.audio?.duration_seconds || 0);
      if (this.audioElement && this.show.audio) {
        return clamp(Number(this.audioElement.currentTime || 0), 0, Math.max(0, duration));
      }
      const idle = (performance.now() - this.startedAt) / 1000;
      return duration ? idle % duration : idle;
    }

    draw() {
      const width = this.canvas.width || BASE_WIDTH;
      const height = this.canvas.height || BASE_HEIGHT;
      this.ctx.save();
      this.ctx.clearRect(0, 0, width, height);
      this.ctx.scale(width / BASE_WIDTH, height / BASE_HEIGHT);
      this.lastFrame = drawStage(this.ctx, this.show, this.currentTime());
      this.ctx.restore();
      if (typeof this.options.onFrame === "function") this.options.onFrame(this.lastFrame);
      return this.lastFrame;
    }

    start() {
      if (this.running) return;
      this.running = true;
      const tick = () => {
        if (!this.running) return;
        this.draw();
        requestAnimationFrame(tick);
      };
      tick();
    }

    stop() {
      this.running = false;
    }
  }

  window.PuppetStage = {
    create(canvas, options) {
      const stage = new StageController(canvas, options);
      stage.start();
      return stage;
    },
  };
})();

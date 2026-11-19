// Interaktives Frontend für das SIMALITÄT Ökosystem-Observatorium
(function () {
  "use strict";

  const state = {
    meta: null,
    payload: null,
    scrubT: null,      // null => live letzter Frame
    compareMode: false,
    t1: 0,
    t2: 0,
    diffData: null,
    selectedId: "SOIL_TERRACE_SOUTH",
    selectedEventId: null,
    hitboxes: [],
    rainParticles: Array.from({ length: 85 }, () => ({
      x: Math.random(), y: Math.random(), len: 8 + Math.random() * 12, spd: 0.7 + Math.random() * 0.6,
    })),
    pollTimer: null,
  };

  const els = {
    canvas: document.getElementById("worldCanvas"),
    popOverlay: document.getElementById("popOverlay"),
    tooltip: document.getElementById("canvasTooltip"),
    selScenario: document.getElementById("selScenario"),
    selSeason: document.getElementById("selSeason"),
    inpSeed: document.getElementById("inpSeed"),
    btnPlayPause: document.getElementById("btnPlayPause"),
    btnStep5: document.getElementById("btnStep5"),
    btnRunCycle: document.getElementById("btnRunCycle"),
    btnReset: document.getElementById("btnReset"),
    pillClock: document.getElementById("pillClock"),
    pillWeather: document.getElementById("pillWeather"),
    pillPerf: document.getElementById("pillPerf"),
    quickList: document.getElementById("quickObjectList"),
    scrubTime: document.getElementById("scrubTime"),
    lblTime: document.getElementById("lblTime"),
    lblTimeMode: document.getElementById("lblTimeMode"),
    lblMaxTime: document.getElementById("lblMaxTime"),
    chkCompareMode: document.getElementById("chkCompareMode"),
    scrubT1: document.getElementById("scrubT1"),
    scrubT2: document.getElementById("scrubT2"),
    lblT1: document.getElementById("lblT1"),
    lblT2: document.getElementById("lblT2"),
    inspectorBody: document.getElementById("inspectorBody"),
    selEventFilter: document.getElementById("selEventFilter"),
    lblEventCount: document.getElementById("lblEventCount"),
    causalChainBox: document.getElementById("causalChainBox"),
    eventFeed: document.getElementById("eventFeed"),
    btnCompareDry: document.getElementById("btnCompareDry"),
    dryBox: document.getElementById("dryComparisonBox"),
    diffTableBox: document.getElementById("diffTableBox"),
    provenanceBox: document.getElementById("provenanceBox"),
    layers: {
      weather: document.getElementById("layerWeather"),
      soil: document.getElementById("layerSoil"),
      plants: document.getElementById("layerPlants"),
      substrates: document.getElementById("layerSubstrates"),
      animals: document.getElementById("layerAnimals"),
      changes: document.getElementById("layerChanges"),
      populations: document.getElementById("layerPopulations"),
    },
  };

  async function apiGet(url) {
    const r = await fetch(url);
    return await r.json();
  }
  async function apiPost(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return await r.json();
  }

  function originBadge(origin) {
    const o = String(origin || "MODELLWERT").toUpperCase();
    if (o.includes("FLYWIRE")) return `<span class="badge orig-fly">${origin}</span>`;
    if (o.includes("GBIF")) return `<span class="badge orig-gbif">${origin}</span>`;
    if (o.includes("DWD")) return `<span class="badge orig-dwd">${origin}</span>`;
    return `<span class="badge orig-model">${origin}</span>`;
  }

  function currentFrame() {
    return state.payload && state.payload.frame ? state.payload.frame : null;
  }

  function worldToCanvas(wx, wy, wPx, hPx) {
    const pad = 14;
    const bmin = state.meta.world_bounds.min;
    const bmax = state.meta.world_bounds.max;
    const spanX = bmax[0] - bmin[0];
    const spanY = bmax[1] - bmin[1];
    const scale = Math.min((wPx - 2 * pad) / spanX, (hPx - 2 * pad) / spanY);
    const ox = 0.5 * (wPx - spanX * scale);
    const oy = 0.5 * (hPx - spanY * scale);
    const cx = ox + (wx - bmin[0]) * scale;
    const cy = hPx - oy - (wy - bmin[1]) * scale;
    return { x: cx, y: cy, scale };
  }

  function drawTag(ctx, text, cx, cy, fg = "#e2e8f0", bg = "rgba(15,23,42,0.78)") {
    ctx.font = "600 9.5px system-ui";
    ctx.textAlign = "center";
    const w = ctx.measureText(text).width + 8;
    ctx.fillStyle = bg;
    ctx.fillRect(cx - w * 0.5, cy - 9, w, 12);
    ctx.fillStyle = fg;
    ctx.fillText(text, cx, cy);
  }

  function resizeCanvas() {
    const rect = els.canvas.parentElement.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    els.canvas.width = Math.max(300, Math.floor(rect.width * dpr));
    els.canvas.height = Math.max(240, Math.floor(rect.height * dpr));
  }

  function moistureColor(pct) {
    const t = Math.max(0, Math.min(1, (pct - 8) / 28));
    const r = Math.round(64 + (24 - 64) * t);
    const g = Math.round(54 + (116 - 54) * t);
    const b = Math.round(44 + (168 - 44) * t);
    return `rgb(${r},${g},${b})`;
  }

  function diffColor(deltaPct) {
    const t = Math.max(-1, Math.min(1, deltaPct / 12));
    if (t >= 0) {
      const r = Math.round(35 * (1 - t));
      const g = Math.round(48 + 140 * t);
      const b = Math.round(64 + 190 * t);
      return `rgb(${r},${g},${b})`;
    }
    const k = -t;
    return `rgb(${Math.round(48 + 185 * k)},${Math.round(52 + 80 * k)},${Math.round(60 - 30 * k)})`;
  }

  function renderCanvas() {
    if (!state.meta || !currentFrame()) return;
    const ctx = els.canvas.getContext("2d");
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = els.canvas.width;
    const H = els.canvas.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.scale(dpr, dpr);
    const wPx = W / dpr;
    const hPx = H / dpr;
    const frame = currentFrame();
    const recentSet = new Set(frame.recent_change_ids || []);
    state.hitboxes = [];

    // 1. Boden- & Hydrologie-Raster (Live oder Vorher-Nachher-Delta)
    const g = state.meta.grid;
    const ref0 = worldToCanvas(g.x_min, g.y_min, wPx, hPx);
    const cellPx = g.cell_size_m * ref0.scale;
    const mGrid = (state.compareMode && state.diffData) ? state.diffData.grid_delta_moisture_pct : frame.grid_moisture_pct;
    const pGrid = (state.compareMode && state.diffData) ? state.diffData.grid_delta_puddle_mm : frame.grid_puddle_mm;

    for (let iy = 0; iy < g.ny; iy++) {
      for (let ix = 0; ix < g.nx; ix++) {
        const wx = g.x_min + ix * g.cell_size_m;
        const wy = g.y_min + (iy + 1) * g.cell_size_m;
        const pt = worldToCanvas(wx, wy, wPx, hPx);
        const isRoof = g.roof_mask[iy][ix] === 1;
        if (isRoof) {
          ctx.fillStyle = "#1e293b";
        } else if (els.layers.soil.checked) {
          const val = mGrid[iy][ix];
          ctx.fillStyle = (state.compareMode && state.diffData) ? diffColor(val) : moistureColor(val);
        } else {
          ctx.fillStyle = "#182234";
        }
        ctx.fillRect(pt.x, pt.y, cellPx + 0.6, cellPx + 0.6);

        if (!isRoof && els.layers.soil.checked) {
          const pud = pGrid[iy][ix];
          if (pud > 0.35) {
            ctx.fillStyle = state.compareMode ? "rgba(56,189,248,0.55)" : `rgba(56, 189, 248, ${Math.min(0.82, 0.25 + pud * 0.08)})`;
            ctx.beginPath();
            ctx.ellipse(pt.x + cellPx * 0.5, pt.y + cellPx * 0.5, cellPx * Math.min(0.45, 0.14 + pud * 0.03), cellPx * Math.min(0.36, 0.11 + pud * 0.024), 0, 0, Math.PI * 2);
            ctx.fill();
          }
          // Oberflächenabfluss-Pfeile
          const vx = frame.grid_flow_vx_cms[iy][ix];
          const vy = frame.grid_flow_vy_cms[iy][ix];
          const fspd = Math.hypot(vx, vy);
          if (fspd >= 0.35) {
            const cx = pt.x + cellPx * 0.5;
            const cy = pt.y + cellPx * 0.5;
            const len = Math.min(cellPx * 0.45, 4 + fspd * 2.2);
            const ux = vx / fspd;
            const uy = -vy / fspd;
            ctx.strokeStyle = "#7dd3fc";
            ctx.lineWidth = 1.4;
            ctx.beginPath();
            ctx.moveTo(cx - ux * len * 0.4, cy - uy * len * 0.4);
            ctx.lineTo(cx + ux * len * 0.6, cy + uy * len * 0.6);
            ctx.stroke();
          }
        }
      }
    }

    // 2. Haus Seestraße 43 + Portal
    const hm = state.meta.house_main;
    const ha = state.meta.house_annex;
    const drawHouseBox = (box, fill, label, yFrac = 0.25) => {
      const p1 = worldToCanvas(box[0][0], box[1][1], wPx, hPx);
      const p2 = worldToCanvas(box[1][0], box[0][1], wPx, hPx);
      ctx.fillStyle = fill;
      ctx.fillRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
      ctx.strokeStyle = "#94a3b8";
      ctx.lineWidth = 1.8;
      ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
      if (label) {
        ctx.fillStyle = "#cbd5e1";
        ctx.font = "bold 10.5px system-ui";
        ctx.textAlign = "center";
        ctx.fillText(label, 0.5 * (p1.x + p2.x), p1.y + (p2.y - p1.y) * yFrac);
      }
    };
    drawHouseBox(hm, "#283548", "Haus Seestraße 43 (Innen-Refugium)", 0.20);
    drawHouseBox(ha, "#232f40", "Anbau", 0.52);

    const port = worldToCanvas(state.meta.house_portal[0], state.meta.house_portal[1], wPx, hPx);
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(port.x - 10, port.y - 3, 20, 6);

    // 3. Boden-Zonen Hitboxen
    const shortZoneNames = {
      SOIL_TERRACE_SOUTH: "Terrasse",
      SOIL_ROOF_EAVE_S: "Dachtraufe",
      SOIL_APPLE_HOLLOW: "Apfel-Mulde",
      SOIL_COMPOST_EAST: "Kompost",
      SOIL_LAWN_WEST: "Westrasen",
      SOIL_INDOOR_FLOOR: "Innenboden",
    };
    if (els.layers.soil.checked) {
      Object.values(frame.soil_zones).forEach((z) => {
        const pt = worldToCanvas(z.center[0], z.center[1], wPx, hPx);
        const rPx = Math.max(14, z.radius_m * pt.scale * 0.78);
        ctx.strokeStyle = z.zone_id === state.selectedId ? "#ffffff" : "rgba(148,163,184,0.45)";
        ctx.lineWidth = z.zone_id === state.selectedId ? 2.2 : 1.0;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, rPx, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        if (els.layers.changes.checked && recentSet.has(z.zone_id)) {
          ctx.strokeStyle = "#f59e0b";
          ctx.lineWidth = 2.4;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, rPx + 4, 0, Math.PI * 2);
          ctx.stroke();
        }
        const zShort = shortZoneNames[z.zone_id] || z.label_de.split("(")[0].trim();
        drawTag(ctx, `${zShort} ${z.soil_moisture_pct.toFixed(0)}%`, pt.x, pt.y + rPx + 11, "#cbd5e1");
        state.hitboxes.push({ id: z.zone_id, x: pt.x, y: pt.y, r: rPx, prio: 1, title: z.label_de, info: `${z.soil_moisture_pct}% Vol. · ${z.puddle_depth_mm} mm` });
      });
    }

    // 4. Pflanzen (Vegetation)
    if (els.layers.plants.checked) {
      Object.values(frame.plants).forEach((pl) => {
        const pt = worldToCanvas(pl.pos[0], pl.pos[1], wPx, hPx);
        const rPx = Math.max(10, pl.radius_m * pt.scale * 0.62);
        const gCh = Math.round(115 + 110 * pl.lushness_index);
        const rCh = Math.round(78 - 34 * pl.turgor_index);
        ctx.fillStyle = `rgba(${rCh}, ${gCh}, 62, 0.72)`;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, rPx, 0, Math.PI * 2);
        ctx.fill();
        // Nässe-Glanzrand
        ctx.strokeStyle = pl.foliage_wetness > 0.25 ? `rgba(56, 189, 248, ${0.4 + 0.6 * pl.foliage_wetness})` : "#14532d";
        ctx.lineWidth = pl.foliage_wetness > 0.25 ? 2.6 : 1.4;
        ctx.stroke();
        if (pl.plant_id === state.selectedId) {
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 2.4;
          ctx.stroke();
        }
        if (els.layers.changes.checked && recentSet.has(pl.plant_id)) {
          ctx.strokeStyle = "#f59e0b";
          ctx.lineWidth = 2.0;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, rPx + 4, 0, Math.PI * 2);
          ctx.stroke();
        }
        const pShort = pl.label_de.split("(")[0].split("-")[0].trim();
        drawTag(ctx, pShort, pt.x, pt.y - rPx - 4, "#dcfce7", "rgba(6,78,59,0.78)");
        state.hitboxes.push({ id: pl.plant_id, x: pt.x, y: pt.y, r: rPx, prio: 2, title: pl.label_de, info: `Turgor ${pl.turgor_index.toFixed(2)} · Nässe ${pl.foliage_wetness.toFixed(2)}` });
      });
    }

    // 5. Substrate / Lebensräume
    if (els.layers.substrates.checked) {
      Object.values(frame.substrates).forEach((s) => {
        const pt = worldToCanvas(s.pos[0], s.pos[1], wPx, hPx);
        const vocR = 7 + s.voc_strength * 4.5;
        ctx.fillStyle = "rgba(251, 146, 60, 0.16)";
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, vocR, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = s.substrate_id === state.selectedId ? "#ffffff" : "#fb923c";
        ctx.fillRect(pt.x - 5, pt.y - 5, 10, 10);
        if (els.layers.changes.checked && recentSet.has(s.substrate_id)) {
          ctx.strokeStyle = "#f59e0b";
          ctx.lineWidth = 2;
          ctx.strokeRect(pt.x - 8, pt.y - 8, 16, 16);
        }
        state.hitboxes.push({ id: s.substrate_id, x: pt.x, y: pt.y, r: 10, prio: 3, title: s.label_de, info: `VOC ${s.voc_strength} · ${s.nutrients} mg` });
      });
    }

    // 6. Tiere: Fliegen, Hummeln, Käfer, 3 Vögel
    if (els.layers.animals.checked) {
      // Fruchtfliegen
      frame.flies.forEach((fl) => {
        const pt = worldToCanvas(fl.pos[0], fl.pos[1], wPx, hPx);
        ctx.fillStyle = fl.state === "ESCAPING" ? "#f43f5e" : (fl.state === "SHELTERED" ? "#94a3b8" : "#c084fc");
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, fl.id === state.selectedId ? 5.5 : 3.4, 0, Math.PI * 2);
        ctx.fill();
        if (fl.id === state.selectedId) {
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 1.6;
          ctx.stroke();
        }
        state.hitboxes.push({ id: fl.id, x: pt.x, y: pt.y, r: 8, prio: 4, title: `Fliege #${fl.fly_num}`, info: `${fl.state} · LC4=${fl.lc4.toFixed(2)}` });
      });

      // Hummeln & Goldlaufkäfer
      Object.values(frame.other_insects).forEach((ins) => {
        const pt = worldToCanvas(ins.pos[0], ins.pos[1], wPx, hPx);
        const isBumble = ins.guild === "BUMBLEBEE";
        ctx.fillStyle = isBumble ? (ins.state === "SHELTERING_RAIN" ? "#60a5fa" : "#facc15") : (ins.state === "AVOIDING_PUDDLE" ? "#f97316" : "#4ade80");
        ctx.beginPath();
        if (isBumble) {
          ctx.ellipse(pt.x, pt.y, 6, 4, 0, 0, Math.PI * 2);
        } else {
          ctx.rect(pt.x - 4.5, pt.y - 3.5, 9, 7);
        }
        ctx.fill();
        ctx.strokeStyle = ins.insect_id === state.selectedId ? "#fff" : "#0f172a";
        ctx.lineWidth = ins.insect_id === state.selectedId ? 2 : 1;
        ctx.stroke();
        state.hitboxes.push({ id: ins.insect_id, x: pt.x, y: pt.y, r: 10, prio: 5, title: ins.label_de, info: `${ins.state} · Akt. ${ins.activity_index}` });
      });

      // Drei Vogelarten
      const birdColors = { CYANISTES_CAERULEUS: "#38bdf8", PARUS_MAJOR: "#a3e635", HIRUNDO_RUSTICA: "#ef4444" };
      Object.values(frame.birds).forEach((b) => {
        const pt = worldToCanvas(b.pos[0], b.pos[1], wPx, hPx);
        const ang = Math.atan2(-b.heading[1], b.heading[0]);
        ctx.save();
        ctx.translate(pt.x, pt.y);
        ctx.rotate(ang);
        ctx.fillStyle = birdColors[b.species_id] || "#fff";
        ctx.beginPath();
        ctx.moveTo(11, 0);
        ctx.lineTo(-7, -6);
        ctx.lineTo(-3, 0);
        ctx.lineTo(-7, 6);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = b.bird_id === state.selectedId ? "#fff" : "#0f172a";
        ctx.lineWidth = b.bird_id === state.selectedId ? 2.2 : 1.2;
        ctx.stroke();
        ctx.restore();
        ctx.fillStyle = "#f8fafc";
        ctx.font = "bold 10px system-ui";
        ctx.textAlign = "left";
        ctx.fillText(`${b.bird_id} (${b.catches})`, pt.x + 11, pt.y - 5);
        state.hitboxes.push({ id: b.bird_id, x: pt.x, y: pt.y, r: 14, prio: 6, title: `${b.common_name_de} (${b.bird_id})`, info: `${b.state} · ${b.energy_j} J` });
      });
    }

    // 7. Wetter- & Tageslicht-Overlay (Wolkenverdunklung & Regentropfen)
    const w = frame.weather;
    if (els.layers.weather.checked) {
      const dark = Math.max(0, 0.28 * (1 - w.daylight_uv_factor));
      if (dark > 0.02) {
        ctx.fillStyle = `rgba(10, 18, 36, ${dark.toFixed(2)})`;
        ctx.fillRect(0, 0, wPx, hPx);
      }
      if (w.rain_mm_h > 0.2) {
        const count = Math.min(state.rainParticles.length, Math.round(15 + w.rain_mm_h * 5.2));
        ctx.strokeStyle = "rgba(125, 211, 252, 0.55)";
        ctx.lineWidth = 1.2;
        for (let i = 0; i < count; i++) {
          const rp = state.rainParticles[i];
          if (state.payload.running) {
            rp.y = (rp.y + 0.022 * rp.spd) % 1;
            rp.x = (rp.x + 0.004) % 1;
          }
          const rx = rp.x * wPx;
          const ry = rp.y * hPx;
          ctx.beginPath();
          ctx.moveTo(rx, ry);
          ctx.lineTo(rx - 3, ry + rp.len);
          ctx.stroke();
        }
      }
    }

    // 8. Populations-Overlay
    if (els.layers.populations.checked) {
      els.popOverlay.classList.remove("hidden");
      const fs = frame.fly_summary;
      const nSh = Object.values(frame.other_insects).filter((i) => i.state === "SHELTERING_RAIN").length;
      const nMoist = Object.values(frame.other_insects).filter((i) => i.state === "FORAGING_MOIST").length;
      els.popOverlay.innerHTML =
        `<strong>Populationen @ ${frame.t_s.toFixed(1)} s</strong><br>` +
        `Fliegen: ${fs.alive} (Küche ${fs.indoor} · Krone ${fs.canopy} · Frei ${fs.open_air})<br>` +
        `Hummeln: ${Object.values(frame.other_insects).filter((i) => i.guild === "BUMBLEBEE").length} (${nSh} im Regenschutz) · ` +
        `Laufkäfer: 4 (${nMoist} feucht-aktiv)<br>` +
        `Vögel: BM ${frame.birds.BM_01.catches} Fänge · KM ${frame.birds.KM_01.catches} · RS ${frame.birds.RS_01.catches}`;
    } else {
      els.popOverlay.classList.add("hidden");
    }
  }

  function updateHeaderAndSliders() {
    if (!state.payload || !currentFrame()) return;
    const pl = state.payload;
    const f = currentFrame();
    const w = f.weather;
    const icon = w.regime === "REGEN" ? "🌧" : (w.regime === "BEWOELKT" || w.regime === "AUFKLAREND" ? "☁" : "☀");

    els.pillClock.textContent = `🕒 ${w.clock_str} · ${w.season} (t=${f.t_s.toFixed(1)} s)`;
    els.pillWeather.textContent = `${icon} ${w.regime} · ${w.rain_mm_h.toFixed(1)} mm/h · ${w.temperature_c.toFixed(1)} °C · ${w.humidity_pct.toFixed(0)}% rF`;
    els.pillPerf.textContent = `${pl.ms_per_tick} ms/Tick · ${pl.rss_mb} MB · SHA ${pl.state_sha256.slice(0, 8)}`;
    els.btnPlayPause.textContent = pl.running ? "⏸ Pause" : "▶ Start";

    if (pl.running && pl.auto_stop_at_s) {
      els.btnRunCycle.disabled = true;
      els.btnRunCycle.textContent = `⏳ Läuft ${f.t_s.toFixed(0)}/${Number(pl.auto_stop_at_s).toFixed(0)}s`;
    } else {
      els.btnRunCycle.disabled = false;
      els.btnRunCycle.textContent = "🌧 90s Regenzyklus";
    }

    if (pl.compare_running) {
      els.btnCompareDry.disabled = true;
      els.btnCompareDry.textContent = "⏳ Vergleiche gegen Trocken-Kontrolle…";
    } else {
      els.btnCompareDry.disabled = false;
      els.btnCompareDry.textContent = "Regen vs. Trocken-Kontrolle (90 s)";
      if (pl.dry_comparison && !pl.dry_comparison.error) {
        renderDryComparisonBox(pl.dry_comparison);
      }
    }

    const times = pl.available_times_s || [0];
    const maxIdx = Math.max(0, times.length - 1);
    els.scrubTime.max = String(maxIdx);
    els.scrubT1.max = String(maxIdx);
    els.scrubT2.max = String(maxIdx);

    if (state.scrubT === null) {
      els.scrubTime.value = String(maxIdx);
      els.lblTime.textContent = `${f.t_s.toFixed(1)} s`;
      els.lblTimeMode.textContent = pl.running ? "LIVE" : "AKTUELL";
    } else {
      els.lblTime.textContent = `${f.t_s.toFixed(1)} s`;
      els.lblTimeMode.textContent = "RÜCKBLICK";
    }
    els.lblMaxTime.textContent = `${times[maxIdx].toFixed(0)} s`;

    if (!state.compareMode && maxIdx > 0) {
      state.t1 = Math.min(state.t1, maxIdx);
      state.t2 = maxIdx;
      els.scrubT1.value = String(state.t1);
      els.scrubT2.value = String(maxIdx);
    }
    const v1 = times[Math.min(maxIdx, Number(els.scrubT1.value))] || 0;
    const v2 = times[Math.min(maxIdx, Number(els.scrubT2.value))] || 0;
    els.lblT1.textContent = `${v1.toFixed(0)} s`;
    els.lblT2.textContent = `${v2.toFixed(0)} s`;
  }

  function renderQuickList() {
    const f = currentFrame();
    if (!f) return;
    const recent = new Set(f.recent_change_ids || []);
    const sections = [
      { title: "Boden & Hydrologie", items: Object.values(f.soil_zones).map((z) => ({ id: z.zone_id, lbl: z.label_de, val: `${z.soil_moisture_pct}%` })) },
      { title: "Pflanzen (Vegetation)", items: Object.values(f.plants).map((p) => ({ id: p.plant_id, lbl: p.label_de, val: `T=${p.turgor_index.toFixed(2)}` })) },
      { title: "Lebensräume (Substrate)", items: Object.values(f.substrates).map((s) => ({ id: s.substrate_id, lbl: s.label_de, val: `VOC ${s.voc_strength}` })) },
      { title: "Vögel (3 Arten)", items: Object.values(f.birds).map((b) => ({ id: b.bird_id, lbl: `${b.common_name_de} (${b.bird_id})`, val: b.state })) },
      { title: "Hummeln & Laufkäfer", items: Object.values(f.other_insects).map((i) => ({ id: i.insect_id, lbl: i.label_de, val: i.state.split("_")[0] })) },
      { title: `Fruchtfliegen (Probe von ${f.flies.length})`, items: f.flies.slice(0, 6).map((fl) => ({ id: fl.id, lbl: `Fliege #${fl.fly_num}`, val: fl.state })) },
    ];
    els.quickList.innerHTML = sections.map((sec) =>
      `<div class="quick-group-title">${sec.title}</div>` +
      sec.items.map((it) => {
        const cls = it.id === state.selectedId ? "quick-btn active" : "quick-btn";
        const dot = recent.has(it.id) ? `<span class="dot-chg" title="kürzlich verändert"></span>` : "";
        return `<button class="${cls}" data-id="${it.id}"><span>${it.lbl}</span><span>${dot} <small class="muted">${it.val}</small></span></button>`;
      }).join("")
    ).join("");
  }

  function buildSparklineSvg(series) {
    if (!series || !series.values || series.values.length < 2) return "";
    const vals = series.values;
    const minV = Math.min(...vals);
    const maxV = Math.max(...vals);
    const span = Math.max(1e-5, maxV - minV);
    const w = 320;
    const h = 68;
    const pts = vals.map((v, i) => {
      const x = 6 + (i / (vals.length - 1)) * (w - 12);
      const y = h - 8 - ((v - minV) / span) * (h - 16);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `<div class="spark-box"><div class="muted">${series.label} (${series.unit}): ${minV.toFixed(2)} .. ${maxV.toFixed(2)}</div>` +
      `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="#38bdf8" stroke-width="2" points="${pts}" /></svg></div>`;
  }

  async function refreshInspector() {
    if (!state.selectedId) return;
    const f = currentFrame();
    const tQuery = f ? `?id=${encodeURIComponent(state.selectedId)}&t=${f.t_s}` : `?id=${encodeURIComponent(state.selectedId)}`;
    const det = await apiGet(`/api/object${tQuery}`);
    if (det.error) {
      els.inspectorBody.innerHTML = `<p class="muted">${det.error}</p>`;
      return;
    }
    const rowsHtml = (det.metrics || []).map((m) =>
      `<tr><td>${m.name}</td><td><strong>${m.value}</strong> ${m.unit}</td><td>${originBadge(m.origin)}</td></tr>`
    ).join("");
    const evHtml = (det.events || []).slice().reverse().slice(0, 8).map((ev) =>
      `<div class="ev-card ${ev.is_non_reaction ? "non-reaction" : ""}" data-ev="${ev.event_id}">` +
      `<div class="ev-head"><span>t=${ev.sim_time_s}s · ${ev.sim_clock_str}</span>${originBadge(ev.is_non_reaction ? "NICHT-REAKTION" : ev.data_origin)}</div>` +
      `<div class="ev-title">${ev.metric_name}: ${ev.old_value} → ${ev.new_value} ${ev.unit}</div>` +
      `<div class="ev-mech">${ev.mechanism}</div></div>`
    ).join("") || `<p class="muted">Bisher keine Ereignisse für dieses Objekt.</p>`;

    els.inspectorBody.innerHTML = `
      <div class="insp-card">
        <h3>${det.label_de}</h3>
        <div class="muted">${det.category} · ${originBadge(det.data_origin)}</div>
        <div class="muted" style="margin-top:4px;">${det.reference_note || ""}</div>
        <table class="metrics">
          <thead><tr><th>Messgröße</th><th>Wert</th><th>Quelle</th></tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>
        ${buildSparklineSvg(det.series)}
      </div>
      <div class="insp-card">
        <h2>Veränderungs- &amp; Ereignisverlauf (${det.events.length})</h2>
        <div class="event-feed">${evHtml}</div>
      </div>`;
  }

  function renderEventFeed() {
    if (!state.payload) return;
    const flt = els.selEventFilter.value;
    const allEvs = state.payload.events || [];
    const list = allEvs.filter((e) => flt === "ALL" || e.category === flt).slice().reverse();
    els.lblEventCount.textContent = String(list.length);
    els.eventFeed.innerHTML = list.map((ev) => `
      <div class="ev-card ${ev.is_non_reaction ? "non-reaction" : ""}" data-ev="${ev.event_id}">
        <div class="ev-head">
          <span>t=${ev.sim_time_s}s (${ev.sim_clock_str}) · ${ev.category}</span>
          ${originBadge(ev.is_non_reaction ? "AUSBLEIBEND" : ev.data_origin)}
        </div>
        <div class="ev-title">${ev.entity_label} — ${ev.metric_name}: ${ev.old_value} → ${ev.new_value} ${ev.unit}</div>
        <div class="ev-mech">${ev.mechanism}</div>
      </div>
    `).join("") || `<p class="muted">Keine Ereignisse im Filter.</p>`;
  }

  async function showCausalChain(eventId) {
    state.selectedEventId = eventId;
    const ch = await apiGet(`/api/causal_chain?event_id=${encodeURIComponent(eventId)}`);
    if (!ch || !ch.target) {
      els.causalChainBox.classList.add("hidden");
      return;
    }
    const renderNode = (n, tag) =>
      `<div class="chain-node"><strong>[${tag}] t=${n.sim_time_s}s · ${n.entity_label}</strong><br>${n.metric_name}: ${n.old_value} → ${n.new_value} ${n.unit}<br><span class="muted">${n.mechanism}</span></div>`;
    let html = `<strong>Kausalkette für ${ch.target.event_id}</strong> ` +
      `<button class="btn" style="padding:2px 6px;margin-left:6px;" onclick="window._jumpToTime(${ch.target.sim_time_s}, '${ch.target.entity_id}')">Zum Zeitpunkt</button>`;
    if (ch.ancestors.length) {
      html += ch.ancestors.map((a) => renderNode(a, "AUSLÖSER") + `<div class="chain-arrow">↓</div>`).join("");
    }
    html += renderNode(ch.target, ch.target.is_non_reaction ? "NICHT-REAKTION" : "EREIGNIS");
    if (ch.descendants.length) {
      html += ch.descendants.slice(0, 6).map((d) => `<div class="chain-arrow">↓</div>` + renderNode(d, "FOLGEWIRKUNG")).join("");
    }
    els.causalChainBox.innerHTML = html;
    els.causalChainBox.classList.remove("hidden");
  }

  async function refreshDiff() {
    const times = (state.payload && state.payload.available_times_s) || [0];
    const i1 = Math.min(times.length - 1, Number(els.scrubT1.value));
    const i2 = Math.min(times.length - 1, Number(els.scrubT2.value));
    const t1 = times[i1] || 0;
    const t2 = times[i2] || 0;
    const eid = state.selectedId || "";
    const diff = await apiGet(`/api/diff?t1=${t1}&t2=${t2}&entity_id=${encodeURIComponent(eid)}`);
    state.diffData = diff;
    if (diff.error) return;

    const selRows = (diff.selected_entity_rows || []).map((r) => {
      const cls = typeof r.delta === "number" ? (r.delta > 0 ? "delta-pos" : (r.delta < 0 ? "delta-neg" : "")) : "";
      return `<tr><td>${r.metric}</td><td>${r.t1}</td><td>${r.t2}</td><td class="${cls}">${r.delta} ${r.unit}</td></tr>`;
    }).join("") || `<tr><td colspan="4" class="muted">Für ${eid} keine numerische Delta-Tabelle</td></tr>`;

    const zoneRows = Object.values(diff.zone_diffs || {}).map((z) =>
      `<tr><td>${z.label_de.split("(")[0]}</td><td>${z.moisture_t1}%</td><td>${z.moisture_t2}%</td><td class="${z.delta_moisture_pct > 0 ? "delta-pos" : ""}">${z.delta_moisture_pct >= 0 ? "+" : ""}${z.delta_moisture_pct}% · ${z.delta_puddle_mm >= 0 ? "+" : ""}${z.delta_puddle_mm}mm</td></tr>`
    ).join("");

    els.diffTableBox.innerHTML = `
      <div class="insp-card">
        <h3>Vorher (${diff.t1_s}s / ${diff.clock_t1}) vs. Nachher (${diff.t2_s}s / ${diff.clock_t2})</h3>
        <div class="muted">Regen Δ: ${diff.weather_delta.cum_rain_delta_mm} mm · Temp Δ: ${diff.weather_delta.temp_delta_c} °C · rF Δ: ${diff.weather_delta.humidity_delta_pct}%</div>
        <div class="muted">Fliegen-Fänge im Fenster: +${diff.fly_delta.new_captures} · Fluchten: +${diff.fly_delta.new_escapes}</div>
        <table class="metrics"><thead><tr><th>Auswahl (${eid})</th><th>t1</th><th>t2</th><th>Δ</th></tr></thead><tbody>${selRows}</tbody></table>
      </div>
      <div class="insp-card">
        <h2>Bodenflächen-Vergleich (t1 → t2)</h2>
        <table class="metrics"><thead><tr><th>Ort</th><th>Feuchte t1</th><th>t2</th><th>Δ Feuchte · Pfütze</th></tr></thead><tbody>${zoneRows}</tbody></table>
      </div>`;

    if (state.meta) {
      const dwd = state.meta.dwd_weather_reference || {};
      const fw = state.meta.flywire_subcircuit || {};
      els.provenanceBox.innerHTML =
        `<strong>Transparenz &amp; Messquellen</strong><br>` +
        `• <span class="badge orig-fly">FLYWIRE v783</span> ${fw.n_neurons} reale Neurone / ${fw.n_edges} Synapsen<br>` +
        `• <span class="badge orig-gbif">GBIF WÖLFERSHEIM</span> Blaumeise (n=19), Kohlmeise (n=20), Rauchschwalbe (n=5), Holunder (n=17), Ackerhummel (n=1), Goldlaufkäfer (n=1)<br>` +
        `• <span class="badge orig-dwd">DWD ICON-D2</span> ${dwd.available ? `Anker ${dwd.time}: ${dwd.temp_c} °C, ${dwd.rh_pct}% rF, ${dwd.wind_kmh} km/h` : "offline"}<br>` +
        `• <span class="badge orig-model">MODELLWERT</span> Zeitskalierte Hydrologie, Turgor-Lag (14s), Wetter-Regenzyklus.`;
    }
  }

  window._jumpToTime = async (tSec, entityId) => {
    const times = (state.payload && state.payload.available_times_s) || [0];
    let bestIdx = 0;
    let bestD = 1e9;
    times.forEach((tv, idx) => { if (Math.abs(tv - tSec) < bestD) { bestD = Math.abs(tv - tSec); bestIdx = idx; } });
    state.scrubT = times[bestIdx];
    els.scrubTime.value = String(bestIdx);
    if (entityId) state.selectedId = entityId;
    await pullState();
    switchTab("tabInspector");
  };

  function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.toggle("active", c.id === tabId));
  }

  async function pullState() {
    const q = state.scrubT !== null ? `?t=${state.scrubT}` : "";
    state.payload = await apiGet(`/api/state${q}`);
    updateHeaderAndSliders();
    renderQuickList();
    renderEventFeed();
    if (state.compareMode || document.getElementById("tabCompare").classList.contains("active")) {
      await refreshDiff();
    }
    renderCanvas();
    await refreshInspector();
  }

  async function selectEntity(eid) {
    state.selectedId = eid;
    renderQuickList();
    renderCanvas();
    await refreshInspector();
    if (state.compareMode) await refreshDiff();
  }

  function bindEvents() {
    window.addEventListener("resize", () => { resizeCanvas(); renderCanvas(); });
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        switchTab(btn.dataset.tab);
        if (btn.dataset.tab === "tabCompare") await refreshDiff();
      });
    });

    Object.values(els.layers).forEach((cb) => cb.addEventListener("change", () => renderCanvas()));

    els.canvas.addEventListener("mousemove", (ev) => {
      const r = els.canvas.getBoundingClientRect();
      const mx = ev.clientX - r.left;
      const my = ev.clientY - r.top;
      let hit = null;
      let bestScore = -1;
      for (const hb of state.hitboxes) {
        const d = Math.hypot(mx - hb.x, my - hb.y);
        if (d <= hb.r && hb.prio * 100 - d > bestScore) {
          bestScore = hb.prio * 100 - d;
          hit = hb;
        }
      }
      if (hit) {
        els.tooltip.innerHTML = `<strong>${hit.title}</strong><br>${hit.info}<br><span class="muted">Klick für Details</span>`;
        els.tooltip.style.left = `${Math.min(r.width - 170, mx + 12)}px`;
        els.tooltip.style.top = `${Math.max(8, my - 24)}px`;
        els.tooltip.classList.remove("hidden");
      } else {
        els.tooltip.classList.add("hidden");
      }
    });
    els.canvas.addEventListener("mouseleave", () => els.tooltip.classList.add("hidden"));
    els.canvas.addEventListener("click", async (ev) => {
      const r = els.canvas.getBoundingClientRect();
      const mx = ev.clientX - r.left;
      const my = ev.clientY - r.top;
      let hit = null;
      let bestScore = -1;
      for (const hb of state.hitboxes) {
        const d = Math.hypot(mx - hb.x, my - hb.y);
        if (d <= hb.r && hb.prio * 100 - d > bestScore) {
          bestScore = hb.prio * 100 - d;
          hit = hb;
        }
      }
      if (hit) {
        await selectEntity(hit.id);
        switchTab("tabInspector");
      }
    });

    els.quickList.addEventListener("click", async (ev) => {
      const btn = ev.target.closest(".quick-btn");
      if (btn && btn.dataset.id) {
        await selectEntity(btn.dataset.id);
      }
    });

    els.eventFeed.addEventListener("click", async (ev) => {
      const card = ev.target.closest(".ev-card");
      if (card && card.dataset.ev) await showCausalChain(card.dataset.ev);
    });
    els.inspectorBody.addEventListener("click", async (ev) => {
      const card = ev.target.closest(".ev-card");
      if (card && card.dataset.ev) {
        switchTab("tabCausal");
        await showCausalChain(card.dataset.ev);
      }
    });
    els.selEventFilter.addEventListener("change", () => renderEventFeed());

    els.btnPlayPause.addEventListener("click", async () => {
      state.scrubT = null;
      const act = (state.payload && state.payload.running) ? "pause" : "play";
      await apiPost("/api/control", { action: act });
      await pullState();
    });
    els.btnStep5.addEventListener("click", async () => {
      state.scrubT = null;
      els.btnStep5.disabled = true;
      await apiPost("/api/control", { action: "step", seconds: 5.0 });
      els.btnStep5.disabled = false;
      await pullState();
    });
    els.btnRunCycle.addEventListener("click", async () => {
      state.scrubT = null;
      els.btnRunCycle.disabled = true;
      els.btnRunCycle.textContent = "⏳ Starte 90s…";
      await apiPost("/api/control", { action: "run_rain_cycle", target_s: 90.0 });
      await pullState();
    });
    els.btnReset.addEventListener("click", async () => {
      state.scrubT = null;
      await apiPost("/api/control", {
        action: "reset",
        scenario: els.selScenario.value,
        season: els.selSeason.value,
        seed: Number(els.inpSeed.value) || 42,
      });
      await pullState();
    });

    els.scrubTime.addEventListener("input", async () => {
      const times = (state.payload && state.payload.available_times_s) || [0];
      const idx = Number(els.scrubTime.value);
      state.scrubT = idx >= times.length - 1 ? null : times[idx];
      await pullState();
    });

    els.chkCompareMode.addEventListener("change", async () => {
      state.compareMode = els.chkCompareMode.checked;
      await refreshDiff();
      renderCanvas();
    });
    const onScrubAB = async () => { await refreshDiff(); renderCanvas(); };
    els.scrubT1.addEventListener("input", onScrubAB);
    els.scrubT2.addEventListener("input", onScrubAB);

    els.btnCompareDry.addEventListener("click", async () => {
      els.btnCompareDry.disabled = true;
      els.btnCompareDry.textContent = "⏳ Vergleiche gegen Trocken-Kontrolle…";
      await apiPost("/api/compare_control", { duration_s: 90.0, async: true });
      await pullState();
    });
  }

  function renderDryComparisonBox(res) {
    els.dryBox.innerHTML =
      `<strong>Gegenprobe: ${res.rain_scenario} vs. TROCKEN_KONTROLLE (Seed=${res.seed}, t=${res.duration_s}s)</strong>` +
      `<table class="metrics"><thead><tr><th>Kenngröße</th><th>Regen</th><th>Trocken</th></tr></thead><tbody>` +
      `<tr><td>Niederschlagssumme</td><td><strong>${res.rain_cum_mm} mm</strong></td><td>${res.dry_cum_mm} mm</td></tr>` +
      `<tr><td>Südterrasse Bodenfeuchte</td><td><strong>${res.terrace_moisture_wet_pct} % Vol.</strong></td><td>${res.terrace_moisture_dry_pct} % Vol.</td></tr>` +
      `<tr><td>Südterrasse Pfützentiefe</td><td><strong>${res.terrace_puddle_wet_mm} mm</strong></td><td>${res.terrace_puddle_dry_mm} mm</td></tr>` +
      `<tr><td>Kompost Bodenfeuchte</td><td><strong>${res.compost_moisture_wet_pct} % Vol.</strong></td><td>${res.compost_moisture_dry_pct} % Vol.</td></tr>` +
      `<tr><td>Apfelbaum Turgor</td><td><strong>${res.apple_turgor_wet}</strong></td><td>${res.apple_turgor_dry}</td></tr>` +
      `<tr><td>Innenboden Küche (Kontrolle)</td><td>${res.indoor_moisture_wet_pct} % Vol.</td><td>${res.indoor_moisture_dry_pct} % Vol.</td></tr>` +
      `<tr><td>Fliegen gefangen / Freiluft</td><td>${res.fly_captured_wet} / ${res.fly_open_air_wet}</td><td>${res.fly_captured_dry} / ${res.fly_open_air_dry}</td></tr>` +
      `</tbody></table>`;
    els.dryBox.classList.remove("hidden");
  }

  async function init() {
    state.meta = await apiGet("/api/meta");
    resizeCanvas();
    bindEvents();
    await pullState();
    setInterval(async () => {
      if (state.payload && ((state.payload.running && state.scrubT === null) || state.payload.compare_running)) {
        await pullState();
      }
    }, 450);
  }

  init();
})();

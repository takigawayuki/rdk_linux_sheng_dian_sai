import "./styles.css";
import Activity from "lucide/dist/esm/icons/activity.js";
import Aperture from "lucide/dist/esm/icons/aperture.js";
import Camera from "lucide/dist/esm/icons/camera.js";
import Check from "lucide/dist/esm/icons/check.js";
import CircleDot from "lucide/dist/esm/icons/circle-dot.js";
import Crosshair from "lucide/dist/esm/icons/crosshair.js";
import Eye from "lucide/dist/esm/icons/eye.js";
import Grid3X3 from "lucide/dist/esm/icons/grid-3x3.js";
import MapIcon from "lucide/dist/esm/icons/map.js";
import Pause from "lucide/dist/esm/icons/pause.js";
import Play from "lucide/dist/esm/icons/play.js";
import Plus from "lucide/dist/esm/icons/plus.js";
import RefreshCw from "lucide/dist/esm/icons/refresh-cw.js";
import RotateCcw from "lucide/dist/esm/icons/rotate-ccw.js";
import Ruler from "lucide/dist/esm/icons/ruler.js";
import ScanLine from "lucide/dist/esm/icons/scan-line.js";
import Sparkles from "lucide/dist/esm/icons/sparkles.js";
import Video from "lucide/dist/esm/icons/video.js";
import Zap from "lucide/dist/esm/icons/zap.js";
import createLucideElement from "lucide/dist/esm/createElement.js";
import {
  type CalibrationSample,
  type MappingModel,
  fitHomography,
  fitLinear,
  fitProjective,
  mappingStats,
} from "./math";
import { WorkbenchScene, type SensorSettings } from "./scene";
import { BallSimulation } from "./simulation";

type Stage = "overview" | "calibration" | "mapping" | "simulation";
type MappingMode = "linear" | "projective" | "homography";

const app = document.querySelector<HTMLDivElement>("#app")!;
app.innerHTML = `
  <header class="topbar">
    <div class="brand-block">
      <div class="brand-mark"><i data-lucide="circle-dot"></i></div>
      <div>
        <h1>滚球视觉实验台</h1>
        <p>H题 · 视觉建模与闭环仿真</p>
      </div>
    </div>
    <div class="source-status" title="当前使用虚拟相机数据源">
      <span class="status-dot"></span>
      <span>仿真源</span>
      <strong>120 FPS</strong>
    </div>
  </header>

  <nav class="stage-tabs" aria-label="教学阶段">
    <button class="stage-tab is-active" data-stage="overview"><i data-lucide="eye"></i><span>系统总览</span></button>
    <button class="stage-tab" data-stage="calibration"><i data-lucide="crosshair"></i><span>几何标定</span></button>
    <button class="stage-tab" data-stage="mapping"><i data-lucide="map"></i><span>映射验证</span></button>
    <button class="stage-tab" data-stage="simulation"><i data-lucide="activity"></i><span>动态仿真</span></button>
  </nav>

  <main class="workspace" data-stage="overview">
    <aside class="step-rail" aria-label="实验流程">
      <button class="rail-step is-active" data-stage="overview" title="系统总览"><span>01</span><i data-lucide="camera"></i></button>
      <button class="rail-step" data-stage="calibration" title="几何标定"><span>02</span><i data-lucide="crosshair"></i></button>
      <button class="rail-step" data-stage="mapping" title="映射验证"><span>03</span><i data-lucide="ruler"></i></button>
      <button class="rail-step" data-stage="simulation" title="动态仿真"><span>04</span><i data-lucide="activity"></i></button>
    </aside>

    <section class="scene-shell" aria-label="三维实验场景">
      <div id="scene-host"></div>
      <div class="scene-toolbar" aria-label="三维视角">
        <button class="icon-button is-active" data-view="perspective" title="透视视角"><i data-lucide="sparkles"></i></button>
        <button class="icon-button" data-view="top" title="俯视视角"><i data-lucide="grid-3x3"></i></button>
        <button class="icon-button" data-view="side" title="侧面视角"><i data-lucide="scan-line"></i></button>
      </div>
      <div class="scene-title">
        <span id="stage-kicker">STEP 01</span>
        <strong id="stage-title">视觉系统总览</strong>
      </div>

      <figure class="camera-monitor">
        <figcaption><i data-lucide="video"></i><span>虚拟相机 · 640×480</span><b id="preview-status">UNDISTORTED</b></figcaption>
        <canvas id="camera-preview" width="640" height="480"></canvas>
      </figure>

      <figure class="plot-monitor">
        <figcaption><i data-lucide="activity"></i><span id="plot-title">映射残差</span><b id="plot-value">RMSE 0.00 cm</b></figcaption>
        <canvas id="data-plot" width="560" height="180"></canvas>
      </figure>
    </section>

    <aside class="inspector">
      <div class="inspector-heading">
        <div><span>实验参数</span><strong id="inspector-title">相机与钢球</strong></div>
        <button class="icon-button" id="reset-view" title="恢复默认视角"><i data-lucide="rotate-ccw"></i></button>
      </div>

      <section class="control-section section-position">
        <div class="section-heading"><i data-lucide="circle-dot"></i><strong>钢球位置</strong><output id="ball-x-output">0.00 cm</output></div>
        <input id="ball-x" type="range" min="-12" max="12" step="0.1" value="0" />
        <div class="range-labels"><span>-12 cm</span><span>O</span><span>+12 cm</span></div>
      </section>

      <section class="control-section section-camera">
        <div class="section-heading"><i data-lucide="aperture"></i><strong>虚拟相机</strong><span>针孔模型</span></div>
        <label class="control-row"><span>安装高度</span><input id="camera-height" type="range" min="8" max="26" step="0.5" value="15" /><output id="camera-height-out">15.0 cm</output></label>
        <label class="control-row"><span>斜视角度</span><input id="camera-angle" type="range" min="0" max="38" step="1" value="12" /><output id="camera-angle-out">12°</output></label>
        <label class="control-row"><span>垂直视场</span><input id="camera-fov" type="range" min="34" max="72" step="1" value="48" /><output id="camera-fov-out">48°</output></label>
        <label class="control-row"><span>径向畸变 k₁</span><input id="camera-k1" type="range" min="-0.25" max="0.18" step="0.01" value="-0.08" /><output id="camera-k1-out">-0.08</output></label>
        <label class="control-row"><span>测量噪声</span><input id="camera-noise" type="range" min="0" max="2.5" step="0.1" value="0.2" /><output id="camera-noise-out">0.2 px</output></label>
      </section>

      <section class="control-section section-calibration">
        <div class="section-heading"><i data-lucide="crosshair"></i><strong>标定点</strong><span id="sample-count">5 点</span></div>
        <div class="command-row">
          <button class="command-button primary" id="capture-point"><i data-lucide="plus"></i>采集当前位置</button>
          <button class="icon-button" id="reset-samples" title="重建默认标定点"><i data-lucide="refresh-cw"></i></button>
        </div>
        <div class="sample-table-wrap">
          <table class="sample-table">
            <thead><tr><th>真值</th><th>像素 u</th><th>像素 v</th><th></th></tr></thead>
            <tbody id="sample-table"></tbody>
          </table>
        </div>
      </section>

      <section class="control-section section-mapping">
        <div class="section-heading"><i data-lucide="map"></i><strong>坐标映射</strong><span id="mapping-state">有效</span></div>
        <div class="segmented" role="group" aria-label="映射模型">
          <button class="is-active" data-mapping="linear">线性</button>
          <button data-mapping="projective">射影</button>
          <button data-mapping="homography">单应性</button>
        </div>
        <div class="formula-box"><code id="mapping-formula">x = au + b</code></div>
        <div class="metric-grid">
          <div><span>RMSE</span><strong id="metric-rmse">0.00 cm</strong></div>
          <div><span>最大误差</span><strong id="metric-max">0.00 cm</strong></div>
        </div>
      </section>

      <section class="control-section section-simulation">
        <div class="section-heading"><i data-lucide="activity"></i><strong>闭环仿真</strong><span>PID</span></div>
        <label class="number-row"><span>目标位置</span><input id="sim-target" type="number" min="-10" max="10" step="0.5" value="0" /><em>cm</em></label>
        <label class="number-row"><span>Kp</span><input id="sim-kp" type="number" min="0" max="5" step="0.05" value="1.25" /></label>
        <label class="number-row"><span>Kd</span><input id="sim-kd" type="number" min="0" max="3" step="0.05" value="0.78" /></label>
        <div class="command-row simulation-actions">
          <button class="command-button primary" id="sim-play"><i data-lucide="play"></i><span>运行</span></button>
          <button class="icon-button" id="sim-disturb" title="施加速度扰动"><i data-lucide="zap"></i></button>
          <button class="icon-button" id="sim-reset" title="重置仿真"><i data-lucide="rotate-ccw"></i></button>
        </div>
      </section>
    </aside>
  </main>

  <footer class="telemetry">
    <div><span>真实位置</span><strong id="telemetry-true">0.00 cm</strong></div>
    <div><span>像素坐标</span><strong id="telemetry-pixel">320.0, 240.0</strong></div>
    <div><span>映射位置</span><strong id="telemetry-mapped">0.00 cm</strong></div>
    <div><span>绝对误差</span><strong id="telemetry-error">0.00 cm</strong></div>
    <div><span>状态</span><strong class="good" id="telemetry-status"><i data-lucide="check"></i>映射有效</strong></div>
  </footer>
`;

const icons = {
  activity: Activity,
  aperture: Aperture,
  camera: Camera,
  check: Check,
  "circle-dot": CircleDot,
  crosshair: Crosshair,
  eye: Eye,
  "grid-3x3": Grid3X3,
  map: MapIcon,
  pause: Pause,
  play: Play,
  plus: Plus,
  "refresh-cw": RefreshCw,
  "rotate-ccw": RotateCcw,
  ruler: Ruler,
  "scan-line": ScanLine,
  sparkles: Sparkles,
  video: Video,
  zap: Zap,
} as const;

function mountIcons(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>("[data-lucide]").forEach((placeholder) => {
    const name = placeholder.dataset.lucide as keyof typeof icons;
    const icon = icons[name];
    if (!icon) return;
    const svg = createLucideElement(icon);
    svg.setAttribute("class", `lucide lucide-${name}`);
    placeholder.replaceWith(svg);
  });
}

mountIcons();

const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const scene = new WorkbenchScene($("#scene-host"));
const simulation = new BallSimulation();
const preview = $("#camera-preview") as HTMLCanvasElement;
const previewContext = preview.getContext("2d")!;
const plot = $("#data-plot") as HTMLCanvasElement;
const plotContext = plot.getContext("2d")!;

let stage: Stage = "overview";
let mappingMode: MappingMode = "linear";
let nextSampleId = 1;
let samples: CalibrationSample[] = [];
let mappingModel: MappingModel;
let lastFrameTime = performance.now();
let lastPaintTime = 0;
let historyTimer = 0;
const positionHistory: Array<{ time: number; position: number; target: number }> = [];

const settings: SensorSettings = {
  height: 15,
  angleDeg: 12,
  fov: 48,
  k1: -0.08,
  noise: 0.2,
};

const stageMeta: Record<Stage, { step: string; title: string; inspector: string }> = {
  overview: { step: "STEP 01", title: "视觉系统总览", inspector: "相机与钢球" },
  calibration: { step: "STEP 02", title: "像素标定采集", inspector: "相机与标定点" },
  mapping: { step: "STEP 03", title: "物理坐标映射", inspector: "映射模型与误差" },
  simulation: { step: "STEP 04", title: "闭环动态仿真", inspector: "控制器与扰动" },
};

function readNumber(id: string) {
  return Number(($(`#${id}`) as HTMLInputElement).value);
}

function updateSensorSettings() {
  settings.height = readNumber("camera-height");
  settings.angleDeg = readNumber("camera-angle");
  settings.fov = readNumber("camera-fov");
  settings.k1 = readNumber("camera-k1");
  settings.noise = readNumber("camera-noise");
  scene.setSensorSettings(settings);
  $("#camera-height-out").textContent = `${settings.height.toFixed(1)} cm`;
  $("#camera-angle-out").textContent = `${settings.angleDeg.toFixed(0)}°`;
  $("#camera-fov-out").textContent = `${settings.fov.toFixed(0)}°`;
  $("#camera-k1-out").textContent = settings.k1.toFixed(2);
  $("#camera-noise-out").textContent = `${settings.noise.toFixed(1)} px`;
  recalculateMapping();
}

function generateDefaultSamples() {
  samples = [-10, -5, 0, 5, 10].map((trueX) => {
    const [u, v] = scene.projectPhysicalPoint(trueX);
    return { id: nextSampleId++, trueX, u, v };
  });
  renderSampleTable();
  recalculateMapping();
}

function getMappingModel(): MappingModel {
  if (mappingMode === "linear") return fitLinear(samples);
  if (mappingMode === "projective") return fitProjective(samples);
  return fitHomography(scene.getRodImageCorners(), [
    [-12.5, -1],
    [12.5, -1],
    [12.5, 1],
    [-12.5, 1],
  ]);
}

function recalculateMapping() {
  try {
    mappingModel = getMappingModel();
    const stats = mappingStats(mappingModel, samples);
    $("#mapping-formula").textContent = mappingModel.formula;
    $("#metric-rmse").textContent = `${stats.rmse.toFixed(3)} cm`;
    $("#metric-max").textContent = `${stats.maxError.toFixed(3)} cm`;
    $("#mapping-state").textContent = "有效";
    $("#mapping-state").className = "state-good";
    $("#plot-value").textContent = `RMSE ${stats.rmse.toFixed(3)} cm`;
    scene.setCalibrationPositions(samples.map((sample) => sample.trueX));
  } catch (error) {
    mappingModel = { name: "无效", estimate: () => Number.NaN, formula: "标定点不足" };
    $("#mapping-formula").textContent = error instanceof Error ? error.message : "映射无效";
    $("#metric-rmse").textContent = "--";
    $("#metric-max").textContent = "--";
    $("#mapping-state").textContent = "无效";
    $("#mapping-state").className = "state-bad";
  }
}

function renderSampleTable() {
  const body = $("#sample-table");
  body.innerHTML = samples
    .map(
      (sample) => `
      <tr>
        <td>${sample.trueX >= 0 ? "+" : ""}${sample.trueX.toFixed(1)}</td>
        <td>${sample.u.toFixed(1)}</td>
        <td>${sample.v.toFixed(1)}</td>
        <td><button class="table-delete" data-delete-sample="${sample.id}" title="删除标定点">×</button></td>
      </tr>`,
    )
    .join("");
  $("#sample-count").textContent = `${samples.length} 点`;
  body.querySelectorAll<HTMLButtonElement>("[data-delete-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      samples = samples.filter((sample) => sample.id !== Number(button.dataset.deleteSample));
      renderSampleTable();
      recalculateMapping();
    });
  });
}

function setStage(nextStage: Stage) {
  stage = nextStage;
  $(".workspace").dataset.stage = stage;
  document.querySelectorAll<HTMLElement>("[data-stage]").forEach((element) => {
    element.classList.toggle("is-active", element.dataset.stage === stage);
  });
  const meta = stageMeta[stage];
  $("#stage-kicker").textContent = meta.step;
  $("#stage-title").textContent = meta.title;
  $("#inspector-title").textContent = meta.inspector;
  $("#plot-title").textContent = stage === "simulation" ? "位置响应" : "映射残差";
  if (stage !== "simulation") {
    simulation.running = false;
    updatePlayButton();
    scene.setRodTilt(0);
  }
}

function updateBallPosition(value: number, fromScene = false) {
  const clamped = Math.max(-12, Math.min(12, value));
  if (!fromScene) scene.setBallPosition(clamped);
  ($("#ball-x") as HTMLInputElement).value = clamped.toFixed(1);
  $("#ball-x-output").textContent = `${clamped.toFixed(2)} cm`;
  if (!simulation.running) simulation.reset(clamped);
}

function updatePlayButton() {
  const button = $("#sim-play");
  button.innerHTML = simulation.running
    ? '<i data-lucide="pause"></i><span>暂停</span>'
    : '<i data-lucide="play"></i><span>运行</span>';
  mountIcons(button);
}

function drawCameraPreview() {
  const ctx = previewContext;
  ctx.fillStyle = "#e8ebe5";
  ctx.fillRect(0, 0, 640, 480);
  ctx.strokeStyle = "#d0d5cd";
  ctx.lineWidth = 1;
  for (let x = 0; x <= 640; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 480); ctx.stroke();
  }
  for (let y = 0; y <= 480; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(640, y); ctx.stroke();
  }

  const corners = scene.getRodImageCorners();
  ctx.beginPath();
  corners.forEach(([u, v], index) => (index === 0 ? ctx.moveTo(u, v) : ctx.lineTo(u, v)));
  ctx.closePath();
  ctx.fillStyle = "#f7f8f4";
  ctx.fill();
  ctx.strokeStyle = "#20241f";
  ctx.lineWidth = 4;
  ctx.stroke();

  ctx.strokeStyle = "#747b73";
  ctx.lineWidth = 1;
  for (let x = -12; x <= 12; x += 1) {
    const [u1, v1] = scene.projectPhysicalPoint(x, 0.76, 0.53);
    const [u2, v2] = scene.projectPhysicalPoint(x, 1, 0.53);
    ctx.beginPath(); ctx.moveTo(u1, v1); ctx.lineTo(u2, v2); ctx.stroke();
  }

  samples.forEach((sample) => {
    ctx.strokeStyle = sample.trueX === 0 ? "#d79a26" : "#168958";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(sample.u - 5, sample.v); ctx.lineTo(sample.u + 5, sample.v);
    ctx.moveTo(sample.u, sample.v - 5); ctx.lineTo(sample.u, sample.v + 5);
    ctx.stroke();
  });

  const [ballU, ballV] = scene.projectPhysicalPoint(scene.getBallPosition());
  ctx.beginPath();
  ctx.arc(ballU, ballV, 10, 0, Math.PI * 2);
  ctx.fillStyle = "#d53f38";
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 3;
  ctx.stroke();
  ctx.fillStyle = "#171916";
  ctx.font = "18px system-ui";
  ctx.fillText(`u ${ballU.toFixed(1)}  v ${ballV.toFixed(1)}`, 18, 30);
}

function drawResidualPlot() {
  const ctx = plotContext;
  ctx.clearRect(0, 0, plot.width, plot.height);
  ctx.fillStyle = "#f4f5f1";
  ctx.fillRect(0, 0, plot.width, plot.height);
  ctx.strokeStyle = "#cbd0c8";
  ctx.beginPath(); ctx.moveTo(36, 90); ctx.lineTo(540, 90); ctx.stroke();

  if (stage === "simulation") {
    const recent = positionHistory.slice(-220);
    if (recent.length < 2) return;
    const drawSeries = (key: "position" | "target", color: string) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = key === "position" ? 3 : 2;
      ctx.beginPath();
      recent.forEach((point, index) => {
        const x = 36 + (index / Math.max(1, recent.length - 1)) * 504;
        const y = 90 - (point[key] / 12) * 70;
        index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
    };
    drawSeries("target", "#d49a2c");
    drawSeries("position", "#158b59");
    return;
  }

  if (!mappingModel) return;
  const stats = mappingStats(mappingModel, samples);
  samples.forEach((sample, index) => {
    const x = 36 + ((sample.trueX + 12) / 24) * 504;
    const y = 90 - (stats.errors[index] / 1.2) * 70;
    ctx.beginPath();
    ctx.arc(x, Math.max(14, Math.min(166, y)), 5, 0, Math.PI * 2);
    ctx.fillStyle = Math.abs(stats.errors[index]) <= 1 ? "#158b59" : "#d53f38";
    ctx.fill();
  });
}

function updateTelemetry() {
  const trueX = scene.getBallPosition();
  const [u, v] = scene.projectPhysicalPoint(trueX);
  const mapped = mappingModel?.estimate(u, v) ?? Number.NaN;
  const error = Math.abs(mapped - trueX);
  $("#telemetry-true").textContent = `${trueX.toFixed(2)} cm`;
  $("#telemetry-pixel").textContent = `${u.toFixed(1)}, ${v.toFixed(1)}`;
  $("#telemetry-mapped").textContent = Number.isFinite(mapped) ? `${mapped.toFixed(2)} cm` : "--";
  $("#telemetry-error").textContent = Number.isFinite(error) ? `${error.toFixed(3)} cm` : "--";
  const status = $("#telemetry-status");
  status.className = error <= 1 ? "good" : "bad";
  status.textContent = error <= 1 ? "映射有效" : "误差超限";
}

document.querySelectorAll<HTMLElement>("[data-stage]").forEach((element) => {
  element.addEventListener("click", () => setStage(element.dataset.stage as Stage));
});
document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    scene.setView(button.dataset.view as "perspective" | "top" | "side");
  });
});
document.querySelectorAll<HTMLButtonElement>("[data-mapping]").forEach((button) => {
  button.addEventListener("click", () => {
    mappingMode = button.dataset.mapping as MappingMode;
    document.querySelectorAll("[data-mapping]").forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    recalculateMapping();
  });
});

$("#ball-x").addEventListener("input", (event) => updateBallPosition(Number((event.target as HTMLInputElement).value)));
scene.onBallChange = (x) => updateBallPosition(x, true);
["camera-height", "camera-angle", "camera-fov", "camera-k1", "camera-noise"].forEach((id) => {
  $(`#${id}`).addEventListener("input", updateSensorSettings);
});
$("#capture-point").addEventListener("click", () => {
  const trueX = scene.getBallPosition();
  const [u, v] = scene.projectPhysicalPoint(trueX);
  samples.push({ id: nextSampleId++, trueX, u, v });
  samples.sort((left, right) => left.trueX - right.trueX);
  renderSampleTable();
  recalculateMapping();
});
$("#reset-samples").addEventListener("click", generateDefaultSamples);
$("#reset-view").addEventListener("click", () => scene.setView("perspective"));
$("#sim-play").addEventListener("click", () => {
  simulation.running = !simulation.running;
  updatePlayButton();
});
$("#sim-disturb").addEventListener("click", () => simulation.disturb());
$("#sim-reset").addEventListener("click", () => {
  simulation.running = false;
  simulation.reset(0);
  positionHistory.length = 0;
  scene.setRodTilt(0);
  updateBallPosition(0);
  updatePlayButton();
});
$("#sim-target").addEventListener("input", () => (simulation.config.target = readNumber("sim-target")));
$("#sim-kp").addEventListener("input", () => (simulation.config.kp = readNumber("sim-kp")));
$("#sim-kd").addEventListener("input", () => (simulation.config.kd = readNumber("sim-kd")));

function animate(now: number) {
  requestAnimationFrame(animate);
  // The virtual sensor is 120 FPS, while the teaching UI is intentionally
  // rendered at 30 Hz to leave CPU/GPU headroom for the real vision pipeline.
  if (now - lastPaintTime < 1000 / 30) return;
  lastPaintTime = now;
  const dt = Math.min(0.03, (now - lastFrameTime) / 1000);
  lastFrameTime = now;
  if (stage === "simulation") {
    const state = simulation.update(dt);
    scene.setBallPosition(state.position);
    scene.setRodTilt(state.tiltDeg);
    ($("#ball-x") as HTMLInputElement).value = state.position.toFixed(1);
    $("#ball-x-output").textContent = `${state.position.toFixed(2)} cm`;
    historyTimer += dt;
    if (historyTimer >= 0.05) {
      historyTimer = 0;
      positionHistory.push({ time: now, position: state.position, target: simulation.config.target });
      if (positionHistory.length > 300) positionHistory.shift();
    }
    $("#plot-value").textContent = `x ${state.position.toFixed(2)} cm`;
  }
  scene.render();
  drawCameraPreview();
  drawResidualPlot();
  updateTelemetry();
}

scene.setSensorSettings(settings);
generateDefaultSamples();
updateBallPosition(0);
setStage("overview");
requestAnimationFrame(animate);

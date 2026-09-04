import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

// --------------------------------------------------------------------------- //
// scene
// --------------------------------------------------------------------------- //
const canvas = document.getElementById("stage");
const fallbackEl = document.getElementById("fallback");
const hintEl = document.getElementById("hint");

const renderer = new THREE.WebGLRenderer({
  canvas, alpha: true, antialias: true, premultipliedAlpha: false,
});
renderer.setClearColor(0x000000, 0);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
camera.position.set(0, 1.35, 4.2);
camera.lookAt(0, 1.15, 0);

scene.add(new THREE.HemisphereLight(0xffffff, 0x333944, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(2.5, 4, 3);
scene.add(key);
const rim = new THREE.DirectionalLight(0x88b4ff, 0.9);
rim.position.set(-3, 2, -2.5);
scene.add(rim);

// --------------------------------------------------------------------------- //
// model
// --------------------------------------------------------------------------- //
const loader = new GLTFLoader();
let root = null;               // THREE.Group we translate/scale
let mixer = null;
const spineBones = [];
let headBone = null;
const lightMats = [];          // emissive "Lights" materials
let baseY = 0;
let userScale = 1;

function clearModel() {
  if (root) {
    scene.remove(root);
    root.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) [].concat(o.material).forEach((m) => m.dispose());
    });
  }
  root = null;
  mixer = null;
  spineBones.length = 0;
  headBone = null;
  lightMats.length = 0;
}

function loadModel(pathStr) {
  if (!pathStr) {
    showFallback(true);
    return;
  }
  const norm = pathStr.replace(/\\/g, "/");
  const url = /^([a-zA-Z]:|\/)/.test(norm)
    ? "file:///" + encodeURI(norm.replace(/^\//, ""))
    : encodeURI(norm);
  loader.load(
    url,
    (gltf) => {
      clearModel();
      const model = gltf.scene;

      // --- up-axis: this robot (and many Blender/Sketchfab GLBs) come in
      // Z-up / lying down. If depth dominates height, stand it up. ---
      let box = new THREE.Box3().setFromObject(model);
      let size = box.getSize(new THREE.Vector3());
      if (size.z > size.y * 1.4) {
        model.rotation.x = -Math.PI / 2;
        box = new THREE.Box3().setFromObject(model);
        size = box.getSize(new THREE.Vector3());
      }

      // --- centre on X/Z, feet at y=0, scale to a target height ---
      const center = box.getCenter(new THREE.Vector3());
      const targetH = 1.7;
      const s = (targetH / (size.y || 1));
      root = new THREE.Group();
      model.position.set(-center.x, -box.min.y, -center.z);
      root.add(model);
      root.userData._baseScale = s;      // the fit-to-view scale
      root.scale.setScalar(s * userScale);
      scene.add(root);
      baseY = 0;

      // --- rig + emissive discovery ---
      model.traverse((o) => {
        if (o.isBone) {
          const n = o.name.toLowerCase();
          if (n.includes("spine")) spineBones.push(o);
          // Rigify: spine.006 is the head
          if (n.includes("spine.006") || n.includes("head") || n.includes("neck")) {
            headBone = headBone || o;
          }
        }
        if (o.isMesh && o.material) {
          const mats = [].concat(o.material);
          for (const m of mats) {
            const isLights =
              (o.name && o.name.toLowerCase().includes("light")) ||
              (m.name && m.name.toLowerCase().includes("light"));
            if (isLights && m.color) {
              m.emissive = m.color.clone();
              m.emissiveIntensity = 0.4;
              m.toneMapped = false;
              lightMats.push(m);
            }
          }
        }
      });
      spineBones.sort((a, b) => a.name.localeCompare(b.name));

      if (gltf.animations && gltf.animations.length) {
        // The bundled clip is usually just the rest pose; only play it if it
        // actually has multiple keyframes.
        const clip = gltf.animations[0];
        const long = clip.tracks.some((t) => t.times.length > 2);
        if (long) {
          mixer = new THREE.AnimationMixer(model);
          mixer.clipAction(clip).play();
        }
      }

      showFallback(false);
    },
    undefined,
    (err) => {
      console.error("[overlay] model load failed:", err);
      showFallback(true);
    }
  );
}

// --------------------------------------------------------------------------- //
// state from the signal bus
// --------------------------------------------------------------------------- //
let busState = "idle";
let busRms = 0;
let lastBusAt = 0;

let reducedMotion = false;

// smoothed animation drivers
let glow = 0.4;          // emissive intensity
let speakEnergy = 0;     // 0..1, smoothed rms
let headYaw = 0, headPitch = 0;

function applyState(dt, t) {
  const stale = performance.now() - lastBusAt > 3000;
  const st = stale ? "idle" : busState;

  // target glow per state
  let glowTarget = 0.4;
  if (st === "listening") glowTarget = 0.95;
  else if (st === "thinking") glowTarget = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(t * 4));
  else if (st === "speaking") {
    speakEnergy += ((stale ? 0 : busRms) - speakEnergy) *
      Math.min(1, dt * (busRms > speakEnergy ? 22 : 9)); // fast attack, slow release
    glowTarget = 0.5 + speakEnergy * 3.2;
  } else {
    speakEnergy += (0 - speakEnergy) * Math.min(1, dt * 6);
  }
  glow += (glowTarget - glow) * Math.min(1, dt * 12);
  for (const m of lightMats) m.emissiveIntensity = glow;

  if (reducedMotion || !root) {
    updateFallback(st, glow);
    return;
  }

  // idle breathing + sway
  const breathe = Math.sin(t * 0.9) * 0.012;
  root.position.y = baseY + breathe + speakEnergy * 0.02;
  for (let i = 0; i < spineBones.length; i++) {
    const b = spineBones[i];
    if (b.userData._rest === undefined) b.userData._rest = b.rotation.z;
    b.rotation.z = b.userData._rest + Math.sin(t * 0.6 + i * 0.7) * 0.006;
  }

  // head: gentle wander when idle, small nod bursts when speaking, tilt to
  // "camera" when listening
  let yawT = Math.sin(t * 0.23) * 0.10;
  let pitchT = Math.sin(t * 0.31) * 0.05;
  if (st === "speaking") pitchT += speakEnergy * 0.18 * Math.sin(t * 9);
  if (st === "listening") { yawT *= 0.3; pitchT = 0.12; }
  headYaw += (yawT - headYaw) * Math.min(1, dt * 4);
  headPitch += (pitchT - headPitch) * Math.min(1, dt * 6);
  if (headBone) {
    if (headBone.userData._ry === undefined) {
      headBone.userData._ry = headBone.rotation.y;
      headBone.userData._rx = headBone.rotation.x;
    }
    headBone.rotation.y = headBone.userData._ry + headYaw;
    headBone.rotation.x = headBone.userData._rx + headPitch;
  }
}

// --------------------------------------------------------------------------- //
// fallback orb
// --------------------------------------------------------------------------- //
let usingFallback = false;
function showFallback(on) {
  usingFallback = on;
  fallbackEl.hidden = !on;
  canvas.style.visibility = on ? "hidden" : "visible";
}
function updateFallback(st, g) {
  const orb = fallbackEl.firstElementChild;
  if (!orb) return;
  const scale = 1 + (st === "speaking" ? speakEnergy * 0.35 : 0);
  orb.style.transform = `scale(${scale.toFixed(3)})`;
  orb.style.boxShadow = `0 0 ${20 + g * 40}px ${4 + g * 10}px rgba(60,220,170,0.35)`;
  orb.style.filter = st === "listening" ? "hue-rotate(-25deg)" : "none";
}

// --------------------------------------------------------------------------- //
// render loop
// --------------------------------------------------------------------------- //
const clock = new THREE.Clock();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;
  if (mixer) mixer.update(dt);
  applyState(dt, t);
  if (!usingFallback) renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize);

// --------------------------------------------------------------------------- //
// interaction: hit-test -> click-through toggle, drag, scroll-scale
// --------------------------------------------------------------------------- //
const raycaster = new THREE.Raycaster();
const ndc = new THREE.Vector2();
let overAvatar = false;
let dragging = false;

function hitTest(ev) {
  if (usingFallback) {
    // rough circular hitbox in the middle of the window
    const cx = innerWidth / 2, cy = innerHeight / 2;
    return Math.hypot(ev.clientX - cx, ev.clientY - cy) < 90;
  }
  if (!root) return false;
  ndc.x = (ev.clientX / innerWidth) * 2 - 1;
  ndc.y = -(ev.clientY / innerHeight) * 2 + 1;
  raycaster.setFromCamera(ndc, camera);
  return raycaster.intersectObject(root, true).length > 0;
}

addEventListener("pointermove", (ev) => {
  if (dragging) {
    window.overlay.dragBy(ev.movementX, ev.movementY);
    return;
  }
  const over = hitTest(ev);
  if (over !== overAvatar) {
    overAvatar = over;
    window.overlay.setInteractive(over);
    canvas.style.cursor = over ? "grab" : "default";
    hintEl.classList.toggle("show", over);
  }
});

addEventListener("pointerdown", (ev) => {
  if (!hitTest(ev)) return;
  dragging = true;
  canvas.style.cursor = "grabbing";
});
addEventListener("pointerup", () => {
  if (dragging) {
    dragging = false;
    canvas.style.cursor = overAvatar ? "grab" : "default";
    window.overlay.saveBounds();
  }
});

addEventListener("wheel", (ev) => {
  if (!overAvatar && !dragging) return;
  ev.preventDefault();
  window.overlay.nudgeScale(ev.deltaY < 0 ? 1 : -1);
}, { passive: false });

// --------------------------------------------------------------------------- //
// wire-up
// --------------------------------------------------------------------------- //
function applyScale(s) {
  userScale = s || 1;
  if (root && root.userData._baseScale) {
    root.scale.setScalar(root.userData._baseScale * userScale);
  }
}

window.overlay.onBus((snap) => {
  busState = snap.state || "idle";
  busRms = snap.rms || 0;
  lastBusAt = performance.now();
});
window.overlay.onLoadModel((p) => loadModel(p));
window.overlay.onSetScale((s) => applyScale(s));
window.overlay.onReducedMotion((v) => { reducedMotion = v; });

(async () => {
  const c = await window.overlay.getConfig();
  reducedMotion = !!c.reducedMotion;
  userScale = c.modelScale || 1;   // applied inside loadModel's callback
  resize();
  frame();
  loadModel(c.modelPath);
})();

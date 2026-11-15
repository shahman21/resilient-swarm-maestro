import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

const overlay = document.querySelector('#lattice');
const dock = document.querySelector('#latticeControls');
const byId = id => document.getElementById(id);
const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(0, 1, 0, 1, 0.1, 4000);
camera.position.z = 1000;
const renderer = new THREE.WebGLRenderer({ canvas: overlay, alpha: true, antialias: true });
renderer.setClearColor(0, 0);
const count = 144;
const shapes = ['Crystal Sphere', 'Helical Lattice', 'Fractal Web'];
const palette = ['#32dfff', '#59ffac', '#ffac56', '#bd91ff', '#ff618e', '#eaf3ff'];
const swatches = byId('latticeColors');
const targetColor = new THREE.Color(palette[0]);
const glow = document.createElement('canvas');
glow.width = glow.height = 48;
const ink = glow.getContext('2d');
const gradient = ink.createRadialGradient(24, 24, 0, 24, 24, 24);
gradient.addColorStop(0, '#fff');
gradient.addColorStop(0.18, '#ffffffdd');
gradient.addColorStop(1, '#ffffff00');
ink.fillStyle = gradient;
ink.fillRect(0, 0, 48, 48);
const texture = new THREE.CanvasTexture(glow);
const pointsMaterial = new THREE.PointsMaterial({
  map: texture, color: targetColor.clone(), size: 7, transparent: true,
  depthWrite: false, blending: THREE.AdditiveBlending,
});
const lineMaterial = new THREE.LineBasicMaterial({
  color: targetColor.clone(), transparent: true, opacity: 0.32, depthWrite: false,
  blending: THREE.AdditiveBlending,
});
const fibonacciAngle = Math.PI * (3 - Math.sqrt(5));
const topologies = shapes.map((_, shape) => Array.from({ length: count }, (_, i) => {
  const t = i / (count - 1);
  if (shape === 0) {
    const y = 1 - 2 * t;
    const radius = Math.sqrt(1 - y * y);
    return new THREE.Vector3(radius * Math.cos(i * fibonacciAngle), y, radius * Math.sin(i * fibonacciAngle));
  }
  if (shape === 1) {
    const angle = 2 * Math.PI * (t * 2.5 + (i % 3) / 3);
    return new THREE.Vector3(0.64 * Math.cos(angle), 2 * t - 1, 0.64 * Math.sin(angle));
  }
  const branch = i % 6;
  const depth = Math.floor(i / 6) / (count / 6 - 1);
  const angle = branch * Math.PI / 3 + 0.42 * Math.sin(i * 1.7) * depth;
  return new THREE.Vector3(depth * Math.cos(angle), depth * Math.sin(angle), Math.sin(i * 2) * depth * 0.47);
}));
const robots = Array.from({ length: 4 }, () => {
  const group = new THREE.Group();
  scene.add(group);
  const cloud = new THREE.BufferGeometry();
  const nodes = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
  cloud.setAttribute('position', nodes);
  const edges = new THREE.BufferGeometry();
  const links = new THREE.BufferAttribute(new Float32Array(count * 12), 3);
  edges.setAttribute('position', links);
  const points = new THREE.Points(cloud, pointsMaterial);
  const lines = new THREE.LineSegments(edges, lineMaterial);
  points.frustumCulled = lines.frustumCulled = false;
  group.add(points, lines);
  return { group, cloud, edges, nodes, links };
});

let shape = 0, colorIndex = 0, frozen = false, angle = 0;
let view = 'swarm';
const globeScales = [1, 0.92, 0.74, 0.56];
let width = 0, height = 0, scale = 0, beatEnergy = 0, previous = 0;
let viewX = 0, viewY = 0;
const positions = topologies[0].map(point => point.clone());
const density = byId('latticeDensity');
const waves = [];
const morph = byId('latticeMorph');
const freeze = byId('latticeFreeze');
const reset = byId('latticeReset');
const focus = byId('latticeFocus');
const stage = overlay.parentElement;
function switchView(nextView) {
  view = view === nextView ? 'swarm' : nextView;
  stage.classList.toggle('globe-view', view === 'globe');
  focus.setAttribute('aria-pressed', String(view === 'globe'));
  focus.textContent = view === 'globe' ? 'Swarm View' : 'Globe View';
  if (view === 'globe' && shape !== 0) {
    shape = 0;
    morph.textContent = 'Morph · ' + shapes[shape];
  }
}
focus.onclick = () => switchView('globe');
function changeShape() {
  shape = (shape + 1) % shapes.length;
  morph.textContent = 'Morph · ' + shapes[shape];
}
function changeColor(index) {
  colorIndex = index;
  targetColor.set(palette[index]);
  Array.from(swatches.children).forEach((button, i) => button.setAttribute('aria-pressed', i === index));
}
palette.forEach((color, i) => {
  const button = document.createElement('button');
  button.type = 'button';
  button.style.backgroundColor = color;
  button.setAttribute('aria-label', ['Cyan', 'Green', 'Orange', 'Violet', 'Rose', 'Frost'][i]);
  button.onclick = () => changeColor(i);
  swatches.append(button);
});
changeColor(0);
morph.onclick = changeShape;
freeze.onclick = () => {
  frozen = !frozen;
  freeze.textContent = frozen ? 'Play Visuals' : 'Freeze Visuals';
  freeze.setAttribute('aria-pressed', frozen);
};
reset.onclick = () => { angle = viewX = viewY = 0; };
const arena = byId('arena');
let drag = null;
arena.addEventListener('pointerdown', event => {
  if (!event.isPrimary || event.button !== 0) return;
  drag = { x: event.clientX, y: event.clientY, viewX, viewY, moved: false };
  arena.setPointerCapture(event.pointerId);
});
arena.addEventListener('pointermove', event => {
  if (!drag || !event.isPrimary) return;
  const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
  drag.moved ||= Math.hypot(dx, dy) > 6;
  if (drag.moved) {
    viewX = drag.viewX + dy * 0.012;
    viewY = drag.viewY + dx * 0.012;
  }
});
arena.addEventListener('pointerup', event => {
  if (!event.isPrimary || !drag) return;
  if (!drag.moved) {
    const rect = overlay.getBoundingClientRect();
    waves.push({ x: event.clientX - rect.left, y: event.clientY - rect.top, start: performance.now() });
    if (waves.length > 6) waves.shift();
  }
  drag = null;
});
arena.addEventListener('lostpointercapture', () => { drag = null; });
const ringGeometry = new THREE.RingGeometry(0.97, 1, 64);
const rings = Array.from({ length: 6 }, () => {
  const material = new THREE.MeshBasicMaterial({
    color: 0x76eaff, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });
  const ring = new THREE.Mesh(ringGeometry, material);
  scene.add(ring);
  return ring;
});

window.renderSwarmLattice = (now, beat) => {
  const globeView = view === 'globe';
  const rect = overlay.getBoundingClientRect();
  const ratio = Math.min(devicePixelRatio || 1, 2);
  if (!rect.width || !rect.height) return false;
  if (width !== rect.width || height !== rect.height || scale !== ratio) {
    width = rect.width;
    height = rect.height;
    scale = ratio;
    renderer.setPixelRatio(scale);
    renderer.setSize(width, height, false);
    camera.right = width;
    camera.bottom = height;
    camera.updateProjectionMatrix();
  }
  const dt = Math.max(0, Math.min(0.05, (now - previous) / 1000));
  previous = now;
  const blend = 1 - Math.exp(-dt * 8);
  if (!frozen) {
    angle += dt * 0.64;
    beatEnergy = (1 - beat) ** 3;
  }
  pointsMaterial.color.lerp(targetColor, blend);
  lineMaterial.color.copy(pointsMaterial.color);
  pointsMaterial.size = globeView ? 9 + 5 * beatEnergy : 5 + 3 * beatEnergy;
  lineMaterial.opacity = globeView ? 0.14 + 0.22 * beatEnergy : 0.19 + 0.28 * beatEnergy;
  const visible = Math.round(count * Number(density.value) / 100);
  positions.forEach((point, i) => point.lerp(topologies[shape][i], blend));
  const shortSide = Math.min(width, height);
  const radius = shortSide * 0.43;
  robots.forEach(({ group, cloud, edges, nodes, links }, index) => {
    group.visible = globeView;
    if (!globeView) return;
    group.position.set(width / 2, height / 2, 0);
    group.rotation.set(0.45 + index * 0.22 + viewX, angle + index * 1.2 + viewY, angle * 0.46);
    group.scale.setScalar(radius * globeScales[index] * (1 + 0.09 * beatEnergy));
    const pointAt = index => positions[Math.floor((index % visible) * count / visible)];
    for (let i = 0; i < visible; i++) {
      const point = pointAt(i);
      const near = pointAt(i + 1);
      const far = pointAt(i + 6);
      nodes.setXYZ(i, point.x, point.y, point.z);
      links.setXYZ(i * 4, point.x, point.y, point.z);
      links.setXYZ(i * 4 + 1, near.x, near.y, near.z);
      links.setXYZ(i * 4 + 2, point.x, point.y, point.z);
      links.setXYZ(i * 4 + 3, far.x, far.y, far.z);
    }
    cloud.setDrawRange(0, visible);
    edges.setDrawRange(0, visible * 4);
    nodes.needsUpdate = links.needsUpdate = true;
  });
  while (waves.length && now - waves[0].start > 1000) waves.shift();
  rings.forEach((ring, i) => {
    const wave = waves[i];
    ring.visible = Boolean(wave);
    if (!wave) return;
    const progress = Math.max(0, (now - wave.start) / 1000);
    ring.position.set(wave.x, wave.y, 120);
    ring.scale.setScalar(4 + progress * Math.min(width, height) * 0.74);
    ring.material.opacity = (1 - progress) * 0.8;
  });
  if (renderer.getContext().isContextLost()) return false;
  renderer.render(scene, camera);
  return globeView;
};
dock.hidden = false;

const gestureButton = byId('latticeGestures');
const preview = byId('latticePreview');
const video = byId('latticeVideo');
const status = byId('latticeGestureStatus');
const dragHandle = byId('latticeDrag');
let stream = null, modelPromise = null, session = 0;

dragHandle.onpointerdown = event => {
  const start = preview.getBoundingClientRect();
  dragHandle.setPointerCapture(event.pointerId);
  dragHandle.onpointermove = move => {
    preview.style.left = Math.max(0, Math.min(innerWidth - start.width, start.left + move.clientX - event.clientX)) + 'px';
    preview.style.top = Math.max(0, Math.min(innerHeight - start.height, start.top + move.clientY - event.clientY)) + 'px';
    preview.style.bottom = 'auto';
  };
  dragHandle.onlostpointercapture = () => { dragHandle.onpointermove = null; };
};

async function loadModel() {
  const base = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21';
  const { FilesetResolver, HandLandmarker } = await import(base + '/vision_bundle.mjs');
  const vision = await FilesetResolver.forVisionTasks(base + '/wasm');
  return HandLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
    },
    runningMode: 'VIDEO',
    numHands: 1,
  });
}

function stopCamera() {
  session++;
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  video.srcObject = null;
  preview.hidden = true;
  gestureButton.textContent = 'Enable Gestures';
  gestureButton.setAttribute('aria-pressed', 'false');
}

function classify(hand) {
  if (!hand) return '';
  const distance = (a, b) => Math.hypot(hand[a].x - hand[b].x, hand[a].y - hand[b].y);
  const palm = distance(0, 9);
  if (palm < 0.01) return '';
  const extended = [8, 12, 16, 20].filter(tip => distance(0, tip) > 1.22 * distance(0, tip - 2)).length;
  if (extended === 0 && distance(4, 8) > palm * 0.26) return 'fist';
  if (distance(4, 8) < palm * 0.22 && extended >= 1) return 'pinch';
  if (extended === 4 && distance(4, 17) > palm * 0.82) return 'open';
  return '';
}

gestureButton.onclick = async () => {
  if (!preview.hidden) {
    stopCamera();
    status.textContent = '';
    return;
  }
  const current = ++session;
  preview.hidden = false;
  status.textContent = 'Starting camera and loading hand tracking…';
  gestureButton.textContent = 'Disable Gestures';
  gestureButton.setAttribute('aria-pressed', 'true');
  try {
    const cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 480 }, height: { ideal: 360 }, facingMode: 'user' }, audio: false,
    });
    if (current !== session) {
      cameraStream.getTracks().forEach(track => track.stop());
      return;
    }
    stream = cameraStream;
    video.srcObject = stream;
    await video.play();
    const model = await (modelPromise ||= loadModel().catch(error => { modelPromise = null; throw error; }));
    if (current !== session) return;
    status.textContent = 'Pinch to morph · Open palm for color · Fist to freeze';
    let sampledAt = 0, lastVideoTime = -1, candidate = '', candidateSince = 0;
    let latched = false, lastAction = -Infinity;
    function track(now) {
      if (current !== session) return;
      if (now - sampledAt >= 70 && video.readyState >= 2 && video.currentTime !== lastVideoTime) {
        sampledAt = now;
        lastVideoTime = video.currentTime;
        try {
          const pose = classify(model.detectForVideo(video, now).landmarks[0]);
          if (pose !== candidate) {
            candidate = pose;
            candidateSince = now;
          } else if (!pose && now - candidateSince >= 200) {
            latched = false;
          } else if (pose && !latched && now - candidateSince >= 180 && now - lastAction >= 700) {
            if (pose === 'pinch') changeShape();
            if (pose === 'open') changeColor((colorIndex + 1) % palette.length);
            if (pose === 'fist') freeze.click();
            latched = true;
            lastAction = now;
          }
        } catch (error) {
          stopCamera();
          status.textContent = 'Hand tracking stopped. Try enabling it again.';
          console.warn(error);
          return;
        }
      }
      requestAnimationFrame(track);
    }
    requestAnimationFrame(track);
  } catch (error) {
    if (current !== session) return;
    stopCamera();
    status.textContent = 'Camera or hand tracking unavailable. Check camera permission and internet access.';
    console.warn(error);
  }
};
addEventListener('pagehide', stopCamera);

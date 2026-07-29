import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export type SensorSettings = {
  height: number;
  angleDeg: number;
  fov: number;
  k1: number;
  noise: number;
};

export class WorkbenchScene {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly viewerCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 120);
  readonly sensorCamera = new THREE.PerspectiveCamera(48, 4 / 3, 0.1, 100);
  readonly controls: OrbitControls;
  readonly rodGroup = new THREE.Group();
  readonly ball: THREE.Mesh;
  readonly calibrationGroup = new THREE.Group();
  onBallChange?: (x: number) => void;

  private readonly host: HTMLElement;
  private readonly cameraBody: THREE.Group;
  private readonly accelerationArrow: THREE.ArrowHelper;
  private cameraHelper: THREE.CameraHelper;
  private ballX = 0;
  private settings: SensorSettings = { height: 15, angleDeg: 12, fov: 48, k1: -0.08, noise: 0.2 };
  private dragging = false;
  private readonly raycaster = new THREE.Raycaster();
  private readonly pointer = new THREE.Vector2();
  private readonly dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -0.82);

  constructor(host: HTMLElement) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x171a17, 1);
    this.renderer.shadowMap.enabled = !navigator.webdriver;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.dataset.testid = "three-canvas";
    host.appendChild(this.renderer.domElement);

    this.viewerCamera.position.set(18, 13, 20);
    this.viewerCamera.lookAt(0, 0, 0);
    this.controls = new OrbitControls(this.viewerCamera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0.5, 0);
    this.controls.minDistance = 10;
    this.controls.maxDistance = 52;
    this.controls.maxPolarAngle = Math.PI * 0.49;

    const hemisphere = new THREE.HemisphereLight(0xf2f0e8, 0x262b25, 2.2);
    this.scene.add(hemisphere);
    const keyLight = new THREE.DirectionalLight(0xffffff, 3.2);
    keyLight.position.set(-9, 16, 10);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(1024, 1024);
    this.scene.add(keyLight);
    const rim = new THREE.DirectionalLight(0x73c89a, 1.4);
    rim.position.set(12, 8, -10);
    this.scene.add(rim);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(80, 50),
      new THREE.MeshStandardMaterial({ color: 0x20241f, roughness: 0.98 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.72;
    ground.receiveShadow = true;
    this.scene.add(ground);
    const grid = new THREE.GridHelper(50, 50, 0x4b574b, 0x30362f);
    grid.position.y = -0.7;
    this.scene.add(grid);

    this.accelerationArrow = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(-4, 0.05, -3.2),
      4,
      0xf1b84b,
      0.7,
      0.35,
    );
    this.accelerationArrow.visible = false;
    this.scene.add(this.accelerationArrow);

    this.buildRod();
    this.ball = this.buildBall();
    this.rodGroup.add(this.ball);
    this.scene.add(this.rodGroup);
    this.scene.add(this.calibrationGroup);

    this.cameraBody = this.buildCameraBody();
    this.scene.add(this.cameraBody);
    this.cameraHelper = new THREE.CameraHelper(this.sensorCamera);
    this.scene.add(this.cameraHelper);
    this.setSensorSettings(this.settings);

    this.renderer.domElement.addEventListener("pointerdown", this.handlePointerDown);
    window.addEventListener("pointermove", this.handlePointerMove);
    window.addEventListener("pointerup", this.handlePointerUp);
    new ResizeObserver(() => this.resize()).observe(host);
    this.resize();
  }

  private buildRod() {
    const base = new THREE.Mesh(
      new THREE.BoxGeometry(25, 0.34, 2.15),
      new THREE.MeshStandardMaterial({ color: 0xd7d9d2, roughness: 0.62, metalness: 0.04 }),
    );
    base.castShadow = true;
    base.receiveShadow = true;
    this.rodGroup.add(base);

    const railGeometry = new THREE.CylinderGeometry(0.23, 0.23, 25, 32);
    const railMaterial = new THREE.MeshStandardMaterial({ color: 0xf0f1eb, roughness: 0.42 });
    for (const z of [-0.94, 0.94]) {
      const rail = new THREE.Mesh(railGeometry, railMaterial);
      rail.rotation.z = Math.PI / 2;
      rail.position.set(0, 0.34, z);
      rail.castShadow = true;
      this.rodGroup.add(rail);
    }

    const groove = new THREE.Mesh(
      new THREE.BoxGeometry(24.6, 0.08, 1.45),
      new THREE.MeshStandardMaterial({ color: 0x7b8179, roughness: 0.74 }),
    );
    groove.position.y = 0.24;
    this.rodGroup.add(groove);

    const tickMaterial = new THREE.LineBasicMaterial({ color: 0x252925 });
    const positions: number[] = [];
    for (let index = -125; index <= 125; index += 1) {
      const x = index / 10;
      const major = index % 10 === 0;
      const medium = index % 5 === 0;
      const length = major ? 0.52 : medium ? 0.35 : 0.2;
      positions.push(x, 0.52, 1.09, x, 0.52, 1.09 - length);
    }
    const tickGeometry = new THREE.BufferGeometry();
    tickGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    this.rodGroup.add(new THREE.LineSegments(tickGeometry, tickMaterial));

    const centerLine = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.05, 2.5),
      new THREE.MeshBasicMaterial({ color: 0xe04b42 }),
    );
    centerLine.position.y = 0.54;
    this.rodGroup.add(centerLine);

    const hinge = new THREE.Mesh(
      new THREE.CylinderGeometry(0.52, 0.52, 2.8, 32),
      new THREE.MeshStandardMaterial({ color: 0x40463f, metalness: 0.45, roughness: 0.38 }),
    );
    hinge.rotation.x = Math.PI / 2;
    hinge.position.set(0, -0.05, 0);
    this.rodGroup.add(hinge);
  }

  private buildBall() {
    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(0.5, 48, 32),
      new THREE.MeshStandardMaterial({ color: 0xbfc8c4, metalness: 0.92, roughness: 0.16 }),
    );
    ball.position.set(0, 0.82, 0);
    ball.castShadow = true;
    return ball;
  }

  private buildCameraBody() {
    const group = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(2.4, 1.25, 1.8),
      new THREE.MeshStandardMaterial({ color: 0x343936, metalness: 0.22, roughness: 0.55 }),
    );
    const lens = new THREE.Mesh(
      new THREE.CylinderGeometry(0.42, 0.52, 0.72, 32),
      new THREE.MeshStandardMaterial({ color: 0x101412, metalness: 0.7, roughness: 0.2 }),
    );
    lens.rotation.x = Math.PI / 2;
    lens.position.z = -1.15;
    group.add(body, lens);
    return group;
  }

  setSensorSettings(settings: SensorSettings) {
    this.settings = { ...settings };
    const angle = THREE.MathUtils.degToRad(settings.angleDeg);
    this.sensorCamera.fov = settings.fov;
    this.sensorCamera.aspect = 4 / 3;
    this.sensorCamera.position.set(0, settings.height, Math.tan(angle) * settings.height);
    this.sensorCamera.lookAt(0, 0.3, 0);
    this.sensorCamera.updateProjectionMatrix();
    this.sensorCamera.updateMatrixWorld(true);

    this.cameraBody.position.copy(this.sensorCamera.position);
    this.cameraBody.quaternion.copy(this.sensorCamera.quaternion);
    this.cameraHelper.update();
  }

  setBallPosition(x: number, notify = false) {
    this.ballX = Math.max(-12, Math.min(12, x));
    this.ball.position.x = this.ballX;
    if (notify) this.onBallChange?.(this.ballX);
  }

  getBallPosition() {
    return this.ballX;
  }

  setRodTilt(degrees: number) {
    // The model defines positive tilt as lowering the +x end of the rail.
    this.rodGroup.rotation.z = -THREE.MathUtils.degToRad(degrees);
  }

  setVehicleAcceleration(accelerationMps2: number) {
    const magnitude = Math.abs(accelerationMps2);
    this.accelerationArrow.visible = magnitude >= 0.01;
    if (!this.accelerationArrow.visible) return;
    this.accelerationArrow.setDirection(new THREE.Vector3(Math.sign(accelerationMps2), 0, 0));
    this.accelerationArrow.position.x = accelerationMps2 >= 0 ? -4 : 4;
    this.accelerationArrow.setLength(Math.min(7, 1.8 + magnitude * 1.5), 0.7, 0.35);
  }

  setCalibrationPositions(positions: number[]) {
    this.calibrationGroup.clear();
    const geometry = new THREE.SphereGeometry(0.13, 16, 12);
    positions.forEach((x, index) => {
      const marker = new THREE.Mesh(
        geometry,
        new THREE.MeshBasicMaterial({ color: index === Math.floor(positions.length / 2) ? 0xf1b84b : 0x45c482 }),
      );
      marker.position.set(x, 0.66, 1.32);
      this.calibrationGroup.add(marker);
    });
  }

  projectPhysicalPoint(x: number, z = 0, height = 0.82): [number, number] {
    const point = new THREE.Vector3(x, height, z).project(this.sensorCamera);
    let nx = point.x;
    let ny = point.y;
    const radiusSquared = nx * nx + ny * ny;
    const distortion = 1 + this.settings.k1 * radiusSquared;
    nx *= distortion;
    ny *= distortion;
    const noise = this.settings.noise * Math.sin(x * 4.17 + z * 3.1);
    return [((nx + 1) * 0.5) * 640 + noise, ((1 - ny) * 0.5) * 480 - noise * 0.45];
  }

  getRodImageCorners(): Array<[number, number]> {
    return [
      this.projectPhysicalPoint(-12.5, -1, 0.5),
      this.projectPhysicalPoint(12.5, -1, 0.5),
      this.projectPhysicalPoint(12.5, 1, 0.5),
      this.projectPhysicalPoint(-12.5, 1, 0.5),
    ];
  }

  setView(view: "perspective" | "top" | "side") {
    const positions = {
      perspective: new THREE.Vector3(18, 13, 20),
      top: new THREE.Vector3(0, 30, 0.01),
      side: new THREE.Vector3(0, 5.5, 30),
    };
    this.viewerCamera.position.copy(positions[view]);
    this.controls.target.set(0, 0.5, 0);
    this.controls.update();
  }

  render() {
    this.controls.update();
    this.renderer.render(this.scene, this.viewerCamera);
  }

  private resize() {
    const width = Math.max(1, this.host.clientWidth);
    const height = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(width, height, false);
    this.viewerCamera.aspect = width / height;
    this.viewerCamera.updateProjectionMatrix();
  }

  private updatePointer = (event: PointerEvent) => {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.viewerCamera);
  };

  private handlePointerDown = (event: PointerEvent) => {
    this.updatePointer(event);
    if (this.raycaster.intersectObject(this.ball).length > 0) {
      this.dragging = true;
      this.controls.enabled = false;
      this.renderer.domElement.setPointerCapture(event.pointerId);
    }
  };

  private handlePointerMove = (event: PointerEvent) => {
    if (!this.dragging) return;
    this.updatePointer(event);
    const point = new THREE.Vector3();
    if (this.raycaster.ray.intersectPlane(this.dragPlane, point)) {
      this.setBallPosition(point.x, true);
    }
  };

  private handlePointerUp = () => {
    this.dragging = false;
    this.controls.enabled = true;
  };
}

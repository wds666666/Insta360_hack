import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

type Props = {
  src: string | null;
  meter: string | null;
  flowing: boolean;
  onContinue: (() => void) | null;
};

export function GlbViewer({ src, meter, flowing, onContinue }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!src) {
      setMessage("");
    }
  }, [src]);

  useEffect(() => {
    const element = host.current;
    if (!element || !src) {
      return;
    }

    setMessage("正在打开空间地图");
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(element.clientWidth, element.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const bay = getComputedStyle(document.documentElement).getPropertyValue("--bay").trim();
    scene.background = new THREE.Color(bay || "#e6dfd4");
    const camera = new THREE.PerspectiveCamera(40, element.clientWidth / Math.max(element.clientHeight, 1), 0.01, 1000);
    camera.position.set(1.6, 1.2, 1.8);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(new THREE.AmbientLight("#f4f7f5", 0.85));
    const key = new THREE.DirectionalLight("#fffaf2", 1.4);
    key.position.set(3, 5, 2);
    scene.add(key);
    const fill = new THREE.DirectionalLight("#d5e2ea", 0.45);
    fill.position.set(-3, 2, -2);
    scene.add(fill);

    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const envMap = pmrem.fromScene(room, 0.04).texture;
    room.dispose();
    scene.environment = envMap;
    pmrem.dispose();

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const loader = new GLTFLoader();
    let model: THREE.Object3D | null = null;
    loader.load(
      src,
      (gltf) => {
        model = gltf.scene;
        model.traverse((child) => {
          if (!(child instanceof THREE.Mesh)) {
            return;
          }
          const materials = Array.isArray(child.material) ? child.material : [child.material];
          for (const material of materials) {
            material.side = THREE.DoubleSide;
          }
        });
        scene.add(model);
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const radius = Math.max(size.x, size.y, size.z) * 0.8 || 1;
        controls.target.copy(center);
        camera.position.set(center.x + radius, center.y + radius * 0.7, center.z + radius);
        camera.near = radius / 100;
        camera.far = radius * 20;
        camera.updateProjectionMatrix();
        controls.update();
        setMessage("");
      },
      undefined,
        () => setMessage("空间地图没有打开"),
    );

    const resize = () => {
      const width = element.clientWidth;
      const height = Math.max(element.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      if (model) {
        model.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.geometry.dispose();
            const materials = Array.isArray(child.material) ? child.material : [child.material];
            for (const material of materials) {
              material.dispose();
            }
          }
        });
        scene.remove(model);
      }
      envMap.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [src]);

  return (
    <section className="viewer" aria-label="三维模型">
      <header>
        <h2>触觉模型</h2>
        <p>视障者摸到的是同一份形状。拖动可以转动，滚轮可以拉近。</p>
      </header>
      <div className={flowing ? "viewer-frame is-live" : "viewer-frame"}>
        <div className="viewer-bay" ref={host} />
        {onContinue && !src ? (
          <div className="viewer-continue">
            <p>优化图已经好了。要按这张图生成可触摸的模型吗？</p>
            <button className="submit" type="button" onClick={onContinue}>
              用这张图生成触觉模型
            </button>
          </div>
        ) : null}
        {message ? <p className="muted viewer-note">{message}</p> : null}
        {!src && !onContinue && !message && !meter ? <p className="muted viewer-note">触觉模型还在生成</p> : null}
        {meter ? (
          <div className={flowing ? "viewer-meter is-live" : "viewer-meter"}>
            <span className="viewer-meter-flow" aria-hidden="true" />
            <span>{meter}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

/**
 * 3D 沙盘垃圾图层
 *
 * 三类要素，均为"发光的点 + 向天空射出的光柱线"：
 *   - 海浮垃圾：近岸/海湾水面，随海水缓慢漂移并严格骑在波面上起伏
 *   - 沙滩垃圾：贴着水线的低平海岸带，静态微闪
 *   - 光柱线：每个垃圾向天空射出一条 2~3.4km 的细线（底部亮、顶部渐隐），
 *     远看是"从海面/滩涂射向天空的信号线"，与事件光柱同一套发光语言
 *
 * 不同垃圾类别不同颜色（与事件标记/事件中心同一套类别与配色）：
 *   泡沫=橙 / 塑料=蓝 / 渔具=红 / 其他=灰 —— 点色与光柱同色。
 *
 * 为什么用 Points 而不是 InstancedMesh：
 *   165km 场景下真实尺寸的垃圾不足一个像素；Points 的 gl_PointSize 能给出
 *   "最小像素尺寸"保证任何视距都可见，这是地图类应用标注光点的通行做法。
 *   拾取用 raycaster 的 Points.threshold（阈值按视距自适应，见 InteractionLayer）。
 *
 * 坐标为程序化撒点（确定性随机：种子固定，刷新后位置不跳变）。
 */

import * as THREE from 'three'
import { lngLatToScene, seaWaveHeight } from './TerrainLayer.js'

// 垃圾分类：与事件标记（InteractionLayer colorMap）保持同色，
// 沙盘上"哪里有哪类垃圾"与事件中心的类别配色一致
const DEBRIS_CLASSES = [
  { key: 'foam', hex: 0xff9500, label: '泡沫类' },
  { key: 'plastic', hex: 0x007aff, label: '塑料类' },
  { key: 'fishing_gear', hex: 0xff3b30, label: '渔具类' },
  { key: 'other', hex: 0x8e8e93, label: '其他垃圾' },
]
// 类别权重：海漂以塑料/泡沫为主，渔具类少量（更贴近监测统计）
const CLASS_WEIGHTS = [0.34, 0.36, 0.2, 0.1]

const HDR_GAIN = 2.2 // 点核心亮度增益（越过泛光阈值 → 发光）
const BEAM_GAIN = 1.8 // 光柱底部亮度；顶部渐变到几乎全黑（加法混合里=透明）
const BEAM_MIN_H = 2000 // 光柱高度（米）
const BEAM_MAX_H = 3400

// 撒点数量与判定阈值
const FLOATING_COUNT = 260 // 海浮垃圾点数
const BEACH_COUNT = 150 //    沙滩垃圾点数
const NEAR_LAND_RADIUS = 9000 // 海浮垃圾要求 9km 内有陆地（近岸/海湾聚集）
const SHORE_RADIUS = 700 //  沙滩垃圾要求 700m 内有水（贴着水线分布，不在内陆）
const BEACH_MIN_H = 1
const BEACH_MAX_H = 45
const MARGIN = 6000 // 距地形边界留白（米），避免贴边

const POINT_VERT = `
attribute float aSize;
attribute float aPhase;
attribute vec3 aColor;
uniform float uTime;
uniform float uPixelRatio;
varying float vGlow;
varying vec3 vColor;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float dist = max(-mv.z, 1.0);
  // 距离衰减 + 像素上下限：全景下保留可见的最小亮点，近景放大成柔和光斑
  float px = aSize * (6.6e5 / dist);
  gl_PointSize = clamp(px, 3.0, 18.0) * uPixelRatio;
  // 呼吸：每点相位不同，整片垃圾看起来"活的"而不是贴图
  vGlow = 0.68 + 0.32 * sin(uTime * 2.1 + aPhase);
  vColor = aColor;
  gl_Position = projectionMatrix * mv;
}
`

const POINT_FRAG = `
varying float vGlow;
varying vec3 vColor;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d) * 4.0; // 0=中心 1=边缘
  if (r > 1.0) discard;
  float halo = pow(1.0 - r, 2.2);      // 外圈辉光
  float core = smoothstep(0.28, 0.0, r); // 核心锐点
  float a = halo * 0.55 + core * 0.85;
  vec3 col = vColor * (1.0 + core * 2.4); // 核心过亮 → 泛光下形成光晕
  gl_FragColor = vec4(col * vGlow, a * vGlow);
}
`

/** 确定性 LCG（固定种子 → 每次刷新垃圾分布一致，不会"跳来跳去"） */
function makeRng(seed) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

/** 按权重抽一个类别下标 */
function pickClassIndex(rng) {
  let r = rng()
  for (let i = 0; i < CLASS_WEIGHTS.length; i += 1) {
    r -= CLASS_WEIGHTS[i]
    if (r <= 0) return i
  }
  return CLASS_WEIGHTS.length - 1
}

/** 半径为 radius 的一圈上是否有陆地（海浮垃圾"近岸聚集"的判定） */
function hasLandNear(sampleHeight, x, z, radius) {
  for (let i = 0; i < 8; i += 1) {
    const a = (i / 8) * Math.PI * 2
    if (sampleHeight(x + Math.cos(a) * radius, z + Math.sin(a) * radius) > 3) return true
  }
  return false
}

/** 半径为 radius 的一圈上是否有水（沙滩垃圾"贴水线"的判定） */
function hasWaterNear(sampleHeight, x, z, radius) {
  for (let i = 0; i < 8; i += 1) {
    const a = (i / 8) * Math.PI * 2
    if (sampleHeight(x + Math.cos(a) * radius, z + Math.sin(a) * radius) <= -20) return true
  }
  return false
}

export class DebrisLayer {
  /**
   * @param {THREE.Scene} scene
   * @param {Object} options
   * @param {Function} options.sampleHeight 世界 (x,z) → 地形高度（米），海面 -30
   * @param {Object} options.bounds 地形世界范围 { minX, minZ, sizeX, sizeZ }
   */
  constructor(scene, { sampleHeight, bounds } = {}) {
    this.scene = scene
    this.sampleHeight = sampleHeight
    this.bounds = bounds
    this.group = new THREE.Group()
    this.group.name = 'debris'
    scene.add(this.group)

    this.floating = null // 海浮垃圾点
    this.beach = null //    沙滩垃圾点
    this.floatingBeams = null // 海浮垃圾光柱
    this.beachBeams = null //    沙滩垃圾光柱
    this.posAttr = null //   海浮垃圾位置属性（每帧回写）
    this.drift = null //     海浮垃圾漂移速度（vx,vz 交错数组）
    this.floatingClasses = null // 每点类别下标（拾取/配色查表）
    this.beachClasses = null
    this.beamHeights = null // 海浮垃圾光柱高度（每点）
  }

  /** 生成垃圾点与光柱（进场景前调用一次）。放置失败的点自动跳过 */
  build() {
    if (!this.sampleHeight || !this.bounds) return

    const { minX, minZ, sizeX, sizeZ } = this.bounds
    const x0 = minX + MARGIN
    const z0 = minZ + MARGIN
    const w = Math.max(1, sizeX - MARGIN * 2)
    const d = Math.max(1, sizeZ - MARGIN * 2)
    const rng = makeRng(20261009)

    // ---- 海浮垃圾：水面 + 近岸 ----
    const fx = []
    const fz = []
    const fSize = []
    const fPhase = []
    const fClass = []
    const drift = []
    const fBeamH = []
    let guard = FLOATING_COUNT * 60
    while (fx.length < FLOATING_COUNT && guard > 0) {
      guard -= 1
      const x = x0 + rng() * w
      const z = z0 + rng() * d
      if (this.sampleHeight(x, z) > -20) continue // 必须是水面
      if (!hasLandNear(this.sampleHeight, x, z, NEAR_LAND_RADIUS)) continue
      fx.push(x)
      fz.push(z)
      fSize.push(0.85 + rng() * 0.7)
      fPhase.push(rng() * Math.PI * 2)
      fClass.push(pickClassIndex(rng))
      fBeamH.push(BEAM_MIN_H + rng() * (BEAM_MAX_H - BEAM_MIN_H))
      // 缓慢漂移：场景是 165km 地理尺度，真实洋流（<1 m/s）在屏幕上不可见 ——
      // 取 12~34 m/s 的"艺术流速"：远景几乎静止，近景几秒内能看出缓慢位移
      const ang = rng() * Math.PI * 2
      const spd = 12 + rng() * 22
      drift.push(Math.cos(ang) * spd, Math.sin(ang) * spd)
    }

    const fGeo = new THREE.BufferGeometry()
    const fPos = new Float32Array(fx.length * 3)
    for (let i = 0; i < fx.length; i += 1) {
      fPos[i * 3] = fx[i]
      fPos[i * 3 + 1] = 0
      fPos[i * 3 + 2] = fz[i]
    }
    fGeo.setAttribute('position', new THREE.BufferAttribute(fPos, 3))
    fGeo.setAttribute('aSize', new THREE.Float32BufferAttribute(fSize, 1))
    fGeo.setAttribute('aPhase', new THREE.Float32BufferAttribute(fPhase, 1))
    fGeo.setAttribute('aColor', new THREE.Float32BufferAttribute(this._classColors(fClass), 3))
    fGeo.boundingSphere = new THREE.Sphere(
      new THREE.Vector3(minX + sizeX / 2, 0, minZ + sizeZ / 2),
      Math.hypot(sizeX, sizeZ) / 2 + 1000,
    )

    this.posAttr = fGeo.attributes.position
    this.drift = drift
    this.floatingClasses = fClass
    this.beamHeights = fBeamH
    this.floating = new THREE.Points(fGeo, this._makePointMaterial())
    this.floating.name = 'debris-floating'
    this.floating.frustumCulled = false // 位置每帧变化，用预置包围球会误剔除
    this.floating.userData = { type: 'debris', kind: 'floating', layer: this }
    this.group.add(this.floating)

    // 海浮垃圾光柱（从波面射向天空；位置每帧跟着漂移）
    this.floatingBeams = this._buildBeams(
      fx.map((x, i) => ({ x, y: 6, z: fz[i], cls: fClass[i], h: fBeamH[i] })),
      true,
    )
    this.group.add(this.floatingBeams)

    // ---- 沙滩垃圾：贴着水线的低平海岸带（静态）----
    // 命中率注意：低地海岸带在 168km 场景里很窄，随机撒点命中率约 0.5%——
    // 靠"水线 700m 内 + 高程 1~45m"做双重判定，并给足尝试次数
    const bx = []
    const bz = []
    const by = []
    const bSize = []
    const bPhase = []
    const bClass = []
    guard = BEACH_COUNT * 400
    while (bx.length < BEACH_COUNT && guard > 0) {
      guard -= 1
      const x = x0 + rng() * w
      const z = z0 + rng() * d
      const h = this.sampleHeight(x, z)
      if (h < BEACH_MIN_H || h > BEACH_MAX_H) continue // 只落沙滩/低地
      if (!hasWaterNear(this.sampleHeight, x, z, SHORE_RADIUS)) continue // 贴着水线
      bx.push(x)
      bz.push(z)
      by.push(h + 3)
      bSize.push(0.8 + rng() * 0.6)
      bPhase.push(rng() * Math.PI * 2)
      bClass.push(pickClassIndex(rng))
    }

    const bGeo = new THREE.BufferGeometry()
    const bPos = new Float32Array(bx.length * 3)
    for (let i = 0; i < bx.length; i += 1) {
      bPos[i * 3] = bx[i]
      bPos[i * 3 + 1] = by[i]
      bPos[i * 3 + 2] = bz[i]
    }
    bGeo.setAttribute('position', new THREE.BufferAttribute(bPos, 3))
    bGeo.setAttribute('aSize', new THREE.Float32BufferAttribute(bSize, 1))
    bGeo.setAttribute('aPhase', new THREE.Float32BufferAttribute(bPhase, 1))
    bGeo.setAttribute('aColor', new THREE.Float32BufferAttribute(this._classColors(bClass), 3))
    bGeo.computeBoundingSphere()
    this.beachClasses = bClass
    this.beach = new THREE.Points(bGeo, this._makePointMaterial())
    this.beach.name = 'debris-beach'
    this.beach.userData = { type: 'debris', kind: 'beach', layer: this }
    this.group.add(this.beach)

    // 沙滩垃圾光柱（静态）
    this.beachBeams = this._buildBeams(
      bx.map((x, i) => ({ x, y: by[i], z: bz[i], cls: bClass[i], h: BEAM_MIN_H * 0.8 + (i % 7) * 120 })),
      false,
    )
    this.group.add(this.beachBeams)
  }

  /** 每点颜色（HDR 增益后写入 aColor 属性） */
  _classColors(classIdx) {
    const out = new Float32Array(classIdx.length * 3)
    const c = new THREE.Color()
    for (let i = 0; i < classIdx.length; i += 1) {
      c.setHex(DEBRIS_CLASSES[classIdx[i]].hex).multiplyScalar(HDR_GAIN)
      out[i * 3] = c.r
      out[i * 3 + 1] = c.g
      out[i * 3 + 2] = c.b
    }
    return out
  }

  _makePointMaterial() {
    return new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uPixelRatio: { value: 1 },
      },
      vertexShader: POINT_VERT,
      fragmentShader: POINT_FRAG,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.AdditiveBlending,
    })
  }

  /**
   * 光柱线：每个垃圾一条底部亮、顶部渐隐（黑=透明）的细线。
   * LineSegments 一次绘制全部光柱 —— 410 条线共 820 个顶点，几乎零开销。
   * @param {Array<{x,y,z,cls,h}>} items
   * @param {boolean} dynamic 是否每帧写位置（海浮垃圾需要）
   */
  _buildBeams(items, dynamic) {
    const pos = new Float32Array(items.length * 6)
    const col = new Float32Array(items.length * 6)
    const c = new THREE.Color()
    for (let i = 0; i < items.length; i += 1) {
      const it = items[i]
      const p = i * 6
      pos[p] = it.x
      pos[p + 1] = it.y
      pos[p + 2] = it.z
      pos[p + 3] = it.x
      pos[p + 4] = it.y + it.h
      pos[p + 5] = it.z
      c.setHex(DEBRIS_CLASSES[it.cls].hex).multiplyScalar(BEAM_GAIN)
      col[p] = c.r
      col[p + 1] = c.g
      col[p + 2] = c.b
      // 顶色压到 ~4%：加法混合里等于渐隐，光柱像"没入天空"
      col[p + 3] = c.r * 0.04
      col[p + 4] = c.g * 0.04
      col[p + 5] = c.b * 0.04
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
    geo.boundingSphere = new THREE.Sphere(
      new THREE.Vector3(
        (this.bounds?.minX ?? 0) + (this.bounds?.sizeX ?? 1) / 2,
        0,
        (this.bounds?.minZ ?? 0) + (this.bounds?.sizeZ ?? 1) / 2,
      ),
      Math.hypot(this.bounds?.sizeX ?? 1, this.bounds?.sizeZ ?? 1) / 2 + 4000,
    )
    const mat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const lines = new THREE.LineSegments(geo, mat)
    lines.name = dynamic ? 'debris-beams-floating' : 'debris-beams-beach'
    lines.frustumCulled = false
    return lines
  }

  /** 拾取信息：kind + 点下标 → 类别资料（InteractionLayer 命中后调用） */
  getInfoAt(kind, index) {
    const arr = kind === 'beach' ? this.beachClasses : this.floatingClasses
    if (!arr || index == null || index < 0 || index >= arr.length) return null
    const cls = DEBRIS_CLASSES[arr[index]]
    return { kind, main_class: cls.key, label: cls.label }
  }

  /** 供 InteractionLayer 射线拾取（Points 对象本身携带 userData.type='debris'） */
  getInteractiveObjects() {
    return [this.floating, this.beach].filter(Boolean)
  }

  /**
   * 每帧更新
   * @param {number} dt 帧间隔（秒）
   * @param {number} time 累计时间（秒）
   * @param {number} pixelRatio 当前渲染像素比（自适应画质会变）
   */
  update(dt, time, pixelRatio = 1) {
    const beamPulse = 0.42 + 0.12 * Math.sin(time * 1.6) // 光柱整体呼吸（像扫描信号）

    if (this.beach) {
      this.beach.material.uniforms.uTime.value = time
      this.beach.material.uniforms.uPixelRatio.value = pixelRatio
    }
    if (this.beachBeams) this.beachBeams.material.opacity = beamPulse
    if (!this.floating || !this.posAttr) return

    this.floating.material.uniforms.uTime.value = time
    this.floating.material.uniforms.uPixelRatio.value = pixelRatio
    if (this.floatingBeams) this.floatingBeams.material.opacity = beamPulse

    // 海浮垃圾：缓慢漂移 + 严格骑在波面上（与海面着色器同相，才像"浮在海上"）；
    // 光柱底端跟着漂移，顶端同幅平移（保持竖直）
    const arr = this.posAttr.array
    const beamArr = this.floatingBeams?.geometry.attributes.position.array
    const beamH = this.beamHeights
    const { minX, minZ, sizeX, sizeZ } = this.bounds
    const drift = this.drift
    const n = arr.length / 3
    for (let i = 0; i < n; i += 1) {
      let x = arr[i * 3] + drift[i * 2] * dt
      let z = arr[i * 3 + 2] + drift[i * 2 + 1] * dt

      // 漂到岸上 → 退回并沿切线滑走（绕岸漂而不是搁浅/穿模）
      if (this.sampleHeight(x, z) > 0) {
        x = arr[i * 3]
        z = arr[i * 3 + 2]
        const vx = drift[i * 2]
        const vz = drift[i * 2 + 1]
        drift[i * 2] = -vz
        drift[i * 2 + 1] = vx
      }
      // 越界折返
      if (x < minX + 1000 || x > minX + sizeX - 1000) {
        drift[i * 2] = -drift[i * 2]
        x = Math.min(Math.max(x, minX + 1000), minX + sizeX - 1000)
      }
      if (z < minZ + 1000 || z > minZ + sizeZ - 1000) {
        drift[i * 2 + 1] = -drift[i * 2 + 1]
        z = Math.min(Math.max(z, minZ + 1000), minZ + sizeZ - 1000)
      }

      arr[i * 3] = x
      arr[i * 3 + 2] = z
      // 骑浪：海面高度 + 轻微余浮（波谷时也不会沉进水面以下）
      const y = seaWaveHeight(x, z, time) + 6
      arr[i * 3 + 1] = y

      if (beamArr && beamH) {
        const p = i * 6
        beamArr[p] = x
        beamArr[p + 1] = y
        beamArr[p + 2] = z
        beamArr[p + 3] = x
        beamArr[p + 4] = y + beamH[i]
        beamArr[p + 5] = z
      }
    }
    this.posAttr.needsUpdate = true
    if (beamArr) this.floatingBeams.geometry.attributes.position.needsUpdate = true
  }

  dispose() {
    for (const obj of [this.floating, this.beach, this.floatingBeams, this.beachBeams]) {
      if (!obj) continue
      this.group.remove(obj)
      obj.geometry.dispose()
      obj.material.dispose()
    }
    this.floating = null
    this.beach = null
    this.floatingBeams = null
    this.beachBeams = null
    this.posAttr = null
    this.scene.remove(this.group)
  }
}
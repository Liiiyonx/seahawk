/**
 * 3D 沙盘礁石图层（沿岸礁石群）
 *
 * 真实礁石不是均匀撒点，而是"成群"分布：先在水线附近取若干礁群中心，
 * 再在中心周围 0.35~0.9km 内成簇布置 5~9 块岩石 —— 近看是礁石滩，
 * 远看沿线成串，符合"岩基海岸"的自然形态。
 *
 * 关键做法：
 *   - 岩石用"冰面体 + 多频位移"生成碎面几何（三套变体），InstancedMesh 一次绘制；
 *   - 落位高度取采样地形高度并让岩石中心略低于地面（嵌进去一部分），
 *     位于浅水(-26m~0m)的岩石自然露出水面 —— 不需要特判"可见/不可见"；
 *   - 每块岩石按"顶部干出高度"混合湿石/干石颜色（水线以下深色湿石、
 *     水线以上风化石色的干石），这是礁石在航拍照片里最重要的视觉特征；
 *   - 露出水面的岩石配一圈"浪花环"（贴水面的白色环形贴图），
 *     整体透明度缓慢呼吸 —— 礁石周围的碎浪是辨识度最高的细节。
 *
 * 确定性种子：刷新后礁石分布不跳变。
 */

import * as THREE from 'three'

const CLUSTER_COUNT = 46 //   礁群数量
const ROCKS_PER_CLUSTER_MIN = 6
const ROCKS_PER_CLUSTER_MAX = 11
const CLUSTER_RADIUS_MIN = 350 // 簇内散布半径（米）
const CLUSTER_RADIUS_MAX = 900
const ROCK_R_MIN = 26 //        岩石半径范围（米）—— 165km 场景里属"小礁石"
const ROCK_R_MAX = 72
const MARGIN = 5000 //         距地形边界留白（米）
const WATER_TOP = -26 //       只考虑浅水及以上（太深=礁石看不见，没有意义）
const LAND_TOP = 12 //         略高于水线（避免礁石出现在内陆山地）

// 湿石（水线以下）/ 干石（露出水面风化）基色
const WET_COLOR = new THREE.Color(0x2e373d)
const DRY_COLOR = new THREE.Color(0x8a8578)

function makeRng(seed) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

/**
 * 礁石几何：冰面体顶点沿半径做"低频塑形 + 高频碎面"位移。
 * 不用 mergeVertices 是故意的：非索引几何 → 平直着色(flat shading)，
 * 天然出碎面岩石质感（平滑着色会像鹅卵石，不像礁石）。
 */
function makeRockGeometry(seed) {
  const rng = makeRng(seed)
  const o1 = rng() * Math.PI * 2
  const o2 = rng() * Math.PI * 2
  const o3 = rng() * Math.PI * 2
  const geo = new THREE.IcosahedronGeometry(1, 2)
  const pos = geo.attributes.position
  const v = new THREE.Vector3()
  for (let i = 0; i < pos.count; i += 1) {
    v.fromBufferAttribute(pos, i)
    // 低频：整体轮廓（大起伏）；高频：表面碎裂
    const low =
      Math.sin(v.x * 2.3 + o1) * Math.cos(v.y * 1.9 + o2) * Math.sin(v.z * 2.1 + o3)
    const high =
      Math.sin(v.x * 5.7 + o2) * Math.sin(v.y * 4.9 + o3) * Math.cos(v.z * 6.3 + o1)
    const r = 1 + low * 0.24 + high * 0.09
    v.multiplyScalar(r)
    v.y *= 0.72 // 压扁：礁石贴水，上尖下宽（水下部分反而是主体）
    pos.setXYZ(i, v.x, v.y, v.z)
  }
  geo.computeVertexNormals() // 非索引 → 平直面法线
  return geo
}

/** 浪花环贴图：径向渐变的白色圆环（中心透明，避免盖住岩石） */
function makeFoamTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const ctx = canvas.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 30, 64, 64, 64)
  // 更窄更亮的环带：近岸海面本身偏亮，宽而淡的环会糊进水面；
  // 收窄环带 + 峰值提到 0.85，才是"礁石周围一圈翻白的碎浪"
  g.addColorStop(0, 'rgba(255, 255, 255, 0)')
  g.addColorStop(0.5, 'rgba(255, 255, 255, 0)')
  g.addColorStop(0.62, 'rgba(255, 255, 255, 0.9)')
  g.addColorStop(0.74, 'rgba(255, 255, 255, 0.28)')
  g.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

export class ReefLayer {
  /**
   * @param {THREE.Scene} scene
   * @param {Object} options
   * @param {Function} options.sampleHeight 世界 (x,z) → 地形高度（米），海面 0，海床 -30
   * @param {Object} options.bounds 地形世界范围 { minX, minZ, sizeX, sizeZ }
   */
  constructor(scene, { sampleHeight, bounds } = {}) {
    this.scene = scene
    this.sampleHeight = sampleHeight
    this.bounds = bounds
    this.group = new THREE.Group()
    this.group.name = 'reefs'
    scene.add(this.group)

    this.rockMeshes = []
    this.foam = null
    this.foamMat = null
  }

  build() {
    if (!this.sampleHeight || !this.bounds) return
    const { minX, minZ, sizeX, sizeZ } = this.bounds
    const x0 = minX + MARGIN
    const z0 = minZ + MARGIN
    const w = Math.max(1, sizeX - MARGIN * 2)
    const d = Math.max(1, sizeZ - MARGIN * 2)
    const rng = makeRng(20261010)

    // ---- 沿岸候选带：按 ~380m 网格扫描，只留水线附近 ----
    // 为什么不用随机撒点：168km 场景里"水线 ±26m"的带非常窄，随机撒点命中率极低；
    // 为什么网格不能太粗：实测 1.2km 网格全图只命中 16 个候选格（海岸坡陡、窄带），
    // 380m 网格命中 ~150+，才能撑起"沿岸礁石群"的密度（约 6 万次双线性采样，
    // 构建期几十毫秒，可忽略）。
    const cell = 380
    const cand = []
    for (let gx = x0; gx < x0 + w; gx += cell) {
      for (let gz = z0; gz < z0 + d; gz += cell) {
        const h = this.sampleHeight(gx, gz)
        if (h >= WATER_TOP && h <= LAND_TOP) cand.push({ x: gx, z: gz, h })
      }
    }

    // ---- 礁群中心：从候选带里抽，簇间保持最小间距（礁石成串分布、不糊成一片）----
    const centers = []
    const MIN_GAP = 4200
    let pickGuard = cand.length * 4
    while (centers.length < CLUSTER_COUNT && pickGuard > 0) {
      pickGuard -= 1
      const c = cand[Math.floor(rng() * cand.length)]
      if (!c) break
      if (centers.some((p) => Math.hypot(p.x - c.x, p.z - c.z) < MIN_GAP)) continue
      centers.push(c)
    }

    // ---- 每簇内散布岩石 ----
    const rocks = [] // {x,z,h,r,rotY,tiltX,tiltZ,scaleY}
    for (const c of centers) {
      const n = ROCKS_PER_CLUSTER_MIN + Math.floor(rng() * (ROCKS_PER_CLUSTER_MAX - ROCKS_PER_CLUSTER_MIN + 1))
      const spread = CLUSTER_RADIUS_MIN + rng() * (CLUSTER_RADIUS_MAX - CLUSTER_RADIUS_MIN)
      for (let i = 0; i < n; i += 1) {
        const a = rng() * Math.PI * 2
        const dist = Math.sqrt(rng()) * spread
        const x = c.x + Math.cos(a) * dist
        const z = c.z + Math.sin(a) * dist
        const h = this.sampleHeight(x, z)
        // 簇内放宽一个身位：礁群边缘允许越过水线（礁缘自然延伸到滩涂/深水）
        if (h < WATER_TOP - 8 || h > LAND_TOP + 10) continue
        const r = ROCK_R_MIN + rng() * (ROCK_R_MAX - ROCK_R_MIN)
        rocks.push({
          x,
          z,
          h,
          r,
          rotY: rng() * Math.PI * 2,
          tiltX: (rng() - 0.5) * 0.34,
          tiltZ: (rng() - 0.5) * 0.34,
          scaleY: 0.78 + rng() * 0.5,
        })
      }
    }
    if (!rocks.length) return

    // ---- 三套几何变体分桶（形状错落），每桶一个 InstancedMesh ----
    const variantGeo = [makeRockGeometry(11), makeRockGeometry(29), makeRockGeometry(47)]
    const buckets = [[], [], []]
    rocks.forEach((rk, i) => buckets[i % 3].push(rk))

    const mat = new THREE.MeshStandardMaterial({
      color: 0xffffff, // 颜色全部来自 instanceColor
      roughness: 0.94,
      metalness: 0.02,
    })

    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    const foamItems = []
    buckets.forEach((list, bi) => {
      if (!list.length) return
      const mesh = new THREE.InstancedMesh(variantGeo[bi], mat, list.length)
      mesh.name = `reef-rocks-${bi}`
      mesh.castShadow = true
      mesh.receiveShadow = true
      list.forEach((rk, i) => {
        // 岩石中心略低于地面：露出部分是"顶"，水下部分是主体（礁石的自然形态）
        const y = rk.h - rk.r * 0.18
        dummy.position.set(rk.x, y, rk.z)
        dummy.rotation.set(rk.tiltX, rk.rotY, rk.tiltZ)
        dummy.scale.set(rk.r, rk.r * rk.scaleY, rk.r * (0.85 + rng() * 0.3))
        dummy.updateMatrix()
        mesh.setMatrixAt(i, dummy.matrix)

        // 干湿分色：顶部露出水线越多越"干"（风化浅色），水下保持湿石深色
        const topY = y + rk.r * rk.scaleY * 0.72
        const dryness = THREE.MathUtils.clamp((topY - 1.5) / 14, 0, 1)
        color.copy(WET_COLOR).lerp(DRY_COLOR, dryness)
        color.offsetHSL(0, 0, (rng() - 0.5) * 0.06) // 随机明度抖动
        mesh.setColorAt(i, color)

        // 露出水面、且脚下是水线附近的岩石 → 记一圈浪花
        //（滩涂上的礁石离水远，加浪花环物理上是错的，且环会被沙面遮住）
        if (topY > 2.5 && rk.h <= 2) foamItems.push({ x: rk.x, z: rk.z, r: rk.r })
      })
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
      this.rockMeshes.push(mesh)
      this.group.add(mesh)
    })

    // ---- 浪花环（InstancedMesh，贴水面；整体透明度缓慢呼吸）----
    if (foamItems.length) {
      const foamGeo = new THREE.PlaneGeometry(2, 2).rotateX(-Math.PI / 2)
      this.foamMat = new THREE.MeshBasicMaterial({
        map: makeFoamTexture(),
        transparent: true,
        opacity: 0.5,
        depthWrite: false,
        fog: true,
      })
      const foam = new THREE.InstancedMesh(foamGeo, this.foamMat, foamItems.length)
      foam.name = 'reef-foam'
      foam.renderOrder = 2
      foamItems.forEach((f, i) => {
        dummy.position.set(f.x, 2.4, f.z)
        dummy.rotation.set(0, 0, 0)
        const s = f.r * 1.95
        dummy.scale.set(s, 1, s)
        dummy.updateMatrix()
        foam.setMatrixAt(i, dummy.matrix)
      })
      foam.instanceMatrix.needsUpdate = true
      this.foam = foam
      this.group.add(foam)
    }
  }

  /** 每帧：浪花环呼吸（破碎浪的节奏，慢速起伏即可） */
  update(time) {
    if (this.foamMat) this.foamMat.opacity = 0.48 + 0.14 * Math.sin(time * 1.15)
  }

  dispose() {
    for (const mesh of this.rockMeshes) {
      this.group.remove(mesh)
      mesh.geometry.dispose()
      mesh.material.dispose()
    }
    if (this.foam) {
      this.group.remove(this.foam)
      this.foam.geometry.dispose()
      this.foamMat.map?.dispose()
      this.foamMat.dispose()
    }
    this.rockMeshes = []
    this.foam = null
    this.foamMat = null
    this.scene.remove(this.group)
  }
}
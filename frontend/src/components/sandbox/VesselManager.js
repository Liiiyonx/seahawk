/**
 * 3D船体管理器：创建、更新、销毁船体模型
 * 
 * 双体清洁USV设计（参数化放样浮筒，参考 Nukhada USV / three.js Parametric Boat / MARCo 太阳能USV）
 */

import * as THREE from 'three'
import { lngLatToScene, seaWaveHeight } from './TerrainLayer.js'

// 船体状态配色
const VESSEL_COLORS = {
  online: 0x18a999,      // 在线-青绿
  navigating: 0x18a999,  // 航行中-青绿
  collecting: 0xff9500,  // 作业中-橙
  assigned: 0x7a5af8,    // 已派单-紫
  offline: 0x7a8798,     // 离线-灰
  idle: 0x3f8ee8,        // 待命-蓝
}

// 决策高亮
const DECISION_COLORS = {
  selected: 0xff9500,    // 选中-橙
  candidate: 0x7a5af8,   // 候选-紫
}

/**
 * 创建单个船体模型（双体清洁 USV）
 *
 * 船型/工艺参考：
 *   - Nukhada USV（TII 真实无人船）：双端尖浮筒 + 横梁设备平台 + 外侧扶手栏杆
 *   - three.js 社区 Parametric Boat：浮筒用参数化放样截面，不用平板挤出
 *   - MARCo 等太阳能 USV：深蓝电池片网格太阳能顶棚
 *
 * 尺度说明：场景是 165km 级真实地理尺度，模型按 1单位=1m 建（船长 ~4.6m），
 * 再由 group.scale 放大 200 倍（~920m 视觉符号），否则全景视角下不足一个像素。
 */
const VESSEL_SCALE = 200

// ---------------------------------------------------------------- 参数化船体放样
// 沿长度方向逐环放样椭圆截面：宽度、龙骨各自有剖面曲线，
// 两端收尖、中部饱满 —— 真实玻璃钢浮筒的"双端尖"（double-ender）造型
function loftHullGeometry({ length = 4.6, beam = 0.52, depth = 0.6, rings = 26, radial = 14 } = {}) {
  // 宽度剖面：t=0 船尾 → t=1 船首；两端收尖，船尾稍钝
  const widthProfile = (t) => {
    const bow = 1 - Math.pow(Math.max(0, (t - 0.62) / 0.38), 1.8)
    const stern = 1 - Math.pow(Math.max(0, (0.3 - t) / 0.3), 2.2) * 0.92
    return Math.max(0.015, Math.min(bow, stern))
  }
  // 龙骨剖面：两端上抬（船首抬得更多），中部吃水最深
  const keelProfile = (t) => {
    const bow = Math.pow(Math.max(0, (t - 0.68) / 0.32), 2) * 0.5
    const stern = Math.pow(Math.max(0, (0.26 - t) / 0.26), 2) * 0.28
    return Math.min(0.85, bow + stern)
  }

  const positions = []
  const indices = []
  const half = depth / 2
  for (let i = 0; i <= rings; i += 1) {
    const t = i / rings
    const z = (t - 0.5) * length
    const w = (beam / 2) * widthProfile(t)
    const keel = keelProfile(t)
    for (let j = 0; j < radial; j += 1) {
      const a = (j / radial) * Math.PI * 2
      const s = Math.sin(a)
      // 上半截面不动，下半随龙骨线上抬 → 端部自然出水
      positions.push(Math.cos(a) * w, s >= 0 ? s * half : s * half * (1 - keel), z)
    }
  }
  for (let i = 0; i < rings; i += 1) {
    for (let j = 0; j < radial; j += 1) {
      const a = i * radial + j
      const b = i * radial + ((j + 1) % radial)
      const c = (i + 1) * radial + j
      const d = (i + 1) * radial + ((j + 1) % radial)
      indices.push(a, b, c, b, d, c)
    }
  }
  // 端盖（船尾朝 -z、船首朝 +z）
  const sternC = positions.length / 3
  positions.push(0, (-half * (1 - keelProfile(0))) / 2, -length / 2)
  const bowC = positions.length / 3
  positions.push(0, (-half * (1 - keelProfile(1))) / 2, length / 2)
  for (let j = 0; j < radial; j += 1) {
    const j1 = (j + 1) % radial
    indices.push(sternC, j1, j)
    indices.push(bowC, rings * radial + j, rings * radial + j1)
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geo.setIndex(indices)
  geo.computeVertexNormals()
  return geo
}

// ---------------------------------------------------------------- 太阳能板纹理
// CanvasTexture 画电池片网格 + 斜向高光，一次生成全局共享
let sharedSolarTexture = null
function getSolarTexture() {
  if (sharedSolarTexture) return sharedSolarTexture
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const g = canvas.getContext('2d')
  g.fillStyle = '#14395c'
  g.fillRect(0, 0, 128, 128)
  // 电池片
  g.fillStyle = '#1a4a75'
  for (let r = 0; r < 4; r += 1) {
    for (let c = 0; c < 4; c += 1) {
      g.fillRect(c * 32 + 2, r * 32 + 2, 28, 28)
    }
  }
  // 斜向高光
  const grad = g.createLinearGradient(0, 0, 128, 128)
  grad.addColorStop(0, 'rgba(160,210,245,0.22)')
  grad.addColorStop(0.5, 'rgba(160,210,245,0)')
  grad.addColorStop(1, 'rgba(10,25,45,0.25)')
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  // 边框母线
  g.strokeStyle = 'rgba(200,220,240,0.5)'
  g.lineWidth = 2
  g.strokeRect(1, 1, 126, 126)

  sharedSolarTexture = new THREE.CanvasTexture(canvas)
  sharedSolarTexture.wrapS = THREE.RepeatWrapping
  sharedSolarTexture.wrapT = THREE.RepeatWrapping
  sharedSolarTexture.repeat.set(2, 2)
  return sharedSolarTexture
}

// ---------------------------------------------------------------- 尾流纹理
// CanvasTexture 画 V 形泡沫带（一次生成全局共享）：
// 中央螺旋桨尾 + 两侧扩散的泡沫臂，比纯色 Additive 面片更"水"。
// 尾流动画靠 offset 轻微摆动（不做整周期滚动 —— 图案首尾不同，滚动会跳变）
let sharedWakeTexture = null
function getWakeTexture() {
  if (sharedWakeTexture) return sharedWakeTexture
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 256
  const g = canvas.getContext('2d')

  // 中央螺旋桨尾流（上浓下淡）
  const core = g.createLinearGradient(0, 0, 0, 256)
  core.addColorStop(0, 'rgba(255,255,255,0.85)')
  core.addColorStop(0.45, 'rgba(255,255,255,0.30)')
  core.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = core
  g.fillRect(52, 0, 24, 256)

  // 两侧扩散泡沫臂
  g.strokeStyle = 'rgba(255,255,255,0.42)'
  g.lineWidth = 12
  g.lineCap = 'round'
  g.beginPath()
  g.moveTo(64, 8)
  g.quadraticCurveTo(34, 120, 6, 244)
  g.stroke()
  g.beginPath()
  g.moveTo(64, 8)
  g.quadraticCurveTo(94, 120, 122, 244)
  g.stroke()

  sharedWakeTexture = new THREE.CanvasTexture(canvas)
  sharedWakeTexture.wrapS = THREE.ClampToEdgeWrapping
  sharedWakeTexture.wrapT = THREE.ClampToEdgeWrapping
  return sharedWakeTexture
}

// 履带胎纹贴图（履带车共用一张；走带靠 offset 滚动表现"履带在转"）
let sharedTreadTexture = null
function getTreadTexture() {
  if (sharedTreadTexture) return sharedTreadTexture
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 64
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#20262a'
  ctx.fillRect(0, 0, 32, 64)
  ctx.fillStyle = '#39424a'
  for (let y = 0; y < 64; y += 10) ctx.fillRect(0, y, 32, 5)
  const tex = new THREE.CanvasTexture(canvas)
  tex.wrapS = THREE.RepeatWrapping
  tex.wrapT = THREE.RepeatWrapping
  tex.repeat.set(1, 6)
  tex.colorSpace = THREE.SRGBColorSpace
  sharedTreadTexture = tex
  return sharedTreadTexture
}

// HDR 亮度系数：灯光/节点颜色乘上 >1 的系数，让它们在 HDR 缓冲里越过
// 泛光阈值（0.9）—— 这是 UnrealBloom 管线下"灯光会发光"的标准做法
const HDR_LIGHT_GAIN = 1.8

/**
 * 四节机械臂（船体与履带车共用）：转台 → 肩 → 肘 → 腕 → 夹爪。
 * 各节是独立枢轴组，动起来是真正的关节摆动（见 update 里的作业摆动）。
 * @param {number} s 尺度系数（船体 1，履带小车约 0.55）
 */
function createArmAssembly(s = 1) {
  const whiteMat = new THREE.MeshStandardMaterial({ color: 0xe8ecef, roughness: 0.4, metalness: 0.1 })
  const deckMat = new THREE.MeshStandardMaterial({ color: 0x3d4a55, roughness: 0.65, metalness: 0.2, flatShading: true })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x22282c, roughness: 0.6, metalness: 0.4 })
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x18a999, roughness: 0.34, metalness: 0.3 })

  const root = new THREE.Group()
  const armBase = new THREE.Mesh(new THREE.CylinderGeometry(0.18 * s, 0.21 * s, 0.13 * s, 12), accentMat)
  armBase.position.y = 0.06 * s
  root.add(armBase)

  const yaw = new THREE.Group() // 转台（第 0 关节）
  yaw.position.y = 0.13 * s
  root.add(yaw)
  const turret = new THREE.Mesh(new THREE.CylinderGeometry(0.14 * s, 0.15 * s, 0.15 * s, 12), whiteMat)
  turret.position.y = 0.075 * s
  yaw.add(turret)

  const jointGeo = new THREE.SphereGeometry(0.078 * s, 12, 10)
  const mats = [whiteMat, whiteMat, deckMat, darkMat]

  /** 造一节臂：枢轴组 + 节体（沿 +Y 伸展）+ 关节球 + 侧面液压杆 */
  function makeSegment(parent, length, thickness, mat) {
    const pivot = new THREE.Group()
    parent.add(pivot)
    const joint = new THREE.Mesh(jointGeo, accentMat)
    joint.scale.setScalar(thickness / (0.06 * s))
    pivot.add(joint)
    const seg = new THREE.Mesh(new THREE.BoxGeometry(thickness, length, thickness), mat)
    seg.position.y = length / 2
    pivot.add(seg)
    const rod = new THREE.Mesh(
      new THREE.CylinderGeometry(thickness * 0.16, thickness * 0.16, length * 0.7, 6),
      darkMat,
    )
    rod.position.set(thickness * 0.62, length / 2, 0)
    pivot.add(rod)
    return pivot
  }

  const lens = [0.44, 0.36, 0.30, 0.22].map((v) => v * s)
  const j1 = makeSegment(yaw, lens[0], 0.11 * s, mats[0])
  j1.position.y = 0.15 * s
  const j2 = makeSegment(j1, lens[1], 0.095 * s, mats[1]) // 肘
  j2.position.y = lens[0]
  const j3 = makeSegment(j2, lens[2], 0.082 * s, mats[2]) // 腕
  j3.position.y = lens[1]
  const j4 = makeSegment(j3, lens[3], 0.07 * s, mats[3]) // 末节
  j4.position.y = lens[2]

  // 夹爪（两片外张的抓板）+ 末端作业灯
  const clawGeo = new THREE.BoxGeometry(0.035 * s, 0.16 * s, 0.09 * s)
  for (const cx of [-0.06, 0.06]) {
    const claw = new THREE.Mesh(clawGeo, darkMat)
    claw.position.set(cx * 1.4 * s, 0.25 * s, 0)
    claw.rotation.z = cx > 0 ? -0.32 : 0.32
    j4.add(claw)
  }
  const tipLight = new THREE.Mesh(
    new THREE.SphereGeometry(0.05 * s, 10),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0x18a999).multiplyScalar(HDR_LIGHT_GAIN) }),
  )
  tipLight.position.set(0, 0.17 * s, 0.06 * s)
  j4.add(tipLight)

  return { root, joints: { yaw, j1, j2, j3, j4 } }
}

function createVesselModel({ type = 'boat' } = {}) {
  if (type === 'tracked') return createTrackedRoverModel()
  if (type === 'arm') return createArmStationModel()
  const group = new THREE.Group()
  group.name = 'vessel'
  group.scale.setScalar(VESSEL_SCALE)

  // 主船体材质（状态色由 applyStatusStyle 改 hullMat.color，两个浮筒共享同一材质）
  const hullMat = new THREE.MeshStandardMaterial({
    color: VESSEL_COLORS.online,
    roughness: 0.45,
    metalness: 0.2,
  })
  const deckMat = new THREE.MeshStandardMaterial({
    color: 0x3d4a55,
    roughness: 0.65,
    metalness: 0.2,
    flatShading: true,
  })
  const accentMat = new THREE.MeshStandardMaterial({
    color: 0x18a999,
    roughness: 0.34,
    metalness: 0.3,
  })
  const solarMat = new THREE.MeshStandardMaterial({
    map: getSolarTexture(),
    roughness: 0.28,
    metalness: 0.55,
  })
  // 收集网：半透深色，比实心盒更像"网兜"
  const netMat = new THREE.MeshStandardMaterial({
    color: 0x1c262b,
    roughness: 0.9,
    metalness: 0.1,
    transparent: true,
    opacity: 0.6,
  })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x22282c, roughness: 0.6, metalness: 0.4 })
  const whiteMat = new THREE.MeshStandardMaterial({ color: 0xe8ecef, roughness: 0.4, metalness: 0.1 })

  // ---- 双浮筒（参数化放样，双端尖）----
  const HULL_X = 0.82 // 两浮筒间距的一半
  const pontoonGeo = loftHullGeometry({ length: 4.6, beam: 0.52, depth: 0.6 })
  const hullPort = new THREE.Mesh(pontoonGeo, hullMat)
  hullPort.position.set(HULL_X, 0.34, 0)
  group.add(hullPort)
  const hullStarboard = new THREE.Mesh(pontoonGeo, hullMat)
  hullStarboard.position.set(-HULL_X, 0.34, 0)
  group.add(hullStarboard)

  // ---- 推进器吊舱（BlueRobotics T200 风格，浮筒尾部水下）----
  const thrusterGeo = new THREE.CylinderGeometry(0.09, 0.075, 0.42, 10)
  thrusterGeo.rotateX(Math.PI / 2)
  for (const px of [HULL_X, -HULL_X]) {
    const pod = new THREE.Mesh(thrusterGeo, darkMat)
    pod.position.set(px, 0.14, -2.05)
    group.add(pod)
  }

  // ---- 船首收集篮（双体之间的"大嘴"，半透网兜材质）----
  const basket = new THREE.Mesh(new THREE.BoxGeometry(1.14, 0.45, 1.7), netMat)
  basket.position.set(0, 0.3, 0.75)
  group.add(basket)
  const basketRim = new THREE.Mesh(new THREE.BoxGeometry(1.24, 0.08, 1.82), accentMat)
  basketRim.position.set(0, 0.56, 0.75)
  group.add(basketRim)

  // ---- 横梁甲板（双梁 + 中央设备平台，Nukhada 的蜂窝铝板布局）----
  const beamGeo = new THREE.BoxGeometry(2.2, 0.1, 0.42)
  for (const bz of [0.35, -1.15]) {
    const beam = new THREE.Mesh(beamGeo, deckMat)
    beam.position.set(0, 0.68, bz)
    group.add(beam)
  }
  const deck = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.07, 1.9), deckMat)
  deck.position.set(0, 0.7, -0.4)
  group.add(deck)

  // ---- 外侧扶手栏杆（fastening rails 风格：3 立柱 + 1 横杆/舷）----
  const railPostGeo = new THREE.CylinderGeometry(0.02, 0.02, 0.24, 6)
  const railGeo = new THREE.BoxGeometry(0.035, 0.035, 2.7)
  for (const px of [HULL_X + 0.18, -HULL_X - 0.18]) {
    const rail = new THREE.Mesh(railGeo, whiteMat)
    rail.position.set(px, 0.78, -0.3)
    group.add(rail)
    for (const pz of [-1.5, -0.3, 0.9]) {
      const post = new THREE.Mesh(railPostGeo, whiteMat)
      post.position.set(px, 0.66, pz)
      group.add(post)
    }
  }

  // ---- 太阳能顶棚（4 立柱 + 电池片纹理面板，USV 的标志性部件）----
  const postGeo = new THREE.CylinderGeometry(0.035, 0.035, 0.62, 8)
  for (const px of [-0.72, 0.72]) {
    for (const pz of [-0.95, 0.05]) {
      const post = new THREE.Mesh(postGeo, deckMat)
      post.position.set(px, 1.02, pz)
      group.add(post)
    }
  }
  const canopyFrame = new THREE.Mesh(new THREE.BoxGeometry(1.84, 0.05, 1.6), deckMat)
  canopyFrame.position.set(0, 1.345, -0.45)
  group.add(canopyFrame)
  const canopy = new THREE.Mesh(new THREE.BoxGeometry(1.74, 0.05, 1.5), solarMat)
  canopy.position.set(0, 1.385, -0.45)
  canopy.rotation.x = -0.05
  group.add(canopy)

  // ---- GPS 蘑菇头（顶棚尾部）----
  const gps = new THREE.Mesh(
    new THREE.SphereGeometry(0.11, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2),
    whiteMat,
  )
  gps.position.set(0.45, 1.42, -1.0)
  group.add(gps)

  // ---- 视觉云台（顶棚前沿下的摄像头球，清理船的视觉识别传感器）----
  const gimbal = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 10), darkMat)
  gimbal.position.set(0, 1.28, 0.32)
  group.add(gimbal)

  // ---- 传感器桅杆 + 旋转雷达条 + 状态灯 ----
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.065, 0.85, 10), deckMat)
  mast.position.set(0, 1.1, -1.05)
  group.add(mast)

  const radarPivot = new THREE.Group()
  radarPivot.position.set(0, 1.56, -1.05)
  const radarBar = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.06, 0.12), whiteMat)
  radarPivot.add(radarBar)
  group.add(radarPivot)

  // 状态灯（applyStatusStyle 按船态改色）
  const beaconGeo = new THREE.SphereGeometry(0.09, 12)
  const beaconMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x33e3c9).multiplyScalar(HDR_LIGHT_GAIN) })
  const beacon = new THREE.Mesh(beaconGeo, beaconMat)
  beacon.position.set(0, 1.72, -1.05)
  group.add(beacon)

  // ---- 舷灯：左舷(+x)红、右舷(-x)绿（HDR 增益：夜里/近景泛出灯光辉光）----
  const navPort = new THREE.Mesh(
    new THREE.SphereGeometry(0.06, 10),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff3b30).multiplyScalar(HDR_LIGHT_GAIN) }),
  )
  navPort.position.set(HULL_X, 0.68, 1.35)
  group.add(navPort)
  const navStarboard = new THREE.Mesh(
    new THREE.SphereGeometry(0.06, 10),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0x34c759).multiplyScalar(HDR_LIGHT_GAIN) }),
  )
  navStarboard.position.set(-HULL_X, 0.68, 1.35)
  group.add(navStarboard)

  // ---- 四节打捞机械臂（艉部平台，收拢-作业姿态；关节用平台色强调）----
  // 节构：转台(yaw) → 肩 → 肘 → 腕 → 夹爪（与履带车共用 createArmAssembly）
  const armPlatform = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.09, 0.7), deckMat)
  armPlatform.position.set(0, 0.66, -1.72)
  group.add(armPlatform)

  const armAssembly = createArmAssembly(1)
  armAssembly.root.position.set(0, 0.7, -1.72)
  group.add(armAssembly.root)
  const arm = armAssembly.joints

  // ---- 拾取代理（不可见但可射线命中）----
  // 默认 90km 视角下船体只有几个像素，直接点船体常常打不中（点到旁边的垃圾点）；
  // 用一个"不渲染但可被 raycaster 命中"的盒体把可点区域撑到最低 14px 屏幕当量。
  // material.visible=false 只影响渲染，不影响 Mesh.raycast —— 这是标准做法。
  const pickProxy = new THREE.Mesh(
    new THREE.BoxGeometry(3.0, 2.9, 5.4),
    new THREE.MeshBasicMaterial({ visible: false }),
  )
  pickProxy.position.set(0, 1.2, 0)
  pickProxy.name = 'vessel-pick'
  group.add(pickProxy)

  // ---- 尾流（航行时可见，泡沫纹理 + 轻微摆动的动态感）----
  const wakeGeo = new THREE.PlaneGeometry(2.0, 4.0)
  const wakeMat = new THREE.MeshBasicMaterial({
    map: getWakeTexture(),
    color: 0xeaf7ff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  const wake = new THREE.Mesh(wakeGeo, wakeMat)
  wake.rotation.x = -Math.PI / 2
  wake.position.set(0, 0.05, -3.2)
  group.add(wake)

  // ---- 选中光环（默认隐藏）----
  const ringGeo = new THREE.RingGeometry(2.8, 3.1, 48)
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0xff9500,
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const ring = new THREE.Mesh(ringGeo, ringMat)
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.05
  group.add(ring)

  return {
    group,
    hull: hullPort,
    hullMat,
    deckMat,
    accentMat,
    radarPivot,
    beacon,
    wake: wakeMat,
    selectionRing: ringMat,
    // 四节机械臂关节（update 里做作业摆动）
    arm,
    // 拾取代理（update 里按视距做自适应放大）
    pickProxy,
  }
}

/**
 * 履带式滩涂清洁车（chassis=tracked 的机器人）：
 * 与船体的区别是履带底盘（每侧腰带 + 4 负重轮 + 2 主动轮 + 挡泥板），
 * 同样挂四节机械臂 —— 一支队伍两种底盘，装备语言统一。
 * 原点在履带触地面（贴地时 y 即地面高度）。
 */
function createTrackedRoverModel() {
  const group = new THREE.Group()
  group.name = 'vessel'
  group.scale.setScalar(VESSEL_SCALE)
  group.rotation.order = 'YXZ' // 先航向再俯仰/侧倾（车辆姿态的正确组合顺序）

  const whiteMat = new THREE.MeshStandardMaterial({ color: 0xe8ecef, roughness: 0.45, metalness: 0.12 })
  const deckMat = new THREE.MeshStandardMaterial({ color: 0x3d4a55, roughness: 0.65, metalness: 0.2, flatShading: true })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x22282c, roughness: 0.7, metalness: 0.35 })
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x18a999, roughness: 0.34, metalness: 0.3 })
  const wheelMat = new THREE.MeshStandardMaterial({ color: 0x8b939a, roughness: 0.5, metalness: 0.55 })

  const wheels = []
  const treadMat = new THREE.MeshStandardMaterial({ map: getTreadTexture(), roughness: 0.92, metalness: 0.05 })

  // ---- 履带总成（左右各一）：腰带 + 负重轮 + 主动轮 + 挡泥板 ----
  const trackGeo = new THREE.BoxGeometry(0.24, 0.4, 1.5)
  const wheelGeo = new THREE.CylinderGeometry(0.13, 0.13, 0.09, 14).rotateZ(Math.PI / 2)
  const sprocketGeo = new THREE.CylinderGeometry(0.165, 0.165, 0.1, 14).rotateZ(Math.PI / 2)
  const hubGeo = new THREE.CylinderGeometry(0.045, 0.045, 0.12, 8).rotateZ(Math.PI / 2)
  for (const side of [1, -1]) {
    const tx = side * 0.44
    const belt = new THREE.Mesh(trackGeo, treadMat)
    belt.position.set(tx, 0.2, 0)
    group.add(belt)
    for (const wz of [-0.45, -0.15, 0.15, 0.45]) {
      const wheel = new THREE.Mesh(wheelGeo, wheelMat)
      wheel.position.set(tx + side * 0.16, 0.13, wz)
      group.add(wheel)
      wheels.push(wheel)
      const hub = new THREE.Mesh(hubGeo, darkMat)
      hub.position.copy(wheel.position)
      group.add(hub)
    }
    for (const sz of [0.68, -0.68]) {
      const sp = new THREE.Mesh(sprocketGeo, darkMat)
      sp.position.set(tx + side * 0.15, 0.17, sz)
      group.add(sp)
      wheels.push(sp)
    }
    const fender = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.05, 1.6), deckMat)
    fender.position.set(tx, 0.44, 0)
    group.add(fender)
  }

  // ---- 车体（状态色主体，与船体同一套 status 配色）----
  const bodyMat = new THREE.MeshStandardMaterial({
    color: VESSEL_COLORS.online,
    roughness: 0.45,
    metalness: 0.2,
  })
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.3, 1.24), bodyMat)
  body.position.set(0, 0.47, -0.05)
  group.add(body)
  const skirt = new THREE.Mesh(new THREE.BoxGeometry(1.04, 0.12, 1.3), deckMat)
  skirt.position.set(0, 0.34, -0.05)
  group.add(skirt)

  // 前置收集斗（滩面清扫的"嘴"）
  const scoop = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.22, 0.5), deckMat)
  scoop.position.set(0, 0.24, 0.78)
  scoop.rotation.x = -0.16
  group.add(scoop)
  const scoopLip = new THREE.Mesh(new THREE.BoxGeometry(1.08, 0.05, 0.12), accentMat)
  scoopLip.position.set(0, 0.15, 0.99)
  group.add(scoopLip)

  // 传感器桅杆（云台球 + 天线 + 状态灯）与顶部小太阳能板
  const mast = new THREE.Group()
  mast.position.set(0, 0.62, -0.42)
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.045, 0.42, 8), deckMat)
  pole.position.y = 0.21
  mast.add(pole)
  const gimbal = new THREE.Mesh(new THREE.SphereGeometry(0.085, 12, 10), darkMat)
  gimbal.position.set(0, 0.46, 0.03)
  mast.add(gimbal)
  const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.3, 6), whiteMat)
  antenna.position.set(0.09, 0.6, -0.06)
  mast.add(antenna)
  const beaconMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x33e3c9).multiplyScalar(HDR_LIGHT_GAIN) })
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10), beaconMat)
  beacon.position.set(-0.1, 0.48, -0.08)
  mast.add(beacon)
  group.add(mast)

  const panel = new THREE.Mesh(
    new THREE.BoxGeometry(0.7, 0.03, 0.5),
    new THREE.MeshStandardMaterial({ color: 0x1b2b45, roughness: 0.3, metalness: 0.6 }),
  )
  panel.position.set(0, 0.64, -0.02)
  panel.rotation.x = 0.06
  group.add(panel)

  // ---- 四节机械臂（小一号：0.55 尺度）----
  const armAssembly = createArmAssembly(0.55)
  armAssembly.root.position.set(0, 0.62, -0.52)
  group.add(armAssembly.root)
  const arm = armAssembly.joints

  // 拾取代理（同船体：不可见但可射线命中）
  const pickProxy = new THREE.Mesh(
    new THREE.BoxGeometry(1.5, 1.5, 2.0),
    new THREE.MeshBasicMaterial({ visible: false }),
  )
  pickProxy.position.set(0, 0.7, -0.1)
  pickProxy.name = 'vessel-pick'
  group.add(pickProxy)

  // 选中光环（决策高亮用；不带尾流 —— 履带车不划水）
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0xff9500,
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.5, 1.7, 40), ringMat)
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.05
  group.add(ring)

  return {
    group,
    hull: body,
    hullMat: bodyMat,
    deckMat,
    accentMat,
    radarPivot: null,
    beacon,
    wake: null, // 履带车无尾流（update 里有空值保护）
    selectionRing: ringMat,
    arm,
    pickProxy,
    tracked: { wheels, treadMat, mast },
  }
}

/**
 * 岸基机械臂工位（chassis=arm）。
 *
 * 与船体/履带车不同，机械臂是**固定在岸上的作业端**：不巡航、不下水。
 * 之前它落进「非 tracked 即 boat」的兜底分支，被渲染成一条船停在岸上 ——
 * 所以这里给它独立模型（桩基平台 + 料槽 + 四节臂 + 状态灯），
 * 视觉语言（配色 / 四节臂装配 / 光环）与其余两种底盘保持一致。
 * 原点在桩基触地面，与其它模型同口径；`tracked: null` 表示不参与履带滚动。
 */
function createArmStationModel() {
  const group = new THREE.Group()
  group.name = 'vessel'
  group.scale.setScalar(VESSEL_SCALE)

  const whiteMat = new THREE.MeshStandardMaterial({ color: 0xe8ecef, roughness: 0.45, metalness: 0.12 })
  const deckMat = new THREE.MeshStandardMaterial({ color: 0x3d4a55, roughness: 0.7, metalness: 0.2, flatShading: true })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x22282c, roughness: 0.7, metalness: 0.35 })
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x18a999, roughness: 0.34, metalness: 0.3 })

  // ---- 桩基平台：四根桩 + 台面 ----
  for (const sx of [1, -1]) {
    for (const sz of [1, -1]) {
      const pile = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.44, 8), darkMat)
      pile.position.set(sx * 0.42, 0.06, sz * 0.42)
      group.add(pile)
    }
  }
  const deck = new THREE.Mesh(new THREE.BoxGeometry(1.05, 0.1, 1.05), deckMat)
  deck.position.set(0, 0.32, 0)
  group.add(deck)

  // ---- 料槽：对应抓取闭环里的放置点（side_hopper）----
  const hopper = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.2, 0.3), whiteMat)
  hopper.position.set(0.3, 0.47, 0.02)
  group.add(hopper)
  const hopperRim = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.03, 0.32), accentMat)
  hopperRim.position.set(0.3, 0.58, 0.02)
  group.add(hopperRim)

  // ---- 控制柜 ----
  const cabinet = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.34, 0.22), whiteMat)
  cabinet.position.set(-0.32, 0.54, -0.3)
  group.add(cabinet)

  // ---- 四节机械臂（与船体/履带车同一套装配）----
  const armAssembly = createArmAssembly(0.6)
  armAssembly.root.position.set(-0.06, 0.37, 0.02)
  group.add(armAssembly.root)
  const arm = armAssembly.joints

  // ---- 状态灯（色由 applyStatusStyle 按在线/作业状态驱动）----
  const beaconMat = new THREE.MeshStandardMaterial({ color: 0x18a999, roughness: 0.3, metalness: 0.2 })
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10), beaconMat)
  beacon.position.set(-0.32, 0.74, -0.3)
  group.add(beacon)

  // ---- 拾取代理：不可见但可射线命中（远视角下也要点得中）----
  const pickProxy = new THREE.Mesh(
    new THREE.BoxGeometry(1.4, 1.6, 1.4),
    new THREE.MeshBasicMaterial({ visible: false }),
  )
  pickProxy.position.set(0, 0.6, 0)
  pickProxy.name = 'vessel-pick'
  group.add(pickProxy)

  // ---- 选中光环（决策高亮用）----
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0xff9500, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false,
  })
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.5, 1.7, 40), ringMat)
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.05
  group.add(ring)

  return {
    group,
    hull: deck,
    hullMat: deckMat,
    deckMat,
    accentMat,
    radarPivot: null,
    beacon,
    wake: null,
    selectionRing: ringMat,
    arm,
    pickProxy,
    tracked: null, // ★ 不参与履带滚动（update 里有空值保护）
  }
}

/**
 * 船体管理器类
 */
export class VesselManager {
  /**
   * @param {THREE.Scene} scene
   * @param {Object} [options]
   * @param {Function} [options.sampleHeight] 世界坐标 (x,z) → 地形高度（米），
   *   用于把落在岸上的船体抬到地形之上（否则模型会被山体埋掉）
   */
  constructor(scene, options = {}) {
    this.scene = scene
    this.sampleHeight = options.sampleHeight || null
    this.vessels = new Map() // robot_id → vessel data
    this.waveTime = 0
  }

  /** 船体基准高度：海面最低 25m；陆地上的船抬到地形之上；履带车贴地 */
  baseYFor(x, z, chassis = 'boat') {
    const ground = this.sampleHeight ? this.sampleHeight(x, z) : 0
    if (chassis === 'tracked' || chassis === 'arm') {
      // 贴地单位（履带车 / 岸基机械臂工位）：贴地 +2 留一点余量防陷
      return ground + 2
    }
    let base = 25
    if (ground > 3) {
      // +70：船模在水线处的原点面向下还有约 60m 船体（scale=200），
      // 只抬 45m 时船底会扎进地表约 15m（实测观感"半埋"）；+70 留 10m 余量
      base = Math.max(base, ground + 70)
    }
    return base
  }
  
  /**
   * 更新船体列表（对照数据增删改）
   * @param {Array} robots 机器人数据数组
   * @param {Object} decision 派单决策（可选，用于高亮）
   */
  syncVessels(robots, decision = null) {
    const seen = new Set()
    
    for (const robot of robots) {
      const id = robot.robot_id
      if (!id) continue
      seen.add(id)
      
      const existing = this.vessels.get(id)
      if (existing) {
        this.updateVessel(existing, robot, decision)
      } else {
        this.createVessel(robot, decision)
      }
    }
    
    // 移除已不存在的船
    for (const [id, vessel] of this.vessels) {
      if (!seen.has(id)) {
        this.removeVessel(id)
      }
    }
  }
  
  createVessel(robot, decision) {
    const type = robot.chassis === 'tracked' ? 'tracked'
      : (robot.chassis === 'arm' ? 'arm' : 'boat')
    const model = createVesselModel({ type })
    const { x, z } = lngLatToScene(robot.lng || 119.86, robot.lat || 26.35)
    const baseY = this.baseYFor(x, z, robot.chassis)
    
    model.group.position.set(x, baseY, z)
    model.group.userData = {
      type: 'vessel',
      robotId: robot.robot_id,
      robotData: robot,
    }
    
    // 初始朝向
    if (robot.heading != null) {
      model.group.rotation.y = -robot.heading * Math.PI / 180
    }
    
    this.scene.add(model.group)
    
    const vessel = {
      id: robot.robot_id,
      model,
      data: { ...robot },
      baseY,
      targetPos: new THREE.Vector3(x, baseY, z),
      currentPos: new THREE.Vector3(x, baseY, z),
      targetHeading: model.group.rotation.y,
      decisionRole: null,
    }
    
    this.vessels.set(robot.robot_id, vessel)
    this.applyStatusStyle(vessel, robot, decision)
  }
  
  updateVessel(vessel, robot, decision) {
    vessel.data = { ...vessel.data, ...robot }
    
    // 更新目标位置（平滑移动）
    const { x, z } = lngLatToScene(robot.lng || 119.86, robot.lat || 26.35)
    vessel.baseY = this.baseYFor(x, z, robot.chassis)
    vessel.targetPos.set(x, vessel.baseY, z)
    
    // 更新目标朝向
    if (robot.heading != null) {
      vessel.targetHeading = -robot.heading * Math.PI / 180
    }
    
    this.applyStatusStyle(vessel, robot, decision)
  }
  
  applyStatusStyle(vessel, robot, decision) {
    const { model } = vessel
    const status = robot.status || 'offline'
    const baseColor = VESSEL_COLORS[status] || VESSEL_COLORS.offline
    
    // 决策高亮优先
    let decisionRole = null
    if (decision?.selected_robot_id === robot.robot_id) {
      decisionRole = 'selected'
      model.selectionRing.color.setHex(DECISION_COLORS.selected)
      model.selectionRing.opacity = 0.6
    } else if (decision?.candidates?.some(c => c.robot_id === robot.robot_id)) {
      decisionRole = 'candidate'
      model.selectionRing.color.setHex(DECISION_COLORS.candidate)
      model.selectionRing.opacity = 0.35
    } else {
      model.selectionRing.opacity = 0
    }
    vessel.decisionRole = decisionRole
    
    // 船体颜色
    model.hullMat.color.setHex(baseColor)
    
    // 尾流：航行中显示（纹理摆动在 update 里驱动）
    const isMoving = ['navigating', 'collecting'].includes(status)
    if (model.wake) model.wake.opacity = isMoving ? 0.42 : 0.06 // 履带车无尾流
    
    // 航行灯颜色（保持 HDR 增益，泛光管线里才是"灯"而不是"色块"）
    const beaconColor = status === 'collecting' ? 0xff9500 : 
                        status === 'navigating' ? 0x33e3c9 : 0x18a999
    model.beacon.material.color.setHex(beaconColor).multiplyScalar(HDR_LIGHT_GAIN)
  }
  
  removeVessel(id) {
    const vessel = this.vessels.get(id)
    if (vessel) {
      this.scene.remove(vessel.model.group)
      this.vessels.delete(id)
    }
  }
  
  /**
   * 每帧更新（平滑移动 + 波浪起伏）
   */
  update(dt, time, camera = null, viewportH = 800) {
    this.waveTime = time

    // 尾流纹理轻微摆动：所有船共享同一张纹理，统一步调即可（不做整周期滚动，防图案跳变）
    if (this._wakeTex === undefined) this._wakeTex = getWakeTexture()
    this._wakeTex.offset.y = 0.05 + Math.sin(time * 0.9) * 0.08

    for (const vessel of this.vessels.values()) {
      const { model, targetPos, targetHeading } = vessel
      
      // 平滑位置插值
      const damping = 1 - Math.exp(-dt * 2.4)
      model.group.position.lerp(targetPos, damping)
      
      // 随浪摇摆 / 履带车贴地姿态
      const isMoving = ['navigating', 'collecting'].includes(vessel.data.status)
      const isTracked = vessel.data.chassis === 'tracked'
      
      // 岸基机械臂工位与履带车同属「贴地单位」：不随浪起伏，按地形取基准高度。
      // 它没有履带，滚动分支靠 model.tracked 的空值保护跳过。
      if ((isTracked || vessel.data.chassis === 'arm') && this.sampleHeight) {
        // 履带车：贴地 + 沿航向采样坡度做俯仰/侧倾（不是船，不随浪起伏）；
        // 履带轮与走带按"实际位移速度"滚动 —— 数据不动，履带就不空转
        const hdg = model.group.rotation.y
        const fwdX = Math.sin(hdg)
        const fwdZ = Math.cos(hdg)
        const rgtX = Math.cos(hdg)
        const rgtZ = -Math.sin(hdg)
        const px = model.group.position.x
        const pz = model.group.position.z
        const hF = this.sampleHeight(px + fwdX * 4, pz + fwdZ * 4)
        const hB = this.sampleHeight(px - fwdX * 4, pz - fwdZ * 4)
        const hR = this.sampleHeight(px + rgtX * 4, pz + rgtZ * 4)
        const hL = this.sampleHeight(px - rgtX * 4, pz - rgtZ * 4)
        model.group.position.y = vessel.baseY
        model.group.rotation.x = -Math.atan2(hF - hB, 8) // 前高 → 车头上仰
        model.group.rotation.z = Math.atan2(hR - hL, 8) // 右高 → 右侧抬起
        
        const moved =
          vessel.lastX === undefined ? 0 : Math.hypot(px - vessel.lastX, pz - vessel.lastZ)
        const speed = dt > 0 ? moved / dt : 0
        if (model.tracked) {
          vessel.wheelSpin = (vessel.wheelSpin || 0) + (speed / 26) * dt
          for (const wheel of model.tracked.wheels) wheel.rotation.x = vessel.wheelSpin
          model.tracked.treadMat.map.offset.y = -vessel.wheelSpin * 0.22
          model.tracked.mast.rotation.y = Math.sin(time * 0.5) * 0.9 // 云台缓慢扫视
        }
        vessel.lastX = px
        vessel.lastZ = pz
      } else {
        // 波浪起伏（波幅 ~±23m；基线抬高保证浪谷时船底也不穿海面；
        // 落在岸上的坐标由 baseY 抬到地形之上）
        const waveH = this.waveHeight(model.group.position.x, model.group.position.z, time)
        model.group.position.y = vessel.baseY + waveH * 0.6
        // 随浪摇摆
        const rollAmp = isMoving ? 0.05 : 0.022
        const pitchAmp = isMoving ? 0.035 : 0.016
        model.group.rotation.z = Math.sin(time * 1.25) * rollAmp
        model.group.rotation.x = Math.sin(time * 0.95 + 1.4) * pitchAmp
      }
      
      // 平滑转向（最短弧）
      let delta = targetHeading - model.group.rotation.y
      while (delta > Math.PI) delta -= Math.PI * 2
      while (delta < -Math.PI) delta += Math.PI * 2
      model.group.rotation.y += delta * (1 - Math.exp(-dt * 3))
      
      // 雷达旋转
      if (model.radarPivot) {
        model.radarPivot.rotation.y = time * (isMoving ? 1.9 : 0.9)
      }

      // 四节机械臂：缓慢作业摆动。作业中（collecting）幅度更大、更快，
      // 待机时只是轻微浮动 —— 一眼能看出"哪艘在干活"
      if (model.arm) {
        const working = vessel.data.status === 'collecting'
        const act = working ? 1 : 0.38
        const wsp = working ? 1.5 : 0.5
        const { yaw, j1, j2, j3, j4 } = model.arm
        yaw.rotation.y = Math.PI + Math.sin(time * wsp * 0.9) * 0.5 * act
        j1.rotation.x = 0.6 + Math.sin(time * wsp * 1.1 + 0.5) * 0.15 * act
        j2.rotation.x = 0.75 + Math.sin(time * wsp * 1.35 + 1.7) * 0.2 * act
        j3.rotation.x = 0.8 + Math.sin(time * wsp * 1.6 + 3.0) * 0.24 * act
        j4.rotation.x = 0.5 + Math.sin(time * wsp * 1.9 + 4.1) * 0.18 * act
      }

      // 拾取代理自适应：保证远视角下船体也有 ~14px 的可点窗口，
      // 否则"点船"在默认 90km 视角里几乎点不中（会被旁边的垃圾点抢走）
      if (model.pickProxy && camera) {
        const dist = camera.position.distanceTo(model.group.position)
        const worldPerPx =
          (2 * dist * Math.tan(((camera.fov || 45) * Math.PI) / 360)) / Math.max(1, viewportH)
        const need = worldPerPx * 14 // 目标：14px 屏幕当量
        const base = 3.0 // 代理盒最窄边（局部单位；group 已 ×200）
        const s = Math.min(6, Math.max(1, need / (base * VESSEL_SCALE)))
        model.pickProxy.scale.setScalar(s)
      }

      // 选中光环脉冲
      if (vessel.decisionRole) {
        const pulse = 0.5 + 0.5 * Math.sin(time * 3)
        model.selectionRing.opacity = (vessel.decisionRole === 'selected' ? 0.5 : 0.3) + pulse * 0.2
      }
    }
  }
  
  /**
   * 波浪高度计算：直接使用 TerrainLayer 的共享波参数（SEA_WAVE），
   * 与海面顶点着色器严格同相，船体才不会"陷进"或"飘在"浪面上。
   */
  waveHeight(x, z, t) {
    return seaWaveHeight(x, z, t)
  }
  
  /**
   * 所有船的当前场景坐标（供 RouteManager 记录轨迹/绘制剩余航线）
   * @returns {Map<string, THREE.Vector3>}
   */
  getPositions() {
    const map = new Map()
    for (const [id, vessel] of this.vessels) {
      map.set(id, vessel.model.group.position)
    }
    return map
  }
  
  /**
   * 获取船体 group（供标签层挂 CSS2DObject）
   * @param {string} robotId
   * @returns {THREE.Group|null}
   */
  getVesselGroup(robotId) {
    return this.vessels.get(robotId)?.model.group || null
  }

  /**
   * 获取指定位置的船体（用于射线检测）
   */
  getVesselByObject(object) {
    let current = object
    while (current) {
      if (current.userData?.type === 'vessel') {
        return this.vessels.get(current.userData.robotId)
      }
      current = current.parent
    }
    return null
  }
  
  /**
   * 获取所有可交互对象
   */
  getInteractiveObjects() {
    return Array.from(this.vessels.values()).map(v => v.model.group)
  }
  
  dispose() {
    for (const [id] of this.vessels) {
      this.removeVessel(id)
    }
    this.vessels.clear()
  }
}

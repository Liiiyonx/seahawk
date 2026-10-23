/**
 * 航线可视化管理器：已走轨迹 ribbon + 剩余航线脉冲圆点 + 目标浮标
 *
 * 数据来源：
 *   - 已走轨迹：VesselManager 前端累积的位置历史（不依赖后端轨迹接口）
 *   - 剩余航线：工单目标坐标（tasks.lng/lat）→ 当前船位
 *
 * 视觉分工：
 *   - trail ribbon：实色带状条贴浪面，回答"它从哪来"
 *   - planned dots：沿路径流动的脉冲圆点，回答"它要去哪"（流动方向=航向）
 *   - target buoy：目标点浮标 + 双脉冲环，可点击 → 跳转对应工单仿真页
 */

import * as THREE from 'three'
import { lngLatToScene, seaWaveHeight } from './TerrainLayer.js'

const MAX_TRAIL_POINTS = 180   // 每条船最多保留的轨迹点
const TRAIL_WIDTH = 60         // 轨迹带宽度（米，按 165km 场景符号化）
const PLANNED_DOTS = 36        // 剩余航线圆点数
const DOT_SIZE = 28            // 圆点半径（米）
const SURFACE_OFFSET = 25      // 贴浪元素的抬升高度（浪幅 ±20m，防穿模）

/** 航线配色（与图例/船体状态同色系） */
const ROUTE_COLORS = {
  navigating: 0x18a999,
  collecting: 0xff9500,
  assigned: 0x7a5af8,
  default: 0x18a999,
}

// ---------------------------------------------------------------- 目标浮标

function createTargetBuoy(color) {
  const group = new THREE.Group()
  group.name = 'route-target'

  const buoyMat = new THREE.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0.2 })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x232b32, roughness: 0.6 })

  // 浮体（符号化尺寸：165km 场景下的视觉锚点，非真实比例）
  const buoy = new THREE.Mesh(new THREE.CylinderGeometry(150, 110, 170, 16), buoyMat)
  buoy.position.y = 85
  group.add(buoy)

  const stripe = new THREE.Mesh(new THREE.CylinderGeometry(152, 152, 34, 16), darkMat)
  stripe.position.y = 110
  group.add(stripe)

  // 标杆 + 旗
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(12, 12, 340, 8), darkMat)
  pole.position.y = 330
  group.add(pole)

  const flag = new THREE.Mesh(new THREE.BoxGeometry(150, 90, 8), buoyMat)
  flag.position.set(78, 440, 0)
  group.add(flag)

  // 双层脉冲环
  const ringGeo = new THREE.RingGeometry(240, 290, 48)
  const ringMat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.5,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const ring = new THREE.Mesh(ringGeo, ringMat)
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 20
  group.add(ring)

  const ring2Mat = ringMat.clone()
  ring2Mat.opacity = 0.25
  const ring2 = new THREE.Mesh(new THREE.RingGeometry(340, 380, 48), ring2Mat)
  ring2.rotation.x = -Math.PI / 2
  ring2.position.y = 18
  group.add(ring2)

  return { group, ring, ring2 }
}

// ---------------------------------------------------------------- 单条航线

class ShipRoute {
  constructor(scene, robotId, color) {
    this.robotId = robotId
    this.color = color

    // ---- 已走轨迹 ribbon（动态 BufferGeometry）
    this.trailPoints = [] // Vector3[]（场景坐标，y 由波高实时计算）
    const maxVerts = MAX_TRAIL_POINTS * 2
    this.trailGeo = new THREE.BufferGeometry()
    this.trailPositions = new Float32Array(maxVerts * 3)
    this.trailGeo.setAttribute('position', new THREE.BufferAttribute(this.trailPositions, 3))
    // 索引：每对相邻点构成两个三角形
    const indices = []
    for (let i = 0; i < MAX_TRAIL_POINTS - 1; i += 1) {
      const a = i * 2
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2)
    }
    this.trailGeo.setIndex(indices)
    this.trailGeo.setDrawRange(0, 0)
    this.trailMat = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    this.trailMesh = new THREE.Mesh(this.trailGeo, this.trailMat)
    this.trailMesh.frustumCulled = false
    this.trailMesh.renderOrder = 2
    scene.add(this.trailMesh)

    // ---- 剩余航线圆点（InstancedMesh + 流动脉冲）
    this.dotsMesh = new THREE.InstancedMesh(
      new THREE.CircleGeometry(DOT_SIZE, 12),
      new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.85,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
      PLANNED_DOTS,
    )
    this.dotsMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
    this.dotsMesh.frustumCulled = false
    this.dotsMesh.renderOrder = 3
    // 实例颜色：逐个写入，流动脉冲靠颜色亮度差
    this.dotsMesh.instanceColor = new THREE.InstancedBufferAttribute(
      new Float32Array(PLANNED_DOTS * 3), 3,
    )
    scene.add(this.dotsMesh)

    // ---- 目标浮标
    const buoy = createTargetBuoy(color)
    this.targetGroup = buoy.group
    this.targetRing = buoy.ring
    this.targetRing2 = buoy.ring2
    this.targetGroup.visible = false
    scene.add(this.targetGroup)

    // 当前航线状态
    this.targetPos = null // Vector3 | null
    this.taskId = ''
    this.phase = ''
  }

  /** 追加轨迹点（距离阈值由调用方把控） */
  pushTrailPoint(pos) {
    this.trailPoints.push(pos.clone())
    if (this.trailPoints.length > MAX_TRAIL_POINTS) {
      this.trailPoints.shift()
    }
  }

  clearTrail() {
    this.trailPoints.length = 0
    this.trailGeo.setDrawRange(0, 0)
  }

  /** 设置航线目标（null = 无活跃航线，隐藏剩余航线与浮标） */
  setTarget(targetLngLat, { taskId = '', phase = '' } = {}) {
    if (!targetLngLat) {
      this.targetPos = null
      this.taskId = ''
      this.phase = ''
      this.targetGroup.visible = false
      this.dotsMesh.count = 0
      return
    }
    const { x, z } = lngLatToScene(targetLngLat.lng, targetLngLat.lat)
    this.targetPos = new THREE.Vector3(x, 0, z)
    this.taskId = taskId
    this.phase = phase
    this.targetGroup.position.set(x, 0, z)
    this.targetGroup.visible = true
    // 点击跳转工单的载体
    this.targetGroup.userData = {
      type: 'routeTarget',
      taskId,
      robotId: this.robotId,
    }
  }

  /**
   * 每帧更新
   * @param {THREE.Vector3} shipPos 船当前位置
   * @param {number} time
   */
  update(shipPos, time) {
    this.updateTrail(time)
    this.updatePlannedDots(shipPos, time)
    this.updateTargetPulse(time)
  }

  updateTrail(time) {
    const pts = this.trailPoints
    const n = pts.length
    if (n < 2) {
      this.trailGeo.setDrawRange(0, 0)
      return
    }
    const half = TRAIL_WIDTH / 2
    for (let i = 0; i < n; i += 1) {
      const p = pts[i]
      // 路径切线 → 法线（XZ 平面内垂直）
      const prev = pts[Math.max(0, i - 1)]
      const next = pts[Math.min(n - 1, i + 1)]
      let dx = next.x - prev.x
      let dz = next.z - prev.z
      const len = Math.hypot(dx, dz) || 1
      dx /= len
      dz /= len
      const nx = -dz
      const nz = dx
      const y = SURFACE_OFFSET + seaWaveHeight(p.x, p.z, time) * 0.6 // 贴浪但抬高，防浪峰穿模
      const base = i * 6
      this.trailPositions[base] = p.x + nx * half
      this.trailPositions[base + 1] = y
      this.trailPositions[base + 2] = p.z + nz * half
      this.trailPositions[base + 3] = p.x - nx * half
      this.trailPositions[base + 4] = y
      this.trailPositions[base + 5] = p.z - nz * half
    }
    this.trailGeo.attributes.position.needsUpdate = true
    this.trailGeo.setDrawRange(0, (n - 1) * 6)
  }

  updatePlannedDots(shipPos, time) {
    if (!this.targetPos || !shipPos) {
      this.dotsMesh.count = 0
      return
    }
    const start = shipPos
    const end = this.targetPos
    const span = Math.hypot(end.x - start.x, end.z - start.z)
    if (span < 30) {
      // 快到目标点，圆点收起
      this.dotsMesh.count = 0
      return
    }
    this.dotsMesh.count = PLANNED_DOTS

    const tmpMatrix = new THREE.Matrix4()
    const tmpQuat = new THREE.Quaternion()
    const tmpScale = new THREE.Vector3()
    const tmpPos = new THREE.Vector3()
    const flatQuat = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0))
    const color = new THREE.Color(this.color)

    for (let i = 0; i < PLANNED_DOTS; i += 1) {
      const t = (i + 1) / (PLANNED_DOTS + 1)
      tmpPos.lerpVectors(start, end, t)
      tmpPos.y = SURFACE_OFFSET + seaWaveHeight(tmpPos.x, tmpPos.z, time) * 0.6
      tmpQuat.copy(flatQuat)
      // 远端圆点略小，透视感更强
      const s = 1 - t * 0.3
      tmpScale.setScalar(s)
      tmpMatrix.compose(tmpPos, tmpQuat, tmpScale)
      this.dotsMesh.setMatrixAt(i, tmpMatrix)

      // 流动脉冲：亮度波沿路径向目标方向传播
      const wave = 0.5 + 0.5 * Math.sin(time * 3.2 - t * 9.0)
      const brightness = 0.35 + wave * 0.65
      this.dotsMesh.setColorAt(i, color.clone().multiplyScalar(brightness))
    }
    this.dotsMesh.instanceMatrix.needsUpdate = true
    if (this.dotsMesh.instanceColor) this.dotsMesh.instanceColor.needsUpdate = true
  }

  updateTargetPulse(time) {
    if (!this.targetGroup.visible) return
    const pulse = 0.5 + 0.5 * Math.sin(time * 2.2)
    this.targetRing.scale.setScalar(1 + pulse * 0.25)
    this.targetRing.material.opacity = 0.3 + pulse * 0.3
    const pulse2 = 0.5 + 0.5 * Math.sin(time * 2.2 - 1.1) // 相位错开，双层扩散感
    this.targetRing2.scale.setScalar(1 + pulse2 * 0.35)
    this.targetRing2.material.opacity = 0.12 + pulse2 * 0.18
    // 浮标随浪起伏
    this.targetGroup.position.y = SURFACE_OFFSET + seaWaveHeight(
      this.targetGroup.position.x,
      this.targetGroup.position.z,
      time,
    ) * 0.6
  }

  setColor(color) {
    this.color = color
    this.trailMat.color.setHex(color)
  }

  dispose(scene) {
    scene.remove(this.trailMesh)
    scene.remove(this.dotsMesh)
    scene.remove(this.targetGroup)
    this.trailGeo.dispose()
    this.trailMat.dispose()
    this.dotsMesh.geometry.dispose()
    this.dotsMesh.material.dispose()
  }
}

// ---------------------------------------------------------------- 管理器

export class RouteManager {
  /**
   * @param {THREE.Scene} scene
   * @param {Function} onTargetClick 点击目标浮标回调 ({ taskId, robotId }) => void
   */
  constructor(scene, onTargetClick) {
    this.scene = scene
    this.onTargetClick = onTargetClick || (() => {})
    this.routes = new Map() // robotId → ShipRoute
  }

  /**
   * 同步航线目标
   * @param {Array} routes [{ robotId, targetLng, targetLat, taskId, phase }]
   */
  syncRoutes(routes) {
    const seen = new Set()
    for (const r of routes || []) {
      if (!r?.robotId) continue
      seen.add(r.robotId)
      let route = this.routes.get(r.robotId)
      if (!route) {
        const color = ROUTE_COLORS[r.phase] || ROUTE_COLORS.default
        route = new ShipRoute(this.scene, r.robotId, color)
        this.routes.set(r.robotId, route)
      }
      if (r.targetLng != null && r.targetLat != null) {
        route.setTarget({ lng: r.targetLng, lat: r.targetLat }, { taskId: r.taskId, phase: r.phase })
        route.setColor(ROUTE_COLORS[r.phase] || ROUTE_COLORS.default)
      } else {
        route.setTarget(null)
      }
    }
    // 没有活跃航线的船：保留轨迹但隐藏目标
    for (const [robotId, route] of this.routes) {
      if (!seen.has(robotId)) route.setTarget(null)
    }
  }

  /**
   * 记录船位到轨迹（由外部在每帧/定时调用）
   * @param {string} robotId
   * @param {THREE.Vector3} pos 场景坐标（y 忽略）
   * @param {number} minDistance 距上一个轨迹点的最小记录间距（米）
   */
  recordTrailPoint(robotId, pos, minDistance = 15) {
    let route = this.routes.get(robotId)
    if (!route) {
      route = new ShipRoute(this.scene, robotId, ROUTE_COLORS.default)
      this.routes.set(robotId, route)
    }
    const pts = route.trailPoints
    if (!pts.length) {
      route.pushTrailPoint(pos)
      return
    }
    const last = pts[pts.length - 1]
    if (Math.hypot(pos.x - last.x, pos.z - last.z) >= minDistance) {
      route.pushTrailPoint(pos)
    }
  }

  clearTrail(robotId) {
    this.routes.get(robotId)?.clearTrail()
  }

  /**
   * 每帧更新所有航线
   * @param {Map<string, THREE.Vector3>} shipPositions robotId → 场景坐标
   * @param {number} time
   */
  update(shipPositions, time) {
    for (const [robotId, route] of this.routes) {
      route.update(shipPositions.get(robotId) || null, time)
    }
  }

  /** 目标浮标加入可交互列表 */
  getInteractiveObjects() {
    const list = []
    for (const route of this.routes.values()) {
      if (route.targetGroup.visible) list.push(route.targetGroup)
    }
    return list
  }

  /** 处理点击命中（返回是否消费了这次点击） */
  handleClick(object) {
    let current = object
    while (current) {
      if (current.userData?.type === 'routeTarget') {
        this.onTargetClick(current.userData)
        return true
      }
      current = current.parent
    }
    return false
  }

  dispose() {
    for (const route of this.routes.values()) {
      route.dispose(this.scene)
    }
    this.routes.clear()
  }
}

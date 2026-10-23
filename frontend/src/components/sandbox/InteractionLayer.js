/**
 * 交互层：处理3D场景中的点击、悬停事件
 * 
 * 职责：
 * - 射线检测（Raycasting）
 * - 点击跳转路由
 * - 悬停高亮反馈
 */

import * as THREE from 'three'
import { lngLatToScene } from './TerrainLayer.js'

export class InteractionLayer {
  /**
   * @param {THREE.Camera} camera
   * @param {THREE.Scene} scene
   * @param {Object} options
   * @param {Function} options.onVesselClick 点击船体回调 (robotData) => void
   * @param {Function} options.onEventClick 点击事件标记回调 (eventData) => void
   * @param {Function} options.onRouteTargetClick 点击航线目标浮标回调 ({ taskId, robotId }) => void
   * @param {Function} options.onHover 悬停回调 (hitData | null) => void
   */
  constructor(camera, scene, options = {}) {
    this.camera = camera
    this.scene = scene
    this.onVesselClick = options.onVesselClick || (() => {})
    this.onEventClick = options.onEventClick || (() => {})
    this.onRouteTargetClick = options.onRouteTargetClick || (() => {})
    this.onDebrisClick = options.onDebrisClick || (() => {})
    this.onEmptyClick = options.onEmptyClick || (() => {}) // 点空白（未命中任何可交互对象）
    this.onHover = options.onHover || (() => {})
    
    this.raycaster = new THREE.Raycaster()
    this.pointer = new THREE.Vector2()
    this.pointerDirty = false
    this.domElement = null
    this.hoveredObject = null
    this.interactiveObjects = []
    
    // 绑定事件
    this.handleClick = this.handleClick.bind(this)
    this.handlePointerMove = this.handlePointerMove.bind(this)
    this.handlePointerLeave = this.handlePointerLeave.bind(this)
  }
  
  /**
   * 注册可交互对象
   * @param {Array<THREE.Object3D>} objects
   */
  setInteractiveObjects(objects) {
    this.interactiveObjects = objects
  }
  
  /**
   * 添加事件监听到DOM元素
   */
  attach(domElement) {
    this.domElement = domElement
    domElement.addEventListener('click', this.handleClick)
    // 悬停只记坐标，射线检测放到 rAF 里（每帧最多一次），
    // pointermove 高频触发时不再重复做 intersect，主线程不再被鼠标拖卡
    domElement.addEventListener('pointermove', this.handlePointerMove)
    domElement.addEventListener('pointerleave', this.handlePointerLeave)
  }
  
  detach(domElement) {
    domElement.removeEventListener('click', this.handleClick)
    domElement.removeEventListener('pointermove', this.handlePointerMove)
    domElement.removeEventListener('pointerleave', this.handlePointerLeave)
    this.domElement = null
  }
  
  handleClick(event) {
    this.updatePointer(event)
    this.prepareRaycast()
    
    const intersects = this.raycaster.intersectObjects(this.interactiveObjects, true)
    const resolved = this.resolveHit(intersects)
    if (!resolved) {
      this.onEmptyClick()
      return
    }
    const { hit, root } = resolved
    
    const { type, robotData, eventData, taskId } = root.userData
    
    if (type === 'vessel' && robotData) {
      this.onVesselClick(robotData, hit.point)
    } else if (type === 'event' && eventData) {
      this.onEventClick(eventData, hit.point)
    } else if (type === 'routeTarget' && taskId) {
      // 航线目标浮标：点击跳转对应工单仿真页
      this.onRouteTargetClick({ taskId, robotId: root.userData.robotId }, hit.point)
    } else if (type === 'debris') {
      // 垃圾点云：hit.index 是命中点在几何里的下标 → 反查类别
      const info = root.userData.layer?.getInfoAt(root.userData.kind, hit.index)
      if (info) this.onDebrisClick(info, hit.point)
    }
  }

  /**
   * 射线准备：
   * 1) 点云（垃圾）拾取阈值按"12 像素的屏幕当量"换算 —— 之前用视距的固定比例，
   *    远景下阈值换算成屏幕足有 ~27 像素，会把船/事件点的点击全部抢走；
   * 2) 用相机 fov + 画布高度求"每像素对应多少世界单位"，任何视距下都是同一手感。
   */
  prepareRaycast() {
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const viewDist = this.camera.position.length()
    const hPx = this.domElement?.clientHeight || 800
    const worldPerPx =
      (2 * viewDist * Math.tan(((this.camera.fov || 45) * Math.PI) / 360)) / hPx
    this.raycaster.params.Points.threshold = Math.max(60, worldPerPx * 12)
  }

  /**
   * 从命中列表里挑"最该响应的对象"：实体模型（船/事件/作业目标）优先于点云（垃圾）。
   * 点云的阈值是屏幕像素当量，总会盖到实体周围的空域 —— 不设类型优先级的话，
   * 站在船边上一点就被判定成点到了垃圾。
   */
  resolveHit(intersects) {
    if (!intersects.length) return null // 空命中（点空白）必须早退，交给 onEmptyClick
    for (const hit of intersects) {
      const root = this.findInteractiveRoot(hit.object)
      if (root && root.userData.type !== 'debris') return { hit, root }
    }
    const hit = intersects[0]
    const root = this.findInteractiveRoot(hit.object)
    return root ? { hit, root } : null
  }
  
  handlePointerMove(event) {
    this.updatePointer(event)
    this.pointerDirty = true
  }

  /** 指针离开画布：清悬停（否则 tooltip 会"钉"在最后一帧） */
  handlePointerLeave() {
    this.pointerDirty = false
    if (this.hoveredObject) {
      this.setHoverStyle(this.hoveredObject, false)
      this.hoveredObject = null
    }
    if (this.domElement) this.domElement.style.cursor = ''
    this.onHover(null)
  }

  /**
   * 每帧调用（由渲染循环驱动）：仅在指针移动过时才做射线检测
   */
  update() {
    if (!this.pointerDirty) return
    this.pointerDirty = false
    this.prepareRaycast()
    
    const intersects = this.raycaster.intersectObjects(this.interactiveObjects, true)
    const resolved = this.resolveHit(intersects)
    
    if (resolved) {
      const { hit, root } = resolved
      
      if (this.domElement) this.domElement.style.cursor = 'pointer'
      if (root !== this.hoveredObject) {
        // 离开旧对象
        if (this.hoveredObject) {
          this.setHoverStyle(this.hoveredObject, false)
        }
        // 进入新对象
        this.hoveredObject = root
        if (root) {
          this.setHoverStyle(root, true)
        }
      }
      if (root) {
        // 垃圾点云悬停：带类别资料（其他对象直接透传 userData 里的实体数据）
        const data =
          root.userData.type === 'debris'
            ? { kind: root.userData.kind, ...(root.userData.layer?.getInfoAt(root.userData.kind, hit.index) || {}) }
            : root.userData.robotData || root.userData.eventData || root.userData
        this.onHover({
          type: root.userData.type,
          data,
          point: hit.point,
        })
      } else if (this.hoveredObject === null) {
        // 命中但不可交互（如地形被误选）：确保 tooltip 清空
        this.onHover(null)
      }
    } else {
      if (this.domElement) this.domElement.style.cursor = ''
      if (this.hoveredObject) {
        this.setHoverStyle(this.hoveredObject, false)
        this.hoveredObject = null
        this.onHover(null)
      }
    }
  }
  
  updatePointer(event) {
    const rect = event.target.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  }
  
  findInteractiveRoot(object) {
    let current = object
    while (current) {
      const t = current.userData?.type
      if (t === 'vessel' || t === 'event' || t === 'routeTarget' || t === 'debris') {
        return current
      }
      current = current.parent
    }
    return null
  }
  
  setHoverStyle(object, isHover) {
    // 通过遍历子对象设置emissive
    object.traverse((child) => {
      if (child.isMesh && child.material) {
        if (isHover) {
          child.userData._originalEmissive = child.material.emissive?.getHex() || 0x000000
          child.material.emissive?.setHex(0x333333)
        } else {
          const original = child.userData._originalEmissive
          if (original !== undefined) {
            child.material.emissive?.setHex(original)
            delete child.userData._originalEmissive
          }
        }
      }
    })
  }
  
  dispose() {
    this.interactiveObjects = []
    this.hoveredObject = null
  }
}

/**
 * 事件标记管理器：在3D场景中标记事件位置
 */
export class EventMarkerManager {
  constructor(scene) {
    this.scene = scene
    this.markers = new Map()
  }
  
  syncEvents(events) {
    const seen = new Set()
    
    for (const event of events) {
      const id = event.event_id
      if (!id) continue
      seen.add(id)
      
      const existing = this.markers.get(id)
      if (existing) {
        this.updateMarker(existing, event)
      } else {
        this.createMarker(event)
      }
    }
    
    for (const [id, marker] of this.markers) {
      if (!seen.has(id)) {
        this.removeMarker(id)
      }
    }
  }
  
  createMarker(event) {
    const group = new THREE.Group()
    group.name = 'event-marker'
    
    // 事件颜色（按垃圾类别）
    const colorMap = {
      foam: 0xff9500,
      plastic: 0x007aff,
      fishing_gear: 0xff3b30,
      other: 0x8e8e93,
    }
    const color = colorMap[event.main_class] || 0x8e8e93
    
    // 垂直光柱：165km 场景下小浮标不可见，光柱是远距定位的主要视觉锚点。
    // 颜色 ×3 + 提高不透明度 → 叠加亮度越过泛光阈值，远看是一根"发光的针"
    const beamGeo = new THREE.CylinderGeometry(40, 90, 4000, 12, 1, true)
    const beamMat = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.26,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    beamMat.color.multiplyScalar(3.0)
    const beam = new THREE.Mesh(beamGeo, beamMat)
    beam.position.y = 2000
    group.add(beam)
    
    // 浮标主体（符号化放大）
    const buoyGeo = new THREE.CylinderGeometry(160, 120, 240, 16)
    const buoyMat = new THREE.MeshStandardMaterial({ color, roughness: 0.6 })
    const buoy = new THREE.Mesh(buoyGeo, buoyMat)
    buoy.position.y = 120
    group.add(buoy)
    
    // 顶部标志杆
    const poleGeo = new THREE.CylinderGeometry(16, 16, 500, 8)
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xc2cbd2, roughness: 0.3, metalness: 0.8 })
    const pole = new THREE.Mesh(poleGeo, poleMat)
    pole.position.y = 480
    group.add(pole)
    
    // 顶部警示灯（HDR 增益：闪烁时泛出光晕）
    const lightGeo = new THREE.SphereGeometry(45, 12)
    const lightMat = new THREE.MeshBasicMaterial({ color: 0xff3b30 })
    lightMat.color.multiplyScalar(1.9)
    const light = new THREE.Mesh(lightGeo, lightMat)
    light.position.y = 780
    group.add(light)

    // 脉冲光环（海面，颜色提亮靠向泛光阈值）
    const ringGeo = new THREE.RingGeometry(300, 360, 48)
    const ringMat = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.5,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    ringMat.color.multiplyScalar(1.5)
    const ring = new THREE.Mesh(ringGeo, ringMat)
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 30
    group.add(ring)
    
    // 位置
    const { x, z } = lngLatToScene(event.lng || 119.86, event.lat || 26.35)
    group.position.set(x, 0, z)
    
    group.userData = {
      type: 'event',
      eventData: event,
    }
    
    this.scene.add(group)
    
    this.markers.set(event.event_id, {
      id: event.event_id,
      group,
      ring,
      light,
      beam,
      data: { ...event },
    })
  }
  
  updateMarker(marker, event) {
    marker.data = { ...marker.data, ...event }
    // 可添加位置更新逻辑
  }
  
  removeMarker(id) {
    const marker = this.markers.get(id)
    if (marker) {
      this.scene.remove(marker.group)
      this.markers.delete(id)
    }
  }
  
  update(time) {
    // 脉冲动画
    for (const marker of this.markers.values()) {
      const scale = 1 + Math.sin(time * 2) * 0.15
      marker.ring.scale.setScalar(scale)
      marker.ring.material.opacity = 0.3 + Math.sin(time * 2) * 0.2
      
      // 警示灯闪烁（保持 HDR 增益，泛光下才有"警示灯"的脉冲感）
      marker.light.material.color
        .setHex(Math.sin(time * 4) > 0 ? 0xff3b30 : 0xff9500)
        .multiplyScalar(1.9)
      
      // 光柱呼吸：透明度缓慢脉动，远看像扫描信号
      if (marker.beam) {
        marker.beam.material.opacity = 0.16 + 0.10 * (0.5 + 0.5 * Math.sin(time * 1.4))
      }
    }
  }
  
  getInteractiveObjects() {
    return Array.from(this.markers.values()).map(m => m.group)
  }

  /**
   * 获取标记 group（供标签层挂 CSS2DObject）
   * @param {string} eventId
   * @returns {THREE.Group|null}
   */
  getMarkerGroup(eventId) {
    return this.markers.get(eventId)?.group || null
  }
  
  dispose() {
    for (const [id] of this.markers) {
      this.removeMarker(id)
    }
    this.markers.clear()
  }
}

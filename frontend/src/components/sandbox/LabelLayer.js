/**
 * 标签层：CSS2D 悬浮标签（船名/状态、事件类别）
 *
 * 参考 three.js 官方示例 css2d_label（CSS2DRenderer）：
 *   把 DOM 元素锚到 3D 坐标上 —— 标签永远清晰锐利（不受 WebGL 分辨率/透视模糊影响），
 *   这是数字孪生大屏的行业惯例（Cesium / Mapbox 的 annotation 同理）。
 *
 * 显示纪律（避免大屏被标签淹没）：
 *   - 船标签：常显（平台船只数量少），远距离降透明度
 *   - 事件标签：只显示相机 120km 内最近的一批，其余隐藏
 *
 * 注意 CSS2DRenderer 的已知坑：对象从场景移除时 DOM 不会自动清理，
 * 必须在 detach 时手动 el.remove()，否则会留下"幽灵标签"。
 */

import * as THREE from 'three'
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { classLabel, WASTE_CLASSES } from '@/utils/constants'

// 与船体状态同源的中文标签/配色（和 SandBoxMap 的图例保持一致）
const VESSEL_STATUS = {
  online: '在线',
  offline: '离线',
  idle: '待命',
  navigating: '前往中',
  collecting: '作业中',
  assigned: '已派单',
}
const VESSEL_COLORS = {
  online: '#18a999',
  navigating: '#18a999',
  collecting: '#ff9500',
  assigned: '#7a5af8',
  offline: '#7a8798',
  idle: '#3f8ee8',
}

const EVENT_LABEL_RANGE = 120000 // 相机 120km 内才显示事件标签
const EVENT_LABEL_MAX = 14 // 事件标签最多同屏数量（按距离取最近）
const UPDATE_INTERVAL = 0.25 // 可见性判定节流（秒）

export class LabelLayer {
  /** @param {HTMLElement} container 沙盘根容器（canvas 的父节点） */
  constructor(container) {
    this.renderer = new CSS2DRenderer()
    this.renderer.domElement.className = 'sandbox-map__labels'
    container.appendChild(this.renderer.domElement)

    this.vesselLabels = new Map() // robotId → { el, obj, ...domRefs, _far }
    this.eventLabels = new Map() // eventId → { el, obj, _hidden, _dist }
    this._timer = UPDATE_INTERVAL
    this._tmp = new THREE.Vector3()
  }

  setSize(width, height) {
    this.renderer.setSize(width, height)
  }

  // ---------------------------------------------------------------- 船标签

  /**
   * 同步船标签（挂点取自 VesselManager 的船体 group，标签随船平滑移动）
   * @param {Array} robots
   * @param {import('./VesselManager.js').VesselManager} vesselManager
   */
  syncVessels(robots, vesselManager) {
    const seen = new Set()
    for (const robot of robots || []) {
      const id = robot.robot_id
      if (!id) continue
      seen.add(id)
      let entry = this.vesselLabels.get(id)
      if (!entry) {
        const group = vesselManager?.getVesselGroup(id)
        if (!group) continue // 船体还没建出来，下一轮同步再挂
        const el = document.createElement('div')
        el.className = 'sb-label sb-label--vessel'
        el.innerHTML = '<i></i><span class="sb-label__name"></span><em></em>'
        const obj = new CSS2DObject(el)
        obj.position.set(0, 3.4, 0) // 船体 group scale=200 → 世界高度 ~680m，浮在桅杆上方
        obj.center.set(0.5, 1) // 标签底边贴锚点
        group.add(obj)
        entry = {
          el,
          obj,
          dotEl: el.querySelector('i'),
          nameEl: el.querySelector('.sb-label__name'),
          tagEl: el.querySelector('em'),
          _far: null,
        }
        this.vesselLabels.set(id, entry)
      }
      this.applyVessel(entry, robot)
    }
    for (const [id, entry] of this.vesselLabels) {
      if (!seen.has(id)) this.detach(entry, this.vesselLabels, id)
    }
  }

  applyVessel(entry, robot) {
    const status = robot.status || 'offline'
    const name = robot.name || robot.robot_id || ''
    if (entry.nameEl.textContent !== name) entry.nameEl.textContent = name
    const tag = VESSEL_STATUS[status] || status
    if (entry.tagEl.textContent !== tag) entry.tagEl.textContent = tag
    const color = VESSEL_COLORS[status] || VESSEL_COLORS.offline
    if (entry._color !== color) {
      entry.dotEl.style.background = color
      entry._color = color
    }
    entry.el.classList.toggle('is-selected', robot.decision_role === 'selected')
    entry.el.classList.toggle('is-candidate', robot.decision_role === 'candidate')
  }

  // ---------------------------------------------------------------- 事件标签

  /**
   * 同步事件标签（挂点取自 EventMarkerManager 的标记 group）
   * @param {Array} events
   * @param {import('./InteractionLayer.js').EventMarkerManager} eventManager
   */
  syncEvents(events, eventManager) {
    const seen = new Set()
    for (const event of events || []) {
      const id = event.event_id
      if (!id) continue
      seen.add(id)
      let entry = this.eventLabels.get(id)
      if (!entry) {
        const group = eventManager?.getMarkerGroup(id)
        if (!group) continue
        const el = document.createElement('div')
        el.className = 'sb-label sb-label--event is-hidden'
        el.innerHTML = '<i></i><span></span>'
        const obj = new CSS2DObject(el)
        obj.position.set(0, 900, 0) // 光柱顶端（警示灯 780m）之上
        obj.center.set(0.5, 1)
        group.add(obj)
        entry = { el, obj, dotEl: el.querySelector('i'), nameEl: el.querySelector('span'), _hidden: true, _dist: Infinity }
        this.eventLabels.set(id, entry)
      }
      const cls = event.main_class || 'other'
      const color = WASTE_CLASSES[cls]?.color || '#8e8e93'
      if (entry._color !== color) {
        entry.dotEl.style.background = color
        entry._color = color
      }
      const label = classLabel(cls)
      if (entry.nameEl.textContent !== label) entry.nameEl.textContent = label
      entry.el.classList.toggle('is-new', !!event._isNew)
    }
    for (const [id, entry] of this.eventLabels) {
      if (!seen.has(id)) this.detach(entry, this.eventLabels, id)
    }
  }

  // ---------------------------------------------------------------- 逐帧

  /**
   * 可见性/透明度分级（0.25s 节流，避免每帧碰 DOM）
   * @param {THREE.Camera} camera
   * @param {number} dt
   */
  update(camera, dt) {
    this._timer += dt
    if (this._timer < UPDATE_INTERVAL) return
    this._timer = 0
    const camPos = camera.position

    // 船标签：远距离降透明（不隐藏 —— 船是态势主角）
    for (const entry of this.vesselLabels.values()) {
      entry.obj.getWorldPosition(this._tmp)
      const far = this._tmp.distanceTo(camPos) > 150000
      if (far !== entry._far) {
        entry.el.style.opacity = far ? '0.66' : ''
        entry._far = far
      }
    }

    // 事件标签：范围内按距离取最近 N 个，其余隐藏
    const visible = []
    for (const entry of this.eventLabels.values()) {
      entry.obj.getWorldPosition(this._tmp)
      entry._dist = this._tmp.distanceTo(camPos)
      if (entry._dist < EVENT_LABEL_RANGE) visible.push(entry)
    }
    visible.sort((a, b) => a._dist - b._dist)
    visible.forEach((entry, i) => this.setHidden(entry, i >= EVENT_LABEL_MAX))
    for (const entry of this.eventLabels.values()) {
      if (entry._dist >= EVENT_LABEL_RANGE) this.setHidden(entry, true)
    }
  }

  setHidden(entry, hidden) {
    if (entry._hidden === hidden) return
    entry._hidden = hidden
    entry.el.classList.toggle('is-hidden', hidden)
  }

  render(scene, camera) {
    this.renderer.render(scene, camera)
  }

  // ---------------------------------------------------------------- 清理

  detach(entry, map, id) {
    entry.obj.removeFromParent()
    entry.el.remove()
    map.delete(id)
  }

  dispose() {
    for (const [id, entry] of this.vesselLabels) this.detach(entry, this.vesselLabels, id)
    for (const [id, entry] of this.eventLabels) this.detach(entry, this.eventLabels, id)
    this.renderer.domElement.remove()
  }
}
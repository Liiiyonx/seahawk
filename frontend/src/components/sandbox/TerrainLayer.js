/**
 * 连江3D地形生成器（网格位移版）
 *
 * 为什么不续用 ExtrudeGeometry：
 *   挤出几何体的顶面顶点只落在多边形轮廓上，内部没有网格点，做不了山地起伏；
 *   且连江 GeoJSON 有数千个轮廓点，earcut 三角化慢、三角形数量不可控。
 *
 * 本版方案（一张 PlaneGeometry 解决全部）：
 *   1. 256×256 网格覆盖整个连江 bbox（含远海岛屿），逐顶点做射线法包含判定
 *   2. 陆地顶点：基础高度 × 海岸衰减（腐蚀窗口）× fbm 噪声起伏 → 自然山丘
 *   3. 海域顶点：压到海平面以下，海面单独用波浪着色器覆盖
 *   4. 顶点色按海拔分层：沙滩 → 植被 → 山体，无需贴图也有层次
 *   5. 轮廓环先过 Douglas-Peucker 简化，包含判定提速一个量级
 */

import * as THREE from 'three'
import lianjiangGeo from '@/assets/lianjiang-350122.json'

// 连江中心点
const CENTER_LNG = lianjiangGeo.features[0]?.properties?.center?.[0] || 119.86
const CENTER_LAT = lianjiangGeo.features[0]?.properties?.center?.[1] || 26.35

const METERS_PER_DEG_LAT = 110540
const METERS_PER_DEG_LNG = 111320 * Math.cos((CENTER_LAT * Math.PI) / 180)

/**
 * 海天接缝色：海面距离雾的终点色 == 天空穹顶"地平线以下"的底色。
 * 两处必须同源 —— 有限大的海面在远处收进这个颜色，若天空地平线以下是另一个
 * 浅色，海面边缘（世界尽头）就会显出一条硬边。
 */
const SEA_FOG_COLOR = 0xa9c9dd

/**
 * 全场景统一太阳方向（单位向量）。
 * 海面高光 / 天空日盘 / 地形凹凸阴影必须同源 —— 否则"波光在左、影子在右"，
 * 立体感会互相打架。
 *
 * 方位取西南、仰角 ~35°（下午的太阳，符合东海岸真实光照）：
 * ★ 关键是与默认相机方位"垂直"——默认镜头从东南上方看向西北，
 *   若太阳也在东南（顺光），山体只有受光面、投影全藏在山背后，立体感为零；
 *   垂直侧光下每道山脊都有明暗两面，体积感才真正出来（地形渲染的行业惯例）。
 */
export const SUN_DIR = new THREE.Vector3(-0.55, 0.55, 0.55).normalize()

/** 经纬度转场景坐标（以连江中心为原点，单位≈米） */
export function lngLatToScene(lng, lat) {
  const x = (lng - CENTER_LNG) * METERS_PER_DEG_LNG
  const z = -(lat - CENTER_LAT) * METERS_PER_DEG_LAT
  return { x, z }
}

/** 场景坐标转经纬度 */
export function sceneToLngLat(x, z) {
  const lng = CENTER_LNG + x / METERS_PER_DEG_LNG
  const lat = CENTER_LAT - z / METERS_PER_DEG_LAT
  return { lng, lat }
}

// ---------------------------------------------------------------- 多边形预处理

/**
 * Douglas-Peucker 折线简化（在近似米制平面上做，容差与视觉对齐）。
 * 容差自适应：主岛环（百公里级）用 18m，远海小岛（百米级）自动降到几米，
 * 否则小环会被简化成三角形直接消失。
 */
function simplifyRing(ring) {
  if (ring.length <= 4) return ring
  // 环 bbox 对角线决定容差
  let minLng = Infinity
  let maxLng = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  for (const [lng, lat] of ring) {
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  const diagM = Math.hypot(
    (maxLng - minLng) * METERS_PER_DEG_LNG,
    (maxLat - minLat) * METERS_PER_DEG_LAT,
  )
  const toleranceMeters = Math.min(18, Math.max(3, diagM / 80))

  const pts = ring.map(([lng, lat]) => {
    const { x, z } = lngLatToScene(lng, lat)
    return { x, y: z, lng, lat }
  })
  const keep = new Uint8Array(pts.length)
  keep[0] = keep[pts.length - 1] = 1
  const stack = [[0, pts.length - 1]]
  while (stack.length) {
    const [a, b] = stack.pop()
    const pa = pts[a]
    const pb = pts[b]
    const dx = pb.x - pa.x
    const dy = pb.y - pa.y
    const lenSq = dx * dx + dy * dy
    let maxDist = 0
    let maxIdx = -1
    for (let i = a + 1; i < b; i += 1) {
      const p = pts[i]
      let dist
      if (lenSq < 1e-9) {
        dist = Math.hypot(p.x - pa.x, p.y - pa.y)
      } else {
        const t = Math.max(0, Math.min(1, ((p.x - pa.x) * dx + (p.y - pa.y) * dy) / lenSq))
        dist = Math.hypot(p.x - (pa.x + t * dx), p.y - (pa.y + t * dy))
      }
      if (dist > maxDist) {
        maxDist = dist
        maxIdx = i
      }
    }
    if (maxDist > toleranceMeters && maxIdx > 0) {
      keep[maxIdx] = 1
      stack.push([a, maxIdx], [maxIdx, b])
    }
  }
  const out = []
  for (let i = 0; i < pts.length; i += 1) {
    if (keep[i]) out.push([pts[i].lng, pts[i].lat])
  }
  // 保底：简化到太少点会让多边形退化，宁可不简化
  return out.length >= 8 ? out : ring
}

/** 收集 GeoJSON 全部环（含远海岛屿，不再只取最大多边形） */
function collectRings() {
  const rings = []
  for (const feature of lianjiangGeo.features) {
    const geometry = feature.geometry
    if (!geometry) continue
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
    for (const polygon of polygons || []) {
      // polygon[0] 是外环；该数据集无洞，内环忽略不影响视觉
      const outer = polygon?.[0]
      if (outer?.length > 3) rings.push(simplifyRing(outer))
    }
  }
  return rings
}

/** 全部环的经纬度 bbox（含 padding，让海面在视野边缘仍有延伸） */
function computeBounds(rings) {
  let minLng = Infinity
  let maxLng = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  for (const ring of rings) {
    for (const [lng, lat] of ring) {
      if (lng < minLng) minLng = lng
      if (lng > maxLng) maxLng = lng
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
    }
  }
  const padLng = (maxLng - minLng) * 0.18
  const padLat = (maxLat - minLat) * 0.18
  return {
    minLng: minLng - padLng,
    maxLng: maxLng + padLng,
    minLat: minLat - padLat,
    maxLat: maxLat + padLat,
  }
}

// ---------------------------------------------------------------- 包含判定

/**
 * 扫描线栅格化：把多边形环整行填充进"超采样网格"，再降采样为
 * 陆地掩膜 + 每格覆盖率（0..255）。
 *
 * 为什么超采样：1024 网格 ≈ 160m/格，二值掩膜在近景会出现肉眼可见的
 * 岸线台阶；2× 超采样给出亚格覆盖率，配合高度加权把水线柔化到半格精度。
 * 为什么 async：4098² 超采样网格的填充是秒级工作，按环/按行让出主线程，
 * 加载进度才能持续刷新（onChunk 回调汇报 0..1）。
 * 性能上仍远快于旧版"逐顶点射线判定"（O(行 × 边) vs O(顶点 × 边)）。
 */
async function rasterizeRings(rings, bounds, side, cellLng, cellLat, sub = 2, onChunk = null) {
  const fineSide = side * sub
  const fineCellLng = cellLng / sub
  const fineCellLat = cellLat / sub
  const fine = new Uint8Array(fineSide * fineSide)

  const xs = []
  const ys = []
  const crossX = []

  for (let ringIdx = 0; ringIdx < rings.length; ringIdx += 1) {
    const ring = rings[ringIdx]
    if (onChunk) await onChunk(ringIdx / rings.length)
    const n = ring.length
    xs.length = n
    ys.length = n
    let minRow = Infinity
    let maxRow = -Infinity
    let minCol = Infinity
    let maxCol = -Infinity
    for (let i = 0; i < n; i += 1) {
      const cx = (ring[i][0] - bounds.minLng) / fineCellLng
      const cy = (bounds.maxLat - ring[i][1]) / fineCellLat
      xs[i] = cx
      ys[i] = cy
      if (cy < minRow) minRow = cy
      if (cy > maxRow) maxRow = cy
      if (cx < minCol) minCol = cx
      if (cx > maxCol) maxCol = cx
    }
    const rowStart = Math.max(0, Math.floor(minRow))
    const rowEnd = Math.min(fineSide - 1, Math.ceil(maxRow))
    const colStart = Math.max(0, Math.floor(minCol - 1))
    const colEnd = Math.min(fineSide - 1, Math.ceil(maxCol + 1))

    for (let r = rowStart; r <= rowEnd; r += 1) {
      const scanY = r + 0.5 // 行中心
      crossX.length = 0
      for (let i = 0, j = n - 1; i < n; j = i, i += 1) {
        const yi = ys[i]
        const yj = ys[j]
        if (yi > scanY !== yj > scanY) {
          crossX.push(xs[i] + ((scanY - yi) * (xs[j] - xs[i])) / (yj - yi))
        }
      }
      if (crossX.length < 2) continue
      crossX.sort((a, b) => a - b)
      const base = r * fineSide
      for (let k = 0; k + 1 < crossX.length; k += 2) {
        const c0 = Math.max(colStart, Math.ceil(crossX[k] - 0.5))
        const c1 = Math.min(colEnd, Math.floor(crossX[k + 1] - 0.5))
        for (let c = c0; c <= c1; c += 1) fine[base + c] = 1
      }
    }
  }

  // 降采样：掩膜（多数表决）+ 覆盖率（0..255）
  if (onChunk) await onChunk(0.96)
  const inside = new Uint8Array(side * side)
  const coverage = new Uint8Array(side * side)
  const subArea = sub * sub
  const scale = 255 / subArea
  for (let r = 0; r < side; r += 1) {
    for (let c = 0; c < side; c += 1) {
      let cnt = 0
      for (let dr = 0; dr < sub; dr += 1) {
        const rowBase = (r * sub + dr) * fineSide + c * sub
        for (let dc = 0; dc < sub; dc += 1) cnt += fine[rowBase + dc]
      }
      const i = r * side + c
      inside[i] = cnt * 2 >= subArea ? 1 : 0
      coverage[i] = Math.round(cnt * scale)
    }
  }
  return { inside, coverage }
}

/**
 * chamfer 距离变换（两遍 O(n)）：种子格（值 0）向其余格扩散曼哈顿对角距离。
 * 陆地→海（离岸距离）与海→陆（近岸距离）各跑一次，
 * 海岸衰减因子因此不再需要 O(格 × 窗口²) 的邻域统计。async：按行分片让出。
 */
async function chamferDistance(grid, side, onChunk = null) {
  const W_DIAG = Math.SQRT2
  for (let r = 0; r < side; r += 1) {
    if (onChunk && (r & 511) === 0) await onChunk(r / side * 0.5)
    const base = r * side
    for (let c = 0; c < side; c += 1) {
      const i = base + c
      let d = grid[i]
      if (c > 0) d = Math.min(d, grid[i - 1] + 1)
      if (r > 0) {
        d = Math.min(d, grid[i - side] + 1)
        if (c > 0) d = Math.min(d, grid[i - side - 1] + W_DIAG)
        if (c < side - 1) d = Math.min(d, grid[i - side + 1] + W_DIAG)
      }
      grid[i] = d
    }
  }
  for (let r = side - 1; r >= 0; r -= 1) {
    if (onChunk && (r & 511) === 0) await onChunk(0.5 + (side - r) / side * 0.5)
    const base = r * side
    for (let c = side - 1; c >= 0; c -= 1) {
      const i = base + c
      let d = grid[i]
      if (c < side - 1) d = Math.min(d, grid[i + 1] + 1)
      if (r < side - 1) {
        d = Math.min(d, grid[i + side] + 1)
        if (c < side - 1) d = Math.min(d, grid[i + side + 1] + W_DIAG)
        if (c > 0) d = Math.min(d, grid[i + side - 1] + W_DIAG)
      }
      grid[i] = d
    }
  }
  return grid
}

// ---------------------------------------------------------------- 噪声（value noise + fbm）

/**
 * 整数混合 hash（imul 版）——不用 fract(sin(...))：
 * sin 版每次调用含一次 Math.sin，1024² 网格 × 数十次噪声采样会拖到秒级，
 * 纯位运算快一个数量级，且没有跨平台 Math.sin 精度差异。
 */
function hash2(ix, iz) {
  let h = Math.imul(ix, 374761393) ^ Math.imul(iz, 668265263)
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  h ^= h >>> 16
  return (h >>> 0) / 4294967295
}

function valueNoise(x, z) {
  const ix = Math.floor(x)
  const iz = Math.floor(z)
  const fx = x - ix
  const fz = z - iz
  const ux = fx * fx * (3 - 2 * fx)
  const uz = fz * fz * (3 - 2 * fz)
  const a = hash2(ix, iz)
  const b = hash2(ix + 1, iz)
  const c = hash2(ix, iz + 1)
  const d = hash2(ix + 1, iz + 1)
  return a + (b - a) * ux + (c - a) * uz + (a - b - c + d) * ux * uz
}

/** fbm：4 个八度叠加，输出约 [0,1]，低频做山势、高频做细节 */
function fbm(x, z) {
  return (
    valueNoise(x, z) * 0.52 +
    valueNoise(x * 2.13 + 7.3, z * 2.13 + 3.1) * 0.26 +
    valueNoise(x * 4.41 + 13.7, z * 4.41 + 9.2) * 0.14 +
    valueNoise(x * 8.87 + 31.1, z * 8.87 + 17.5) * 0.08
  )
}

/** ridged fbm：1-|n| 再平方，制造锐利山脊（Musgrave 的经典山地方案） */
function ridgedFbm(x, z) {
  let sum = 0
  let amp = 0.5
  let freq = 1
  for (let i = 0; i < 4; i += 1) {
    const n = 1 - Math.abs(valueNoise(x * freq, z * freq) * 2 - 1)
    sum += n * n * amp
    amp *= 0.5
    freq *= 2.13
  }
  return sum // ~[0, 1]
}

/**
 * 近景岩峰皱褶：ridged 细噪声（基础层格距 ~160m 下的"可采样"频段）。
 * ★ 只取 3 个八度：波长为 2.8km / 1.3km / 605m —— 最细一档仍有约 3.8 个
 *   顶点/波长。此前到 5 个八度（280m/128m）在基础层直接欠采样，产生
 *   逐顶点的随机抖动，被上采样平滑后表现为 160m 周期的"编织网"格点
 *   （地形渲染最典型的采样定理事故）。更细的岩面颗粒交给逐像素细节法线。
 */
function cragFbm(x, z) {
  let sum = 0
  let amp = 0.5
  let freq = 1
  for (let i = 0; i < 3; i += 1) {
    const n = 1 - Math.abs(valueNoise(x * freq, z * freq) * 2 - 1)
    sum += n * amp
    amp *= 0.52
    freq *= 2.17
  }
  return sum
}

/**
 * domain warping：采样坐标先被低频噪声扭曲再进 fbm，
 * 山脊走向因此蜿蜒自然而不是一团团圆馒头（Inigo Quilez 的经典技巧）
 */
function warpedFbm(x, z) {
  const qx = fbm(x, z)
  const qz = fbm(x + 5.2, z + 1.3)
  return fbm(x + 2.0 * qx, z + 2.0 * qz)
}

// ---------------------------------------------------------------- 海拔配色（顶点色分层）

const COLOR_SEA_FLOOR = new THREE.Color(0x2a4a5e) // 海床（被海面盖住，只露边缘）
const COLOR_BEACH = new THREE.Color(0xe6d29a)     // 沙滩
const COLOR_BEACH_WET = new THREE.Color(0xc2a877) // 湿沙滩（浪溅带，比干沙深一档）
const COLOR_GRASS = new THREE.Color(0x58a06b)     // 植被
const COLOR_FOREST = new THREE.Color(0x2f7a4e)    // 林地
const COLOR_ROCK = new THREE.Color(0x8a7f70)      // 山体岩石
const COLOR_SNOW = new THREE.Color(0xdde4ea)      // 峰顶积雪（压暗：纯白在强光+泛光下会糊成光斑）

// 色带按 colorMax 归一（而非理论最大海拔），保证海滩→雪顶全色带都会实际出现。
// snowJitter：雪线噪声偏移 —— 真实的雪线不是一条等高线，是随坡向起伏的碎边
function altitudeColor(h, colorMax, out, snowJitter = 0) {
  const t = Math.min(1, Math.max(0, h / colorMax))
  if (h < 3) {
    out.copy(COLOR_SEA_FLOOR)
  } else if (t < 0.06) {
    out.copy(COLOR_BEACH)
    // 湿沙带：最低 12m 内的沙滩掺入深色，远看岸线有一条"被浪打湿"的暗边
    const wet = Math.max(0, 1 - Math.max(0, h - 3) / 12)
    if (wet > 0) out.lerp(COLOR_BEACH_WET, wet * 0.75)
  } else if (t < 0.3) {
    out.copy(COLOR_BEACH).lerp(COLOR_GRASS, (t - 0.06) / 0.24)
  } else if (t < 0.62) {
    out.copy(COLOR_GRASS).lerp(COLOR_FOREST, (t - 0.3) / 0.32)
  } else if (t < 0.85) {
    out.copy(COLOR_FOREST).lerp(COLOR_ROCK, (t - 0.62) / 0.23)
  } else {
    const ts = Math.min(1, Math.max(0, t + snowJitter))
    out.copy(COLOR_ROCK).lerp(COLOR_SNOW, Math.max(0, (ts - 0.85) / 0.15))
  }
  return out
}

// ---------------------------------------------------------------- 主入口

/**
 * 创建连江3D地形（异步分片构建）
 *
 * ★ 为什么是 async：2048² 网格的构建即使优化过也要数秒，若整段同步执行，
 *   主线程冻结、加载动画停在第一帧（用户以为崩了）。这里按阶段/按行分段
 *   让出主线程（setTimeout 0），并通过 onProgress 回调汇报 0..1 进度。
 *
 * @param {Object} options
 * @param {number} options.grid 网格分辨率（顶点数 = (grid+1)²）
 * @param {number} options.maxHeight 陆地最大海拔（场景单位≈米）
 * @param {number} options.coastTaper 海岸渐变窗口（格数，越大岸线越柔和）
 * @param {Function} [onProgress] 进度回调 (0..1) => void
 */
export async function createTerrain(
  {
    grid = 256,
    maxHeight = 1400,
    coastTaper = 8,
  } = {},
  onProgress = null,
) {
  const report = (p) => {
    if (onProgress) onProgress(p)
  }
  const yieldFrame = () => new Promise((resolve) => setTimeout(resolve, 0))

  // 先让出一帧：让加载动画（CSS 转圈）画出来再开始重计算
  await yieldFrame()

  const rings = collectRings()
  const bounds = computeBounds(rings)

  // 场景尺寸（米）
  const spanLng = bounds.maxLng - bounds.minLng
  const spanLat = bounds.maxLat - bounds.minLat
  const widthM = spanLng * METERS_PER_DEG_LNG
  const depthM = spanLat * METERS_PER_DEG_LAT

  // ---------- 网格缓冲（自定义构建 + 分片让出） ----------
  // 不用 PlaneGeometry：它带 uv（我们本来就要删）且一次性创建无法分片 ——
  // 2048² 顶点 + 800 万索引的一次性生成曾是加载期最大的一段同步阻塞
  const side = grid + 1
  const vertexCount = side * side
  const cellW = widthM / grid
  const cellH = depthM / grid
  const positions = new Float32Array(vertexCount * 3)
  const normalsRaw = new Float32Array(vertexCount * 3)
  const colors = new Float32Array(vertexCount * 3)
  const halfW = widthM / 2
  const halfD = depthM / 2

  for (let r = 0; r < side; r += 1) {
    if ((r & 255) === 0) {
      report(0.02 + (r / side) * 0.05)
      await yieldFrame()
    }
    const z = -halfD + r * cellH
    let p = r * side * 3
    for (let c = 0; c < side; c += 1) {
      positions[p] = -halfW + c * cellW
      positions[p + 2] = z
      p += 3
    }
  }

  // 索引：每格两个三角形（绕序与旧 PlaneGeometry 一致，法线朝上）
  const indices = new Uint32Array(grid * grid * 6)
  for (let r = 0; r < grid; r += 1) {
    if ((r & 255) === 0) {
      report(0.07 + (r / grid) * 0.03)
      await yieldFrame()
    }
    let k = r * grid * 6
    for (let c = 0; c < grid; c += 1) {
      const a = r * side + c
      const b = a + side
      indices[k] = a
      indices[k + 1] = b
      indices[k + 2] = a + 1
      indices[k + 3] = a + 1
      indices[k + 4] = b
      indices[k + 5] = b + 1
      k += 6
    }
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('normal', new THREE.BufferAttribute(normalsRaw, 3))
  geometry.setIndex(new THREE.BufferAttribute(indices, 1))
  geometry.computeBoundingSphere() // 自定义几何需要显式包围球（视锥剔除用）
  const pos = geometry.attributes.position

  // ---------- 第一遍：陆地栅格（扫描线） + 双向海岸距离场 ----------
  const cellLng = spanLng / grid
  const cellLat = spanLat / grid
  const insideGridRaw = await rasterizeRings(
    rings,
    bounds,
    side,
    cellLng,
    cellLat,
    2,
    async (f) => {
      report(0.1 + f * 0.08)
      await yieldFrame()
    },
  )
  const insideGrid = insideGridRaw.inside
  const coastCoverage = insideGridRaw.coverage // 0..255，亚格覆盖率（柔化水线用）

  // 陆地→海（离岸距离，海面浅水/浪花带用）；海→陆（近岸距离，陆地海岸衰减用）
  const seaDist = new Float32Array(vertexCount)
  const inlandDist = new Float32Array(vertexCount)
  for (let i = 0; i < vertexCount; i += 1) {
    seaDist[i] = insideGrid[i] ? 0 : 1e9
    inlandDist[i] = insideGrid[i] ? 1e9 : 0
  }
  await chamferDistance(seaDist, side, async (f) => {
    report(0.18 + f * 0.02)
    await yieldFrame()
  })
  await chamferDistance(inlandDist, side, async (f) => {
    report(0.2 + f * 0.02)
    await yieldFrame()
  })

  // ---------- 第二遍：基础层（半分辨率：全套噪声 + 侵蚀） ----------
  // ★ 为什么要分两层：2048² 顶点直接跑全套噪声（~25 次 valueNoise/顶点）是
  //   十秒级的 JS 构建；拆开后 —— 半分辨率（1024²）跑重噪声得到地形"骨架"
  //   （山形/山脊/沟壑，并做热侵蚀），全分辨率只做 Catmull-Rom 平滑上采样 +
  //   360m 级细节噪声叠加。视觉精度 2×，CPU 成本约 1/4。
  const NOISE_CYCLES = 14 // 全图噪声周期数：太少是一块大馒头，太多是碎疙瘩
  const baseSide = grid / 2 + 1 // 基础层网格（顶点恰为全分辨率网格的偶数点）
  const baseHeights = new Float32Array(baseSide * baseSide)

  for (let row = 0; row < side; row += 2) {
    const br = row >> 1
    if ((row & 255) === 0) {
      report(0.22 + (row / side) * 0.2)
      await yieldFrame()
    }
    for (let col = 0; col < side; col += 2) {
      const idx = row * side + col
      let height
      if (!insideGrid[idx]) {
        height = -30 // 海床压到浪谷之下（浪幅最大 ~20m），保证任何波相都不露底
      } else {
        // 海岸衰减：用真实"离岸格距离"做 smoothstep —— 岸线附近高度渐降到 0
        let coastFactor = Math.min(1, inlandDist[idx] / coastTaper)
        coastFactor = coastFactor * coastFactor * (3 - 2 * coastFactor)

        // 归一化格点坐标 × 周期数 → 与网格分辨率解耦的起伏
        const nx = (col / grid) * NOISE_CYCLES
        const nz = (row / grid) * NOISE_CYCLES
        // domain-warped fbm 定大山走向，ridged fbm 叠锐利山脊，
        // 第三层 cragFbm 把 300m 级岩峰皱褶带进来（远看是山棱，近看是岩面）
        const base = warpedFbm(nx, nz)
        const ridge = ridgedFbm(nx * 1.7 + 4.7, nz * 1.7 + 9.1)
        const crag = cragFbm(nx * 4.1 + 23.4, nz * 3.7 + 12.6)
        const m = Math.min(1, base * 0.55 + ridge * 0.5 + crag * 0.18)
        // m^1.5 压低谷、留峰线；基础 15m 让最低陆地也高出浪峰
        height = (15 + Math.pow(m, 1.5) * maxHeight) * coastFactor
        // 假侵蚀沟壑（参考 SimonStorlSchulke/threejs-examples 的做法）：
        // pingpong 噪声的脊线连成树枝状沟网，沿沟下切出排水纹理。
        // ★ 频率 1.6（而非 2.3）：fbm 内部最高八度 ×8.87，在基础层仍保有
        //   约 2.6 个顶点/波长；用 2.3 时最高八度只有 358m ≈ 2.2 格，欠采样
        const ping = 1 - Math.abs(2 * fbm(nx * 1.6 + 17.0, nz * 1.6 + 11.0) - 1)
        const channel = Math.pow(1 - ping, 3)
        // 滩涂不冲沟（coastFactor 低），高山冲沟深
        height -= channel * coastFactor * Math.min(1, height / (maxHeight * 0.35)) * maxHeight * 0.1
        // 亚格海岸平滑：按覆盖率把贴岸一圈的高度加权 —— 内陆覆盖率=1 不受影响，
        // 水线因此落在"半格"精度上，近景不再是一排 160m 的锯齿台阶
        height *= 0.35 + 0.65 * (coastCoverage[idx] / 255)
      }
      baseHeights[br * baseSide + (col >> 1)] = height
    }
  }

  // ---- 基础层热侵蚀松弛（talus 碎石坡模拟） ----
  // 参考 getButterfly 的 three.js 侵蚀地形笔记：邻格高差超过临界休止角
  // 就向最低邻格滑落一份，几轮后山脊更锐、山脚出现堆积裙。
  const baseCellM = widthM / (grid / 2)
  const TALUS = baseCellM * 0.55 // 休止角 ~29°：高差超过它就滑落
  const MOVE = 0.18
  for (let iter = 0; iter < 4; iter += 1) {
    const next = Float32Array.from(baseHeights)
    for (let r = 1; r < baseSide - 1; r += 1) {
      for (let c = 1; c < baseSide - 1; c += 1) {
        const i = r * baseSide + c
        const h = baseHeights[i]
        if (h < 3) continue // 海床与贴岸低地不参与（避免把陆坡"漏"进海里）
        let lowest = h
        let li = -1
        if (baseHeights[i - 1] > 0 && baseHeights[i - 1] < lowest) { lowest = baseHeights[i - 1]; li = i - 1 }
        if (baseHeights[i + 1] > 0 && baseHeights[i + 1] < lowest) { lowest = baseHeights[i + 1]; li = i + 1 }
        if (baseHeights[i - baseSide] > 0 && baseHeights[i - baseSide] < lowest) { lowest = baseHeights[i - baseSide]; li = i - baseSide }
        if (baseHeights[i + baseSide] > 0 && baseHeights[i + baseSide] < lowest) { lowest = baseHeights[i + baseSide]; li = i + baseSide }
        const diff = h - lowest
        if (li >= 0 && diff > TALUS) {
          const slide = (diff - TALUS) * MOVE
          next[i] -= slide
          next[li] += slide
        }
      }
    }
    baseHeights.set(next)
    report(0.42 + ((iter + 1) / 4) * 0.08)
    await yieldFrame()
  }

  // ---------- 第三遍：全分辨率高度（Catmull-Rom 平滑上采样 + 360m 级细碎起伏） ----------
  // ★ 为什么不能用双线性：2× 上采样时逐行/逐列的线性插值在每个顶点行上
  //   留下导数不连续的"折痕"（周期 ≈ 80m 的菱形刻面），配合解析法线会被
  //   放大成规则的"编织网"伪影。Catmull-Rom 中点式插值在采样点间 C1 连续，
  //   表面处处光滑，只剩噪声本身的起伏。
  const heights = new Float32Array(vertexCount)
  const baseLast = baseSide - 1
  // 水平方向：偶数列为基础值；奇数列为中点 CR 插值
  const hAt = (rowPtr, c) => {
    const cc = c >> 1
    if ((c & 1) === 0) return baseHeights[rowPtr + cc]
    const p0 = baseHeights[rowPtr + (cc > 0 ? cc - 1 : 0)]
    const p1 = baseHeights[rowPtr + cc]
    const p2 = baseHeights[rowPtr + Math.min(baseLast, cc + 1)]
    const p3 = baseHeights[rowPtr + Math.min(baseLast, cc + 2)]
    return (-p0 + 9 * p1 + 9 * p2 - p3) * 0.0625
  }
  for (let row = 0; row < side; row += 1) {
    const x = row >> 1
    const even = (row & 1) === 0
    if ((row & 255) === 0) {
      report(0.5 + (row / side) * 0.12)
      await yieldFrame()
    }
    const rA = (x > 0 ? x - 1 : 0) * baseSide
    const rB = x * baseSide
    const rC = Math.min(baseLast, x + 1) * baseSide
    const rD = Math.min(baseLast, x + 2) * baseSide
    for (let col = 0; col < side; col += 1) {
      const idx = row * side + col
      if (!insideGrid[idx]) {
        heights[idx] = -30
        continue
      }
      let h
      if (even) {
        h = hAt(rB, col)
      } else {
        // 垂直方向同样用中点 CR：(-p0 + 9·p1 + 9·p2 - p3) / 16
        const vA = hAt(rA, col)
        const vB = hAt(rB, col)
        const vC = hAt(rC, col)
        const vD = hAt(rD, col)
        h = (-vA + 9 * vB + 9 * vC - vD) * 0.0625
      }
      // ★ 顶点层不再叠加任何细节噪声：两个不同朝向的噪声场叠加会交叉成
      //   "菱形编织网"（此前伪影的来源之一），且 80m 网格可表达的波长有限。
      //   山体几何只保留 Catmull-Rom 平滑后的骨架；岩面颗粒细节统一由
      //   片元着色器的逐像素细节法线承担（世界空间、带限、无网格结构）
      heights[idx] = h
    }
  }
  for (let i = 0; i < vertexCount; i += 1) pos.setY(i, heights[i])

  // ---------- 基础层顶点色（半分辨率：全套着色，写进全分辨率颜色缓冲的偶数点） ----------
  // 颜色是平滑渐变，半分辨率计算 + 全分辨率双线性上采样无可见损失；
  // 细粒度的明暗斑驳由片元着色器里的细节噪声承担（见下方的材质注入）
  const tmpColor = new THREE.Color()
  for (let br = 0; br < baseSide; br += 1) {
    const row = br * 2
    if ((br & 127) === 0) {
      report(0.62 + (br / baseSide) * 0.1)
      await yieldFrame()
    }
    for (let bc = 0; bc < baseSide; bc += 1) {
      const col = bc * 2
      const idx = row * side + col
      const height = baseHeights[br * baseSide + bc]
      // 色带按可达峰值的 ~60% 归一：噪声峰 rarely 顶到 maxHeight，
      // 不归一则岩石/雪顶色带永远不出现。
      // 雪线用两层噪声打碎 —— 雪顶边界随坡形起伏，而不是一条光滑等高线
      const snowJitter = (valueNoise(bc * 0.13 + 9, br * 0.13 + 4) - 0.5) * 0.1
      altitudeColor(height, maxHeight * 0.6, tmpColor, snowJitter)
      // 植被斑驳：单档 457m 噪声（约 2.9 基础格）；远景"椒盐感"主要来自
      // 更细的斑驳在远距离变成子像素噪点，细尺度斑驳交给片元层带限处理
      if (height > 40 && height < 620) {
        tmpColor.offsetHSL(0, 0, (valueNoise(bc * 0.35 + 31, br * 0.35 + 57) - 0.5) * 0.07)
      }
      // 岩层横纹：380m 以上的山体掺入随高度振荡的沉积色带，
      // 崖壁一圈圈明暗 —— 近看是岩层，远看把"一整块灰"切成有层次的岩面
      if (height > 380) {
        const band = Math.sin(height * 0.045 + valueNoise(bc * 0.21 + 7, br * 0.21 + 3) * 2.6)
        tmpColor.offsetHSL(0, 0, band * 0.028)
      }
      colors[idx * 3] = tmpColor.r
      colors[idx * 3 + 1] = tmpColor.g
      colors[idx * 3 + 2] = tmpColor.b
    }
  }

  // ---------- 基础层谷地暗角（多尺度 AO 近似） ----------
  // 参考 mapbox-gl-js 的 hillshade 思路：与邻域均值比较 —— 低于邻域（谷地）
  // 压暗、高于邻域（山脊）微提亮。两个半径（~640m / ~2km）叠加，
  // 避免单尺度产生"每个山头一圈光"的假感（基础层格距 160m，同旧版尺度）
  const AO_R1 = 4
  const AO_R2 = 12
  const neighborAvg = (r, c, R) => {
    let sum = 0
    let n = 0
    for (const [dr, dc] of [[-R, 0], [R, 0], [0, -R], [0, R]]) {
      const rr = Math.min(baseSide - 1, Math.max(0, r + dr))
      const cc = Math.min(baseSide - 1, Math.max(0, c + dc))
      const hN = baseHeights[rr * baseSide + cc]
      if (hN < 3) continue // 海面（-30）不参与均值，避免岸线出现亮边
      sum += hN
      n += 1
    }
    return n > 0 ? sum / n : null
  }
  for (let br = 0; br < baseSide; br += 1) {
    if ((br & 127) === 0) {
      report(0.72 + (br / baseSide) * 0.05)
      await yieldFrame()
    }
    for (let bc = 0; bc < baseSide; bc += 1) {
      const h = baseHeights[br * baseSide + bc]
      if (h < 3) continue
      const a1 = neighborAvg(br, bc, AO_R1)
      const a2 = neighborAvg(br, bc, AO_R2)
      let conc = 0
      if (a1 != null) conc += ((a1 - h) / (baseCellM * AO_R1)) * 0.65
      if (a2 != null) conc += ((a2 - h) / (baseCellM * AO_R2)) * 0.35
      // conc>0 = 谷地压暗（最多 -32%），conc<0 = 脊线提亮（最多 +14%）
      const dark = Math.min(0.32, Math.max(0, conc * 6))
      const bright = Math.min(0.14, Math.max(0, -conc * 4))
      const k = 1 - dark + bright
      if (k !== 1) {
        const idx = br * 2 * side + bc * 2
        colors[idx * 3] = Math.min(1, colors[idx * 3] * k)
        colors[idx * 3 + 1] = Math.min(1, colors[idx * 3 + 1] * k)
        colors[idx * 3 + 2] = Math.min(1, colors[idx * 3 + 2] * k)
      }
    }
  }

  // ---------- 颜色上采样：Catmull-Rom（与高度同法） ----------
  // ★ 双线性会在每条格线留下"色彩折痕"（周期 80/160m，幅度 2–8%），
  //   掠射角下正是那层菱形织网的残根 —— 颜色与高度必须用同一种平滑插值
  const cAt = (baseRowIndex, cFinal, ch) => {
    const rowOff = baseRowIndex * side // 偶数行/列在最终缓冲中是隔行存储的
    const cc = cFinal >> 1
    if ((cFinal & 1) === 0) return colors[(rowOff + cc) * 6 + ch]
    const p0 = colors[(rowOff + (cc > 0 ? cc - 1 : 0)) * 6 + ch]
    const p1 = colors[(rowOff + cc) * 6 + ch]
    const p2 = colors[(rowOff + Math.min(baseLast, cc + 1)) * 6 + ch]
    const p3 = colors[(rowOff + Math.min(baseLast, cc + 2)) * 6 + ch]
    return (-p0 + 9 * p1 + 9 * p2 - p3) * 0.0625
  }
  for (let row = 0; row < side; row += 1) {
    if ((row & 255) === 0) {
      report(0.77 + (row / side) * 0.07)
      await yieldFrame()
    }
    const br = row >> 1
    const even = (row & 1) === 0
    const rA = br > 0 ? br - 1 : 0
    const rC = Math.min(baseLast, br + 1)
    const rD = Math.min(baseLast, br + 2)
    for (let col = 0; col < side; col += 1) {
      if (even && (col & 1) === 0) continue // 偶数点已由基础层写入
      const o = (row * side + col) * 3
      for (let ch = 0; ch < 3; ch += 1) {
        let v
        if (even) {
          v = cAt(br, col, ch)
        } else {
          const vA = cAt(rA, col, ch)
          const vB = cAt(br, col, ch)
          const vC = cAt(rC, col, ch)
          const vD = cAt(rD, col, ch)
          v = (-vA + 9 * vB + 9 * vC - vD) * 0.0625
        }
        colors[o + ch] = v < 0 ? 0 : v > 1 ? 1 : v
      }
    }
  }

  // ---------- 海岸距离场纹理 ----------
  // 复用第一步算好的"离岸距离"（chamfer O(n)）：值 = 归一化"离岸近度" [0,1]，
  // 海面着色器靠它画近岸浅水色和岸线浪花带。
  // 半径 56 格（~4.5km）：2048 网格的格距是 80m，与旧版视觉带宽一致
  const NEARSHORE_RADIUS = 56
  const coastData = new Uint8Array(vertexCount)
  for (let i = 0; i < vertexCount; i += 1) {
    const near = Math.max(0, 1 - seaDist[i] / NEARSHORE_RADIUS)
    coastData[i] = Math.round(near * 255)
  }
  const coastTex = new THREE.DataTexture(coastData, side, side, THREE.RedFormat)
  coastTex.minFilter = THREE.LinearFilter
  coastTex.magFilter = THREE.LinearFilter
  coastTex.needsUpdate = true

  // ---------- 高度场纹理（海面"山影"用） ----------
  // 水面着色器沿太阳方向做高度场光线步进：山体在海面投下阴影。
  // 为什么不用 three 的 shadowMap：海面是自定义 ShaderMaterial，接 shadow chunk
  // 既脆弱又受阴影取景框限制；高度场步进是世界空间解析的，全域有效且自包含。
  // 分辨率用基础层（~160m）：阴影边缘本就柔化 ~100m，无需全分辨率，
  // 还省掉 400 万次半浮点转换（构建提速近 1 秒）
  const HEIGHT_BASE = 60
  const HEIGHT_RANGE = 1600
  const baseVertCount = baseSide * baseSide
  const heightHalf = new Uint16Array(baseVertCount)
  for (let i = 0; i < baseVertCount; i += 1) {
    heightHalf[i] = THREE.DataUtils.toHalfFloat((baseHeights[i] + HEIGHT_BASE) / HEIGHT_RANGE)
  }
  const heightTex = new THREE.DataTexture(heightHalf, baseSide, baseSide, THREE.RedFormat, THREE.HalfFloatType)
  heightTex.minFilter = THREE.LinearFilter
  heightTex.magFilter = THREE.LinearFilter
  heightTex.needsUpdate = true

  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  pos.needsUpdate = true
  report(0.86)
  await yieldFrame()

  // ---------- 解析法线（中心差分） ----------
  // 800 万三角面下 computeVertexNormals 要遍历索引做面积累（秒级）；
  // 高度场直接用左右上下差分求梯度 —— 快数倍，结果等价（连续高度场）。
  // 注意 cellW / cellH 已在“网格缓冲”段声明，此处不再重复声明
  const normalAttr = geometry.attributes.normal
  const nrm = normalAttr.array
  for (let r = 0; r < side; r += 1) {
    if ((r & 255) === 0) {
      report(0.86 + (r / side) * 0.08)
      await yieldFrame()
    }
    const rowUp = Math.max(0, r - 1) * side
    const rowDn = Math.min(side - 1, r + 1) * side
    const rowCur = r * side
    for (let c = 0; c < side; c += 1) {
      const cL = Math.max(0, c - 1)
      const cR = Math.min(side - 1, c + 1)
      const nx = (heights[rowCur + cL] - heights[rowCur + cR]) / (2 * cellW)
      const nz = (heights[rowDn + c] - heights[rowUp + c]) / (2 * cellH)
      const inv = 1 / Math.sqrt(nx * nx + nz * nz + 1)
      const o = (rowCur + c) * 3
      nrm[o] = nx * inv
      nrm[o + 1] = inv
      nrm[o + 2] = nz * inv
    }
  }
  normalAttr.needsUpdate = true

  // ---------- 第三遍：坡度着色 ----------
  // 参考 mapbox hillshade / procedural-gl 的渲染思路：颜色不只由海拔决定，
  // 陡坡强制染成岩壁色 —— 山脊线立刻"锐"起来，低多边形切面的立体感也靠它
  const normals = geometry.attributes.normal
  for (let i = 0; i < vertexCount; i += 1) {
    if (pos.getY(i) < 3) continue // 海床不参与
    const slope = 1 - normals.getY(i) // 0=平地，越大越陡
    let t = (slope - 0.12) / 0.3
    t = Math.max(0, Math.min(1, t))
    t = t * t * (3 - 2 * t) // smoothstep：缓坡留植被，陡壁出岩石
    if (t > 0.01) {
      tmpColor.setRGB(colors[i * 3], colors[i * 3 + 1], colors[i * 3 + 2])
      tmpColor.lerp(COLOR_ROCK, t * 0.85)
      colors[i * 3] = tmpColor.r
      colors[i * 3 + 1] = tmpColor.g
      colors[i * 3 + 2] = tmpColor.b
    }
  }

  // ---------- 第五遍（最后）：谷地暗角已随基础层颜色烘焙（见上文 AO 段） ----------
  report(1)
  await yieldFrame()

  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.96,
    metalness: 0.02,
    // dithering：片元末端加微噪声，打散统一量化的条带感
    dithering: true,
    // 平滑法线（不再是低多边形切面）：配合着色器里的细节法线，
    // 远景不被子像素切面磨平、近景有岩面微起伏 —— 这是"山体立体"的关键
  })

  // 逐像素基础场法线所需的 uniforms（nwCorner 在下方才算出，先占位再回填）
  const uTerrainOrigin = { value: new THREE.Vector2(0, 0) }
  const uTerrainSize = { value: new THREE.Vector2(widthM, depthM) }
  const uMaxHeight = { value: maxHeight }

  // ---------------------------------------------------------------- 细节着色器注入
  // onBeforeCompile 补丁 MeshStandardMaterial（保留 PBR 光照/阴影/雾，不另写材质）：
  //   1) 细节法线：世界坐标上的多八度噪声梯度扰动法线（Inigo Quilez 的
  //      "normal from height gradient" 思路）。
  //   2) 颜色细节：八度斑驳 + 陡坡岩层横纹，让"一整块灰"的岩壁有层次。
  //   3) ★ 核心纪律 —— 逐八度带限：每个八度的强度按"像素足迹"淡出，
  //      波长小于 ~2 个像素的八度一律不参与（不这么做就是欠采样，
  //      远景/中景会出现规则网格摩尔纹，这正是此前"编织网"伪影的根因）；
  //      差分步长同步取像素足迹，与像素网格对齐。
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTerrainOrigin = uTerrainOrigin
    shader.uniforms.uTerrainSize = uTerrainSize
    shader.uniforms.uMaxHeight = uMaxHeight
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vTerrainPos;')
      .replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\nvTerrainPos = (modelMatrix * vec4(transformed, 1.0)).xyz;',
      )

    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
        varying vec3 vTerrainPos;
        uniform vec2 uTerrainOrigin;  // 地形 bbox 西北角（世界 XZ）
        uniform vec2 uTerrainSize;    // 地形 bbox 尺寸（米）
        uniform float uMaxHeight;
        // ---- 基础场逐像素重建（与 JS 端一字不差的移植）----
        // ★ 为什么要在片元里重算：几何是 80m 网格，三角面内法线线性插值，
        //   在掠射角下会出现与网格同周期的"刻面"（量化实测周期 47–80m）。
        //   这里用同一噪声场（同 hash、同频率、同参数）逐像素求解析法线，
        //   彻底摆脱三角网格分辨率 —— 网格只负责轮廓，不负责明暗。
        float jHash2(int ix, int iz) {
          uint h = uint(ix) * 374761393u ^ uint(iz) * 668265263u;
          h = (h ^ (h >> 13)) * 1274126177u;
          h ^= h >> 16;
          return float(h) / 4294967295.0;
        }
        float vNoise(vec2 p) {
          int ix = int(floor(p.x));
          int iz = int(floor(p.y));
          float fx = p.x - float(ix);
          float fz = p.y - float(iz);
          float ux = fx * fx * (3.0 - 2.0 * fx);
          float uz = fz * fz * (3.0 - 2.0 * fz);
          float a = jHash2(ix, iz);
          float b = jHash2(ix + 1, iz);
          float c = jHash2(ix, iz + 1);
          float d = jHash2(ix + 1, iz + 1);
          return a + (b - a) * ux + (c - a) * uz + (a - b - c + d) * ux * uz;
        }
        float vFbm(vec2 p) {
          return vNoise(p) * 0.52 + vNoise(p * 2.13 + vec2(7.3, 3.1)) * 0.26
               + vNoise(p * 4.41 + vec2(13.7, 9.2)) * 0.14 + vNoise(p * 8.87 + vec2(31.1, 17.5)) * 0.08;
        }
        float vRidged(vec2 p) {
          float sum = 0.0;
          float amp = 0.5;
          float freq = 1.0;
          for (int i = 0; i < 4; i++) {
            float n = 1.0 - abs(vNoise(p * freq) * 2.0 - 1.0);
            sum += n * n * amp;
            amp *= 0.5;
            freq *= 2.13;
          }
          return sum;
        }
        float vCrag(vec2 p) {
          float sum = 0.0;
          float amp = 0.5;
          float freq = 1.0;
          for (int i = 0; i < 3; i++) {
            float n = 1.0 - abs(vNoise(p * freq) * 2.0 - 1.0);
            sum += n * amp;
            amp *= 0.52;
            freq *= 2.17;
          }
          return sum;
        }
        float vWarp(vec2 p) {
          float qx = vFbm(p);
          float qz = vFbm(p + vec2(5.2, 1.3));
          return vFbm(p + vec2(2.0 * qx, 2.0 * qz));
        }
        /** 与 createTerrain 的基础层高度公式同构（不含海岸衰减/侵蚀的小偏差） */
        float vBaseHeight(vec2 w) {
          vec2 n = ((w - uTerrainOrigin) / uTerrainSize) * 14.0;
          float base = vWarp(n);
          float ridge = vRidged(n * 1.7 + vec2(4.7, 9.1));
          float crag = vCrag(n * vec2(4.1, 3.7) + vec2(23.4, 12.6));
          float m = min(1.0, base * 0.55 + ridge * 0.5 + crag * 0.18);
          float h = 15.0 + pow(m, 1.5) * uMaxHeight;
          float ping = 1.0 - abs(2.0 * vFbm(n * 1.6 + vec2(17.0, 11.0)) - 1.0);
          float channel = pow(1.0 - ping, 3.0);
          h -= channel * min(1.0, h / (uMaxHeight * 0.35)) * uMaxHeight * 0.1;
          return h;
        }
        // 细节噪声：Dave Hoskins 无 sin hash，十万级世界坐标下不退化
        float tHash(vec2 p) {
          p = mod(p, 4096.0);
          vec3 p3 = fract(vec3(p.xyx) * 0.1031);
          p3 += dot(p3, p3.yzx + 33.33);
          return fract((p3.x + p3.y) * p3.z);
        }
        // 梯度噪声（Perlin 风格）：格点放随机梯度，格点处值恒为 0。
        // ★ 不用 value noise：后者是"格点放随机值"，插值后带方形格点脊，
        //   中近距细节会显成规则"编织网"（本项目踩过的坑）；梯度噪声无此结构
        vec2 tGrad(vec2 i) {
          vec2 g = vec2(tHash(i), tHash(i + vec2(37.7, 17.3))) * 2.0 - 1.0;
          return g / max(length(g), 1e-4);
        }
        float tNoise(vec2 p) {
          vec2 i = floor(p);
          vec2 f = fract(p);
          vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
          float n00 = dot(tGrad(i), f);
          float n10 = dot(tGrad(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0));
          float n01 = dot(tGrad(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0));
          float n11 = dot(tGrad(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0));
          return mix(mix(n00, n10, u.x), mix(n01, n11, u.x), u.y) * 0.7 + 0.5;
        }`,
      )
      .replace(
        '#include <color_fragment>',
        `#include <color_fragment>
        {
          // ★ 像素足迹用屏幕导数 fwidth 求：它天然包含"掠射角压缩"——
          //   斜视时沿视线方向的世界足迹可达数倍，各向同性的距离估计会把
          //   被压成亚像素的细八度继续算进来，欠采样成规则织纹
          float pf = max(length(fwidth(vTerrainPos.xz)), 4.0);
          // 逐八度带限：pf/λ > 0.25 起淡出、> 0.42 收光（λ ≥ ~4 像素才完整保留）
          float w1 = 1.0 - smoothstep(0.25, 0.42, pf * 0.0016);   // ~625m
          float w2 = 1.0 - smoothstep(0.25, 0.42, pf * 0.00385);  // ~260m
          float w3 = 1.0 - smoothstep(0.25, 0.42, pf * 0.0091);   // ~110m
          float n1 = tNoise(vTerrainPos.xz * 0.0016);
          float n2 = tNoise(vTerrainPos.xz * 0.00385 + 5.2);
          float n3 = tNoise(vTerrainPos.xz * 0.0091 + 9.4);
          float mott = (n1 - 0.5) * 0.24 * w1 + (n2 - 0.5) * 0.16 * w2 + (n3 - 0.5) * 0.1 * w3;
          // 陡壁岩层横纹：vNormal 是视图空间，先转回世界空间再判坡向
          vec3 worldN = normalize((vec4(normalize(vNormal), 0.0) * viewMatrix).xyz);
          float slopeC = 1.0 - clamp(worldN.y, 0.0, 1.0);
          float strata = sin(vTerrainPos.y * 0.05 + n1 * 7.0);
          diffuseColor.rgb *= 1.0 + mott - slopeC * 0.06 * (0.5 + 0.5 * strata) * w2;
        }`,
      )
      .replace(
        '#include <normal_fragment_begin>',
        `#include <normal_fragment_begin>
        {
          // 像素足迹用屏幕导数 fwidth（含掠射角压缩）
          float pf = max(length(fwidth(vTerrainPos.xz)), 4.0);
          vec2 tw = vTerrainPos.xz;

          // ---- ① 基础场解析法线：取代三角面插值的 vNormal ----
          // 几何是 80m 网格、面内法线线性插值，掠射角下会暴露与网格同周期的
          // 刻面（量化实测 47–80m 周期）——解析场逐像素求梯度后彻底摆脱
          // 网格分辨率：网格只负责轮廓，明暗由解析法线负责
          float eB = max(pf * 2.0, 24.0);
          float hB = vBaseHeight(tw);
          float hBx = vBaseHeight(tw + vec2(eB, 0.0));
          float hBz = vBaseHeight(tw + vec2(0.0, eB));
          vec3 baseNormalWorld = normalize(vec3(-(hBx - hB) / eB, 1.0, -(hBz - hB) / eB));
          vec3 baseNormalView = normalize((viewMatrix * vec4(baseNormalWorld, 0.0)).xyz);
          // 低地/海岸带混回插值法线：解析场未含海岸衰减（差异仅存在于低地），
          // 且低地平坦本就不会出现刻面
          float coastal = 1.0 - smoothstep(30.0, 120.0, hB);
          normal = normalize(mix(baseNormalView, normal, coastal));

          // ---- ② 细节法线：逐八度带限的高频颗粒 ----
          float w1 = 1.0 - smoothstep(0.25, 0.42, pf * 0.0016);
          float w2 = 1.0 - smoothstep(0.25, 0.42, pf * 0.00385);
          float w3 = 1.0 - smoothstep(0.25, 0.42, pf * 0.0091);
          float w4 = 1.0 - smoothstep(0.25, 0.42, pf * 0.0217);
          float e = pf;
          // ★ 对角差分（±45° 两个正交方向）而不是沿 x/z 轴：轴向取样会把
          //   固定方向偏好烙进法线扰动，在光照下显成有方向的织纹
          vec2 d1 = vec2(0.70711, 0.70711);
          vec2 d2 = vec2(0.70711, -0.70711);
          vec2 o1 = tw + d1 * e;
          vec2 o2 = tw + d2 * e;
          float d0 = tNoise(tw * 0.0016) * w1 + tNoise(tw * 0.00385 + 5.2) * w2
                   + tNoise(tw * 0.0091 + 9.4) * w3 + tNoise(tw * 0.0217 + 3.1) * w4;
          float d1v = tNoise(o1 * 0.0016) * w1 + tNoise(o1 * 0.00385 + 5.2) * w2
                   + tNoise(o1 * 0.0091 + 9.4) * w3 + tNoise(o1 * 0.0217 + 3.1) * w4;
          float d2v = tNoise(o2 * 0.0016) * w1 + tNoise(o2 * 0.00385 + 5.2) * w2
                   + tNoise(o2 * 0.0091 + 9.4) * w3 + tNoise(o2 * 0.0217 + 3.1) * w4;
          vec2 g = ((d1v - d0) * d1 + (d2v - d0) * d2) / e;
          // 陡坡上细节更强（岩壁），缓坡弱（草甸）；判坡向要转回世界空间
          vec3 worldN2 = normalize((vec4(normal, 0.0) * viewMatrix).xyz);
          float slopeN = 1.0 - clamp(worldN2.y, 0.0, 1.0);
          float k = (0.6 + slopeN * 1.4) * 18.0;
          // ★ 梯度是"世界空间"的，normal 是"视图空间"的 —— 必须先把扰动
          //   转到视图空间再叠加，否则光影响应随相机转动漂移
          vec3 perturbView = (viewMatrix * vec4(-g.x, 0.0, -g.y, 0.0)).xyz;
          normal = normalize(normal + perturbView * k);
        }`,
      )
  }

  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = 'terrain'
  mesh.receiveShadow = true
  mesh.castShadow = true // 山体自阴影：主光源按需重烤（见 SandBoxMap 的 updateSunShadow）
  mesh.userData = { type: 'terrain' }

  // 网格顶点以平面中心为原点，平移到「lngLatToScene 坐标系」下对齐：
  // 推导：顶点本地 x = -width/2 + col*cellW，目标世界 x = minScene.x + col*cellW
  // → mesh.position.x = minScene.x + width/2（z 同理）
  const nwCorner = lngLatToScene(bounds.minLng, bounds.maxLat) // 西北角
  mesh.position.set(nwCorner.x + widthM / 2, 0, nwCorner.z + depthM / 2)
  // 回填逐像素基础场的坐标映射（着色器里用它把世界 XZ 换算成噪声坐标）
  uTerrainOrigin.value.set(nwCorner.x, nwCorner.z)

  // 世界坐标 → 地形高度（双线性，墨卡托近似平面内查表）：
  // 供船体/标记贴地使用 —— 机器人坐标若落在岸上，模型会被山体埋掉，
  // 有了采样就能把模型抬到地形之上，保证永远可见、可点击
  // 注：cellW / cellH 已在“解析法线”段于同一函数作用域内声明，此处不再重复声明
  function sampleHeight(worldX, worldZ) {
    const fx = (worldX - nwCorner.x) / cellW
    const fz = (worldZ - nwCorner.z) / cellH
    if (fx < 0 || fz < 0 || fx >= grid || fz >= grid) return -30
    const c0 = Math.floor(fx)
    const r0 = Math.floor(fz)
    const tx = fx - c0
    const tz = fz - r0
    const c1 = Math.min(grid, c0 + 1)
    const r1 = Math.min(grid, r0 + 1)
    const h00 = heights[r0 * side + c0]
    const h10 = heights[r0 * side + c1]
    const h01 = heights[r1 * side + c0]
    const h11 = heights[r1 * side + c1]
    return (h00 * (1 - tx) + h10 * tx) * (1 - tz) + (h01 * (1 - tx) + h11 * tx) * tz
  }

  const group = new THREE.Group()
  group.name = 'terrain'
  group.add(mesh)

  return {
    group,
    mesh,
    bounds,
    widthM,
    depthM,
    /** 世界坐标 (x,z) → 地形高度（米），海面返回 -30 */
    sampleHeight,
    /** 海面尺寸：远大于地形 bbox —— 配合"海面跟随相机"的无限海做法，
     *  可视边缘推到 ~330km 外的雾区深处（雾在 300km 处已全饱和），
     *  全景/俯视/极限拉远都不会露出"世界尽头"的平面边界 */
    seaSize: Math.max(widthM, depthM) * 7.0,
    center: { lng: CENTER_LNG, lat: CENTER_LAT },
    /** 海岸距离场纹理（R 通道 = 离岸近度 [0,1]），海面浅水色/浪花带用 */
    coastTex,
    /** 距离场的世界坐标映射：uv = (worldXZ - min) / size */
    coastBounds: { minX: nwCorner.x, minZ: nwCorner.z, sizeX: widthM, sizeZ: depthM },
    /** 高度场纹理（R16F，编码后的米值）：海面"山影"光线步进用 */
    heightTex,
    heightBounds: {
      minX: nwCorner.x,
      minZ: nwCorner.z,
      sizeX: widthM,
      sizeZ: depthM,
      base: HEIGHT_BASE,
      range: HEIGHT_RANGE,
    },
  }
}

/**
 * 创建波浪海面材质（顶点位移 + 菲涅尔 + 波峰泡沫）
 * 与 VesselManager.waveHeight 保持同一组波参数，船体起伏才贴合浪面。
 */
export const SEA_WAVE = {
  // 顶点着色器与 CPU 共用的波参数：方向、频率、振幅、速度。
  // 振幅按 165km 场景尺度放大（厘米级浪在百公里视角下等于镜面）。
  // 6 组非轴向、非整倍数频率的波叠加 —— 3 组轴向正弦会在海面织出
  // 规则格点（泡沫/高光落在干涉峰上形成点阵），多方向乱频才能打散。
  waves: [
    { fx: 0.0008, fz: 0, t: 1.05, amp: 7.5 },
    { fx: 0, fz: 0.00058, t: -0.82, amp: 5.6 },
    { fx: 0.00042, fz: 0.00036, t: 1.55, amp: 3.6 },
    { fx: -0.00031, fz: 0.00052, t: 1.21, amp: 2.6 },
    { fx: 0.00061, fz: -0.00033, t: -1.37, amp: 2.0 },
    { fx: 0.00023, fz: 0.00071, t: 0.94, amp: 1.6 },
  ],
}

/** CPU 侧波高（供船体/航线贴浪） */
export function seaWaveHeight(x, z, time) {
  let h = 0
  for (const w of SEA_WAVE.waves) {
    h += Math.sin(x * w.fx + z * w.fz + time * w.t) * w.amp
  }
  return h
}

export function createSeaMaterial({
  coastTex = null,
  coastBounds = null,
  heightTex = null,
  heightBounds = null,
} = {}) {
  const uniforms = {
    uTime: { value: 0 },
    uSunDir: { value: SUN_DIR.clone() },
    uDeepColor: { value: new THREE.Color(0x06334f) },
    uShallowColor: { value: new THREE.Color(0x1a7ba1) },
    uHorizonColor: { value: new THREE.Color(0xc6dfec) },
    // 海面专用距离雾色：比天空地平线略深一档 —— 远处海面呈"雾蓝"而非惨白，
    // 真实海天线本来就是比天空暗一点的线；与天空穹顶底色的同源见 SEA_FOG_COLOR
    uFogColor: { value: new THREE.Color(SEA_FOG_COLOR) },
    uCoastTex: { value: coastTex },
    uBoundsMin: { value: new THREE.Vector2(coastBounds?.minX ?? 0, coastBounds?.minZ ?? 0) },
    uBoundsSize: { value: new THREE.Vector2(coastBounds?.sizeX ?? 1, coastBounds?.sizeZ ?? 1) },
    // 高度场（山影用）
    uHeightTex: { value: heightTex },
    uHeightMin: { value: new THREE.Vector2(heightBounds?.minX ?? 0, heightBounds?.minZ ?? 0) },
    uHeightSize: { value: new THREE.Vector2(heightBounds?.sizeX ?? 1, heightBounds?.sizeZ ?? 1) },
    uHeightBase: { value: heightBounds?.base ?? 0 },
    uHeightRange: { value: heightBounds?.range ?? 1 },
  }

  // 波场 GLSL 从 SEA_WAVE 常量生成，保证与 CPU 的 seaWaveHeight 严格一致。
  // waveField = 波高（sin 项），waveGrad = 解析梯度（cos 项）——
  // 梯度直接给逐像素法线，不再依赖网格顶点的有限差分。
  const waveSinTerms = SEA_WAVE.waves
    .map(
      (w) =>
        `h += sin(p.x * ${w.fx.toFixed(6)} + p.y * ${w.fz.toFixed(6)} + uTime * ${w.t.toFixed(3)}) * ${w.amp.toFixed(2)};`,
    )
    .join('\n      ')
  const waveCosTerms = SEA_WAVE.waves
    .map(
      (w) =>
        `g += vec2(${(w.fx * w.amp).toFixed(6)}, ${(w.fz * w.amp).toFixed(6)}) * cos(p.x * ${w.fx.toFixed(6)} + p.y * ${w.fz.toFixed(6)} + uTime * ${w.t.toFixed(3)});`,
    )
    .join('\n      ')
  const waveGLSL = /* glsl */ `
    float waveField(vec2 p) {
      float h = 0.0;
      ${waveSinTerms}
      return h;
    }
    vec2 waveGrad(vec2 p) {
      vec2 g = vec2(0.0);
      ${waveCosTerms}
      return g;
    }
  `

  // 顶点着色器：只做几何位移（锚定世界坐标，海面网格可跟随相机移动而不漂移波场）
  const vertexShader = /* glsl */ `
    uniform float uTime;
    varying vec3 vWorldPosition;

    ${waveGLSL}

    void main() {
      vec3 pos = position;
      // 用世界坐标采样波场：海面网格随相机平移时波形纹丝不动
      vec4 base = modelMatrix * vec4(pos, 1.0);
      pos.y += waveField(base.xz);

      vec4 worldPos = modelMatrix * vec4(pos, 1.0);
      vWorldPosition = worldPos.xyz;

      gl_Position = projectionMatrix * viewMatrix * worldPos;
    }
  `

  const fragmentShader = /* glsl */ `
    uniform float uTime;
    uniform vec3 uSunDir;
    uniform vec3 uDeepColor;
    uniform vec3 uShallowColor;
    uniform vec3 uHorizonColor;
    uniform vec3 uFogColor;
    uniform sampler2D uCoastTex;
    uniform vec2 uBoundsMin;
    uniform vec2 uBoundsSize;
    uniform sampler2D uHeightTex;
    uniform vec2 uHeightMin;
    uniform vec2 uHeightSize;
    uniform float uHeightBase;
    uniform float uHeightRange;
    varying vec3 vWorldPosition;

    ${waveGLSL}

    // 程序化噪声：泡沫斑块与闪辉调制（Wawa Sensei 水着色器的噪声泡沫方案）。
    // hash 用 Dave Hoskins 的无 sin 方案并先 mod 限幅 ——
    // 经典 fract(sin(dot(p,k))*43758) 在世界坐标（十万级）+ 高频倍频下
    // 精度退化，会输出成块的伪结构（也是点阵伪影的帮凶）
    float hash(vec2 p) {
      p = mod(p, 4096.0);
      vec3 p3 = fract(vec3(p.xyx) * 0.1031);
      p3 += dot(p3, p3.yzx + 33.33);
      return fract((p3.x + p3.y) * p3.z);
    }
    float vnoise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      f = f * f * (3.0 - 2.0 * f);
      float a = hash(i);
      float b = hash(i + vec2(1.0, 0.0));
      float c = hash(i + vec2(0.0, 1.0));
      float d = hash(i + vec2(1.0, 1.0));
      return a + (b - a) * f.x + (c - a) * f.y + (a - b - c + d) * f.x * f.y;
    }
    float fbm2(vec2 p) {
      return vnoise(p) * 0.5 + vnoise(p * 2.17 + vec2(5.2, 1.3)) * 0.3
           + vnoise(p * 4.73 + vec2(9.1, 3.7)) * 0.2;
    }

    /** 采样地形高度（米）：出界（远海）返回一个低值，不参与遮挡 */
    float terrainHeight(vec2 w) {
      vec2 uv = (w - uHeightMin) / uHeightSize;
      if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) return -80.0;
      return texture2D(uHeightTex, uv).r * uHeightRange - uHeightBase;
    }

    /**
     * 山影：沿太阳方向做高度场光线步进（10 步、指数加距，覆盖 ~35km）。
     * 射线始终向上（slope = tan(太阳仰角)），任一步被地形"顶穿"即为阴影。
     * 步进在世界空间解析——不依赖 three 阴影贴图，全域有效、无取景框边界。
     */
    float sunShadow(vec2 wp) {
      vec3 L = normalize(uSunDir);
      vec2 dir = normalize(L.xz + vec2(1e-4));
      float slope = L.y / max(length(L.xz), 1e-4);
      float sh = 1.0;
      // 起步距离加抖动：离散步进的阴影边界会排成同心"阶梯带"，
      // 按像素抖动起点把条带打散成噪点（远处观感即柔和渐变）
      float t = 220.0 * (0.8 + 0.4 * hash(wp * 0.013));
      for (int i = 0; i < 12; i++) {
        float rayH = slope * t;
        float th = terrainHeight(wp + dir * t);
        sh = min(sh, smoothstep(-40.0, 110.0, rayH - th));
        t *= 1.62;
      }
      return sh;
    }

    void main() {
      vec2 fp = vWorldPosition.xz;
      vec3 V = normalize(cameraPosition - vWorldPosition);
      vec3 L = normalize(uSunDir);
      float dist = length(vWorldPosition - cameraPosition);

      // 逐像素解析波场：波高 + 梯度（法线）。
      // 之前按顶点采样（网格 1.2km ≈ 波长量级）再插值 —— 插值在三角形格点上
      // 产生规则的"雪花簇"点阵摩尔纹，这是海面白点阵列的根因
      float h = waveField(fp);
      vec2 grad = waveGrad(fp);
      vec3 N = normalize(vec3(-grad.x, 1.0, -grad.y));

      // 高频法线扰动：噪声调制振幅，闪辉更有聚散感；
      // 远处按距离衰减 —— 像素级噪声在百公里外交叠成摩尔纹，必须收掉
      float rippleAmp = 0.06 + fbm2(fp * 0.0016 + uTime * 0.05) * 0.10;
      rippleAmp *= 1.0 - smoothstep(6000.0, 25000.0, dist);
      N.x += sin(fp.x * 0.021 + uTime * 1.9) * cos(fp.y * 0.017 - uTime * 1.4) * rippleAmp;
      N.z += sin(fp.x * 0.013 - uTime * 1.1 + fp.y * 0.019) * rippleAmp;
      // 近景细波：更短波长（~140m）只在 3~10km 内出现 —— 近看水面的碎光更细密
      float rippleAmp2 = 0.045 * (1.0 - smoothstep(3000.0, 10000.0, dist));
      N.x += sin(fp.x * 0.045 - uTime * 2.3) * rippleAmp2;
      N.z += cos(fp.y * 0.038 + uTime * 2.1) * rippleAmp2;
      N = normalize(N);
      vec3 H = normalize(L + V);

      // 距离压平系数：波场驱动的颜色起伏/高光在全景视角下收掉 ——
      // 7~15km 波长的正弦干涉在远处呈"规则斜向条纹"，观感像摩尔纹
      float waveFar = smoothstep(20000.0, 70000.0, dist);

      float depthMix = smoothstep(-19.0, 19.0, h);
      depthMix = mix(depthMix, 0.35, waveFar);
      vec3 color = mix(uDeepColor, uShallowColor, depthMix);

      // 近岸：采样海岸距离场 → 浅水变青
      float nearshore = 0.0;
      vec2 cuv = (vWorldPosition.xz - uBoundsMin) / uBoundsSize;
      if (uBoundsSize.x > 1.0 && cuv.x > 0.0 && cuv.x < 1.0 && cuv.y > 0.0 && cuv.y < 1.0) {
        nearshore = texture2D(uCoastTex, cuv).r;
      }
      float shallow = smoothstep(0.25, 0.85, nearshore);
      color = mix(color, vec3(0.23, 0.75, 0.70), shallow * 0.55);

      // 天空反射（webgl_shaders_ocean 的菲涅尔混色）：掠射角混入反射方向的天色，
      // 海面从"一滩颜料"变成"有环境的镜面"。权重压低 —— 混太多会整片泛白
      vec3 R = reflect(-V, N);
      float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 2.6);
      vec3 skyRefl = mix(uHorizonColor, vec3(0.32, 0.62, 0.85), clamp(R.y, 0.0, 1.0));
      color = mix(color, skyRefl, fres * 0.35);

      // 大尺度云影：低频噪声在海面投下缓慢漂移的暗斑（天空云场的廉价投影）
      float cloudShadow = smoothstep(0.55, 0.8, fbm2(fp * 0.00006 + vec2(uTime * 0.004, uTime * 0.002)));
      color *= 1.0 - cloudShadow * 0.06;

      // 山影：地形高度场沿太阳方向光线步进 —— 被山遮住的水面整体压暗、
      // 高光熄灭；这是"山在海上有影子"的立体暗示（自包含，无取景框边界）
      float sunSh = sunShadow(fp);
      color *= mix(0.5, 1.0, sunSh);

      float diff = max(dot(N, L), 0.0);
      color += diff * 0.15 * sunSh;

      // 宽高光打底 + 噪声调制的紧致闪辉（阳光下的波光粼粼）。
      // 都是像素级高频，只在近景（跟随/局部视角）成立；
      // 全景视角下必须几乎收光 —— 否则 20m 级的噪声在一个像素内混叠成规则点阵。
      // glintPatch：8km 级低频斑块把镜面带打碎成不规则光斑（真实海面的闪光是散的）
      float glintFade = 1.0 - smoothstep(8000.0, 35000.0, dist) * 0.92;
      float glintPatch = 0.45 + 0.55 * fbm2(fp * 0.00012 + 11.7);
      float spec = pow(max(dot(N, H), 0.0), 120.0);
      color += vec3(0.9, 0.95, 1.0) * spec * 0.35 * (0.12 + glintFade * 0.88) * glintPatch * sunSh;
      float glitter = pow(max(dot(N, H), 0.0), 340.0) * (0.4 + fbm2(fp * 0.05 + uTime * 0.3));
      color += vec3(1.0, 0.97, 0.9) * glitter * 1.5 * glintFade * sunSh;

      // 波峰泡沫：只在真正的浪尖上出现，且用噪声把"浪高门槛"本身打乱 ——
      // 之前把泡沫直接挂在解析波高 h 的等值带上，泡沫顺着正弦干涉峰连成
      // 规则的条纹格点；hFoam 掺入低频噪声后，泡沫变成散乱的斑块。
      // 远处收得更早：百米级泡沫斑在一个像素内混叠就只是噪点
      float foamNoise = fbm2(fp * 0.006 + uTime * 0.12);
      float hFoam = h + (fbm2(fp * 0.0021 + uTime * 0.05) - 0.5) * 16.0;
      float crestFade = 1.0 - smoothstep(15000.0, 60000.0, dist);
      float crest = smoothstep(12.0, 18.0, hFoam) * smoothstep(0.45, 0.72, foamNoise) * crestFade;
      color = mix(color, vec3(0.80, 0.86, 0.88), smoothstep(0.15, 0.45, crest) * 0.6);
      color = mix(color, vec3(0.97, 0.99, 1.0), smoothstep(0.5, 0.85, crest));

      // 岸线浪花带：噪声斑块化 + 随时间向岸推移呼吸
      float surfNoise = fbm2(fp * 0.004 - uTime * 0.06);
      float surfPhase = 0.07 * sin(uTime * 1.2 + vWorldPosition.x * 0.004 + vWorldPosition.z * 0.003);
      float surf = smoothstep(0.72, 0.92, nearshore + surfPhase + surfNoise * 0.14);
      color = mix(color, vec3(0.95, 0.98, 1.0), surf * (0.5 + 0.35 * surfNoise));

      // 距离雾化推到百公里级之外：中景的海保持饱和的蓝，只有真正远处才收进海雾蓝。
      // 雾起太近 + 雾色太亮是"整片海发白"的元凶（默认全景视距 ~90km 正好落在雾区）
      float fog = smoothstep(80000.0, 300000.0, dist);
      color = mix(color, uFogColor, fog);

      // 深海完全不透明：地形平面（含 -30 海床）只覆盖 bbox 范围，
      // 若深海半透明，bbox 内外的海底底色差会透出一块"矩形接缝"；
      // 浅水区保留透明度（0.84）以透出近岸沙底色
      gl_FragColor = vec4(color, 1.0 - shallow * 0.16);

      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }
  `

  return new THREE.ShaderMaterial({
    uniforms,
    vertexShader,
    fragmentShader,
    transparent: true,
  })
}

/** 天空穹顶 */
export function createSkyDome() {
  const uniforms = {
    uTopColor: { value: new THREE.Color(0x4da2e0) },
    // 地平线以下与海面雾色同源：海面边缘因此"溶解"进天空，没有世界尽头硬边
    uBottomColor: { value: new THREE.Color(SEA_FOG_COLOR) },
    uHorizonColor: { value: new THREE.Color(0xc6dfec) },
    uSunDir: { value: SUN_DIR.clone() },
    uTime: { value: 0 },
  }

  const material = new THREE.ShaderMaterial({
    uniforms,
    side: THREE.BackSide,
    depthWrite: false,
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uTopColor;
      uniform vec3 uBottomColor;
      uniform vec3 uHorizonColor;
      uniform vec3 uSunDir;
      uniform float uTime;
      varying vec3 vDir;

      float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
      float noise(vec2 p) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        float a = hash(i);
        float b = hash(i + vec2(1.0, 0.0));
        float c = hash(i + vec2(0.0, 1.0));
        float d = hash(i + vec2(1.0, 1.0));
        return a + (b - a) * f.x + (c - a) * f.y + (a - b - c + d) * f.x * f.y;
      }
      float fbmSky(vec2 p) {
        return noise(p) * 0.52 + noise(p * 2.13 + vec2(7.3, 3.1)) * 0.26
             + noise(p * 4.41 + vec2(13.7, 9.2)) * 0.14;
      }
      float cloudField(vec3 dir, float t) {
        vec2 p = dir.xz * 3.5 + vec2(t * 0.04, t * 0.02);
        float n = fbmSky(p);
        // domain warping
        n = fbmSky(p + vec2(n * 1.2));
        return smoothstep(0.52, 0.74, n);
      }

      void main() {
        vec3 dir = normalize(vDir);
        float h = clamp(dir.y, -0.1, 1.0);

        vec3 sky = mix(uHorizonColor, uBottomColor, smoothstep(-0.1, 0.1, dir.y));
        sky = mix(sky, uTopColor, pow(max(h, 0.0), 0.72));

        float sun = pow(max(dot(dir, uSunDir), 0.0), 260.0) * 1.4;
        float glow = pow(max(dot(dir, uSunDir), 0.0), 14.0) * 0.25;
        sky += vec3(1.0, 0.92, 0.72) * (sun + glow);

        // fbm 云层：带 domain warping、缓慢漂移、底部投影暗化
        float t = uTime; // 这里借 uTime 做漂移，须通过 uniforms 注入
        float cloud = cloudField(dir, t);
        cloud *= smoothstep(0.0, 0.18, h); // 地平线附近无云
        cloud *= (1.0 - smoothstep(0.62, 0.88, h)); // 高空云散
        vec3 cloudCol = vec3(1.0);
        vec3 cloudShadow = vec3(0.72, 0.76, 0.82);
        cloudCol = mix(cloudShadow, cloudCol, smoothstep(0.0, 0.35, dot(dir, uSunDir)));
        sky = mix(sky, cloudCol, cloud * 0.55);

        gl_FragColor = vec4(sky, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  })

  const geometry = new THREE.SphereGeometry(400000, 48, 24)
  return new THREE.Mesh(geometry, material)
}

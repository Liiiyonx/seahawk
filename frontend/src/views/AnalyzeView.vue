<template>
  <div class="analyze">
    <div class="analyze__head">
      <h2 class="analyze__title">图片分析</h2>
      <p class="analyze__sub">
        上传一张海漂垃圾图片，OpenCV 识别泡沫 / 塑胶 / 渔具 / 其他，并框出目标位置。
      </p>
    </div>

    <div class="analyze__body">
      <!-- 上传 / 预览 -->
      <section class="panel analyze__upload">
        <div class="panel-title">
          <span>图片</span>
          <button class="btn" @click="pick" :disabled="analyzing">选择图片</button>
        </div>
        <input ref="fileInput" type="file" accept="image/*" class="analyze__file" @change="onFile" />
        <div class="analyze__stage">
          <div v-if="!preview" class="analyze__drop" @click="pick">
            <div class="analyze__drop-icon">＋</div>
            <p>点击上传图片</p>
            <p class="text-dim">支持 jpg / png</p>
          </div>
          <canvas v-else ref="canvas" class="analyze__canvas"></canvas>
        </div>
      </section>

      <!-- 结果 -->
      <section class="panel analyze__result">
        <div class="panel-title"><span>分析结果</span></div>
        <div class="analyze__result-body">
          <div v-if="analyzing" class="empty">分析中…</div>
          <div v-else-if="error" class="empty text-danger">{{ error }}</div>
          <div v-else-if="!result" class="empty">上传图片后自动分析</div>
          <template v-else>
            <div class="analyze__summary">
              检测到 <b class="text-primary">{{ result.count }}</b> 个目标
              <span class="text-dim">（引擎：OpenCV · {{ result.width }}×{{ result.height }}）</span>
            </div>
            <div v-if="!result.count" class="empty">未检测到明显的垃圾目标</div>
            <div v-for="(d, i) in result.detections" :key="i" class="det-item">
              <span class="det-item__dot" :style="{ background: classColor(d.class) }"></span>
              <span class="det-item__class">{{ classLabel(d.class) }}</span>
              <span class="det-item__box">{{ fmtBox(d.bbox) }}</span>
              <span class="det-item__conf">{{ (d.confidence * 100).toFixed(1) }}%</span>
            </div>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { aiApi } from '@/api'
import { classLabel, classColor } from '@/utils/constants'

const fileInput = ref(null)
const canvas = ref(null)
const preview = ref('')
const result = ref(null)
const analyzing = ref(false)
const error = ref('')

function pick() {
  fileInput.value?.click()
}

async function onFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  error.value = ''
  result.value = null

  const reader = new FileReader()
  reader.onload = () => {
    preview.value = reader.result
    draw()
  }
  reader.readAsDataURL(file)

  analyzing.value = true
  try {
    const res = await aiApi.analyzeImage(file)
    result.value = res
    await nextTick()
    draw()
  } catch (err) {
    error.value = err.message || '分析失败'
  } finally {
    analyzing.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

/** 把预览图 + 检测框画到 canvas */
function draw() {
  if (!preview.value || !canvas.value) return
  const img = new Image()
  img.onload = () => {
    const c = canvas.value
    c.width = img.naturalWidth
    c.height = img.naturalHeight
    const ctx = c.getContext('2d')
    ctx.drawImage(img, 0, 0)
    for (const d of result.value?.detections || []) {
      const [x1, y1, x2, y2] = d.bbox
      const color = classColor(d.class)
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
      ctx.fillStyle = color
      ctx.font = '13px sans-serif'
      const label = `${classLabel(d.class)} ${(d.confidence * 100).toFixed(0)}%`
      const tw = ctx.measureText(label).width
      ctx.fillRect(x1, Math.max(0, y1 - 20), tw + 8, 20)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, x1 + 4, y1 - 6)
    }
  }
  img.src = preview.value
}

function fmtBox(b) {
  return `[${b.map((n) => Math.round(n)).join(', ')}]`
}
</script>

<style scoped>
.analyze {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  min-height: 0;
}

.analyze__head {
  flex-shrink: 0;
}

.analyze__title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
  letter-spacing: 1px;
}

.analyze__sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-sub);
}

.analyze__body {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.analyze__upload,
.analyze__result {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.analyze__file {
  display: none;
}

.analyze__stage {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px;
  overflow: auto;
}

.analyze__drop {
  width: 100%;
  height: 100%;
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1.5px dashed var(--border-bright);
  border-radius: var(--radius-lg);
  cursor: pointer;
  color: var(--text-sub);
  transition: border-color 0.2s var(--ease), background 0.2s var(--ease);
}

.analyze__drop:hover {
  border-color: var(--c-primary-dim);
  background: var(--bg-hover);
}

.analyze__drop-icon {
  font-size: 36px;
  color: var(--c-primary);
}

.analyze__canvas {
  max-width: 100%;
  max-height: 100%;
  border-radius: 6px;
}

.analyze__result-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px;
}

.analyze__summary {
  font-size: 13px;
  color: var(--text-main);
  margin-bottom: 12px;
}

.det-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.det-item__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.det-item__class {
  color: var(--text-main);
  font-weight: 500;
  min-width: 60px;
}

.det-item__box {
  flex: 1;
  color: var(--text-dim);
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 11px;
}

.det-item__conf {
  color: var(--c-primary);
  font-variant-numeric: tabular-nums;
}
</style>

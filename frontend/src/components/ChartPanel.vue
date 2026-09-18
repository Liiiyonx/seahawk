<template>
  <div class="chart-panel panel">
    <div class="panel-title">
      <span>{{ title }}</span>
      <slot name="action"></slot>
    </div>
    <div ref="chartEl" class="chart-panel__body" :style="{ height: `${height}px` }"></div>
  </div>
</template>

<script setup>
/**
 * ECharts 通用封装。
 *
 * 关键点：
 * 1. resize 监听要防抖 —— 大屏拖拽窗口时 ECharts 重绘很吃性能
 * 2. 组件卸载必须 dispose —— 否则切页会把实例泄漏在内存里
 * 3. option 变化用 setOption(option, true) 而不是重建实例
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  title: { type: String, default: '' },
  option: { type: Object, required: true },
  height: { type: Number, default: 240 },
})

const chartEl = ref(null)
let chart = null
let resizeTimer = null

function render() {
  if (!chartEl.value) return
  if (!chart) {
    chart = echarts.init(chartEl.value, null, { renderer: 'canvas' })
  }
  chart.setOption(props.option, true)
}

function onResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => chart?.resize(), 150)
}

onMounted(async () => {
  await nextTick()
  render()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  chart?.dispose()
  chart = null
})

watch(() => props.option, render, { deep: true })
</script>

<style scoped>
.chart-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chart-panel__body {
  width: 100%;
  flex: 1;
  min-height: 0;
}
</style>

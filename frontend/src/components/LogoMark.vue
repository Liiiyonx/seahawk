<template>
  <svg
    class="logo-mark"
    viewBox="0 0 36 36"
    :width="size"
    :height="size"
    aria-hidden="true"
  >
    <defs>
      <linearGradient id="seasight-logo-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#18e0c8" />
        <stop offset="1" stop-color="#4a9eff" />
      </linearGradient>
    </defs>
    <!-- 眼睛轮廓（灵眸） -->
    <path
      d="M5 18 Q18 4.5 31 18 Q18 31.5 5 18 Z"
      fill="none"
      stroke="url(#seasight-logo-grad)"
      stroke-width="2.1"
      stroke-linecap="round"
    />
    <!-- 虹膜 -->
    <circle cx="18" cy="18" r="7" fill="url(#seasight-logo-grad)" />
    <!-- 瞳孔 -->
    <circle cx="18" cy="18" r="2.9" fill="#06121c" />
    <!-- 高光 -->
    <circle cx="15.2" cy="15.2" r="1.6" fill="#ffffff" opacity="0.9" />
    <!-- 底部波浪（探海） -->
    <path
      d="M8 27.5 q2.8 -2.4 5.5 0 t5.5 0 t5.5 0"
      fill="none"
      stroke="url(#seasight-logo-grad)"
      stroke-width="1.7"
      stroke-linecap="round"
    />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: Number, default: 30 },
})
</script>

<style scoped>
.logo-mark {
  display: block;
  filter: drop-shadow(0 0 8px rgba(24, 224, 200, 0.45));
}
</style>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite" aria-label="通知">
      <TransitionGroup name="toast">
        <div
          v-for="t in toastList"
          :key="t.id"
          class="toast"
          :class="[`toast--${t.type}`, { 'toast--hidden': !t.visible }]"
          role="alert"
        >
          <!-- 图标 -->
          <span class="toast__icon" aria-hidden="true">
            <template v-if="t.type === 'success'">✓</template>
            <template v-else-if="t.type === 'error'">✕</template>
            <template v-else-if="t.type === 'warning'">⚠</template>
            <template v-else-if="t.type === 'loading'">
              <span class="toast__spinner"></span>
            </template>
            <template v-else>ℹ</template>
          </span>
          
          <!-- 内容 -->
          <div class="toast__body">
            <div class="toast__message">{{ t.message }}</div>
            
            <!-- 操作按钮 -->
            <div v-if="t.actions?.length" class="toast__actions">
              <button
                v-for="(action, i) in t.actions"
                :key="i"
                class="toast__action"
                @click="handleAction(t, action)"
              >
                {{ action.label }}
              </button>
            </div>
          </div>
          
          <!-- 关闭按钮 -->
          <button
            v-if="t.type !== 'loading'"
            class="toast__close"
            aria-label="关闭通知"
            @click="removeToast(t.id)"
          >
            ×
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { toastList, removeToast } from '@/utils/toast'

function handleAction(toast, action) {
  action.onClick?.()
  removeToast(toast.id)
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 80px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
  max-width: min(400px, calc(100vw - 40px));
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--bg-panel, #1a1f2e);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(16px);
  pointer-events: auto;
  min-width: 280px;
  max-width: 100%;
  transition: all 0.3s ease;
}

.toast--hidden {
  opacity: 0;
  transform: translateX(100%);
}

.toast--success {
  border-left: 3px solid var(--c-success, #34c759);
}

.toast--error {
  border-left: 3px solid var(--c-danger, #ff3b30);
}

.toast--warning {
  border-left: 3px solid var(--c-warn, #ff9500);
}

.toast--info {
  border-left: 3px solid var(--c-primary, #007aff);
}

.toast--loading {
  border-left: 3px solid var(--c-primary, #007aff);
}

.toast__icon {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

.toast--success .toast__icon { color: var(--c-success, #34c759); }
.toast--error .toast__icon { color: var(--c-danger, #ff3b30); }
.toast--warning .toast__icon { color: var(--c-warn, #ff9500); }
.toast--info .toast__icon { color: var(--c-primary, #007aff); }
.toast--loading .toast__icon { color: var(--c-primary, #007aff); }

.toast__spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: toast-spin 0.8s linear infinite;
}

@keyframes toast-spin {
  to { transform: rotate(360deg); }
}

.toast__body {
  flex: 1;
  min-width: 0;
}

.toast__message {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-main, #fff);
  word-break: break-word;
}

.toast__actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.toast__action {
  padding: 5px 12px;
  border: 1px solid var(--c-primary, #007aff);
  border-radius: 6px;
  background: transparent;
  color: var(--c-primary, #007aff);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.toast__action:hover {
  background: var(--c-primary, #007aff);
  color: #fff;
}

.toast__close {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-dim, #8e8e93);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.toast__close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-main, #fff);
}

/* 动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.toast-move {
  transition: transform 0.3s ease;
}

/* 移动端适配 */
@media (max-width: 640px) {
  .toast-container {
    top: auto;
    bottom: 100px;
    right: 16px;
    left: 16px;
    max-width: none;
  }
  
  .toast {
    min-width: 0;
    width: 100%;
  }
}
</style>

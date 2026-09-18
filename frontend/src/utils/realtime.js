/**
 * WebSocket 实时推送。
 *
 * 要点：
 * 1. 指数退避重连 —— 后端重启时不要疯狂重试打满连接
 * 2. 心跳保活 —— 中间有 nginx/代理时闲置连接会被静默切断
 * 3. 断线期间的状态可见 —— 大屏必须让人知道"数据不动了是因为断线"
 */
import { ref, onUnmounted } from 'vue'

export function useRealtime(handlers = {}) {
  const connected = ref(false)
  const lastMessageAt = ref(null)
  const retries = ref(0)

  let ws = null
  let heartbeatTimer = null
  let reconnectTimer = null
  let closedByUser = false

  const MAX_RETRY_DELAY = 30000

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}/api/v1/ws/alerts`
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    try {
      ws = new WebSocket(wsUrl())
    } catch (err) {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      connected.value = true
      retries.value = 0
      startHeartbeat()
      handlers.onOpen?.()
    }

    ws.onmessage = (event) => {
      lastMessageAt.value = Date.now()
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        return
      }
      // 心跳响应不入业务
      if (msg.type === 'pong') return
      handlers.onMessage?.(msg)
    }

    ws.onclose = () => {
      connected.value = false
      stopHeartbeat()
      if (!closedByUser) scheduleReconnect()
    }

    ws.onerror = () => {
      // onerror 后一定跟 onclose，重连逻辑统一放 onclose
      handlers.onError?.()
    }
  }

  function startHeartbeat() {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping', ts: Date.now() }))
      }
    }, 25000)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    retries.value += 1
    // 指数退避：1s → 2s → 4s → ... → 30s 封顶
    const delay = Math.min(1000 * 2 ** (retries.value - 1), MAX_RETRY_DELAY)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function close() {
    closedByUser = true
    stopHeartbeat()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws?.close()
    ws = null
    connected.value = false
  }

  onUnmounted(close)

  return { connected, lastMessageAt, retries, connect, close }
}

/**
 * ArmSimConsole 独立挂载入口 —— **仅供软著说明书截图用，不进产物**。
 *
 * 为什么单独挂一个入口：这份截图要的是机械臂控制台**组件本身**的样子。
 * 走真实页面（/simulation）得先起后端 + Postgres + Redis + EMQX 整套，
 * 而控制台显示的内容全部来自 props，与后端无关。独立挂载既省掉整套依赖，
 * 又不会因为后端空数据把面板渲染成空态。
 *
 * 数据取自仓库真实配置，不是杜撰：
 *   edge/arm_bridge/config.yaml → device_id RBT-ARM-01、servo_ids [1,2,3,4]、
 *     home_positions [[1,500],[2,500]]、pick_sequence [[1,650],[2,500]] → [[1,300],[2,600]]
 *   frontend/.env.local → VITE_ARM_CONSOLE_URL=nx://192.168.149.1（真机跳转地址）
 * 舵机遥测行的字段名（vin/temp/position）对齐 ArmSimConsole 的 servoRows 计算，
 * 口径对齐 edge/arm_bridge/drivers.py 里厂商 SDK 的回读约定：
 *   vin 单位 mV、position 是 0..1000 脉宽量程（不是角度）。
 */
import { createApp, h, ref } from 'vue'
import ArmSimConsole from '@/components/ArmSimConsole.vue'

createApp({
  setup() {
    // 抓取行程中段：大臂已下探、夹爪收拢，是「正在打捞」的一帧。
    const servos = ref({
      1: { vin: 11840, temp: 43, position: 468 },
      2: { vin: 11790, temp: 41, position: 552 },
      3: { vin: 11860, temp: 39, position: 612 },
      4: { vin: 11710, temp: 37, position: 285 },
    })

    return () =>
      h(ArmSimConsole, {
        taskId: 'T-20261012-004',
        target: '119.6540, 26.3870',
        servos: servos.value,
      })
  },
}).mount('#app')

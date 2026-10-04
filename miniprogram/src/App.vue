<script>
/**
 * 小程序端定位：Web 大屏管「看」，小程序管「干」——
 * 现场作业人员接单/推进状态、管理者收告警。不做大屏、不做仿真。
 *
 * 登录态策略：与 Web 端共用后端 /auth/login（JWT），token 存小程序 storage。
 * 未登录时所有业务页 onShow 跳 /pages/login/login。
 */
export default {
  onLaunch() {
    // 占位：后续按需初始化
  },
}
</script>

<style>
/**
 * 设计 tokens 与 Web 端 frontend/src/assets/main.css 同源（轻量 iOS 风格）。
 * 小程序无 html 根，CSS 变量挂在 page 上。
 */
page {
  --c-primary: #007aff;
  --c-primary-dim: #0066d6;
  --c-danger: #ff3b30;
  --c-warn: #ff9500;
  --c-success: #34c759;
  --c-assigned: #5856d6;

  --bg-page: #f2f2f7;
  --bg-panel: #ffffff;
  --bg-panel-2: #f7f7fa;
  --bg-hover: rgba(0, 0, 0, 0.045);
  --bg-active: rgba(0, 122, 255, 0.1);

  --text-main: #1c1c1e;
  --text-sub: #636366;
  --text-dim: #8e8e93;

  --border: rgba(60, 60, 67, 0.16);
  --separator: rgba(60, 60, 67, 0.12);
  --panel-border: rgba(60, 60, 67, 0.12);

  --radius: 10px;
  --radius-lg: 14px;

  background: var(--bg-page);
  color: var(--text-main);
  font-size: 28rpx;
  line-height: 1.5;
}

/* ---------- 通用卡片 / 分组（iOS 列表风） ---------- */
.card {
  background: var(--bg-panel);
  border-radius: var(--radius-lg);
  padding: 24rpx 28rpx;
  margin: 0 24rpx 20rpx;
}

.card-title {
  font-size: 30rpx;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 16rpx;
}

/* ---------- 状态徽标 ---------- */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2rpx 18rpx;
  border-radius: 999rpx;
  font-size: 22rpx;
  font-weight: 500;
  line-height: 36rpx;
  white-space: nowrap;
}
.badge-online,
.badge-done { background: rgba(52, 199, 89, 0.14); color: var(--c-success); }
.badge-offline,
.badge-pending,
.badge-cancelled { background: rgba(142, 142, 147, 0.14); color: var(--text-sub); }
.badge-new { background: rgba(255, 149, 0, 0.14); color: var(--c-warn); }
.badge-dispatched,
.badge-navigating,
.badge-collecting { background: rgba(0, 122, 255, 0.13); color: var(--c-primary); }
.badge-assigned { background: rgba(88, 86, 214, 0.13); color: var(--c-assigned); }

/* ---------- 按钮 ---------- */
.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 84rpx;
  padding: 16rpx 28rpx;
  border-radius: 20rpx;
  background: var(--bg-panel-2);
  color: var(--text-main);
  font-size: 28rpx;
  font-weight: 500;
  border: none;
  line-height: 1.2;
}
.btn::after {
  border: none;
}
.btn-primary {
  background: var(--c-primary);
  color: #ffffff;
}
.btn-danger {
  background: rgba(255, 59, 48, 0.12);
  color: var(--c-danger);
}
.btn-disabled {
  opacity: 0.42;
}

/* ---------- 表单 ---------- */
.form-input {
  width: 100%;
  min-height: 92rpx;
  padding: 20rpx 24rpx;
  border: 1px solid var(--border);
  border-radius: 20rpx;
  background: var(--bg-panel);
  color: var(--text-main);
  font-size: 32rpx;
  box-sizing: border-box;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200rpx;
  color: var(--text-dim);
  font-size: 26rpx;
}
</style>

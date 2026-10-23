-- ============================================================
-- 演示数据刷新脚本（幂等，可重复执行）
-- ============================================================
-- 用途：演前/demo 前一键把库刷成「每个页面都有数据、每个闭环可走通」的状态。
--
-- 覆盖内容：
--   1. 设备在线状态与心跳（摄像头/无人机/机器人的电量与仓容）
--   2. 当天事件：代办/已派单/已清理/已忽略 全状态 + 六乡镇分布
--   3. 工单：待派单/已派单/前往中/作业中/已完成/已取消 全状态
--   4. 作业中工单的 t_track 轨迹（供执行仿真页回放）
--   5. 历史工单的 ACK 审计账本（供仿真页“运行日志”页签）
--   6. 演示锚点事件 evt_demo_0015（A 镜头固定事件）时间刷新为“刚刚”
--
-- 执行（容器内路径已挂载 /sql）：
--   docker compose exec -T postgres psql -U seasight -d seasight -f /sql/refresh_demo_data.sql
-- 本机原生 PostgreSQL：
--   psql -U seasight -d seasight -f deploy/postgres/refresh_demo_data.sql
--
-- ★ 时间戳全部相对 now()，任何时刻执行数据都是“新鲜的”。
-- ★ 只清理本脚本自己写入的固定 ID（evt_demo_002x/003x、tsk_demo_10xx），
--   不触碰历史数据与其它演示脚本的数据。
-- ============================================================

BEGIN;

-- ---------- 0. 设备状态刷新 ----------
-- 摄像头与无人机上线（大屏视频位、设备页需要 online 状态）
UPDATE t_device
SET status = 'online', last_heartbeat = now()
WHERE device_id IN (
    'CAM-MABI-01', 'CAM-HUANGQI-01', 'CAM-XIAOCHENG-01',
    'CAM-TAILU-01', 'CAM-ANKAI-01', 'CAM-XIAGONG-01', 'UAV-001'
);

-- 机器人：统一命名「探海X号」。
-- 船体在**水域**（3D 沙盘按真实海岸线判定水/陆，摆到镇上会"开上岸"）：
--   探海一/二号在各镇近岸海域（离岸 400~900m，地形水线有约半格柔化精度）；
--   探海三号驻**安凯渔排区（养殖区）**——该点位于罗源湾内湾水面，是养殖区主场景。
UPDATE t_device
SET name = '探海一号', status = 'online', last_heartbeat = now(),
    location = ST_SetSRID(ST_MakePoint(119.6391, 26.4129), 4326),   -- 马鼻镇外海水域（离岸约 420m）
    meta = '{"hull":"双体","chassis":"boat","battery":86,"bins":{"foam":0.05,"plastic":0.03,"mixed":0.02}}'::jsonb
WHERE device_id = 'RBT-001';

UPDATE t_device
SET name = '探海二号', status = 'online', last_heartbeat = now(),
    location = ST_SetSRID(ST_MakePoint(119.9067, 26.3058), 4326),   -- 黄岐镇南侧海域（离岸约 410m）
    meta = '{"hull":"双体","chassis":"boat","battery":78,"bins":{"foam":0.06,"plastic":0.04,"mixed":0.02}}'::jsonb
WHERE device_id = 'RBT-002';

UPDATE t_device
SET name = '探海三号', status = 'online', last_heartbeat = now(),
    location = ST_SetSRID(ST_MakePoint(119.7605, 26.4198), 4326),   -- 安凯渔排区（养殖区）内湾水面
    meta = '{"hull":"双体","chassis":"boat","battery":88,"bins":{"foam":0.04,"plastic":0.02,"mixed":0.01}}'::jsonb
WHERE device_id = 'RBT-003';

-- 履带式滩涂清除车（chassis=tracked）：坐标沿用生产库的滩涂点位（岸线内侧 0~100m）
-- bins 的键统一为平台契约的 mixed（原生库里曾写成 fishing，三仓面板会少显示一格）
INSERT INTO t_device (device_id, device_type, name, location, status, last_heartbeat, meta) VALUES
('RBT-004', 'robot', '探海四号', ST_SetSRID(ST_MakePoint(119.677264, 26.263910), 4326), 'online', now(),
 '{"chassis":"tracked","battery":85,"bins":{"foam":0.20,"plastic":0.30,"mixed":0.10}}'),
('RBT-005', 'robot', '探海五号', ST_SetSRID(ST_MakePoint(119.531399, 26.422147), 4326), 'online', now(),
 '{"chassis":"tracked","battery":88,"bins":{"foam":0.20,"plastic":0.30,"mixed":0.10}}'),
('RBT-006', 'robot', '探海六号', ST_SetSRID(ST_MakePoint(119.875410, 26.366790), 4326), 'online', now(),
 '{"chassis":"tracked","battery":92,"bins":{"foam":0.20,"plastic":0.30,"mixed":0.10}}')
ON CONFLICT (device_id) DO UPDATE
SET device_type = EXCLUDED.device_type,
    name = EXCLUDED.name,
    location = EXCLUDED.location,
    status = EXCLUDED.status,
    last_heartbeat = EXCLUDED.last_heartbeat,
    meta = EXCLUDED.meta;

-- ---------- 1. 清理本脚本上一轮写入的演示数据（幂等） ----------
DELETE FROM t_task_ack WHERE task_id LIKE 'tsk_demo_10%';
DELETE FROM t_track    WHERE task_id LIKE 'tsk_demo_10%';
DELETE FROM t_task     WHERE task_id LIKE 'tsk_demo_10%';
DELETE FROM t_event    WHERE event_id LIKE 'evt_demo_002%' OR event_id LIKE 'evt_demo_003%';

-- 槽位让位：下方事件 INSERT 占用的 (device_id, seq) 槽位是固定的。
-- 本机库中存在历史批次演示数据（demo26_hist_*，另一来源的回填脚本），
-- 其 seq 段与本节槽位重叠（实测 CAM-MABI-01 的 2101~2104 已被占用），
-- 不做处理会因唯一约束 uq_event_device_seq 让整个刷新事务回滚。
-- 只删「非本脚本（evt_demo_*）」且恰占目标槽位的行，其余历史数据一概不动。
DELETE FROM t_event
 WHERE event_id NOT LIKE 'evt_demo_%'
   AND (device_id, seq) IN (
     ('CAM-MABI-01',2101),('CAM-MABI-01',2102),('CAM-MABI-01',2103),('CAM-MABI-01',2104),
     ('CAM-HUANGQI-01',2201),('CAM-HUANGQI-01',2202),('CAM-HUANGQI-01',2203),('CAM-HUANGQI-01',2204),
     ('CAM-XIAOCHENG-01',2301),('CAM-XIAOCHENG-01',2302),('CAM-XIAOCHENG-01',2303),
     ('CAM-TAILU-01',2401),('CAM-TAILU-01',2402),
     ('CAM-ANKAI-01',2501),('CAM-ANKAI-01',2502),
     ('UAV-001',2701)
   );

-- ---------- 2. 当天事件（六乡镇 × 四类别 × 四状态） ----------
-- 状态语义：new=待处理 / dispatched=已派单 / resolved=已清理 / ignored=已忽略
INSERT INTO t_event (event_id, device_id, event_time, location, main_class, det_count,
                     max_confidence, model_version, seq, status, township) VALUES
-- ---- 待处理（new）：可被补派/审批建单/人工忽略 ----
('evt_demo_0021', 'CAM-MABI-01',      now() - interval '25 minutes', ST_SetSRID(ST_MakePoint(119.6532, 26.3868), 4326), 'foam',         5, 0.9100, 'det_v0.1.0', 2101, 'new', '马鼻镇'),
('evt_demo_0022', 'CAM-HUANGQI-01',   now() - interval '2 hours',    ST_SetSRID(ST_MakePoint(119.9050, 26.3165), 4326), 'foam',         4, 0.8800, 'det_v0.1.0', 2201, 'new', '黄岐镇'),
('evt_demo_0023', 'CAM-XIAOCHENG-01', now() - interval '3 hours',    ST_SetSRID(ST_MakePoint(119.8365, 26.3520), 4326), 'fishing_gear', 2, 0.8100, 'det_v0.1.0', 2301, 'new', '筱埕镇'),
('evt_demo_0024', 'CAM-TAILU-01',     now() - interval '4 hours',    ST_SetSRID(ST_MakePoint(120.0100, 26.2935), 4326), 'plastic',      3, 0.7600, 'det_v0.1.0', 2401, 'new', '苔菉镇'),
('evt_demo_0025', 'CAM-ANKAI-01',     now() - interval '5 hours',    ST_SetSRID(ST_MakePoint(119.7600, 26.4200), 4326), 'other',        1, 0.6800, 'det_v0.1.0', 2501, 'new', '安凯镇'),
('evt_demo_0026', 'UAV-001',          now() - interval '6 hours',    ST_SetSRID(ST_MakePoint(119.8700, 26.3600), 4326), 'foam',         8, 0.8900, 'det_v0.1.0', 2701, 'new', '下宫镇'),
-- ---- 已派单（dispatched）：分别对应 已派单/前往中/作业中 三张工单 ----
('evt_demo_0027', 'CAM-MABI-01',      now() - interval '35 minutes', ST_SetSRID(ST_MakePoint(119.6535, 26.3871), 4326), 'foam',         6, 0.9200, 'det_v0.1.0', 2102, 'dispatched', '马鼻镇'),
('evt_demo_0028', 'CAM-HUANGQI-01',   now() - interval '150 minutes', ST_SetSRID(ST_MakePoint(119.9053, 26.3160), 4326), 'fishing_gear', 3, 0.8400, 'det_v0.1.0', 2202, 'dispatched', '黄岐镇'),
('evt_demo_0029', 'CAM-XIAOCHENG-01', now() - interval '210 minutes', ST_SetSRID(ST_MakePoint(119.8368, 26.3518), 4326), 'foam',        4, 0.8700, 'det_v0.1.0', 2302, 'dispatched', '筱埕镇'),
-- ---- 已清理（resolved）：对应已完成工单（含打捞量，供报表聚合） ----
('evt_demo_0030', 'CAM-MABI-01',      now() - interval '8 hours',    ST_SetSRID(ST_MakePoint(119.6528, 26.3872), 4326), 'foam',         7, 0.9300, 'det_v0.1.0', 2103, 'resolved', '马鼻镇'),
('evt_demo_0031', 'CAM-HUANGQI-01',   now() - interval '10 hours',   ST_SetSRID(ST_MakePoint(119.9048, 26.3168), 4326), 'foam',         5, 0.8900, 'det_v0.1.0', 2203, 'resolved', '黄岐镇'),
('evt_demo_0032', 'CAM-XIAOCHENG-01', now() - interval '12 hours',   ST_SetSRID(ST_MakePoint(119.8362, 26.3522), 4326), 'fishing_gear', 4, 0.8500, 'det_v0.1.0', 2303, 'resolved', '筱埕镇'),
-- ---- 已忽略（ignored）：人工确认误报 ----
('evt_demo_0033', 'CAM-ANKAI-01',     now() - interval '7 hours',    ST_SetSRID(ST_MakePoint(119.7603, 26.4197), 4326), 'other',        1, 0.6100, 'det_v0.1.0', 2502, 'ignored', '安凯镇'),
-- ---- 昨日（10-09）：供趋势图与日报表连续两天 ----
('evt_demo_0034', 'CAM-MABI-01',      now() - interval '30 hours',   ST_SetSRID(ST_MakePoint(119.6530, 26.3866), 4326), 'foam',         6, 0.9000, 'det_v0.1.0', 2104, 'resolved', '马鼻镇'),
('evt_demo_0035', 'CAM-HUANGQI-01',   now() - interval '28 hours',   ST_SetSRID(ST_MakePoint(119.9051, 26.3162), 4326), 'plastic',      3, 0.7800, 'det_v0.1.0', 2204, 'resolved', '黄岐镇'),
('evt_demo_0036', 'CAM-TAILU-01',     now() - interval '27 hours',   ST_SetSRID(ST_MakePoint(120.0102, 26.2933), 4326), 'other',        2, 0.6600, 'det_v0.1.0', 2402, 'ignored', '苔菉镇');

-- ---------- 3. 工单（全状态覆盖） ----------
-- 时间戳链完整：created → assigned → ack → started → finished
INSERT INTO t_task (task_id, event_id, robot_id, target_location, status, priority, township,
                    created_at, assigned_at, ack_at, started_at, finished_at,
                    collected_weight, review_result, remark) VALUES
-- 待派单（人工建单，无事件无机器人）→ 「触发补派」按钮的演示对象
('tsk_demo_1000', NULL, NULL, ST_SetSRID(ST_MakePoint(119.6535, 26.3872), 4326), 'pending', 3, '马鼻镇',
 now() - interval '45 minutes', NULL, NULL, NULL, NULL, NULL, 'pending', '人工建单：巡湾发现零星泡沫，等待补派'),
-- 已派单（等机器人 ACK）→ 「执行仿真」页可启动完整作业闭环
('tsk_demo_1001', 'evt_demo_0027', 'RBT-001', ST_SetSRID(ST_MakePoint(119.6535, 26.3871), 4326), 'assigned', 1, '马鼻镇',
 now() - interval '35 minutes', now() - interval '30 minutes', NULL, NULL, NULL, NULL, 'pending', NULL),
-- 前往中（机器人已 ACK）
('tsk_demo_1002', 'evt_demo_0028', 'RBT-002', ST_SetSRID(ST_MakePoint(119.9053, 26.3160), 4326), 'navigating', 1, '黄岐镇',
 now() - interval '150 minutes', now() - interval '145 minutes', now() - interval '148 minutes', NULL, NULL, NULL, 'pending', NULL),
-- 作业中（有轨迹，供仿真页“历史回放/运行日志”）
('tsk_demo_1003', 'evt_demo_0029', 'RBT-002', ST_SetSRID(ST_MakePoint(119.8368, 26.3518), 4326), 'collecting', 1, '筱埕镇',
 now() - interval '210 minutes', now() - interval '205 minutes', now() - interval '208 minutes', now() - interval '200 minutes', NULL, NULL, 'pending', NULL),
-- 已完成（今日 3 单，打捞量供报表聚合）
('tsk_demo_1004', 'evt_demo_0030', 'RBT-001', ST_SetSRID(ST_MakePoint(119.6528, 26.3872), 4326), 'done', 1, '马鼻镇',
 now() - interval '8 hours', now() - interval '7 hours 50 minutes', now() - interval '7 hours 48 minutes', now() - interval '7 hours 45 minutes', now() - interval '7 hours', 12.500, 'confirmed', NULL),
('tsk_demo_1005', 'evt_demo_0031', 'RBT-002', ST_SetSRID(ST_MakePoint(119.9048, 26.3168), 4326), 'done', 1, '黄岐镇',
 now() - interval '10 hours', now() - interval '9 hours 50 minutes', now() - interval '9 hours 48 minutes', now() - interval '9 hours 45 minutes', now() - interval '9 hours', 8.250, 'confirmed', NULL),
('tsk_demo_1006', 'evt_demo_0032', 'RBT-001', ST_SetSRID(ST_MakePoint(119.8362, 26.3522), 4326), 'done', 1, '筱埕镇',
 now() - interval '12 hours', now() - interval '11 hours 50 minutes', now() - interval '11 hours 48 minutes', now() - interval '11 hours 45 minutes', now() - interval '11 hours', 15.800, 'confirmed', NULL),
-- 已完成（昨日 2 单，供日报表连续两天）
('tsk_demo_1007', 'evt_demo_0034', 'RBT-001', ST_SetSRID(ST_MakePoint(119.6530, 26.3866), 4326), 'done', 1, '马鼻镇',
 now() - interval '30 hours', now() - interval '29 hours 50 minutes', now() - interval '29 hours 48 minutes', now() - interval '29 hours 45 minutes', now() - interval '29 hours', 9.600, 'confirmed', NULL),
('tsk_demo_1008', 'evt_demo_0035', 'RBT-002', ST_SetSRID(ST_MakePoint(119.9051, 26.3162), 4326), 'done', 3, '黄岐镇',
 now() - interval '28 hours', now() - interval '27 hours 50 minutes', now() - interval '27 hours 48 minutes', now() - interval '27 hours 45 minutes', now() - interval '27 hours', 6.400, 'confirmed', NULL),
-- 已取消（展示取消态与备注）
('tsk_demo_1009', NULL, NULL, ST_SetSRID(ST_MakePoint(120.0100, 26.2930), 4326), 'cancelled', 3, '苔菉镇',
 now() - interval '5 hours', NULL, NULL, NULL, NULL, NULL, 'pending', '人工取消：与相邻工单区域重叠，合并处理');

-- ---------- 4. 作业中工单的轨迹（供执行仿真页回放） ----------
-- RBT-002 从黄岐驻点驶向筱埕目标点，50 个点、电量缓降、对应仓容增长
INSERT INTO t_track (robot_id, task_id, location, battery, bin_foam, bin_plastic, bin_mixed,
                     speed, recorded_at)
SELECT
    'RBT-002',
    'tsk_demo_1003',
    ST_SetSRID(ST_MakePoint(
        119.9050 + (119.8368 - 119.9050) * i / 49.0,
        26.3165 + (26.3518 - 26.3165) * i / 49.0
    ), 4326),
    (74 - (i / 8))::smallint,
    (0.060 + 0.0012 * i)::numeric(4,3),
    (0.040 + 0.0004 * i)::numeric(4,3),
    (0.020 + 0.0006 * i)::numeric(4,3),
    1.20,
    now() - interval '190 minutes' + (i * interval '3.4 minutes')
FROM generate_series(0, 49) AS i;

-- ---------- 5. 历史工单的 ACK 审计账本（供仿真页“运行日志”与工单 ACK 查询） ----------
INSERT INTO t_task_ack (command_id, task_id, device_id, seq, outcome, accepted, reason, mode,
                        received_at, received_wall_at, raw_payload)
VALUES
('cmd_tsk_demo_1002', 'tsk_demo_1002', 'RBT-002', 11, 'new', true, '', 'auto',
 now() - interval '148 minutes', now() - interval '148 minutes',
 '{"command_id":"cmd_tsk_demo_1002","device_id":"RBT-002","accepted":true,"mode":"auto"}'::jsonb),
('cmd_tsk_demo_1003', 'tsk_demo_1003', 'RBT-002', 12, 'new', true, '', 'auto',
 now() - interval '208 minutes', now() - interval '208 minutes',
 '{"command_id":"cmd_tsk_demo_1003","device_id":"RBT-002","accepted":true,"mode":"auto"}'::jsonb),
('cmd_tsk_demo_1004', 'tsk_demo_1004', 'RBT-001', 21, 'new', true, '', 'auto',
 now() - interval '7 hours 48 minutes', now() - interval '7 hours 48 minutes',
 '{"command_id":"cmd_tsk_demo_1004","device_id":"RBT-001","accepted":true,"mode":"auto"}'::jsonb),
('cmd_tsk_demo_1005', 'tsk_demo_1005', 'RBT-002', 22, 'new', true, '', 'auto',
 now() - interval '9 hours 48 minutes', now() - interval '9 hours 48 minutes',
 '{"command_id":"cmd_tsk_demo_1005","device_id":"RBT-002","accepted":true,"mode":"auto"}'::jsonb),
('cmd_tsk_demo_1006', 'tsk_demo_1006', 'RBT-001', 23, 'new', true, '', 'auto',
 now() - interval '11 hours 48 minutes', now() - interval '11 hours 48 minutes',
 '{"command_id":"cmd_tsk_demo_1006","device_id":"RBT-001","accepted":true,"mode":"auto"}'::jsonb),
('cmd_tsk_demo_1007', 'tsk_demo_1007', 'RBT-001', 24, 'new', true, '', 'auto',
 now() - interval '29 hours 48 minutes', now() - interval '29 hours 48 minutes',
 '{"command_id":"cmd_tsk_demo_1007","device_id":"RBT-001","accepted":true,"mode":"auto"}'::jsonb),
('cmd_tsk_demo_1008', 'tsk_demo_1008', 'RBT-002', 25, 'new', true, '', 'auto',
 now() - interval '27 hours 48 minutes', now() - interval '27 hours 48 minutes',
 '{"command_id":"cmd_tsk_demo_1008","device_id":"RBT-002","accepted":true,"mode":"auto"}'::jsonb);

-- ---------- 6. 机器人当前任务指针（看板/派单展示一致性） ----------
-- ★ 口径与后端 /robots 一致：取该机器人**最新创建**的活跃工单。
--   两边口径不同会让同一台船在「设备页」和「机器人接口」显示两个不同任务号。
UPDATE t_device d
SET meta = d.meta || jsonb_build_object('current_task_id', sub.task_id)
FROM (
    SELECT DISTINCT ON (robot_id) robot_id, task_id
    FROM t_task
    WHERE status IN ('pending', 'assigned', 'navigating', 'collecting')
      AND robot_id IS NOT NULL
    ORDER BY robot_id, created_at DESC, id DESC
) sub
WHERE d.device_id = sub.robot_id;

-- ---------- 7. 演示锚点事件刷新 ----------
-- evt_demo_0015 是 A 镜头固定事件（避免 6007 冲突的历史结论），
-- 把它刷成“刚刚发生、待处理”，保证任何时间点演示都在 24h 窗口内可见。
UPDATE t_event
SET event_time = now() - interval '40 minutes',
    status = 'new'
WHERE event_id = 'evt_demo_0015';

-- ---------- 8. 校验输出 ----------
DO $$
DECLARE
    evt_today INT; evt_new INT; tsk_active INT; tsk_done INT; trk_cnt INT; ack_cnt INT;
BEGIN
    SELECT COUNT(*) INTO evt_today FROM t_event WHERE event_time >= date_trunc('day', now());
    SELECT COUNT(*) INTO evt_new FROM t_event WHERE status = 'new' AND event_time >= now() - interval '24 hours';
    SELECT COUNT(*) INTO tsk_active FROM t_task WHERE status IN ('pending','assigned','navigating','collecting') AND task_id LIKE 'tsk_demo_10%';
    SELECT COUNT(*) INTO tsk_done FROM t_task WHERE status = 'done' AND task_id LIKE 'tsk_demo_10%';
    SELECT COUNT(*) INTO trk_cnt FROM t_track WHERE task_id = 'tsk_demo_1003';
    SELECT COUNT(*) INTO ack_cnt FROM t_task_ack WHERE task_id LIKE 'tsk_demo_10%';
    RAISE NOTICE '[demo-seed] 今日事件 % 条 | 24h 待处理 % 条 | 演示活跃工单 % 条 | 演示已完成 % 条 | 轨迹 % 点 | ACK % 条',
        evt_today, evt_new, tsk_active, tsk_done, trk_cnt, ack_cnt;
END $$;

COMMIT;
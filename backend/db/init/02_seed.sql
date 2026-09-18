-- ============================================================
-- 探海灵眸 SeaSight — 种子数据
-- 坐标取自连江县真实沿海乡镇位置（用于演示贴近实际）
-- ============================================================
-- 连江沿海乡镇参考经纬度：
--   马鼻镇   ~ (119.652, 26.386)
--   黄岐镇   ~ (119.904, 26.316)
--   筱埕镇   ~ (119.836, 26.352)
--   苔菉镇   ~ (120.010, 26.293)
--   安凯镇   ~ (119.760, 26.420)
--   下宫镇   ~ (119.887, 26.374)
-- ============================================================

-- ---------- 清理旧数据（幂等重跑用） ----------
TRUNCATE TABLE t_track CASCADE;
TRUNCATE TABLE t_task CASCADE;
TRUNCATE TABLE t_event CASCADE;
TRUNCATE TABLE t_device CASCADE;
TRUNCATE TABLE t_report_daily CASCADE;
TRUNCATE TABLE t_user CASCADE;

-- ---------- 用户（密码明文见下方注释，首次登录后请立即修改） ----------
-- admin    / admin123456
-- operator / operator123456
-- viewer   / viewer123456
INSERT INTO t_user (username, hashed_password, full_name, role, township_scope) VALUES
('admin',    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqUoJqxHGm', '系统管理员', 'admin',    NULL),
('operator', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '乡镇操作员', 'operator', '马鼻镇'),
('viewer',   '$2b$12$Vc6V8u7BqC5rP7p3mLjXtuzWZJvBXKZQNHV6ZgT8vJqRZ8YQxZqIu', '访客账号',   'viewer',   NULL)
ON CONFLICT (username) DO NOTHING;

-- ---------- 设备 ----------
-- 岸基摄像头（6 个连江沿海点位）
INSERT INTO t_device (device_id, device_type, name, location, status, last_heartbeat, stream_url, meta) VALUES
('CAM-MABI-01',  'shore_camera', '马鼻码头摄像头',   ST_SetSRID(ST_MakePoint(119.6521, 26.3864), 4326), 'online', now(), 'http://localhost:1984/api/stream.mp4?src=cam01', '{"model":"HK-DS2CD","resolution":"1920x1080"}'),
('CAM-HUANGQI-01','shore_camera','黄岐渔港摄像头',   ST_SetSRID(ST_MakePoint(119.9042, 26.3158), 4326), 'online', now(), 'http://localhost:1984/api/stream.mp4?src=cam02', '{"model":"HK-DS2CD","resolution":"1920x1080"}'),
('CAM-XIAOCHENG-01','shore_camera','筱埕养殖区摄像头',ST_SetSRID(ST_MakePoint(119.8362, 26.3517), 4326), 'online', now(), 'http://localhost:1984/api/stream.mp4?src=cam03', '{"model":"DH-IPC","resolution":"2560x1440"}'),
('CAM-TAILU-01', 'shore_camera', '苔菉航道摄像头',   ST_SetSRID(ST_MakePoint(120.0098, 26.2931), 4326), 'online', now(), NULL, '{"model":"DH-IPC","resolution":"1920x1080"}'),
('CAM-ANKAI-01', 'shore_camera', '安凯渔排区摄像头', ST_SetSRID(ST_MakePoint(119.7605, 26.4198), 4326), 'online', now(), NULL, '{"model":"HK-DS2CD","resolution":"1920x1080"}'),
('CAM-XIAGONG-01','shore_camera','下宫回收点摄像头', ST_SetSRID(ST_MakePoint(119.8871, 26.3742), 4326), 'online', now(), NULL, '{"model":"HK-DS2CD","resolution":"1920x1080"}')
ON CONFLICT (device_id) DO NOTHING;

-- 无人机
INSERT INTO t_device (device_id, device_type, name, location, status, last_heartbeat, meta) VALUES
('UAV-001', 'drone', '巡查无人机 01', ST_SetSRID(ST_MakePoint(119.8700, 26.3600), 4326), 'online', now(), '{"model":"DJI-M3E","endurance_min":45}')
ON CONFLICT (device_id) DO NOTHING;

-- 水面打捞机器人（3 台，含初始状态）
INSERT INTO t_device (device_id, device_type, name, location, status, last_heartbeat, meta) VALUES
('RBT-001', 'robot', '打捞机器人 01 号', ST_SetSRID(ST_MakePoint(119.6540, 26.3870), 4326), 'online', now(), '{"hull":"双体","battery":92,"bins":{"foam":0.05,"plastic":0.02,"mixed":0.01}}'),
('RBT-002', 'robot', '打捞机器人 02 号', ST_SetSRID(ST_MakePoint(119.9050, 26.3165), 4326), 'online', now(), '{"hull":"双体","battery":78,"bins":{"foam":0.35,"plastic":0.10,"mixed":0.05}}'),
('RBT-003', 'robot', '打捞机器人 03 号', ST_SetSRID(ST_MakePoint(119.8370, 26.3525), 4326), 'offline', now() - interval '2 hours', '{"hull":"双体","battery":15,"bins":{"foam":0.60,"plastic":0.40,"mixed":0.20}}')
ON CONFLICT (device_id) DO NOTHING;

-- ---------- 识别事件（模拟最近 48 小时的真实分布） ----------
-- 主要聚集在马鼻、黄岐附近（对应真实海漂垃圾高发区）
INSERT INTO t_event (event_id, device_id, event_time, location, main_class, det_count, max_confidence, evidence_url, model_version, seq, status) VALUES
-- 马鼻镇附近（泡�类为主，高优先级）
('evt_demo_0001', 'CAM-MABI-01',   now() - interval '2 hours',  ST_SetSRID(ST_MakePoint(119.6530, 26.3870), 4326), 'foam',        5, 0.91, NULL, 'det_v0.1.0', 1001, 'new'),
('evt_demo_0002', 'CAM-MABI-01',   now() - interval '3 hours',  ST_SetSRID(ST_MakePoint(119.6535, 26.3875), 4326), 'foam',        3, 0.87, NULL, 'det_v0.1.0', 1002, 'new'),
('evt_demo_0003', 'CAM-MABI-01',   now() - interval '5 hours',  ST_SetSRID(ST_MakePoint(119.6525, 26.3862), 4326), 'plastic',     2, 0.79, NULL, 'det_v0.1.0', 1003, 'new'),
('evt_demo_0004', 'CAM-MABI-01',   now() - interval '8 hours',  ST_SetSRID(ST_MakePoint(119.6545, 26.3880), 4326), 'fishing_gear',4, 0.84, NULL, 'det_v0.1.0', 1004, 'new'),
('evt_demo_0005', 'CAM-MABI-01',   now() - interval '12 hours', ST_SetSRID(ST_MakePoint(119.6518, 26.3858), 4326), 'foam',        7, 0.93, NULL, 'det_v0.1.0', 1005, 'new'),
-- 黄岐镇附近
('evt_demo_0006', 'CAM-HUANGQI-01',now() - interval '4 hours',  ST_SetSRID(ST_MakePoint(119.9050, 26.3165), 4326), 'foam',        4, 0.88, NULL, 'det_v0.1.0', 2001, 'new'),
('evt_demo_0007', 'CAM-HUANGQI-01',now() - interval '7 hours',  ST_SetSRID(ST_MakePoint(119.9055, 26.3160), 4326), 'plastic',     3, 0.76, NULL, 'det_v0.1.0', 2002, 'new'),
('evt_demo_0008', 'CAM-HUANGQI-01',now() - interval '20 hours', ST_SetSRID(ST_MakePoint(119.9045, 26.3170), 4326), 'foam',        6, 0.90, NULL, 'det_v0.1.0', 2003, 'new'),
-- 筱埕镇附近
('evt_demo_0009', 'CAM-XIAOCHENG-01', now() - interval '6 hours', ST_SetSRID(ST_MakePoint(119.8365, 26.3520), 4326), 'fishing_gear',2, 0.81, NULL, 'det_v0.1.0', 3001, 'new'),
('evt_demo_0010', 'CAM-XIAOCHENG-01', now() - interval '16 hours',ST_SetSRID(ST_MakePoint(119.8360, 26.3515), 4326), 'foam',        3, 0.86, NULL, 'det_v0.1.0', 3002, 'new'),
-- 苔菉 / 安凯 / 下宫（零星）
('evt_demo_0011', 'CAM-TAILU-01',  now() - interval '9 hours',  ST_SetSRID(ST_MakePoint(120.0100, 26.2935), 4326), 'other',       1, 0.68, NULL, 'det_v0.1.0', 4001, 'new'),
('evt_demo_0012', 'CAM-ANKAI-01',  now() - interval '11 hours', ST_SetSRID(ST_MakePoint(119.7600, 26.4200), 4326), 'foam',        2, 0.83, NULL, 'det_v0.1.0', 5001, 'new'),
('evt_demo_0013', 'CAM-XIAGONG-01',now() - interval '14 hours', ST_SetSRID(ST_MakePoint(119.8875, 26.3745), 4326), 'plastic',     2, 0.74, NULL, 'det_v0.1.0', 6001, 'new'),
-- 无人机巡查发现
('evt_demo_0014', 'UAV-001',       now() - interval '10 hours', ST_SetSRID(ST_MakePoint(119.8700, 26.3600), 4326), 'foam',        8, 0.89, NULL, 'det_v0.1.0', 7001, 'new')
ON CONFLICT (event_id) DO NOTHING;

-- 模拟一个已完成的工单（让看板有历史数据）
INSERT INTO t_task (task_id, event_id, robot_id, target_location, status, priority,
                    created_at, assigned_at, ack_at, started_at, finished_at,
                    collected_weight, review_result)
VALUES
('tsk_demo_0001', 'evt_demo_0005', 'RBT-001',
 ST_SetSRID(ST_MakePoint(119.6518, 26.3858), 4326), 'done', 1,
 now() - interval '12 hours', now() - interval '11 hours 55 minutes',
 now() - interval '11 hours 54 minutes', now() - interval '11 hours 50 minutes',
 now() - interval '11 hours 30 minutes', 12.500, 'confirmed')
ON CONFLICT (task_id) DO NOTHING;

-- 事件状态同步为已处理
UPDATE t_event SET status = 'resolved' WHERE event_id = 'evt_demo_0005';

-- ---------- 作业轨迹（模拟已完成工单的轨迹） ----------
INSERT INTO t_track (robot_id, task_id, location, battery, bin_foam, bin_plastic, bin_mixed, speed, recorded_at)
SELECT
    'RBT-001',
    'tsk_demo_0001',
    ST_SetSRID(ST_MakePoint(119.6518 + (i * 0.0001), 26.3858 + (i * 0.0001)), 4326),
    92 - i,
    0.01 * i,
    0.005 * i,
    0.002 * i,
    0.8,
    now() - interval '11 hours 50 minutes' + (i || ' minutes')::interval
FROM generate_series(1, 20) AS i;

-- ---------- 统计宽表（预聚合最近 3 天） ----------
INSERT INTO t_report_daily (stat_date, township, main_class, event_count, task_count, done_count, collected_kg, coverage_area)
VALUES
(CURRENT_DATE - 2, '马鼻镇', 'foam',         12, 3, 3, 28.500, 15000.00),
(CURRENT_DATE - 2, '马鼻镇', 'plastic',       5, 1, 1,  6.200,  5000.00),
(CURRENT_DATE - 1, '马鼻镇', 'foam',          9, 2, 2, 21.000, 12000.00),
(CURRENT_DATE - 1, '黄岐镇', 'foam',          7, 2, 1, 15.500,  9000.00),
(CURRENT_DATE,     '马鼻镇', 'foam',          5, 1, 1, 12.500,  8000.00),
(CURRENT_DATE,     '黄岐镇', 'fishing_gear',  4, 1, 0,  0.000,     0.00)
ON CONFLICT (stat_date, township, main_class) DO NOTHING;

-- ---------- 校验输出 ----------
DO $$
DECLARE
    dev_cnt INT; evt_cnt INT; tsk_cnt INT; trk_cnt INT;
BEGIN
    SELECT COUNT(*) INTO dev_cnt FROM t_device;
    SELECT COUNT(*) INTO evt_cnt FROM t_event;
    SELECT COUNT(*) INTO tsk_cnt FROM t_task;
    SELECT COUNT(*) INTO trk_cnt FROM t_track;
    RAISE NOTICE '[seed] 设备 % 台 | 事件 % 条 | 工单 % 条 | 轨迹 % 点',
        dev_cnt, evt_cnt, tsk_cnt, trk_cnt;
END $$;

-- ============================================================
-- 探海灵眸 SeaSight — 数据库 Schema
-- PostgreSQL 14 + PostGIS 3.3
-- 设计原则：平台是中枢，核心表是「事件表」与「工单表」
-- ============================================================

-- ---------- 扩展 ----------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 名称模糊搜索

-- ---------- 枚举类型 ----------
DO $$ BEGIN
    CREATE TYPE device_type_enum AS ENUM ('shore_camera', 'drone', 'robot');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE device_status_enum AS ENUM ('online', 'offline', 'fault');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE waste_class_enum AS ENUM ('foam', 'plastic', 'fishing_gear', 'other');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE event_status_enum AS ENUM ('new', 'dispatched', 'resolved', 'ignored');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE task_status_enum AS ENUM ('pending', 'assigned', 'navigating', 'collecting', 'done', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE review_result_enum AS ENUM ('confirmed', 'not_found', 'recheck', 'pending');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE user_role_enum AS ENUM ('admin', 'operator', 'viewer');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- ============================================================
-- （1）设备表 t_device
-- ============================================================
CREATE TABLE IF NOT EXISTS t_device (
    id              BIGSERIAL PRIMARY KEY,
    device_id       VARCHAR(64)  NOT NULL UNIQUE,          -- 业务编号，如 CAM-MABI-01
    device_type     device_type_enum NOT NULL,
    name            VARCHAR(128) NOT NULL,
    location        geometry(Point, 4326) NOT NULL,        -- 安装/初始位置
    status          device_status_enum NOT NULL DEFAULT 'offline',
    last_heartbeat  TIMESTAMPTZ,
    stream_url      TEXT,                                  -- 视频流地址（go2rtc 转发）
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,    -- 型号、分辨率等扩展
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  t_device IS '设备表：岸基摄像头 / 无人机 / 水面机器人';
COMMENT ON COLUMN t_device.device_id IS '业务编号，边缘端上报时使用此 ID';

-- 空间索引：按区域查设备
CREATE INDEX IF NOT EXISTS idx_device_location ON t_device USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_device_status   ON t_device (status);
CREATE INDEX IF NOT EXISTS idx_device_type     ON t_device (device_type);


-- ============================================================
-- （2）识别事件表 t_event  ★核心表
-- ============================================================
CREATE TABLE IF NOT EXISTS t_event (
    id              BIGSERIAL PRIMARY KEY,
    event_id        VARCHAR(64)  NOT NULL UNIQUE,          -- 事件编号 evt_xxx
    device_id       VARCHAR(64)  NOT NULL,
    event_time      TIMESTAMPTZ  NOT NULL,                 -- 事件发生时间（设备时间）
    location        geometry(Point, 4326) NOT NULL,
    main_class      waste_class_enum NOT NULL,
    det_count       SMALLINT     NOT NULL DEFAULT 1,
    max_confidence  NUMERIC(5,4) NOT NULL,                 -- 0.0000 ~ 1.0000
    evidence_url    TEXT,                                  -- 证据帧 MinIO 地址
    model_version   VARCHAR(32),                           -- 产出该事件的模型版本
    seq             BIGINT       NOT NULL,                 -- 边缘端单调序号（判重用）
    status          event_status_enum NOT NULL DEFAULT 'new',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- 防重复派单：同一设备同一序号只能有一条
    CONSTRAINT uq_event_device_seq UNIQUE (device_id, seq),
    CONSTRAINT chk_event_confidence CHECK (max_confidence >= 0 AND max_confidence <= 1),
    CONSTRAINT chk_event_det_count  CHECK (det_count > 0)
);

COMMENT ON TABLE  t_event IS '识别事件表：平台核心表，所有业务从事件驱动';
COMMENT ON COLUMN t_event.seq IS '边缘端单调递增序号，配合 device_id 建唯一约束，杜绝 MQTT 重传导致的重复派单';

-- 热力图查询主用索引：时间 + 空间
CREATE INDEX IF NOT EXISTS idx_event_time     ON t_event (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_event_location ON t_event USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_event_status   ON t_event (status);
CREATE INDEX IF NOT EXISTS idx_event_class    ON t_event (main_class);
-- 复合索引：热力图按时间窗 + 类别筛选
CREATE INDEX IF NOT EXISTS idx_event_time_class ON t_event (event_time DESC, main_class);


-- ============================================================
-- （3）清理任务表 t_task  ★工单表
-- ============================================================
CREATE TABLE IF NOT EXISTS t_task (
    id                BIGSERIAL PRIMARY KEY,
    task_id           VARCHAR(64) NOT NULL UNIQUE,         -- 任务编号 tsk_xxx
    event_id          VARCHAR(64) REFERENCES t_event(event_id) ON DELETE SET NULL,
    robot_id          VARCHAR(64),                         -- 执行机器人（未派单时为空）
    target_location   geometry(Point, 4326) NOT NULL,
    status            task_status_enum NOT NULL DEFAULT 'pending',
    priority          SMALLINT NOT NULL DEFAULT 5,         -- 1=最高 9=最低

    -- 时间戳链：完整记录任务生命周期
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_at       TIMESTAMPTZ,
    ack_at            TIMESTAMPTZ,                         -- 机器人确认接收
    started_at        TIMESTAMPTZ,                         -- 开始作业
    finished_at       TIMESTAMPTZ,                         -- 作业完成

    collected_weight  NUMERIC(8,3),                        -- 清理量 kg（作业后补录）
    review_result     review_result_enum DEFAULT 'pending',-- 机载复核结果
    remark            TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_task_priority CHECK (priority BETWEEN 1 AND 9)
);

COMMENT ON TABLE  t_task IS '清理任务表（工单表）：状态变更必须走服务层，禁止直接 UPDATE';
COMMENT ON COLUMN t_task.status IS '状态机：pending→assigned→navigating→collecting→done；任意态可→cancelled';

CREATE INDEX IF NOT EXISTS idx_task_status  ON t_task (status);
CREATE INDEX IF NOT EXISTS idx_task_robot   ON t_task (robot_id);
CREATE INDEX IF NOT EXISTS idx_task_event   ON t_task (event_id);
CREATE INDEX IF NOT EXISTS idx_task_created ON t_task (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_target  ON t_task USING GIST (target_location);

-- 防抖关键：同一事件在「未完成任务」状态下不重复派单（部分唯一索引）
CREATE UNIQUE INDEX IF NOT EXISTS uq_task_active_event
    ON t_task (event_id)
    WHERE status NOT IN ('done', 'cancelled') AND event_id IS NOT NULL;


-- ============================================================
-- （4）作业轨迹表 t_track（按日分区，数据量大）
-- ============================================================
CREATE TABLE IF NOT EXISTS t_track (
    id          BIGSERIAL,
    robot_id    VARCHAR(64) NOT NULL,
    task_id     VARCHAR(64),
    location    geometry(Point, 4326) NOT NULL,
    battery     SMALLINT,                                  -- 电量百分比
    bin_foam    NUMERIC(4,3),                              -- 泡沫仓占用 0~1
    bin_plastic NUMERIC(4,3),                              -- 塑胶仓占用
    bin_mixed   NUMERIC(4,3),                              -- 混合仓占用
    speed       NUMERIC(5,2),                              -- m/s
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, recorded_at)
) PARTITION BY RANGE (recorded_at);

COMMENT ON TABLE t_track IS '作业轨迹表：按日分区，超期数据降采样归档';

-- 创建初始分区（当日 + 未来 7 天），生产环境用 pg_partman 自动管理
DO $$
DECLARE
    d date;
BEGIN
    FOR i IN -1..7 LOOP
        d := CURRENT_DATE + i;
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS t_track_%s PARTITION OF t_track FOR VALUES FROM (%L) TO (%L)',
            to_char(d, 'YYYYMMDD'), d, d + 1
        );
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_track_robot_time ON t_track (robot_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_track_location   ON t_track USING GIST (location);


-- ============================================================
-- （5）统计宽表 t_report_daily（预聚合，报表页只读这张表）
-- ============================================================
CREATE TABLE IF NOT EXISTS t_report_daily (
    id             BIGSERIAL PRIMARY KEY,
    stat_date      DATE NOT NULL,
    township       VARCHAR(64),                            -- 乡镇：马鼻/黄岐/筱埕...
    main_class     waste_class_enum,
    event_count    INTEGER NOT NULL DEFAULT 0,
    task_count     INTEGER NOT NULL DEFAULT 0,
    done_count     INTEGER NOT NULL DEFAULT 0,
    collected_kg   NUMERIC(10,3) NOT NULL DEFAULT 0,
    coverage_area  NUMERIC(12,2) NOT NULL DEFAULT 0,       -- 覆盖面积 m²
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_report_daily UNIQUE (stat_date, township, main_class)
);

COMMENT ON TABLE t_report_daily IS '统计宽表：每日凌晨预聚合，用存储换查询速度';

CREATE INDEX IF NOT EXISTS idx_report_date     ON t_report_daily (stat_date DESC);
CREATE INDEX IF NOT EXISTS idx_report_township ON t_report_daily (township);


-- ============================================================
-- （6）用户与权限 t_user / t_role
-- ============================================================
CREATE TABLE IF NOT EXISTS t_user (
    id             BIGSERIAL PRIMARY KEY,
    username       VARCHAR(64)  NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name      VARCHAR(64),
    role           user_role_enum NOT NULL DEFAULT 'viewer',
    township_scope VARCHAR(64),                            -- 操作员的数据辖区（乡镇）
    is_active      BOOLEAN NOT NULL DEFAULT true,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE t_user IS '用户表：admin=全部 / operator=本辖区 / viewer=只读大屏';

CREATE INDEX IF NOT EXISTS idx_user_role ON t_user (role);


-- ============================================================
-- 通用触发器：自动维护 updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at_device ON t_device;
CREATE TRIGGER set_updated_at_device
    BEFORE UPDATE ON t_device FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS set_updated_at_task ON t_task;
CREATE TRIGGER set_updated_at_task
    BEFORE UPDATE ON t_task FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();


-- ============================================================
-- 示例查询：热力图网格聚合（供参考，接口调用）
-- ============================================================
-- 按 500m 网格聚合最近 24 小时事件，输出网格中心与密度
-- 注意：必须投影到 3857（米制），否则 ST_SnapToGrid 的单位是「度」
--
-- SELECT
--     ST_Y(ST_Transform(grid, 4326)) AS lat,
--     ST_X(ST_Transform(grid, 4326)) AS lng,
--     cnt,
--     density,
--     main_class
-- FROM (
--     SELECT ST_SnapToGrid(ST_Transform(location::geometry, 3857), 500) AS grid,
--            COUNT(*) AS cnt,
--            COUNT(*) / 250000.0 AS density,          -- 500*500 m²
--            MODE() WITHIN GROUP (ORDER BY main_class) AS main_class
--     FROM t_event
--     WHERE event_time > now() - interval '24 hours'
--       AND status <> 'ignored'
--     GROUP BY grid
-- ) t
-- ORDER BY cnt DESC
-- LIMIT 500;

-- ============================================================
-- 示例查询：KNN 就近派单（找最近的可用机器人）
-- ============================================================
-- SELECT r.device_id, r.name,
--        ST_Distance(r.location::geography, e.location::geography) AS dist_m
-- FROM t_device r
-- JOIN t_event e ON e.event_id = $1
-- WHERE r.device_type = 'robot'
--   AND r.status = 'online'
--   AND ST_DWithin(r.location::geography, e.location::geography, 3000)  -- 米制粗筛，走索引
-- ORDER BY r.location <-> e.location                                     -- KNN 算子，走 GiST
-- LIMIT 1;

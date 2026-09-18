# 探海灵眸 SeaSight — 常用命令
# 用法：make <target>     查看全部：make help

.PHONY: help up down restart logs ps db-init db-reset migrate migrate-stamp migration migrate-history migrate-sql upgrade-pending dev-backend dev-frontend simulate demo smoke check check-api check-gitignore check-contract check-contract-selftest check-events-selftest check-dispatch-selftest check-finalize-selftest check-pel-selftest check-data check-data-stats test test-edge test-cv-selftest run-edge run-edge-demo test-all clean

SHELL := /bin/bash

help:  ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- 容器编排 ----------
up:  ## 启动全部依赖服务（后台）
	docker compose up -d
	@echo "等待服务就绪..."
	@sleep 5
	@docker compose ps

down:  ## 停止全部服务
	docker compose down

restart:  ## 重启全部服务
	docker compose restart

logs:  ## 查看全部服务日志（跟随）
	docker compose logs -f

ps:  ## 查看服务状态
	docker compose ps

# ---------- 数据库 ----------
db-init:  ## 初始化数据库（建表 + 空间索引 + 种子数据）
	@echo "[db-init] 执行建表脚本..."
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-seasight} -d $${POSTGRES_DB:-seasight} \
		-f /docker-entrypoint-initdb.d/01_schema.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-seasight} -d $${POSTGRES_DB:-seasight} \
		-f /docker-entrypoint-initdb.d/02_seed.sql
	@echo "[db-init] 完成"

db-reset:  ## 危险：删除数据卷重建（会丢数据，仅开发用）
	@read -p "确定要清空数据库吗？[y/N] " ans; [ "$$ans" = "y" ] || exit 1
	docker compose down -v
	docker compose up -d postgres
	@sleep 8
	$(MAKE) db-init

# ---------- 数据库迁移（Alembic）----------
# schema 管理是「双轨制」：
#   轨道 A —— 初始建表走 backend/db/init/01_schema.sql（容器首次启动自动执行）
#   轨道 B —— 后续增量变更走 Alembic
# 所以新环境必须先 `make migrate-stamp` 打桩，否则第一次 autogenerate
# 会生成一堆 create_table，一执行就报表已存在。
#
# ⚠️ 配置在 backend/pyproject.toml，不在 alembic.ini。
#    （alembic.ini 在中文 Windows 上读不了 —— 编码 bug，详见该文件注释）
#    注意：Python 3.11+ 才支持 tomllib；本机 3.13 没问题。

migrate-stamp:  ## 新环境首次：把 baseline 标记为已应用（不执行 SQL，不建表）
	@echo "[migrate-stamp] 把当前 head 标记为已应用（schema 已由 01_schema.sql 建好）"
	cd backend && python -m alembic stamp head
	@echo "[migrate-stamp] 完成。可执行 make migrate-history 验证"

migrate:  ## 应用全部待执行迁移（upgrade head）
	cd backend && python -m alembic upgrade head

migration:  ## 按模型差异生成迁移，用法：make migration m="add xxx column"
	@if [ -z "$(m)" ]; then \
		echo "用法：make migration m=\"描述这次变更\""; \
		exit 1; \
	fi
	cd backend && python -m alembic revision --autogenerate -m "$(m)"
	@echo ""
	@echo "★ 生成后请人工检查 backend/alembic/versions/ 下的新文件："
	@echo "  autogenerate 对字段类型/默认值变更的判断不总是可靠，"
	@echo "  尤其涉及 PostGIS 几何列与分区表时，务必肉眼过一遍再提交。"

migrate-history:  ## 查看迁移历史
	cd backend && python -m alembic history

migrate-current:  ## 查看数据库当前版本（需数据库在线）
	cd backend && python -m alembic current

migrate-sql:  ## 导出待执行迁移的 SQL（离线，不连库；便于 DBA 审核）
	cd backend && python -m alembic upgrade head --sql

# ---------- 本地开发 ----------
dev-backend:  ## 本地启动后端（热重载，需先 make up）
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:  ## 本地启动前端开发服务器
	cd frontend && npm run dev

# ---------- 演示与测试 ----------
simulate:  ## 运行边缘盒模拟器（真实抽帧节奏，上报冷却 90s）
	cd edge/simulator && python simulator.py --scenario demo --loop

demo:  ## 演示专用：3 秒上报冷却，几秒就能看到连续告警
	cd edge/simulator && python simulator.py --scenario demo --event-interval 3 --loop

smoke:  ## 端到端冒烟测试（构造事件 → 验证派单 → 检查状态流转）
	python scripts/smoke_test.py

check-api:  ## 契约校验：前端调用的 API 路径在后端是否都有实现
	python scripts/check_api_contract.py

check-gitignore:  ## 检查是否有该忽略却没忽略的文件（运行时状态/权重/密钥）
	python scripts/check_gitignore.py

check-contract:  ## 契约漂移检查：MQTT 主题树、状态映射、类别枚举
	python scripts/check_contract_drift.py

check-contract-selftest:  ## 自证：注入 12 种已知缺陷，确认上面的检查真的会红
	python scripts/selftest_contract_drift.py

check-events-selftest:  ## 自证：注入事件上报契约的 4 种缺陷，确认测试会红
	python scripts/selftest_events_contract.py

check-dispatch-selftest:  ## 自证：注入派单引擎的 5 种缺陷，确认测试会红
	python scripts/selftest_dispatch_contract.py

check-finalize-selftest:  ## 自证：注入派单收尾的 7 种缺陷，确认测试会红
	python scripts/selftest_dispatch_finalize.py

check-pel-selftest:  ## 自证：注入消费者 PEL 回收的 4 种缺陷，确认测试会红
	python scripts/selftest_consumer_pel.py

check: check-api check-gitignore check-contract  ## 跑全部静态检查（不需要基础设施）
	@echo "[check] 全部通过"

check-data:  ## 数据集体检：图片/标签配对、类别索引、标签格式
	python ml/scripts/check_dataset.py

check-data-stats:  ## 数据集体检并把统计写回 seasight.yaml 的 stats 段
	@echo "[check-data-stats] 体检 + 写回统计（供训练脚本做负样本/均衡检查）"
	python ml/scripts/check_dataset.py --write-stats
	@echo "[check-data-stats] 完成 —— 请 git diff 确认只改了数字，没动注释"

test-edge:  ## 边缘逻辑测试：时序校验 + OpenCV 检测器（不需要摄像头与 Broker）
	cd edge/simulator && python test_temporal.py
	cd edge/detector && python -m pytest test_detector.py -q

test-cv-selftest:  ## 真实边缘程序自检：合成海面跑通「检测→时序→报文」全链路
	python edge/main.py --source synthetic --dry-run --max-frames 200 --cooldown 0.3 --min-interval 0

run-edge:  ## 启动真实边缘感知程序（RTSP 取流，读 edge/config.yaml）
	python edge/main.py --source rtsp

run-edge-demo:  ## 无摄像头时的演示：合成海面 + 弹窗看检测框
	python edge/main.py --source synthetic --show --cooldown 5 --min-interval 1

test:  ## 运行后端单元测试
	cd backend && pytest -v

test-all: test-edge test  ## 跑全部测试（边缘逻辑 + 后端）
	@echo "[test-all] 全部测试通过"
	@echo ""
	@echo "提示：契约与卫生检查请跑 make check；端到端验证需基础设施，请跑 make smoke（需先 make up）"
	@echo "      怀疑检查脚本本身失效时，跑 make check-contract-selftest"

# ---------- 清理 ----------
clean:  ## 清理 Python 缓存与构建产物
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "[clean] 完成"

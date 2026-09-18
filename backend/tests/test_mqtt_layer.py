"""MQTT 层单元测试。

★ 为什么必须单独为这一层写测试
──────────────────────────────
`handlers.py` 与 `client.py` 是「设备世界」接入平台的唯一入口，
但它们的缺陷有个恶劣特性：**不报错、不抛异常、也没有日志**。

平台与设备之间是消息驱动的，消息进不来或路由不到，
表现出来只是「业务不动了」—— 大屏上工单卡住、事件不更新。
排查时人会先怀疑网络、怀疑 Broker、怀疑设备，最后才怀疑路由表。

`make smoke` 是端到端测试，但它**只打 HTTP 接口**（见其文档），
压根不经过 MQTT 层；于是这一层长期零覆盖。

本文件按 conftest 的约定，**不依赖真实数据库**，
只覆盖纯逻辑：主题路由、状态映射、topic 解析、报文形状校验。
需要数据库的入库链路留给 `scripts/smoke_test.py`。
"""

from __future__ import annotations

import inspect

import pytest

from app.mqtt.client import MqttClient
from app.mqtt.handlers import (
    ROBOT_STATUS_MAP,
    _device_from_topic,
    _robot_from_topic,
)
from app.mqtt.topics import SUBSCRIBE_PLAN, Topics

# ======================================================================
# 主题路由 —— 曾把整条作业链路掐断的地方
# ======================================================================
class TestTopicRouting:
    """`_match_handler` 的主题 → 处理器映射。

    这里守过一个真实缺陷：`robot/{id}/cmd/ack` 用 `len(parts) == 5`
    做判据，而该主题展开只有 4 段，条件永远不成立 →
    ACK 被静默丢弃 → 任务永远停在 assigned。
    """

    @pytest.fixture
    def client(self) -> MqttClient:
        return MqttClient()

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("marine/lianjiang/CAM-MABI-01/event", "handle_event"),
            ("marine/lianjiang/CAM-MABI-01/telemetry", "handle_telemetry"),
            ("marine/lianjiang/CAM-MABI-01/status", "handle_device_status"),
            ("robot/RBT-001/task/progress", "handle_robot_progress"),
            ("robot/RBT-001/cmd/ack", "handle_robot_ack"),
        ],
    )
    def test_all_declared_topics_route(self, client: MqttClient, topic: str, expected: str) -> None:
        """文档声明的每个上行主题都必须能路由到处理器。"""
        assert client._match_handler(topic) == expected

    def test_subscribe_plan_fully_reachable(self, client: MqttClient) -> None:
        """★ SUBSCRIBE_PLAN 里每个通配主题都要能匹配到它声明的处理器。

        这是最强的一条：订阅计划是「平台打算接收什么」的唯一声明，
        如果某个通配主题匹配不到处理器，等于**订阅了却无人处理** ——
        消息到了平台门口又被丢掉，且不会有任何报错。
        """
        unreachable = []
        for wildcard, handler in SUBSCRIBE_PLAN.items():
            sample = wildcard.replace("+", "X")
            got = client._match_handler(sample)
            if got != handler:
                unreachable.append(f"{wildcard} → 期望 {handler}，实际 {got}")
        assert not unreachable, "以下订阅主题路由不到处理器：\n  " + "\n  ".join(unreachable)

    def test_robot_topics_have_same_segment_count(self) -> None:
        """★ 锁住根因：两个 robot 上行主题段数相同。

        这条测试的作用是留下证据 —— 说明为什么不能用 len(parts)
        区分它们。若将来有人改动主题结构，这里会先失败。
        """
        progress = Topics.robot_progress("RBT-001")
        ack = Topics.robot_ack("RBT-001")
        assert len(progress.split("/")) == len(ack.split("/")) == 4, (
            "两个 robot 主题段数相同，路由必须靠逐段比对而非总段数"
        )

    @pytest.mark.parametrize(
        "topic",
        [
            "robot/RBT-001/task/unknown",      # 未知后缀
            "robot/RBT-001/other/ack",         # 中间段不对
            "robot/RBT-001/cmd/ack/extra",     # 多一段
            "marine/lianjiang/CAM-01/unknown", # 未知后缀
            "marine/lianjiang/CAM-01",         # 少一段
            "random/topic/x/y",                # 完全不相关
            "",                                # 空主题
            "marine",                          # 只有一层
        ],
    )
    def test_unmatched_topics_return_none(self, client: MqttClient, topic: str) -> None:
        """不匹配的主题必须返回 None，不能误路由到某个 handler。"""
        assert client._match_handler(topic) is None

    def test_topics_builder_output_is_routable(self, client: MqttClient) -> None:
        """`Topics` 构造函数产出的主题必须能被路由 —— 防止两处各写各的。"""
        built = {
            Topics.event("lianjiang", "CAM-01"): "handle_event",
            Topics.telemetry("lianjiang", "CAM-01"): "handle_telemetry",
            Topics.status("lianjiang", "CAM-01"): "handle_device_status",
            Topics.robot_progress("RBT-001"): "handle_robot_progress",
            Topics.robot_ack("RBT-001"): "handle_robot_ack",
        }
        for topic, expected in built.items():
            assert client._match_handler(topic) == expected, topic

    def test_wildcard_subscription_never_uses_hash(self) -> None:
        """禁止 `#` 大范围订阅（会收到 $SYS 等系统主题，浪费带宽且有隐患）。"""
        bad = [w for w in SUBSCRIBE_PLAN if "#" in w]
        assert not bad, f"以下订阅用了 # 通配：{bad}"

    def test_wildcards_have_no_leading_slash(self) -> None:
        """禁止前导斜杠（会造成空的首层，与 ACL 规则冲突）。"""
        bad = [w for w in SUBSCRIBE_PLAN if w.startswith("/")]
        assert not bad, f"以下订阅有前导斜杠：{bad}"


# ======================================================================
# 作业状态映射 —— 曾漏掉 done 导致任务永不完成
# ======================================================================
class TestRobotStatusMap:
    """`ROBOT_STATUS_MAP` 必须覆盖 mqtt-topics.md §5.6 声明的全部取值。"""

    def test_covers_all_documented_statuses(self) -> None:
        """★ 契约声明的四种状态一个都不能少。

        历史缺陷：漏了 `done`。机器人上报 done → 平台不认识 →
        静默忽略 → 任务永远停在 collecting、事件永不 resolved。
        整条闭环断在最后一步，且没有任何日志。
        """
        documented = ["navigating", "collecting", "returning", "done"]
        missing = [s for s in documented if s not in ROBOT_STATUS_MAP]
        assert not missing, (
            f"作业状态映射缺少 {missing} —— 这些状态的上报会被静默丢弃"
        )

    def test_done_maps_to_done_not_collecting(self) -> None:
        """`done` 必须映射到任务终态，不能像 returning 那样归入 collecting。

        若误映射为 collecting，任务永远不会进入 done，
        事件也就永远不会变 resolved —— 大屏上工单永久卡住。
        """
        assert ROBOT_STATUS_MAP["done"] == "done"

    def test_returning_maps_to_collecting(self) -> None:
        """返航仍属作业中（状态机没有单独的返航态）—— 这是有意的设计。"""
        assert ROBOT_STATUS_MAP["returning"] == "collecting"

    def test_all_targets_are_valid_task_statuses(self) -> None:
        """映射的目标值必须是合法任务状态，否则 transition 会抛异常。"""
        from app.models.task import TaskStatus

        invalid = {k: v for k, v in ROBOT_STATUS_MAP.items() if v not in TaskStatus.ALL}
        assert not invalid, f"以下映射的目标不是合法任务状态：{invalid}"

    def test_all_targets_are_reachable_by_state_machine(self) -> None:
        """每个映射目标都必须能从某个合法前驱到达。

        防止出现「映射写了但没有合法路径能走到它」的死值。
        """
        from app.models.task import TaskStatus

        reachable = {s for nxt in TaskStatus.TRANSITIONS.values() for s in nxt}
        dead = {
            k: v for k, v in ROBOT_STATUS_MAP.items() if v not in reachable
        }
        # NAVIGATING 是 ASSIGNED 的后继，在 reachable 里；
        # done 是 COLLECTING 的后继，也在。这里只排除真正的死值。
        assert not dead, f"以下映射目标在状态机里不可达：{dead}"


# ======================================================================
# topic 解析工具
# ======================================================================
class TestTopicParsers:
    """从主题里提取设备 / 机器人 ID。"""

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("marine/lianjiang/CAM-MABI-01/event", "CAM-MABI-01"),
            ("marine/lianjiang/CAM-MABI-01/telemetry", "CAM-MABI-01"),
            ("marine/lianjiang/UAV-001/status", "UAV-001"),
        ],
    )
    def test_device_id_extracted(self, topic: str, expected: str) -> None:
        assert _device_from_topic(topic) == expected

    @pytest.mark.parametrize(
        "topic",
        [
            "robot/RBT-001/task/progress",   # 不是 marine 前缀
            "marine/lianjiang",              # 层数不够
            "",
            "other/x/y/z",
        ],
    )
    def test_device_id_returns_none_for_foreign_topics(self, topic: str) -> None:
        """非 marine 主题或层数不足时返回 None，不能瞎猜。"""
        assert _device_from_topic(topic) is None

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("robot/RBT-001/task/progress", "RBT-001"),
            ("robot/RBT-001/cmd/ack", "RBT-001"),
            ("robot/RBT-002/task", "RBT-002"),
        ],
    )
    def test_robot_id_extracted(self, topic: str, expected: str) -> None:
        assert _robot_from_topic(topic) == expected

    @pytest.mark.parametrize("topic", ["marine/lianjiang/CAM-01/event", "robot", ""])
    def test_robot_id_returns_none_for_foreign_topics(self, topic: str) -> None:
        assert _robot_from_topic(topic) is None

    def test_two_parsers_do_not_interfere(self) -> None:
        """★ 两个解析器不能互相认错 —— 它们各自检查首层。

        若 _device_from_topic 漏了 `parts[0] == "marine"` 检查，
        就会把 `robot/RBT-001/...` 的 parts[2] 当成设备 ID（可能是 "task"），
        于是遥测里凭空出现一个叫 "task" 的设备。
        """
        robot_topic = "robot/RBT-001/task/progress"
        marine_topic = "marine/lianjiang/CAM-01/event"
        assert _device_from_topic(robot_topic) is None
        assert _robot_from_topic(marine_topic) is None


# ======================================================================
# 时间戳解析
# ======================================================================
class TestParseTimestamp:
    """`_parse_ts` 的容错行为 —— 它决定了 event_time 的正确性。"""

    def test_iso_with_timezone(self) -> None:
        from datetime import datetime

        from app.mqtt.handlers import _parse_ts

        got = _parse_ts("2026-09-18T01:23:45+08:00")
        assert got.year == 2026 and got.month == 9 and got.day == 18
        assert got.hour == 1 and got.minute == 23

    def test_iso_with_z_suffix(self) -> None:
        """`Z` 结尾（UTC）必须能解析 —— 不少嵌入式设备这么发。"""
        from app.mqtt.handlers import _parse_ts

        got = _parse_ts("2026-09-18T01:23:45Z")
        assert got.year == 2026
        # Z 应被替换成 +00:00 而不是解析失败后回落到 now()
        assert got.tzinfo is not None

    def test_datetime_passthrough(self) -> None:
        from datetime import datetime

        from app.mqtt.handlers import _parse_ts

        src = datetime(2026, 9, 18, 1, 0, 0)
        assert _parse_ts(src) is src

    @pytest.mark.parametrize("bad", [None, "", "not-a-date", 12345, {}, []])
    def test_invalid_falls_back_to_now(self, bad) -> None:
        """非法值回落到当前时间，**不能抛异常**。

        事件报文里的时间戳来自现场设备，格式不可控。
        为此中断整个 handler 会让一条坏报文堵住整条消费循环。
        """
        from datetime import datetime

        from app.mqtt.handlers import _parse_ts

        got = _parse_ts(bad)
        assert isinstance(got, datetime)


# ======================================================================
# 报文入口的防御性
# ======================================================================
class TestHandlerRegistry:
    """HANDLERS 注册表与 SUBSCRIBE_PLAN 必须对齐。"""

    def test_registry_covers_all_subscribe_plan_handlers(self) -> None:
        """★ 订阅计划里声明的每个 handler 都必须在注册表里存在。

        注册表少一项，运行时 `self._handlers.get(name)` 返回 None，
        消息被丢掉只留一条 warning —— 演示现场极难注意到。
        """
        from app.mqtt.handlers import HANDLERS

        needed = set(SUBSCRIBE_PLAN.values())
        missing = needed - set(HANDLERS)
        assert not missing, f"SUBSCRIBE_PLAN 需要这些处理器但未注册：{missing}"

    def test_all_handlers_are_async_callables(self) -> None:
        """处理器必须是可 await 的协程函数 —— 否则事件循环里会炸。"""
        from app.mqtt.handlers import HANDLERS

        not_async = [
            name for name, fn in HANDLERS.items() if not inspect.iscoroutinefunction(fn)
        ]
        assert not not_async, f"以下处理器不是 async：{not_async}"

    def test_handler_signature_is_topic_payload(self) -> None:
        """处理器签名统一为 (topic, payload) —— client 就是这么调的。"""
        from app.mqtt.handlers import HANDLERS

        bad = []
        for name, fn in HANDLERS.items():
            params = list(inspect.signature(fn).parameters)
            if params[:2] != ["topic", "payload"]:
                bad.append(f"{name}{tuple(params)}")
        assert not bad, f"以下处理器签名不是 (topic, payload)：{bad}"

    def test_registry_has_no_orphan_entries(self) -> None:
        """注册表里的项都该被订阅计划引用 —— 孤儿项是重构残留。"""
        from app.mqtt.handlers import HANDLERS

        used = set(SUBSCRIBE_PLAN.values())
        orphans = set(HANDLERS) - used
        assert not orphans, (
            f"以下处理器已注册但没有任何订阅会触发它们：{orphans}"
        )


class TestEventPayloadValidation:
    """事件报文的形状校验 —— 坏报文不能把消费循环打死。"""

    def _make_payload(self, **overrides) -> dict:
        base = {
            "event_id": "evt_test_001",
            "device_id": "CAM-MABI-01",
            "device_type": "shore_camera",
            "timestamp": "2026-09-18T01:00:00+08:00",
            "location": {"lng": 119.65, "lat": 26.38},
            "detections": [
                {"class": "foam", "confidence": 0.9, "bbox": [400, 280, 470, 340]}
            ],
            "aggregate": {"main_class": "foam", "count": 1, "max_confidence": 0.9},
            "seq": 1,
        }
        base.update(overrides)
        return base

    def test_valid_payload_parses_into_schema(self) -> None:
        """合法报文应能构造出 EventIngest —— 校验 schema 层与 handler 的一致性。"""
        from app.schemas import DetectionItem, EventAggregate, EventIngest, GeoPoint

        p = self._make_payload()
        ingest = EventIngest(
            event_id=p["event_id"],
            device_id=p["device_id"],
            device_type=p["device_type"],
            timestamp=p["timestamp"],
            location=GeoPoint(**p["location"]),
            detections=[DetectionItem(**d) for d in p["detections"]],
            aggregate=EventAggregate(**p["aggregate"]),
            seq=p["seq"],
        )
        assert ingest.event_id == "evt_test_001"
        assert ingest.aggregate.main_class == "foam"

    @pytest.mark.parametrize("missing", ["event_id", "device_id", "location", "aggregate", "seq"])
    def test_missing_required_field_is_rejected(self, missing: str) -> None:
        """必填字段缺失时 schema 必须拒绝。

        handler 用 try/except (KeyError, TypeError, ValueError) 包住构造，
        所以这里抛任何校验异常都算合格 —— 关键是**不能放行**。
        """
        from pydantic import ValidationError

        from app.schemas import EventAggregate, EventIngest, GeoPoint

        p = self._make_payload()
        del p[missing]
        with pytest.raises((KeyError, TypeError, ValueError, ValidationError)):
            EventIngest(
                event_id=p["event_id"],
                device_id=p["device_id"],
                device_type=p.get("device_type", "shore_camera"),
                timestamp=p.get("timestamp"),
                location=GeoPoint(**p["location"]),
                detections=[],
                aggregate=EventAggregate(**p["aggregate"]),
                seq=p["seq"],
            )

    def test_unknown_main_class_rejected(self) -> None:
        """主类别必须是四类枚举之一，否则前端配色与派单规则都会落空。"""
        from pydantic import ValidationError

        from app.schemas import EventAggregate

        with pytest.raises((ValueError, ValidationError)):
            EventAggregate(main_class="not_a_real_class", count=1, max_confidence=0.9)


class TestAiomqttDependencyDeclared:
    """防止「用了却没声明」的依赖缺陷。"""

    def test_aiomqtt_in_requirements(self, project_root) -> None:
        """★ client.py `import aiomqtt`，requirements.txt 必须有它。

        这条守的是一类真实缺陷：代码里 import 了某个包，
        依赖清单却没写 → 开发机（碰巧装过）一切正常，
        队友新环境一 clone 就 ImportError。MQTT 层整个起不来。
        """
        req = project_root / "backend" / "requirements.txt"
        text = req.read_text(encoding="utf-8")
        assert "aiomqtt" in text, "requirements.txt 未声明 aiomqtt，但 client.py 依赖它"


# ======================================================================
# 类别枚举的单一真源 —— schema 层曾漏约束
# ======================================================================
class TestWasteClassEnumSingleSource:
    """类别枚举必须处处一致，且 schema 层必须真的把关。

    守的缺陷：`EventAggregate.main_class` 与 `DetectionItem.class`
    曾是裸 `str`，任意字符串都放行。而该字段同时被三处消费：
      1. 前端配色 —— 查 CLASS_ORDER 落空 → 显示成灰色
      2. 派单白名单 —— 条件不命中 → 不派单
      3. 数据库 enum 列 —— 入库被拒 → 整个事件丢失
    三者同时静默失效，且**没有任何一处会抛异常**。
    """

    @pytest.mark.parametrize("bogus", ["", "foam ", "FOAM", "not_a_class", "渔具"])
    def test_aggregate_rejects_non_enum_class(self, bogus: str) -> None:
        from pydantic import ValidationError

        from app.schemas import EventAggregate

        with pytest.raises((ValueError, ValidationError)):
            EventAggregate(main_class=bogus, count=1, max_confidence=0.9)

    @pytest.mark.parametrize("bogus", ["", "FOAM", "ghost"])
    def test_detection_item_rejects_non_enum_class(self, bogus: str) -> None:
        from pydantic import ValidationError

        from app.schemas import DetectionItem

        with pytest.raises((ValueError, ValidationError)):
            DetectionItem(**{"class": bogus, "confidence": 0.9, "bbox": [0, 0, 1, 1]})

    def test_all_four_categories_accepted(self) -> None:
        """四类合法值必须全部放行 —— 防止约束写过头误伤正常上报。"""
        from app.schemas import EventAggregate
        from app.models.event import WasteClass

        for cls in WasteClass.ALL:
            agg = EventAggregate(main_class=cls, count=1, max_confidence=0.9)
            assert agg.main_class == cls

    def test_schema_literal_matches_waste_class_all(self) -> None:
        """★ 穷举守卫：schema 的 Literal 取值必须与 WasteClass.ALL 完全一致。

        抽测几个样本抓不到这类漂移 —— 只有比对两个集合才行。
        若有人给 WasteClass 加了第五类却忘了改 schema（或反之），这条会红。
        """
        import typing

        from app.models.event import WasteClass
        from app.schemas import WasteClassLiteral

        allowed = set(typing.get_args(WasteClassLiteral))
        truth = set(WasteClass.ALL)
        assert allowed == truth, (
            f"schema 类别枚举与 WasteClass.ALL 漂移："
            f"schema 多出 {sorted(allowed - truth)}，缺少 {sorted(truth - allowed)}"
        )

    def test_high_priority_is_subset_of_all(self) -> None:
        """派单白名单必须是合法类别的子集，否则它永远不会命中。"""
        from app.models.event import WasteClass

        assert set(WasteClass.HIGH_PRIORITY) <= set(WasteClass.ALL)
        assert WasteClass.HIGH_PRIORITY, "高优先级白名单不能为空，否则自动派单永不触发"


class TestDispatchWhitelistNotHardcoded:
    """派单白名单必须取自 WasteClass.HIGH_PRIORITY，不能就地硬编码。

    守的缺陷：MQTT 入口（handlers.handle_event）曾写
    `main_class in ("foam", "fishing_gear")`，而 HTTP 入口
    （api/v1/events.py）用的是 WasteClass.HIGH_PRIORITY。
    同一业务规则两处各写一份 —— 改策略时只改一处，
    两条入口的行为就悄悄不一致了。这类漂移没有测试就发现不了。
    """

    def test_handlers_use_constant_not_literal(self, project_root) -> None:
        import ast

        from app.models.event import WasteClass

        src = (project_root / "backend" / "app" / "mqtt" / "handlers.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(src)

        offenders: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or len(node.comparators) != 1:
                continue
            comp = node.comparators[0]
            if not isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                continue
            vals = {
                e.value for e in comp.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            if vals and vals == set(WasteClass.HIGH_PRIORITY):
                offenders.append(node.lineno)

        assert not offenders, (
            f"handlers.py 第 {offenders} 行硬编码了派单白名单 "
            f"{sorted(WasteClass.HIGH_PRIORITY)}，应改用 WasteClass.HIGH_PRIORITY"
        )

    def test_mqtt_and_http_paths_agree(self, project_root) -> None:
        """两条入口对「哪些类别触发派单」必须给出同一答案。

        直接比对两处源码里出现的高优先级类别集合。
        """
        from app.models.event import WasteClass

        root = project_root / "backend" / "app"
        expected = set(WasteClass.HIGH_PRIORITY)

        mqtt_src = (root / "mqtt" / "handlers.py").read_text(encoding="utf-8")
        http_src = (root / "api" / "v1" / "events.py").read_text(encoding="utf-8")

        assert "WasteClass.HIGH_PRIORITY" in mqtt_src, "MQTT 入口未使用 HIGH_PRIORITY 常量"
        assert "WasteClass.HIGH_PRIORITY" in http_src, "HTTP 入口未使用 HIGH_PRIORITY 常量"

        # 常量本身必须覆盖文档承诺的两类
        assert expected == {"foam", "fishing_gear"}, (
            f"HIGH_PRIORITY 与文档承诺（foam / fishing_gear）不符：{sorted(expected)}"
        )


class TestContractDriftCheckerSelfTest:
    """★ 检查脚本自身的自证 —— 防止「永远全绿的检查脚本」。

    本项目反复踩到同一类坑：**校验工具自己静默失效**。
      · 用 `ast.FunctionDef` 分析 handlers.py，5 个 async handler 全部漏掉
        （它们是 AsyncFunctionDef）→ 差点误判「源码里没有这些函数」
      · 路由判据写成 `len(parts) == 5`，该条件对 4 段主题永不成立
        → 脚本自己造出假缺陷
      · 把文档主题总表的「设备 → 平台」当成「平台必须订阅」
        → 把 `marine/{site}/{dev}/cmd/ack` 误报成路由缺失
      · 自证脚本的注入锚点写错（DDL 实为单行写法）→ 该项静默 SKIP

    一个永远返回「全绿」的检查脚本比没有脚本更糟：它给虚假的安全感。
    所以这里既验证它**当前通过**，也验证它**能变红**。
    """

    def test_checker_exists(self, project_root) -> None:
        checker = project_root / "scripts" / "check_contract_drift.py"
        assert checker.exists(), (
            "契约漂移检查脚本不存在 —— Makefile 的 check-contract 会静默什么都不做"
        )

    def test_checker_passes_on_current_code(self, project_root) -> None:
        import subprocess
        import sys

        checker = project_root / "scripts" / "check_contract_drift.py"
        proc = subprocess.run(
            [sys.executable, str(checker)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(project_root),
        )
        fails = [
            ln.strip() for ln in (proc.stdout or "").splitlines() if "[FAIL]" in ln
        ]
        assert proc.returncode == 0, "契约漂移检查未通过：\n" + "\n".join(fails)

    def test_checker_detects_injected_routing_defect(self, project_root) -> None:
        """★ 关键一条：确认脚本**真的会红**。

        实际注入一次历史缺陷（路由判据退回总段数写法），
        跑检查确认退出码非 0，然后还原。
        没有这条，上面那条「通过」毫无意义 —— 脚本可能因为
        解析不到任何检查项而空转通过。
        """
        import subprocess
        import sys

        checker = project_root / "scripts" / "check_contract_drift.py"
        client_py = project_root / "backend" / "app" / "mqtt" / "client.py"
        original = client_py.read_text(encoding="utf-8")

        good = (
            '            if parts[2] == "cmd" and parts[3] == "ack":\n'
            '                return "handle_robot_ack"'
        )
        bad = (
            '        if len(parts) == 5 and parts[0] == "robot":\n'
            '            if parts[3] == "cmd" and parts[4] == "ack":\n'
            '                return "handle_robot_ack"'
        )

        if good not in original:
            pytest.skip("client.py 路由实现已变动，自证锚点失效 —— 请更新本条测试")

        try:
            client_py.write_text(original.replace(good, bad, 1), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(checker)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(project_root),
            )
            assert proc.returncode != 0, (
                "注入了 robot/cmd/ack 路由缺陷，检查脚本仍然返回全绿 —— "
                "该检查项已失效，必须修复后才能依赖它"
            )
        finally:
            client_py.write_text(original, encoding="utf-8")

    def test_checker_restored_after_selftest(self, project_root) -> None:
        """自证注入必须还原干净，否则会污染后续测试与工作区。"""
        client_py = project_root / "backend" / "app" / "mqtt" / "client.py"
        src = client_py.read_text(encoding="utf-8")
        assert 'if parts[3] == "cmd" and parts[4] == "ack"' not in src, (
            "上一轮自证注入未还原！client.py 仍带着 `len(parts) == 5` 的历史缺陷"
        )
        assert 'parts[2] == "cmd" and parts[3] == "ack"' in src, (
            "client.py 的 robot cmd/ack 路由结构判据不见了"
        )

    def test_full_selftest_suite_passes(self, project_root) -> None:
        """跑完整的 8 项注入自证，确认全部命中且锚点未失效。

        这条比上面单独注入一条更严：它会捕获「某项锚点失效被静默跳过」
        —— 那种情况自证报告看起来是过的，实际覆盖率已经掉了。
        """
        import subprocess
        import sys

        script = project_root / "scripts" / "selftest_contract_drift.py"
        assert script.exists(), "自证脚本不存在，无法验证检查脚本的有效性"

        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(project_root),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        assert proc.returncode == 0, (
            "自查脚本自证未通过（存在未被捕获的注入或锚点失效）：\n"
            + "\n".join(
                ln for ln in out.splitlines()
                if "[SKIP]" in ln or "[FAIL]" in ln or "锚点失效" in ln
            )
        )
        assert "锚点失效   : 0" in out, f"有注入项锚点失效，自证覆盖率下降：\n{out[-600:]}"




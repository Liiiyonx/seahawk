"""报表聚合的纯逻辑测试 + 接线守卫。

报表聚合的 SQL 依赖 PostgreSQL/PostGIS（conftest 约定单元测试不连库），
所以这里分两层验证：
1. **纯函数** `nearest_township`（乡镇归属唯一实现）—— 直接断言。
2. **接线守卫**（AST/文本）—— 断言「定时任务真的挂上了」「手动端点
   真的调了聚合函数」，防止重演「docstring 声称有报表聚合、实现却没有」
   的静默缺陷。
3. **真源对账** —— `TOWNSHIPS` 与 seed.sql、前端 constants.js 逐项一致，
   防止乡镇列表在第三处漂移。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.report import TOWNSHIPS, nearest_township


# ----------------------------------------------------------------------
# 1. 乡镇归属纯函数
# ----------------------------------------------------------------------
class TestNearestTownship:
    def test_each_center_maps_to_itself(self) -> None:
        """每个乡镇中心点必须归到自己（归属逻辑不自相矛盾）。"""
        for name, lng, lat in TOWNSHIPS:
            assert nearest_township(lng, lat) == name, (
                f"乡镇中心点 ({lng}, {lat}) 应归属 {name}，"
                f"实际归到了 {nearest_township(lng, lat)}"
            )

    def test_off_center_points(self) -> None:
        """偏移点归属最近乡镇（不是简单地返回第一个匹配）。"""
        # 黄岐(119.904,26.316) 与 筱埕(119.836,26.352) 之间，偏向黄岐
        assert nearest_township(119.890, 26.325) == "黄岐镇"
        # 马鼻(119.652,26.386) 与 安凯(119.760,26.420) 之间，偏向安凯
        assert nearest_township(119.740, 26.410) == "安凯镇"

    def test_return_type_and_membership(self) -> None:
        """返回的乡镇名必须来自 TOWNSHIPS 本身（不出现幽灵名字）。"""
        names = {n for n, _, _ in TOWNSHIPS}
        for lng, lat in [(119.7, 26.4), (119.9, 26.3), (120.0, 26.35)]:
            assert nearest_township(lng, lat) in names


# ----------------------------------------------------------------------
# 2. 真源对账（乡镇列表不得在多处漂移）
# ----------------------------------------------------------------------
class TestTownshipSources:
    def test_townships_match_seed_sql(self, project_root: Path) -> None:
        """TOWNSHIPS 与 02_seed.sql 注释里的乡镇坐标逐项一致。"""
        seed = (project_root / "backend/db/init/02_seed.sql").read_text(encoding="utf-8")
        # 注释格式：--   马鼻镇   ~ (119.652, 26.386)
        found = {}
        for name, lng, lat in re.findall(
            r"--\s*([^\s~]+)\s*~\s*\(([\d.]+),\s*([\d.]+)\)", seed
        ):
            found[name] = (float(lng), float(lat))

        expected = {name: (lng, lat) for name, lng, lat in TOWNSHIPS}
        assert found == expected, (
            "02_seed.sql 注释里的乡镇坐标与 services/report.py 的 TOWNSHIPS 不一致：\n"
            f"  seed 有、TOWNSHIPS 缺：{set(found) - set(expected)}\n"
            f"  TOWNSHIPS 有、seed 缺：{set(expected) - set(found)}\n"
            "两者必须逐字一致，否则「事件归属乡镇」与演示种子数据对不上。"
        )

    def test_townships_match_frontend(self, project_root: Path) -> None:
        """TOWNSHIPS 乡镇名与前端 constants.js 的 TOWNSHIPS 列表一致。"""
        js = (project_root / "frontend/src/utils/constants.js").read_text(encoding="utf-8")
        m = re.search(r"TOWNSHIPS\s*=\s*\[([^\]]*)\]", js)
        assert m, "frontend/src/utils/constants.js 里找不到 TOWNSHIPS 定义"

        front_names = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
        back_names = [name for name, _, _ in TOWNSHIPS]
        assert front_names == back_names, (
            "前端 TOWNSHIPS 与后端 TOWNSHIPS 顺序/内容不一致：\n"
            f"  前端：{front_names}\n  后端：{back_names}\n"
            "乡镇列表是第三处定义，一旦漂移，报表筛选与归属就会对不上。"
        )


# ----------------------------------------------------------------------
# 3. 接线守卫：定时任务与手动端点真的接上了聚合函数
# ----------------------------------------------------------------------
def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


class TestAggregateWiring:
    def test_worker_scheduled_in_main(self, project_root: Path) -> None:
        """main.py 必须真的 create_task(daily_report_worker())。

        历史缺陷：main.py 的 docstring 写了「启动报表聚合」，
        实现却只启动补派。docstring 与实现的错位 grep 抓不到，
        必须用 AST 断言 `asyncio.create_task` 的实参里出现了
        `daily_report_worker`。
        """
        tree = _parse(project_root / "backend/app/main.py")
        scheduled = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # asyncio.create_task(...) 或 create_task(...)
            fn = node.func
            if not isinstance(fn, ast.Attribute) or fn.attr != "create_task":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                    if arg.func.id == "daily_report_worker":
                        scheduled = True
        assert scheduled, (
            "main.py 没有 asyncio.create_task(daily_report_worker()) —— "
            "报表聚合定时任务未挂载，t_report_daily 永远不会被真实生产。"
        )

    def test_aggregate_called_by_endpoint(self, project_root: Path) -> None:
        """reports.py 的手动端点必须真的调用 aggregate_daily。"""
        tree = _parse(project_root / "backend/app/api/v1/reports.py")
        called = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "aggregate_daily":
                    called = True
        assert called, (
            "reports.py 没有任何地方调用 aggregate_daily —— "
            "手动触发报表聚合的端点没有接线。"
        )

    def test_aggregate_function_exists_and_is_async(self, project_root: Path) -> None:
        """聚合函数本身存在且是 async（用 AsyncSession 执行 SQL）。"""
        tree = _parse(project_root / "backend/app/services/report.py")
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "aggregate_daily":
                found = True
        assert found, "services/report.py 缺少 async aggregate_daily 函数"

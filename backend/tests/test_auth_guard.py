"""认证与权限守卫测试。

覆盖两层：
1. **令牌真伪** —— 令牌签发/解析往返、无令牌匿名、篡改提权被拒、过期被拒。
   历史缺陷：get_current_user 从 X-User/X-Role 头读身份，那是**前端可伪造**的，
   「有权限」其实是「没权限」——用户改一下 localStorage 就能把自己改成 admin。
2. **写接口接线** —— require_operator 曾经「定义完整但零路由引用」，
   任何匿名请求都能改工单状态。这里用 AST 钉住三个写接口真的挂了它。
"""

from __future__ import annotations

import asyncio
import ast
import base64
import hashlib
import json
import time
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user, require_operator
from app.core.exceptions import AppException
from app.api.v1.auth import _issue_token


def _auth(token: str | None) -> CurrentUser:
    """模拟 FastAPI 依赖注入：直接调用 get_current_user 传 Authorization 头。"""
    header = f"Bearer {token}" if token else None
    return asyncio.run(get_current_user(authorization=header))


class TestTokenAuth:
    def test_roundtrip(self) -> None:
        token = _issue_token("operator", "operator", "马鼻镇")
        u = _auth(token)
        assert u.username == "operator"
        assert u.role == "operator"
        assert u.township_scope == "马鼻镇"

    def test_no_token_is_anonymous_readonly(self) -> None:
        u = _auth(None)
        assert u.username == "anonymous"
        assert u.role == "viewer"
        assert u.can_write is False

    def test_tampered_role_escalation_rejected(self) -> None:
        """把 viewer 令牌的载荷改成 admin，但签名不匹配 → 必须退回匿名。

        这是「真权限」的核心：角色来自服务端签名，前端改不了。
        """
        token = _issue_token("viewer", "viewer", None)
        body, sig = token.rsplit(".", 1)
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        payload["role"] = "admin"  # 尝试提权
        forged_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        forged = f"{forged_body}.{sig}"  # 签名仍是旧 body 的，无法匹配新 body

        u = _auth(forged)
        assert u.role == "viewer", "篡改后的令牌必须被拒绝为匿名，而不是放行 admin"

    def test_expired_token_rejected(self) -> None:
        payload = {"sub": "admin", "role": "admin", "scope": None, "exp": int(time.time()) - 1000}
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hashlib.sha256(f"{body}.{settings.secret_key}".encode()).hexdigest()[:32]

        u = _auth(f"{body}.{sig}")
        assert u.role == "viewer", "过期令牌必须被拒绝"


class TestRequireOperator:
    def test_rejects_viewer(self) -> None:
        with pytest.raises(AppException):
            asyncio.run(require_operator(CurrentUser("v", "viewer", None)))

    def test_rejects_anonymous(self) -> None:
        with pytest.raises(AppException):
            asyncio.run(require_operator(CurrentUser("anonymous", "viewer", None)))

    def test_allows_operator(self) -> None:
        u = asyncio.run(require_operator(CurrentUser("op", "operator", "马鼻镇")))
        assert u.role == "operator"

    def test_allows_admin(self) -> None:
        u = asyncio.run(require_operator(CurrentUser("ad", "admin", None)))
        assert u.role == "admin"


class TestWriteEndpointsGuarded:
    """★ 接线守卫：三个写接口真的挂了 require_operator。

    历史缺陷：require_operator 定义完整、grep 也搜得到，但**零路由引用**，
    于是匿名请求也能改工单状态 —— 「声明了权限、没接上」的静默缺陷。
    """

    WRITE_HANDLERS = {"create_task", "update_task_status", "dispatch_pending"}

    def test_write_handlers_require_operator(self, project_root: Path) -> None:
        src = (project_root / "backend/app/api/v1/tasks.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        guarded: dict[str, bool] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seg = ast.get_source_segment(src, node) or ""
                guarded[node.name] = "require_operator" in seg

        missing = [n for n in self.WRITE_HANDLERS if not guarded.get(n)]
        assert not missing, (
            f"写接口未挂 require_operator 依赖：{missing}。\n"
            "匿名/viewer 将可以改工单状态，权限形同虚设。"
        )

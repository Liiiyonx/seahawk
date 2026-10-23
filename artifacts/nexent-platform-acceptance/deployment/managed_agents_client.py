#!/usr/bin/env python3
"""
ClawAgent WebSocket 原生客户端

5 步完成与后端的 WebSocket 交互，代码尽量精简，方便理解。

依赖: pip install websockets>=10.0

用法:
  python managed_agents_client.py --url "ws://..." --auth "Bearer xxx" --message "你好"
  python managed_agents_client.py --url "ws://..." --auth "Bearer xxx" --session-id "SC_xxx" --message "你好"
  # IAM 认证（V11-HMAC-SHA256 签名，自动计算）
  python managed_agents_client.py --url "ws://..." --auth-type iam --ak "AK" --sk "SK" --session-id "SC_xxx" --message "你好"
"""

import asyncio
import json
import sys
import time
import uuid
import argparse
from urllib.parse import urlparse

try:
    import websockets
except ImportError:
    print("请安装依赖: pip install websockets>=10.0")
    sys.exit(1)


def build_iam_headers(url, args):
    """用 apig_sdk 计算 V11-HMAC-SHA256 签名，返回 IAM 认证请求头。

    签名规范与网关一致（已实测 101 通过）：
      - CanonicalURI 强制以 '/' 结尾（SDK 内部处理）
      - 密钥派生 = HKDF（signer_v11._hkdf）
      - payload 表示 = X-Sdk-Content-Sha256: UNSIGNED-PAYLOAD
      - host 由 HttpRequest 从 url 自动解析，不额外传，避免重复 Host
      - X-Sdk-Date 由 Sign() 自动取当前 UTC 时间，与签名时间戳天然一致
    """
    from apig_sdk import signer  # 延迟导入，缺依赖时不影响默认模式

    req = signer.HttpRequest(
        "GET", url,
        {
            "Content-Type": "application/json",
            "x-sdk-content-sha256": "UNSIGNED-PAYLOAD",
            "x-hw-agentarts-session-id": args.session_id,
        },
        "",
    )
    sig = signer.Signer(algorithm="V11-HMAC-SHA256", region_id="cn-southwest-2")
    sig.Key = args.ak
    sig.Secret = args.sk
    sig.Sign(req)
    return {
        "Authorization": req.headers["Authorization"],
        "Content-Type": "application/json",
        "X-Sdk-Content-Sha256": "UNSIGNED-PAYLOAD",
        "X-Sdk-Date": req.headers["X-Sdk-Date"],
        "x-hw-agentarts-session-id": args.session_id,
    }


async def main():
    args = parse_args()
    message = args.message or "你好"

    # ── 1. 构建认证头 ─────────────────────────────────────────
    # 这些 HTTP 头在 WS 握手时发送，后端据此鉴权
    p = urlparse(args.url)
    headers = {
        "Authorization": args.auth,
        "x-hw-agentarts-session-id": args.session_id,
        "X-HW-AgentArts-Claw-User-Id": args.user_id,
        "X-HW-AgentGateway-Chat-Id": args.chat_id,
        "Origin": f"{'http' if p.scheme == 'ws' else 'https'}://{p.netloc}",
    }
    # IAM 认证：用 apig_sdk 现场计算 V11-HMAC-SHA256 签名
    if args.auth_type == "iam":
        headers.update(build_iam_headers(args.url, args))
    # ── 2. 连接 WebSocket ─────────────────────────────────────
    # compression=None: 后端不支持压缩
    # additional_headers(>=12.0) / extra_headers(旧版) 兼容
    try:
        ws = await websockets.connect(args.url, additional_headers=headers, compression=None)
    except TypeError:
        ws = await websockets.connect(args.url, extra_headers=headers, compression=None)
    print(f"[2/5] 已连接 {args.url}")

    try:
        # ── 3. 等待 connection.ack ────────────────────────────
        # 后端握手后会发 connection.ack，表示服务端就绪
        async for raw in ws:
            f = json.loads(raw)
            if f.get("type") == "event" and f.get("event") == "connection.ack":
                break
        print("[3/5] 服务端就绪")

        # ── 4. 发送消息 ───────────────────────────────────────
        # chat.send 是发消息的请求方法，is_stream=True 表示流式返回
        await ws.send(json.dumps({
            "request_id": str(uuid.uuid4()),
            "channel_id": args.channel_id,
            "session_id": "session_default",
            "chat_id": args.chat_id,
            "req_method": "chat.send",
            "params": {"query": message, "mode": "agent.plan", "interactive_ask": True},
            "metadata": {"user_id": args.user_id},
            "is_stream": True,
            "timestamp": time.time(),
        }))
        print(f"[4/5] 已发送: {message}\n")

        # ── 5. 接收回复 ───────────────────────────────────────
        # 循环读取每一帧，提取文本直到对话结束
        reply = ""
        async for raw in ws:
            print(f"\n[Frame] {raw}", flush=True)
            f = json.loads(raw)

            # 后端有两种帧格式，这里统一提取 payload
            if f.get("response_kind"):  # E2A 格式
                body = f.get("body") or {}
                if f.get("is_final"):  # 最终帧
                    result = body.get("result") or {}
                    event = result.get("event_type", "chat.final")
                    text = result.get("content", "")
                elif f.get("response_kind") == "e2a.error":
                    print(f"\n[Error] {body.get('message', '未知错误')}")
                    break
                else:  # 增量帧
                    event = body.get("event_type", "chat.delta")
                    delta = body.get("delta")
                    text = delta if isinstance(delta, str) else ""
            else:  # Legacy 格式
                payload = f.get("payload") or {}
                event = payload.get("event_type", "")
                text = payload.get("content", "")

            # 权限请求 → 自动授权
            if f.get("tag") == "TOOL_PERMISSION" and f.get("decision") == "ASK":
                await ws.send(json.dumps({**f, "decision": "GRANT", "source": "user", "scope": "once"}))
                continue

            # 后端提问 → 自动选第一个选项
            if event == "chat.ask_user_question":
                qs = (f.get("payload") or {}).get("questions") or []
                opts = (qs[0] if qs else {}).get("options") or []
                ans = opts[0].get("label", "") if opts else ""
                is_perm = (f.get("payload") or {}).get("source", "permission_interrupt") == "permission_interrupt"
                await ws.send(json.dumps({
                    "request_id": str(uuid.uuid4()),
                    "channel_id": args.channel_id,
                    "session_id": "session_default",
                    "chat_id": args.chat_id,
                    "req_method": "chat.resume" if is_perm else "chat.user_answer",
                    "params": {"request_id": (f.get("payload") or {}).get("request_id", ""),
                               "answers": [{"selected_options": [ans]}],
                               "source": (f.get("payload") or {}).get("source", "permission_interrupt")},
                    "metadata": {"user_id": args.user_id},
                    "is_stream": is_perm,
                    "timestamp": time.time(),
                }))
                continue

            # 流式文本 → 累积并打印
            if text and event in ("chat.delta", "chat.final"):
                reply += text
                print(text, end="", flush=True)

            # 结束信号
            if event in ("chat.final", "chat.done", "chat.error"):
                break
            if f.get("is_complete") or f.get("type") == "done":
                break

        print(f"\n\n{'='*40}")
        print(f"回复: {reply}")

    finally:
        await ws.close()
        print(f"{'='*40}\n[5/5] 已断开")


def parse_args():
    p = argparse.ArgumentParser(description="ClawAgent WebSocket 原生客户端")
    p.add_argument("--url", required=True, help="WebSocket 地址")
    p.add_argument("--auth", default="", help="Authorization 头 (如: Bearer xxx)")
    p.add_argument("--auth-type", choices=["bearer", "iam"], default="bearer", help="认证类型 (默认: bearer; iam 用 AK/SK 自动签名)")
    p.add_argument("--ak", default="", help="Access Key (iam 认证必填)")
    p.add_argument("--sk", default="", help="Secret Key (iam 认证必填)")
    p.add_argument("--session-id", default="", help="Session ID")
    p.add_argument("--user-id", default="user_default", help="User ID (默认: user_default)")
    p.add_argument("--chat-id", default="chat1", help="Chat ID (默认: chat1)")
    p.add_argument("--channel-id", default="officeclaw", help="Channel ID (默认: officeclaw)")
    p.add_argument("--message", default=None, help="消息内容 (默认: 你好)")
    args = p.parse_args()
    if args.auth_type == "iam" and (not args.ak or not args.sk):
        print("[错误] iam 认证必须提供 --ak 和 --sk")
        sys.exit(1)
    return args


if __name__ == "__main__":
    asyncio.run(main())

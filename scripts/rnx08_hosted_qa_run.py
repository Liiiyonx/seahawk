#!/usr/bin/env python3
"""R-NX-08 one-shot rerun: hosted AgentArts managed-agent Skill QA via WebSocket.

Rebuilds the invocation channel verified on 2026-10-02 (R-NX-08 record) on top
of Huawei's official ``managed_agents_client`` protocol:

    wss://<endpoint>/runtimes/<runtime_name>/ws
    headers: Authorization Bearer <Agent Identity API Key>,
             x-hw-agentarts-session-id / X-HW-AgentArts-Claw-User-Id /
             X-HW-AgentGateway-Chat-Id / Origin
    compression disabled; watchdog.initialized + connection.ack then chat.send.

Credentials are read from ``SEASIGHT_AGENTARTS_ENV`` (default
``D:/VeriCall_data/secrets/seasight_agentarts.env``, never committed).

Evidence is written to
``artifacts/nexent-platform-acceptance/evidence/hosted-qa-<UTC date>/``:
``hosted-ws-run-frames.json`` (all frames, masked), ``hosted-ws-answer.txt``,
and a console verdict.  A run only counts as complete when a non-empty final
answer arrives -- keepalive-only or model-timeout text is recorded as
``not_completed`` with the observed reason.

Usage:
    python scripts/rnx08_hosted_qa_run.py                # standard question
    python scripts/rnx08_hosted_qa_run.py --max-seconds 480
    python scripts/rnx08_hosted_qa_run.py --question "..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SECRET_ENV = os.environ.get(
    "SEASIGHT_AGENTARTS_ENV", "D:/VeriCall_data/secrets/seasight_agentarts.env"
)
STANDARD_QUESTION = (
    "连江县海漂垃圾治理中，岸基监控发现疑似漏油事件，"
    "请按照现有政策给出评估与处置建议，并给出证据链。"
)

EXIT_COMPLETED = 0
EXIT_INCOMPLETE = 1
EXIT_NOT_CONFIGURED = 2


def load_secret_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def mask(text: str) -> str:
    secret = os.environ.get("_RNX08_KEY", "")
    if secret and secret in text:
        return text.replace(secret, "***MASKED***")
    return text


async def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    import websockets

    env = load_secret_env(args.secret_env)
    api_key = env.get("SEASIGHT_AGENTARTS_API_KEY", "")
    endpoint = env.get("SEASIGHT_AGENTARTS_ENDPOINT", "")
    runtime_name = env.get("SEASIGHT_AGENTARTS_RUNTIME_NAME", "")
    if not (api_key and endpoint and runtime_name):
        print(
            "[not-configured] 密钥文件缺少 SEASIGHT_AGENTARTS_API_KEY / "
            "_ENDPOINT / _RUNTIME_NAME"
        )
        return EXIT_NOT_CONFIGURED, {}
    os.environ["_RNX08_KEY"] = api_key

    ws_url = f"wss://{endpoint}/runtimes/{runtime_name}/ws"
    session_id = f"seasight-rnx08-{int(time.time() * 1000)}"
    chat_id = f"chat-{session_id}"
    user_id = "user_default"
    channel_id = "officeclaw"
    question = args.question or STANDARD_QUESTION

    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-hw-agentarts-session-id": session_id,
        "X-HW-AgentArts-Claw-User-Id": user_id,
        "X-HW-AgentGateway-Chat-Id": chat_id,
        "Origin": "https://" + endpoint,
    }

    frames: list[dict[str, Any]] = []
    log: list[str] = []
    reply = ""
    verdict = "not_completed"
    close_reason = ""

    def send_frame(frame: dict[str, Any]) -> str:
        return json.dumps(frame, ensure_ascii=False)

    try:
        try:
            ws = await websockets.connect(
                ws_url, additional_headers=headers, compression=None,
                open_timeout=30,
            )
        except TypeError:  # websockets<12
            ws = await websockets.connect(
                ws_url, extra_headers=headers, compression=None, open_timeout=30
            )
        log.append("ws open")
    except Exception as exc:
        print(f"[failed] WebSocket 握手失败: {exc}")
        return EXIT_INCOMPLETE, {
            "ok": False, "stage": "handshake", "error": str(exc),
            "ws_url_host": endpoint,
        }

    started = time.monotonic()

    async def deadline_left() -> float:
        return args.max_seconds - (time.monotonic() - started)

    try:
        # 1) 等 connection.ack
        acked = False
        async for raw in ws:
            frame = json.loads(raw)
            frames.append(frame)
            if (
                frame.get("type") == "event"
                and frame.get("event") == "connection.ack"
            ):
                acked = True
                break
            if await deadline_left() <= 0:
                break
        if not acked:
            close_reason = "no connection.ack within budget"
            return EXIT_INCOMPLETE, await asyncio.to_thread(_summarize, frames, reply, verdict, close_reason, log)
        log.append("ack -> send query")

        # 2) chat.send
        await ws.send(send_frame({
            "request_id": str(uuid.uuid4()),
            "channel_id": channel_id,
            "session_id": "session_default",
            "chat_id": chat_id,
            "req_method": "chat.send",
            "params": {"query": question, "mode": "agent.plan", "interactive_ask": True},
            "metadata": {"user_id": user_id},
            "is_stream": True,
            "timestamp": time.time(),
        }))

        # 3) 收帧直到 chat.final/done/error 或预算耗尽
        async for raw in ws:
            if await deadline_left() <= 0:
                close_reason = "budget exhausted"
                log.append("deadline hit")
                break
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            frames.append(frame)

            payload = frame.get("payload") or {}
            body = frame.get("body") or {}
            if frame.get("response_kind"):
                event = (
                    (body.get("result") or {}).get("event_type", "chat.final")
                    if frame.get("is_final")
                    else body.get("event_type", "chat.delta")
                )
                delta = body.get("delta")
                text = (
                    (body.get("result") or {}).get("content", "")
                    if frame.get("is_final")
                    else (delta if isinstance(delta, str) else "")
                )
                if frame.get("response_kind") == "e2a.error":
                    close_reason = str(body.get("message", "e2a error"))
                    log.append(f"e2a.error: {close_reason}")
                    break
            else:
                event = payload.get("event_type", "")
                text = payload.get("content", "")

            if frame.get("tag") == "TOOL_PERMISSION" and frame.get("decision") == "ASK":
                await ws.send(send_frame(
                    {**frame, "decision": "GRANT", "source": "user", "scope": "once"}
                ))
                log.append("tool permission granted")
                continue
            if event == "chat.ask_user_question":
                questions = payload.get("questions") or []
                options = (questions[0] if questions else {}).get("options") or []
                answer = options[0].get("label", "") if options else ""
                is_perm = payload.get("source", "permission_interrupt") == "permission_interrupt"
                await ws.send(send_frame({
                    "request_id": str(uuid.uuid4()),
                    "channel_id": channel_id,
                    "session_id": "session_default",
                    "chat_id": chat_id,
                    "req_method": "chat.resume" if is_perm else "chat.user_answer",
                    "params": {
                        "request_id": payload.get("request_id", ""),
                        "answers": [{"selected_options": [answer]}],
                        "source": payload.get("source", "permission_interrupt"),
                    },
                    "metadata": {"user_id": user_id},
                    "is_stream": is_perm,
                    "timestamp": time.time(),
                }))
                log.append(f"ask_user answered: {answer[:40]}")
                continue

            if text and event in ("chat.delta", "chat.final"):
                reply += text
                print(text, end="", flush=True)
            if event in ("chat.final", "chat.done", "chat.error"):
                verdict = "completed" if reply.strip() else "not_completed"
                log.append(f"terminal frame: {event}")
                break
            if frame.get("is_complete") or frame.get("type") == "done":
                verdict = "completed" if reply.strip() else "not_completed"
                log.append("done frame")
                break
    except Exception as exc:  # noqa: BLE001
        close_reason = f"{type(exc).__name__}: {exc}"
        log.append(f"exception: {close_reason}")
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass

    elapsed = round(time.monotonic() - started, 1)
    summary = _summarize(frames, reply, verdict, close_reason or f"closed after {elapsed}s", log)
    summary.update(
        {
            "session_id": session_id,
            "question": question,
            "duration_s": elapsed,
            "ws_url_host": endpoint,
            "runtime_name": runtime_name,
        }
    )
    return (EXIT_COMPLETED if verdict == "completed" else EXIT_INCOMPLETE), summary


def _summarize(
    frames: list[dict[str, Any]],
    reply: str,
    verdict: str,
    close_reason: str,
    log: list[str],
) -> dict[str, Any]:
    event_types: dict[str, int] = {}
    for frame in frames:
        kind = frame.get("type", "?")
        event = frame.get("event") or (frame.get("payload") or {}).get("event_type") or ""
        key = f"{kind}.{event}" if event else kind
        event_types[key] = event_types.get(key, 0) + 1
    model_error_pattern = "模型调用异常" in reply or "请求超时" in reply
    if verdict != "completed" and model_error_pattern:
        verdict = "model_error"
    return {
        "ok": verdict == "completed",
        "verdict": verdict,
        "close_reason": close_reason,
        "frame_count": len(frames),
        "event_types": event_types,
        "answer": reply,
        "frames": frames,
        "log": log,
    }


def save_evidence(summary: dict[str, Any]) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = (
        ROOT
        / "artifacts"
        / "nexent-platform-acceptance"
        / "evidence"
        / f"hosted-qa-{date}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_path = out_dir / "hosted-ws-run-frames.json"
    document = {
        "acceptance_id": "R-NX-08",
        "platform": "huawei-agentarts-hosted",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in summary.items()},
    }
    frames_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    answer_path = out_dir / "hosted-ws-answer.txt"
    answer_path.write_text(
        mask(summary.get("answer", "")), encoding="utf-8"
    )
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-env", default=DEFAULT_SECRET_ENV)
    parser.add_argument("--question", default="")
    parser.add_argument("--max-seconds", type=int, default=840)
    args = parser.parse_args()

    if not Path(args.secret_env).exists():
        print(f"[not-configured] 密钥文件不存在: {args.secret_env}")
        return EXIT_NOT_CONFIGURED

    code, summary = asyncio.run(run(args))
    if not summary:
        return code
    out_dir = save_evidence(summary)
    print()
    print("=" * 46)
    print(f"verdict: {summary.get('verdict')}")
    print(f"frames: {summary.get('frame_count')} | duration: {summary.get('duration_s')}s")
    print(f"events: {summary.get('event_types')}")
    print(f"evidence: {out_dir}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

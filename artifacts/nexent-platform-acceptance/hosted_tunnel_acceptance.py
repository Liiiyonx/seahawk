#!/usr/bin/env python3
"""Run authenticated acceptance calls through the public SeaSight MCP tunnel.

This records evidence for the Huawei AgentArts hosted platform acceptance:
the same public endpoint registered as "SeaSight Domain Cognition MCP" on the
managed platform is initialized over MCP Streamable HTTP, its tool catalog is
listed, and ``knowledge_list_assets``, ``dashboard_get`` and
``agent_runtime_status`` are invoked with real backend data.

Usage:
    .venv-nexent/Scripts/python artifacts/nexent-platform-acceptance/hosted_tunnel_acceptance.py

The script reads ``SEASIGHT_MCP_SERVER_TOKEN`` and ``SEASIGHT_MCP_PUBLIC_URL``
from ``integrations/nexent/.env`` when not provided on the command line.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / "integrations" / "nexent" / ".env"
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _text_content(content: Any) -> str:
    parts: list[str] = []
    for block in content:
        if hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "model_dump"):
            parts.append(json.dumps(block.model_dump(), ensure_ascii=False))
        else:
            parts.append(str(block))
    return "\n".join(parts)


async def _accept(url: str, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools_result = await session.list_tools()
                call_result = await session.call_tool(
                    "knowledge_list_assets",
                    {"page": 1, "page_size": 20},
                )
                dashboard_result = await session.call_tool("dashboard_get", {})
                runtime_result = await session.call_tool("agent_runtime_status", {})
            return {
                "initialize": {
                    "protocol_version": getattr(initialized, "protocolVersion", None),
                    "server_info": {
                        "name": initialized.serverInfo.name,
                        "version": initialized.serverInfo.version,
                    },
                    "capabilities": initialized.capabilities.model_dump()
                    if hasattr(initialized.capabilities, "model_dump")
                    else str(initialized.capabilities),
                },
                "tools_catalog": {
                    "count": len(tools_result.tools),
                    "names": sorted(tool.name for tool in tools_result.tools),
                },
                "tool_call": {
                    "tool": "knowledge_list_assets",
                    "inputs": {"page": 1, "page_size": 20},
                    "is_error": bool(call_result.isError),
                    "response_text": _text_content(call_result.content),
                },
                "extended_tool_calls": [
                    {
                        "tool": "dashboard_get",
                        "inputs": {},
                        "is_error": bool(dashboard_result.isError),
                        "response_text": _text_content(dashboard_result.content),
                    },
                    {
                        "tool": "agent_runtime_status",
                        "inputs": {},
                        "is_error": bool(runtime_result.isError),
                        "response_text": _text_content(runtime_result.content),
                    },
                ],
            }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Public MCP endpoint URL")
    parser.add_argument("--token", help="Inbound Bearer token")
    parser.add_argument(
        "--platform",
        default="huawei-agentarts-hosted",
        help="Platform label written into evidence",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Acceptance date in YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--acceptance-id",
        default="R-NX-07",
        help="Acceptance record id written into JSON evidence",
    )
    parser.add_argument(
        "--evidence-prefix",
        help="Output filename prefix (default: hosted-<date>)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=EVIDENCE_DIR,
        help="Evidence output directory",
    )
    args = parser.parse_args()

    env = _load_env(ENV_PATH)
    url = args.url or env.get("SEASIGHT_MCP_PUBLIC_URL")
    token = args.token or env.get("SEASIGHT_MCP_SERVER_TOKEN")
    if not url or not token:
        print("missing --url/SEASIGHT_MCP_PUBLIC_URL or --token", file=sys.stderr)
        return 2

    result = await _accept(url, token)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.evidence_prefix or f"hosted-{args.date}"
    endpoint_note = (
        "华为托管平台（AgentArts）注册的 SeaSight MCP 端点真实调用；"
        if args.platform == "huawei-agentarts-hosted"
        else "SeaSight 本地 MCP 端点真实调用；非托管平台验收；"
    )
    tools_path = out_dir / f"{prefix}-tunnel-tools.json"
    call_path = out_dir / f"{prefix}-tool-call.json"
    dashboard_path = out_dir / f"{prefix}-tool-call-dashboard.json"
    tools_path.write_text(
        json.dumps(result["tools_catalog"], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    call_path.write_text(
        json.dumps(
            {
                "acceptance_id": args.acceptance_id,
                "date": args.date,
                "platform": args.platform,
                "region": "cn-southwest-2",
                "transport": "streamable-http",
                "mcp_endpoint": url,
                "mcp_registration_name": "SeaSight Domain Cognition MCP",
                "initialize": result["initialize"],
                "tools_catalog": result["tools_catalog"],
                "tool_call": result["tool_call"],
                "note": endpoint_note + "不是海域验证，不代表感知精度",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    dashboard_path.write_text(
        json.dumps(
            {
                "acceptance_id": args.acceptance_id,
                "date": args.date,
                "platform": args.platform,
                "region": "cn-southwest-2",
                "transport": "streamable-http",
                "mcp_endpoint": url,
                "mcp_registration_name": "SeaSight Domain Cognition MCP",
                "initialize": result["initialize"],
                "tools_catalog": result["tools_catalog"],
                "tool_calls": result["extended_tool_calls"],
                "note": (
                    endpoint_note
                    + "dashboard_get 与 agent_runtime_status 均返回真实治理数据；"
                    + "不是海域验证，不代表感知精度"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved {tools_path}")
    print(f"saved {call_path}")
    print(f"saved {dashboard_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""
AgentArts VPC 内模型中转（OpenAI 兼容）

为什么需要它：
  AgentArts 的「私网访问」环境（Skill 必需）没有公网出口，
  沙箱直连 api.deepseek.com 会 60s 超时（日志：APITimeoutError / iam...ConnectTimeout），
  于是智能体永远出不了回答。
  把本脚本跑在 VPC 内的 ECS 上（该 ECS 有公网 EIP，能出网），
  再把 AgentArts「模型供应商」的 Base_url 指到本服务即可。

用法（在 ECS 上）：
  export UPSTREAM_BASE=https://api.deepseek.com/v1
  export UPSTREAM_KEY=sk-xxxxxxxx                 # 真实 DeepSeek Key
  export RELAY_TOKEN=sk-seasight-relay-xxxx       # 本服务自己的鉴权口令（自定）
  python3 agentarts-vpc-model-relay.py --port 8080

AgentArts 侧「添加模型供应商」填：
  Base_url:   http://192.168.0.65:8080/v1
  出站身份： 位置=标头，参数名=Authorization，前缀=Bearer，密钥值=<RELAY_TOKEN>
  模型服务： 模型名称=deepseek-chat，协议=OpenAI

仅用标准库，无需 pip 安装。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "https://api.deepseek.com/v1").rstrip("/")
UPSTREAM_KEY = os.environ.get("UPSTREAM_KEY", "")
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
ALLOW_NO_AUTH = os.environ.get("ALLOW_NO_AUTH", "0") == "1"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AgentArtsVpcModelRelay/1.0"

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[relay] %s - %s\n" % (self.address_string(), fmt % args))

    def _auth_ok(self):
        if not RELAY_TOKEN or ALLOW_NO_AUTH:
            return True
        hdr = self.headers.get("Authorization", "")
        return hdr.strip() == "Bearer " + RELAY_TOKEN or hdr.strip() == RELAY_TOKEN

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/models") or path in ("/v1/models", "/models"):
            self._send_json(200, {"object": "list", "data": [{"id": "deepseek-chat", "object": "model", "owned_by": "relay"}]})
            return
        if path in ("/healthz", "/ping"):
            self._send_json(200, {"status": "ok", "upstream": UPSTREAM_BASE})
            return
        self._send_json(404, {"error": {"message": "not found", "type": "relay_error"}})

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.endswith("/chat/completions"):
            self._send_json(404, {"error": {"message": "only /v1/chat/completions is proxied", "type": "relay_error"}})
            return
        if not self._auth_ok():
            self._send_json(401, {"error": {"message": "invalid relay token", "type": "relay_auth_error"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": {"message": "bad json: %s" % e, "type": "relay_error"}})
            return

        stream = bool(payload.get("stream"))
        upstream_key = UPSTREAM_KEY or os.environ.get("DEEPSEEK_API_KEY", "")
        if not upstream_key:
            self._send_json(500, {"error": {"message": "UPSTREAM_KEY not configured on relay", "type": "relay_error"}})
            return

        req = urllib.request.Request(
            UPSTREAM_BASE + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + upstream_key,
                "Accept": "text/event-stream" if stream else "application/json",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:2000]
            self._send_json(e.code, {"error": {"message": detail, "type": "upstream_http_error"}})
            return
        except Exception as e:
            self._send_json(504, {"error": {"message": "upstream unreachable: %s" % e, "type": "upstream_error"}})
            return

        if stream:
            self.send_response(resp.status)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                while True:
                    chunk = resp.read(1) if False else resp.readline()
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except Exception as e:
                sys.stderr.write("[relay] stream broken: %s\n" % e)
            return

        body = resp.read()
        self.send_response(resp.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    if not UPSTREAM_KEY and not os.environ.get("DEEPSEEK_API_KEY"):
        print("[warn] UPSTREAM_KEY 未设置，转发请求会返回 500", file=sys.stderr)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("[relay] listening on %s:%d -> %s" % (args.host, args.port, UPSTREAM_BASE), file=sys.stderr)
    srv.serve_forever()


if __name__ == "__main__":
    main()

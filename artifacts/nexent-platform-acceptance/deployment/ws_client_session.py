"""R-NX-10 WS invocation with session-id header (based on managed_agents_client.py)."""
import argparse
import asyncio
import json
import sys
import time

import websockets

TOOLS_GRANTED = set()


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--auth", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--max-wait", type=int, default=480)
    p.add_argument("--out", default="")
    args = p.parse_args()

    headers = {
        "Authorization": args.auth,
        "X-Hw-Agentarts-Session-Id": args.session_id,
    }
    frames = []

    async with websockets.connect(args.url, additional_headers=headers, compression=None) as ws:
        print("HANDSHAKE-OK", flush=True)
        req = {
            "req_id": "rnx10-" + str(int(time.time())),
            "req_method": "chat.send",
            "params": {"query": args.message, "mode": "agent.plan", "interactive_ask": True},
            "is_stream": True,
        }
        await ws.send(json.dumps(req))
        print("SENT chat.send", flush=True)

        start = time.time()
        final_answer = []
        while time.time() - start < args.max_wait:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=args.max_wait)
            except asyncio.TimeoutError:
                print("TIMEOUT", flush=True)
                break
            except websockets.ConnectionClosed as e:
                print("CLOSED", e.code, str(e.reason)[:200], flush=True)
                break
            try:
                f = json.loads(raw)
            except Exception:
                f = {"raw": raw[:300]}
            frames.append(f)
            t = f.get("type", "")
            ev = f.get("event", "") or f.get("method", "")
            if t == "event" and ev == "connection.ack":
                print("ACK", flush=True)
            # auto-grant tool permissions
            if "tool" in json.dumps(f)[:200] and f.get("method", "").startswith("tool."):
                pass
            m = f.get("method", "")
            if m in ("tool.grant", "tool.confirm", "tool.permission"):
                await ws.send(json.dumps({"req_id": f.get("req_id", ""), "resp_method": m + ".ok", "params": {"allow": True}}))
            # answer interactive ask
            q = json.dumps(f, ensure_ascii=False)
            if f.get("method") == "chat.ask" or '"interactive"' in q[:400]:
                await ws.send(json.dumps({"req_id": f.get("req_id", ""), "resp_method": "chat.ask.answer", "params": {"answer": "继续执行"}}))
            if t == "event" and ev in ("chat.final", "chat.done", "chat.error"):
                print("TERMINAL:", ev, flush=True)
                if ev == "chat.final":
                    final_answer.append(f)
                if ev == "chat.done" or ev == "chat.error":
                    break
            # print progress lines
            if t == "event" and ev not in ("connection.ack",):
                step = f.get("data", {})
                brief = json.dumps(step, ensure_ascii=False)[:160]
                print("FRAME", ev, brief, flush=True)

    print("TOTAL-FRAMES", len(frames), flush=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(frames, fh, ensure_ascii=False, indent=1)
        print("SAVED", args.out, flush=True)


if __name__ == "__main__":
    asyncio.run(main())

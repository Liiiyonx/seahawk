# -*- coding: utf-8 -*-
"""作业台真机模式验收：状态 → 遥测 → 夹爪 → 点动 → home → 推流。

对着开发机上以 `--remote` 启的作业台（127.0.0.1:8090）跑，验证
「开发机作业台 → 板上代理 → 树莓派 ROS/舵机」整条链路的真实下发与回读。

★ 这会**真实驱动机械臂**（夹爪开合 / 舵机 6 摆动 / 回待命位）。
   跑之前确认臂周围没有障碍，且现场有人。
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8090"


def get(path, timeout=20):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post(path, body, timeout=60):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def show_servos(title, tele):
    print("   %s：" % title)
    for sid, row in sorted(tele.items(), key=lambda kv: int(kv[0])):
        print("     #%-3s vin=%8s mV  position=%4s  goal=%4s  error=%s"
              % (sid, row.get("vin"), row.get("position"), row.get("goal"),
                 row.get("error")))


def main():
    print("1) /api/status")
    st = get("/api/status")
    print("   mock=%s  ros_error=%s" % (st.get("mock"), st.get("ros_error")))
    print("   detector=%s" % json.dumps(st.get("detector"), ensure_ascii=False))
    print("   calibration=%s" % json.dumps(st.get("calibration"), ensure_ascii=False))
    print("   place=%s" % json.dumps(st.get("place"), ensure_ascii=False))
    print("   task=%s" % json.dumps(st.get("task"), ensure_ascii=False))
    print("   detections=%d  dets_age=%s" % (len(st.get("detections") or []),
                                             st.get("dets_age")))
    if st.get("mock") or st.get("ros_error"):
        print("   ✗ 不是真机远端模式，停止")
        return 1

    print("\n2) /api/telemetry（动作前）")
    show_servos("动作前", get("/api/telemetry"))

    print("\n3) 夹爪张开（脉宽 %s）" % 200)
    print("   POST /api/gripper open →", post("/api/gripper", {"action": "open"}))
    time.sleep(1.5)

    print("\n4) 舵机 6 摆动 620 → 380 → 500（每段 2s）")
    for pulse in (620, 380, 500):
        code, body = post("/api/jog", {"servo_id": 6, "position": pulse,
                                       "duration_ms": 2000})
        print("   jog #6 → %-4s [%s] %s" % (pulse, code, body))
        time.sleep(2.5)

    print("\n5) 回待命位（板上 py3.6 IK 现算）")
    code, body = post("/api/home", {}, timeout=60)
    print("   POST /api/home → [%s] %s" % (code, body))
    time.sleep(2.5)

    print("\n6) 夹爪渐闭（板端回读停滞判据）")
    code, body = post("/api/gripper", {"action": "close"}, timeout=60)
    print("   POST /api/gripper close → [%s] %s" % (code, body))

    print("\n7) /api/telemetry（动作后）")
    time.sleep(1.0)
    show_servos("动作后", get("/api/telemetry"))

    print("\n8) /stream 推流取 3 帧")
    frames = 0
    first = None
    with urllib.request.urlopen(BASE + "/stream", timeout=25) as resp:
        buf = b""
        deadline = time.time() + 12
        while frames < 3 and time.time() < deadline:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\xff\xd8" in buf and frames < 3:
                start = buf.index(b"\xff\xd8")
                end = buf.find(b"\xff\xd9", start)
                if end < 0:
                    break
                jpg = buf[start:end + 2]
                buf = buf[end + 2:]
                frames += 1
                if first is None:
                    first = jpg
                    out = r"c:\Users\Liii\Desktop\seahawk\_work\shots\arm_console_stream_first.jpg"
                    with open(out, "wb") as fh:
                        fh.write(jpg)
    print("   ✓ 收到 %d 帧（首帧 %d 字节）" % (frames, len(first or b"")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

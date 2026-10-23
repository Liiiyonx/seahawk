import paramiko

host = "192.168.149.1"
user = "ubuntu"
password = "hiwonder"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=host, port=22, username=user, password=password, timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    print(f"=== {cmd} ===", flush=True)
    if out:
        print(out, flush=True)
    if err:
        print(f"[stderr] {err}", flush=True)
    return out

run("python3 --version; ls /usr/bin/python3* 2>/dev/null; which python3 python3.6 python3.7 python3.8 python3.10 2>/dev/null")
run("python3 -c 'import sys; print(sys.executable)'")
run("python3 -m pip --version 2>&1 | head -2")
run("python3 -c 'from __future__ import annotations; print(\"FUTURE_ANNOTATIONS_OK\")' 2>&1 | tail -2")
run("for m in cv2 numpy yaml paho.mqtt fastapi uvicorn ultralytics serial rospy; do python3 -c \"import $m; print('OK', '$m')\" 2>/dev/null || echo MISSING $m; done")
run("timeout 5 curl -sI https://pypi.org/simple/ 2>&1 | head -1 || echo NO_NET_TO_PYPI")
run("df -h / | tail -1")
run("v4l2-ctl --list-devices 2>/dev/null | head -12 || ls -l /dev/video* 2>/dev/null")
run("ps -eo pid,cmd | grep -E 'usb_cam|camera' | grep -v grep || echo NO_CAM_PROC")
run("free -m | head -2; nproc")

client.close()
print("CLOSED")

import paramiko

host = "192.168.149.1"
user = "ubuntu"
password = "hiwonder"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=host, port=22, username=user, password=password, timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    print(f"=== {cmd} ===", flush=True)
    if out:
        print(out, flush=True)
    if err:
        print(f"[stderr] {err}", flush=True)
    return out

run("cat /etc/resolv.conf | grep -v '^#' | head -5; getent hosts pypi.tuna.tsinghua.edu.cn 2>/dev/null | head -1 || echo DNS_FAIL")
run("timeout 6 curl -sI http://pypi.tuna.tsinghua.edu.cn/simple/ -o /dev/null -w 'TUNA:%{http_code}\n' 2>&1 || echo TUNA_FAIL")
run("timeout 6 curl -sI http://mirrors.aliyun.com/pypi/simple/ -o /dev/null -w 'ALI:%{http_code}\n' 2>&1 || echo ALI_FAIL")
run("timeout 6 curl -sI http://mirrors.aliyun.com/ubuntu/ -o /dev/null -w 'ALI_APT:%{http_code}\n' 2>&1 || echo ALI_APT_FAIL")
run("timeout 6 curl -sI http://archive.ubuntu.com/ubuntu/ -o /dev/null -w 'ARCHIVE:%{http_code}\n' 2>&1 || echo ARCHIVE_FAIL")
run("timeout 6 ping -c 1 -W 3 223.5.5.5 >/dev/null 2>&1 && echo PING_ALI_DNS_OK || echo PING_ALI_DNS_FAIL")
run("timeout 6 ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1 && echo PING_G8_OK || echo PING_G8_FAIL")
run("grep -v '^#' /etc/apt/sources.list 2>/dev/null | head -8; ls /etc/apt/sources.list.d/ 2>/dev/null")
run("python2 -c 'import cv2; print(\"py2 cv2\", cv2.__version__)' 2>&1 | head -1")
run("python2 -c 'import numpy; print(\"py2 numpy\", numpy.__version__)' 2>&1 | head -1")
run("python2 -c 'import yaml; print(\"py2 yaml OK\")' 2>&1 | head -1")
run("python2 -c 'import paho.mqtt; print(\"py2 paho OK\")' 2>&1 | head -1")
run("which roscore rosrun roslaunch mjpg_streamer 2>/dev/null; ls /dev/video0 2>/dev/null && echo VIDEO0_OK")
run("env | grep ROS_ | head -5")

client.close()
print("CLOSED")

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

run("cat /home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/config/hiwonder_servo_controller.yaml")
run("ps -eo pid,ppid,cmd | grep -E 'controller_manager|serialproxy|hiwonder_servo' | grep -v grep")
run("ls -l /dev/ttyS0 /dev/ttyUSB0 /dev/ttyAMA0 2>&1")

client.close()
print("CLOSED")

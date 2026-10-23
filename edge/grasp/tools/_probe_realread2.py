import time
import paramiko

host = "192.168.149.1"
user = "ubuntu"
password = "hiwonder"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=host, port=22, username=user, password=password, timeout=10)

def run(cmd, timeout=120):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    print(f"=== {cmd} ===", flush=True)
    if out:
        print(out, flush=True)
    if err:
        print(f"[stderr] {err}", flush=True)
    return out

env = "source /opt/ros/melodic/setup.bash; source $HOME/armpi_fpv/devel/setup.bash; export ROS_HOSTNAME=ubuntu; export ROS_MASTER_URI=http://ubuntu:11311; "
run("tail -120 /home/ubuntu/_manager_realread.log")
run("ps -eo pid,cmd | grep controller_manager | grep -v grep || echo NO_MANAGER")
run(env + "rostopic list | grep -E 'servo|joint' | head -30")
run(env + "python /home/ubuntu/_ctrl_verify.py", timeout=60)

client.close()
print("CLOSED")

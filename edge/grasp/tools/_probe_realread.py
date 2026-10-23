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

yaml_path = "/home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/config/hiwonder_servo_controller.yaml"

run(f"cp {yaml_path} /home/ubuntu/_backup_hsc.yaml && echo BACKUP_OK")
run(f"sed -i 's/fake_read: true/fake_read: false/' {yaml_path}")
run(f"grep fake_read {yaml_path}")

run("echo 'hiwonder' | sudo -S pkill -f controller_manager.py; sleep 1; ps -eo pid,cmd | grep controller_manager | grep -v grep || echo MANAGER_KILLED")

env = "source /opt/ros/melodic/setup.bash; source $HOME/armpi_fpv/devel/setup.bash; export ROS_HOSTNAME=ubuntu; export ROS_MASTER_URI=http://ubuntu:11311; "
run(f"nohup bash -c '{env} roslaunch /home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/launch/start.launch' > /home/ubuntu/_manager_realread.log 2>&1 & sleep 1; echo RELAUNCHED")
run("sleep 12")
run("tail -80 /home/ubuntu/_manager_realread.log")

client.close()
print("CLOSED")

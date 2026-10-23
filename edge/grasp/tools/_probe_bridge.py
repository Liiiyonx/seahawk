import paramiko

host = "192.168.149.1"
user = "ubuntu"
password = "hiwonder"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=host, port=22, username=user, password=password, timeout=10)

def run(cmd, timeout=90):
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
run(env + "python3 -c \"import rospy; from hiwonder_servo_msgs.msg import MultiRawIdPosDur, RawIdPosDur, ServoStateList; print('P3_ROS_MSG_OK')\" 2>&1 | tail -2")
run(env + "python3 -c \"from kinematics import ik_transform; ik=ik_transform.ArmIK(); print('P3_IK_OK')\" 2>&1 | tail -2")
run("find / -name 'inverse_kinematics*' 2>/dev/null | head -5")
run("find / -path '*kinematics*ik_transform*' 2>/dev/null | head -5")
run("ls -l /usr/local/lib/python2.7/dist-packages/kinematics/ 2>/dev/null; ls -l /usr/local/lib/python3*/dist-packages/kinematics/ 2>/dev/null")
run("head -50 /home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/scripts/controller_manager.py")
run(env + "timeout 8 rostopic hz /usb_cam/image_raw/compressed 2>/dev/null | head -4 || echo HZ_FAIL")
run(env + "timeout 8 rostopic echo -n1 /servo_controllers/port_id_1/servo_states 2>/dev/null | head -20 || echo ST_FAIL")

client.close()
print("CLOSED")

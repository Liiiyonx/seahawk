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

grip_src = [
    "# -*- coding: utf-8 -*-",
    "import sys, time",
    "import rospy",
    "from hiwonder_servo_msgs.msg import RawIdPosDur, MultiRawIdPosDur, ServoStateList",
    "rospy.init_node('grip_demo', anonymous=True)",
    "pub = rospy.Publisher('/servo_controllers/port_id_1/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)",
    "def cb(m):",
    "    for s in m.servo_states:",
    "        if s.id == 1:",
    "            print 'GRIP_POS=%d' % s.position",
    "rospy.Subscriber('/servo_controllers/port_id_1/servo_states', ServoStateList, cb)",
    "def send(servo_id, pos, dur):",
    "    m = MultiRawIdPosDur()",
    "    m.id_pos_dur_list = []",
    "    mm = RawIdPosDur()",
    "    mm.id = servo_id",
    "    mm.position = pos",
    "    mm.duration = dur",
    "    m.id_pos_dur_list.append(mm)",
    "    pub.publish(m)",
    "    print 'SEND id=%d pos=%d dur=%d' % (servo_id, pos, dur)",
    "time.sleep(1)",
    "grip_open = 75",
    "grip_close = 450",
    "try:",
    "    send(1, grip_close, 1500)",
    "    time.sleep(2.2)",
    "    send(1, grip_open, 1500)",
    "    time.sleep(2.2)",
    "    send(1, 200, 1500)",
    "    time.sleep(2.2)",
    "    print 'GRIP DEMO DONE'",
    "except rospy.ROSInterruptException:",
    "    pass",
    "",
]
run_src = "\n".join(grip_src)

sftp = client.open_sftp()
with sftp.open("/home/ubuntu/_grip_demo.py", "w") as f:
    f.write(run_src)
sftp.close()

env = "source /opt/ros/melodic/setup.bash; source $HOME/armpi_fpv/devel/setup.bash; export ROS_HOSTNAME=ubuntu; export ROS_MASTER_URI=http://ubuntu:11311; "
run(env + "python /home/ubuntu/_grip_demo.py", timeout=60)

client.close()
print("CLOSED")

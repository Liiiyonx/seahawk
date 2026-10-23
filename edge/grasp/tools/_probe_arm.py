import time
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

ctrl_src = [
    "# -*- coding: utf-8 -*-",
    "import sys, time",
    "import rospy",
    "from hiwonder_servo_msgs.msg import RawIdPosDur, MultiRawIdPosDur, ServoStateList",
    "rospy.init_node('ctrl_swing', anonymous=True)",
    "pub = rospy.Publisher('/servo_controllers/port_id_1/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)",
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
    "time.sleep(0.5)",
    "seq = [(6, 620, 2000), (6, 380, 2000), (6, 500, 2000)]",
    "try:",
    "    for sid, pos, dur in seq:",
    "        send(sid, pos, dur)",
    "        time.sleep(dur / 1000.0 + 0.3)",
    "    print 'SWING DONE'",
    "except rospy.ROSInterruptException:",
    "    pass",
    "",
]

sftp = client.open_sftp()
with sftp.open("/home/ubuntu/_ctrl_swing.py", "w") as f:
    f.write("\n".join(ctrl_src))
sftp.close()

env = "export ROS_HOSTNAME=ubuntu; export ROS_MASTER_URI=http://ubuntu:11311; source /opt/ros/melodic/setup.bash; source $HOME/armpi_fpv/devel/setup.bash; "
run(env + "python /home/ubuntu/_ctrl_swing.py", timeout=60)

time.sleep(1)

duty_check = [
    "# -*- coding: utf-8 -*-",
    "import sys, time",
    "import rospy",
    "from hiwonder_servo_msgs.msg import ServoStateList",
    "rospy.init_node('ctrl_verify', anonymous=True)",
    "got = []",
    "def cb(m):",
    "    got.append(m)",
    "    print 'VERIFY sample#%d: ' % len(got) + ' '.join('id%d=%d' % (s.id, s.position) for s in m.servo_states)",
    "rospy.Subscriber('/servo_controllers/port_id_1/servo_states', ServoStateList, cb)",
    "end = time.time() + 5",
    "while time.time() < end and len(got) < 3:",
    "    time.sleep(0.3)",
    "print 'VERIFY DONE samples=%d' % len(got)",
    "",
]

sftp = client.open_sftp()
with sftp.open("/home/ubuntu/_ctrl_verify.py", "w") as f:
    f.write("\n".join(duty_check))
sftp.close()
run(env + "python /home/ubuntu/_ctrl_verify.py", timeout=40)

client.close()
print("CLOSED")

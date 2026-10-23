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

swing_real = [
    "# -*- coding: utf-8 -*-",
    "import sys, time",
    "import rospy",
    "from hiwonder_servo_msgs.msg import RawIdPosDur, MultiRawIdPosDur, ServoStateList",
    "rospy.init_node('swing_real', anonymous=True)",
    "pub = rospy.Publisher('/servo_controllers/port_id_1/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)",
    "last = {}",
    "def cb(m):",
    "    last[m.servo_states[0].id] = m.servo_states[0].position",
    "    for s in m.servo_states:",
    "        if s.id == 6:",
    "            print 'POS6=%d' % s.position",
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
    "print 'READ0 6=%s' % last.get(6)",
    "seq = [(6, 520, 1500), (6, 480, 1500), (6, 500, 1500)]",
    "try:",
    "    for sid, pos, dur in seq:",
    "        send(sid, pos, dur)",
    "        time.sleep(dur / 1000.0 + 0.6)",
    "        print 'READ_AFTER pos=%d -> 6=%s' % (pos, last.get(6))",
    "    print 'SWING REAL DONE'",
    "except rospy.ROSInterruptException:",
    "    pass",
    "",
]
run_src = "\n".join(swing_real)

sftp = client.open_sftp()
with sftp.open("/home/ubuntu/_ctrl_swing_real.py", "w") as f:
    f.write(run_src)
sftp.close()

env = "source /opt/ros/melodic/setup.bash; source $HOME/armpi_fpv/devel/setup.bash; export ROS_HOSTNAME=ubuntu; export ROS_MASTER_URI=http://ubuntu:11311; "
run(env + "python /home/ubuntu/_ctrl_swing_real.py", timeout=60)

client.close()
print("CLOSED")

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

run("cat /home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/scripts/test_msg.py")
run("grep -rn 'multi_id_pos_dur\\|id_pos_dur\\|port_id_1' /home/ubuntu/armpi_fpv/src --include='*.py' --include='*.launch' --include='*.cpp' --include='*.yaml' | grep -v 'object_\\|warehouse\\|face_detect\\|asr_control\\|lab_config\\|armpi_fpv_common' | head -80")
run("cat /home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/src/hiwonder_servo_controllers/joint_position_controller.py")
run("cat /home/ubuntu/armpi_fpv/src/hiwonder_servo_controllers/src/hiwonder_servo_controllers/joint_controller.py")

client.close()
print("CLOSED")

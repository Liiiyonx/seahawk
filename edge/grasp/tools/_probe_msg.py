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

run("ls /home/ubuntu/armpi_fpv/src")
run("find /home/ubuntu/armpi_fpv/src -path '*/msg/*.msg' -name 'MultiRawIdPosDur.msg' -o -path '*/msg/*.msg' -name 'RawIdPosDur.msg'")
run("find /home/ubuntu/armpi_fpv/src -name 'MultiRawIdPosDur.msg' -print -exec cat {} \\;")
run("find /home/ubuntu/armpi_fpv/src -name 'RawIdPosDur.msg' -print -exec cat {} \\;")
run("find /home/ubuntu/armpi_fpv/src -name 'ServoStateList.msg' -print -exec cat {} \\;")

client.close()
print("CLOSED")

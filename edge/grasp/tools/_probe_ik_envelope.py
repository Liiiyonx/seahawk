# -*- coding: utf-8 -*-
"""只读探针：用厂商 IK（板上 py3.6）算候选位姿/网格/料槽的可达性。

**纯计算，不下发任何指令、不动机械臂。** 用来在写配置之前确认：
  * 俯视观测位姿（相机要正对工作平面）能不能解出来；
  * 9 点标定网格的落点是否都在 IK 可达范围内（否则闭环里 move_to 直接 False）；
  * 料槽放置点（默认 x=±0.275, y=0）是否可达。
"""
import paramiko

host = "192.168.149.1"
user = "ubuntu"
password = "hiwonder"

cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(hostname=host, port=22, username=user, password=password, timeout=15)

PROBE = r'''
# -*- coding: utf-8 -*-
import json

def reach(ik, x, y, z, pitch, a1=-180.0, a2=0.0, d=0.01):
    res = ik.setPitchRanges((x, y, z), pitch, a1, a2, d)
    if not res:
        return None
    theta, servos, alpha = res
    return {"alpha": float(alpha), "servos": {k: int(v) for k, v in servos.items()}}

def main():
    from kinematics import ik_transform
    ik = ik_transform.ArmIK()
    out = {}

    # 1) 俯视观测位姿候选（要正对工作平面看）
    obs = []
    for (x, y, z) in [(0.0, 0.17, 0.30), (0.0, 0.17, 0.26), (0.0, 0.15, 0.28),
                      (0.0, 0.20, 0.30), (0.0, 0.15, 0.32), (0.0, 0.17, 0.22)]:
        for pitch in (-175.0, -170.0, -160.0, -150.0):
            r = reach(ik, x, y, z, pitch)
            obs.append({"coord": [x, y, z], "pitch": pitch, "reach": r})
    out["observe"] = obs

    # 2) 待命位（现状，前视）
    out["home"] = {"home_pitch": -65.0,
                   "reach": reach(ik, 0.0, 0.17, 0.30, -65.0)}

    # 3) 网格/抓取高度可达性：z = plane_z + depth_offset = 0.025，抓取俯仰 -175
    grid = []
    for y in (0.06, 0.10, 0.14, 0.18, 0.22, 0.26):
        for x in (-0.14, -0.10, -0.07, 0.0, 0.07, 0.10, 0.14):
            r = reach(ik, x, y, 0.025, -175.0)
            grid.append({"xy": [x, y], "radius": round((x * x + y * y) ** 0.5, 3),
                         "ok": r is not None})
    out["grid_z0025_pitch-175"] = grid

    # 4) 接近高度 z = plane_z + approach = 0.10
    grid2 = []
    for y in (0.10, 0.17, 0.30):
        for x in (-0.14, 0.0, 0.14):
            r = reach(ik, x, y, 0.10, -175.0)
            grid2.append({"xy": [x, y], "ok": r is not None})
    out["grid_z010_pitch-175"] = grid2

    # 5) 料槽放置点（厂商侧向货架口径）
    place = []
    for xy, z, pitch in [((0.275, 0.0), 0.12, -130.0), ((0.275, 0.0), 0.02, -130.0),
                         ((0.275, 0.0), 0.20, -130.0),
                         ((-0.275, 0.0), 0.12, -130.0), ((-0.275, 0.0), 0.02, -130.0),
                         ((0.20, 0.10), 0.12, -130.0), ((0.20, 0.10), 0.02, -130.0),
                         ((0.15, 0.15), 0.02, -130.0), ((0.10, 0.10), 0.02, -175.0)]:
        x, y = xy
        place.append({"xy": xy, "z": z, "pitch": pitch,
                      "radius": round((x * x + y * y) ** 0.5, 3),
                      "ok": reach(ik, x, y, z, pitch) is not None})
    out["place"] = place

    print("__JSON__" + json.dumps(out))

main()
'''

sftp = cli.open_sftp()
with sftp.open("/home/ubuntu/_ik_envelope.py", "w") as f:
    f.write(PROBE)
sftp.close()

env = ("source /opt/ros/melodic/setup.bash; source $HOME/armpi_fpv/devel/setup.bash; ")
_, so, se = cli.exec_command(env + "python3 /home/ubuntu/_ik_envelope.py 2>&1 | tail -3", timeout=90)
blob = so.read().decode("utf-8", "replace")
err = se.read().decode("utf-8", "replace")
cli.close()

if "__JSON__" not in blob:
    print("没拿到结构化结果：\n%s\n[stderr] %s" % (blob, err))
    raise SystemExit(1)

data = blob.split("__JSON__", 1)[1].strip().split("\n")[0]
import json as J
d = J.loads(data)

print("=== 1) 俯视观测位姿候选（seen=可达） ===")
for row in d["observe"]:
    r = row["reach"]
    print("  coord=%-18s pitch=%-7s %s" % (row["coord"], row["pitch"],
          ("可达 servos=%s alpha=%s" % (r["servos"], round(r["alpha"], 1))) if r else "✗ 不可达"))

print("\n=== 2) 现行待命位（前视） ===")
r = d["home"]["reach"]
print("  home (0,0.17,0.30) pitch=-65 → %s" % ("可达" if r else "✗ 不可达"))

print("\n=== 3) 抓取高度 z=0.025 / pitch=-175 的可达网格（work_radius 默认 0.20） ===")
ys = [0.06, 0.10, 0.14, 0.18, 0.22, 0.26]
xs = [-0.14, -0.10, -0.07, 0.0, 0.07, 0.10, 0.14]
header = "  y\\x   " + "".join("%7s" % x for x in xs)
print(header)
for y in ys:
    cells = []
    for x in xs:
        row = next(r for r in d["grid_z0025_pitch-175"] if r["xy"] == [x, y])
        rad = row["radius"]
        mark = "OK" if row["ok"] else "--"
        if row["ok"] and rad > 0.20:
            mark = "OK*"        # IK 可达但超 work_radius 闸门
        cells.append("%7s" % mark)
    print("  %-6s%s" % (y, "".join(cells)))
print("  注：OK=IK可达且在 work_radius(0.20) 内；OK*=IK可达但半径超 0.20（闭环会拒绝）")

print("\n=== 4) 接近高度 z=0.10 / pitch=-175 ===")
for row in d["grid_z010_pitch-175"]:
    print("  xy=%-14s %s" % (row["xy"], "可达" if row["ok"] else "✗ 不可达"))

print("\n=== 5) 料槽放置点候选 ===")
for row in d["place"]:
    print("  xy=%-14s z=%-6s pitch=%-7s r=%-6s %s"
          % (row["xy"], row["z"], row["pitch"], row["radius"],
             "可达" if row["ok"] else "✗ 不可达"))
print("CLOSED")

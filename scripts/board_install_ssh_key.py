#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用一次密码登录，把本机公钥写到开发板，之后全程免密。

## 为什么需要它

OpenSSH 命令行不接受非交互式密码（没有 TTY 时没法输），而 `sshpass` / `plink`
在 Windows 上默认都没有。paramiko 是纯 Python 的 SSH 实现，**支持程序化密码认证**，
所以用它在板上一次性装好公钥，之后 `ssh` / `scp` / 部署脚本全部免密。

装完会**用系统 OpenSSH 客户端再验一次**（而不是用 paramiko 自证）——
因为后面真正干活的 `scripts/deploy_autopick_to_pi.py` 走的是系统 ssh/scp，
必须确认它们也能免密，否则等于没装。

## 用法

    # 用 .venv 里的 python（带 paramiko）
    .\\.venv\\Scripts\\python.exe scripts\\board_install_ssh_key.py --host 192.168.149.1

    # 指定用户 / 密码 / 密钥
    .\\.venv\\Scripts\\python.exe scripts\\board_install_ssh_key.py \\
        --host 192.168.149.1 --user ubuntu --password ****** --key ~/.ssh/id_ed25519.pub

安全提示：密码只在本进程内存里用一次，不写盘、不记日志（日志里一律打码）。
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path


def load_pubkey(path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_file():
        raise SystemExit(f"公钥不存在：{p}\n先生成：ssh-keygen -t ed25519")
    text = p.read_text(encoding="utf-8").strip()
    if not text or not text.startswith(("ssh-", "ecdsa-")):
        raise SystemExit(f"{p} 不像公钥文件（应以 ssh-ed25519 / ssh-rsa 开头）")
    return text


def run_on_board(client, cmd: str) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return stdout.channel.recv_exit_status(), out, err


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="把本机公钥装到开发板（一次密码，之后免密）")
    ap.add_argument("--host", required=True, help="板子地址（如 192.168.149.1）")
    ap.add_argument("--user", default="ubuntu", help="板上用户（默认 ubuntu）")
    ap.add_argument("--port", type=int, default=22, help="SSH 端口")
    ap.add_argument("--password", default=None,
                    help="板子登录密码；不给则交互式输入（推荐，避免进命令历史）")
    ap.add_argument("--key", default="~/.ssh/id_ed25519.pub",
                    help="要授权的公钥路径（默认 ~/.ssh/id_ed25519.pub）")
    ap.add_argument("--identity", default="~/.ssh/id_ed25519",
                    help="免密验证时用的私钥（默认 ~/.ssh/id_ed25519）")
    ap.add_argument("--timeout", type=float, default=15.0, help="连接超时（秒）")
    args = ap.parse_args(argv)

    try:
        import paramiko
    except ImportError:
        raise SystemExit(
            "缺少 paramiko。用带它的解释器跑：\n"
            r"  .\.venv\Scripts\python.exe scripts\board_install_ssh_key.py --host " + args.host
        )

    pubkey = load_pubkey(args.key)
    key_type = pubkey.split()[0]
    fingerprint = pubkey.split()[1][:16] + "…"

    password = args.password
    if password is None:
        password = getpass.getpass(f"{args.user}@{args.host} 的密码（不回显）：")

    print(f"[key] 目标 {args.user}@{args.host}:{args.port}")
    print(f"[key] 公钥类型 {key_type}  指纹前缀 {fingerprint}")

    client = paramiko.SSHClient()
    # 首次连接没有 known_hosts 条目；这里只提示不阻断（板子是局域网自有设备）
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print("[key] 用密码登录…")
    try:
        client.connect(
            hostname=args.host, port=args.port, username=args.user,
            password=password, timeout=args.timeout,
            allow_agent=False, look_for_keys=False,   # 只走密码，避免误用别的密钥
        )
    except paramiko.AuthenticationException:
        raise SystemExit(
            "✗ 密码认证失败。\n"
            "  可能：密码不对 / 该用户不允许密码登录（sshd 里 PasswordAuthentication no）\n"
            f"  手工确认：ssh {args.user}@{args.host} 'echo ok'"
        )
    except Exception as exc:                                    # noqa: BLE001
        raise SystemExit(f"✗ 连不上 {args.host}:{args.port} —— {type(exc).__name__}: {exc}")

    print("[key] 已登录，写入 authorized_keys")

    # 幂等：已在里面就不重复追加（否则 authorized_keys 会越滚越长）
    quoted = pubkey.replace("'", "'\\''")
    script = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys && "
        f"grep -qF '{quoted}' ~/.ssh/authorized_keys && echo ALREADY || "
        f"(echo '{quoted}' >> ~/.ssh/authorized_keys && echo APPENDED)"
    )
    rc, out, err = run_on_board(client, script)
    print(f"[key] 板上结果：{out.strip() or err.strip()} (rc={rc})")

    # 顺便把板子的基本情况带回来，省一次手工探路
    rc2, out2, _ = run_on_board(
        client,
        "echo \"host=$(hostname) arch=$(uname -m) \""
        "\"os=$(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)\"; "
        "echo \"python2=$(command -v python2 || echo none)\"; "
        "echo \"python3=$(python3 --version 2>&1 || echo none)\"; "
        "echo \"ros=$(ls -d /opt/ros/* 2>/dev/null | tr '\\n' ' ')\"",
    )
    if out2.strip():
        print("[key] 板子概况：")
        for line in out2.strip().splitlines():
            print("   ", line)

    client.close()

    # ★ 关键：用**系统 OpenSSH**再验一次，而不是用 paramiko 自证 ——
    #   后面真正干活的 deploy 脚本走系统 ssh/scp。
    print("[key] 用系统 ssh 验证免密…")
    ident = str(Path(args.identity).expanduser())
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         "-o", "IdentitiesOnly=yes", "-i", ident,
         f"{args.user}@{args.host}", "echo PASSWORDLESS_OK; hostname"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if proc.returncode == 0 and "PASSWORDLESS_OK" in (proc.stdout or ""):
        print("[key] ✓ 免密登录已生效：")
        for line in (proc.stdout or "").strip().splitlines():
            print("   ", line)
        print("\n[deploy] 现在可以免密部署了：")
        print(f"  .\\.venv-analysis\\Scripts\\python.exe scripts\\deploy_autopick_to_pi.py --host {args.host} --user {args.user}")
        return 0

    print("[key] ✗ 系统 ssh 仍然免密失败：")
    print("   ", (proc.stderr or "").strip()[:400])
    print("    可能：authorized_keys 权限不对 / 板子 home 被加密 / sshd 禁了公钥")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

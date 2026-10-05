"""按需从远程 zip（Zenodo D_six）里只下载需要的成员文件。

背景：D_six.zip 有 387MB / 925 个成员，但软著只需要 2~3 张水面漂浮垃圾
图。走 HTTP Range 只取中央目录 → 解析出目标成员的本地文件头与数据偏移 →
再 Range 取那几段字节，本地解出图片。全程下载量 < 5MB。

注意：Zenodo 的 content 接口对 Range 越界会返回 `Illegal Range request`
（22 字节），必须先 HEAD 拿真实 content-length 再算偏移。
"""
from __future__ import annotations

import struct
import sys
import urllib.request
import zlib
from pathlib import Path

URL = "https://zenodo.org/api/records/15195086/files/D_six.zip/content"
OUT = Path(r"C:\Users\Liii\Desktop\seahawk\artifacts\vision-preview")
PROBE = Path(r"C:\Users\Liii\Desktop\seahawk\.d_six_probe")


def http_range(url: str, start: int, end: int, retries: int = 5) -> bytes:
    """取 [start, end] 字节。

    Zenodo 的大文件 Range 请求会随机提前断开（http.client.IncompleteRead），
    单次读取常丢掉尾部落干字节。这里循环拼接直到长度达标 —— 这是本脚本
    唯一可靠的取数方式，重试固定次数仍不足才报错。
    """
    want = end - start + 1
    buf = b""
    for attempt in range(retries):
        req = urllib.request.Request(
            url, headers={"Range": f"bytes={start + len(buf)}-{end}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                chunk = r.read()
            buf += chunk
            if len(buf) >= want:
                return buf[:want]
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == retries - 1:
                raise RuntimeError(
                    f"Range {start}-{end} 失败（已取 {len(buf)}/{want}）: {e}"
                ) from e
    return buf


def remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def read_central_directory(url: str, total: int) -> list[dict]:
    tail = http_range(url, total - 400_000, total - 1)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise RuntimeError("未找到 EOCD")
    cd_size, cd_off = struct.unpack("<II", tail[eocd + 12 : eocd + 20])
    cd = http_range(url, cd_off, cd_off + cd_size - 1)

    entries, i = [], 0
    # 中央目录文件头固定 46 字节；用 struct 逐字段解出所需字段。
    # 字段顺序（zip 规范）：sig(4) ver_made ver_need flag method mtime mdate
    #   crc csize usize nlen elen clen disk intattr extattr offset
    FMT = "<4sHHHHHHIIIHHHHHII"
    FMT_LEN = struct.calcsize(FMT)
    assert FMT_LEN == 46, FMT_LEN
    while i < len(cd) - 4 and cd[i : i + 4] == b"PK\x01\x02":
        f = struct.unpack(FMT, cd[i : i + FMT_LEN])
        nlen, elen, clen = f[10], f[11], f[12]
        size, offset, method = f[8], f[16], f[4]
        name = cd[i + FMT_LEN : i + FMT_LEN + nlen].decode("utf-8", "replace")
        entries.append({"name": name, "size": size, "offset": offset, "method": method})
        i += FMT_LEN + nlen + elen + clen
    return entries


def fetch_member(url: str, entry: dict) -> bytes:
    """取成员的数据段并解压。

    method=8 是 deflate 压缩。**不能**把裸 deflate 流直接喂给 zipfile ——
    它期望的是完整 zip 容器。这里用 zlib.decompress(data, -15) 做 raw
    deflate 解压（wbits=-15 表示无 zlib 头）。
    """
    head = http_range(url, entry["offset"], entry["offset"] + 29)
    nlen, elen = struct.unpack("<HH", head[26:30])
    data_start = entry["offset"] + 30 + nlen + elen
    raw = http_range(url, data_start, data_start + entry["size"] - 1)
    if entry["method"] == 0:
        return raw
    if entry["method"] == 8:
        return zlib.decompress(raw, -15)
    raise RuntimeError(f"不支持的压缩方法 {entry['method']}（{entry['name']}）")


def main() -> int:
    total = remote_size(URL)
    print(f"远程 zip 大小: {total:,} 字节")
    entries = read_central_directory(URL, total)
    print(f"中央目录条目: {len(entries)}")
    imgs = [e for e in entries if e["name"].lower().endswith((".jpg", ".jpeg", ".png"))]
    print(f"图片成员: {len(imgs)}")
    for e in imgs[:12]:
        print(f"  {e['name']}  {e['size']/1024:.0f}KB  method={e['method']}")

    if len(sys.argv) > 1:
        want = sys.argv[1:]
        picked = [e for e in imgs if any(w in e["name"] for w in want)]
        OUT.mkdir(parents=True, exist_ok=True)
        for e in picked:
            data = fetch_member(URL, e)
            dst = OUT / Path(e["name"]).name
            dst.write_bytes(data)
            print(f"已保存 {dst.name}  {len(data)/1024:.0f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

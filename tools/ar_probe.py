#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""严格按 opkg/Debian ar 规范 dump .ipk 的 ar 头，定位 Malformed 根因。"""
import sys

def probe(path):
    with open(path, "rb") as f:
        blob = f.read()
    print("文件: %s  大小: %d" % (path, len(blob)))
    if blob[:8] != b"!<arch>\n":
        print("[FAIL] ar magic 不匹配: %r" % blob[:8])
        return 1
    print("[OK]   ar magic 正确: !<arch>")
    off = 8
    idx = 0
    while off + 60 <= len(blob):
        hdr = blob[off:off + 60]
        name = hdr[0:16]
        mtime = hdr[16:28]
        uid = hdr[28:34]
        gid = hdr[34:40]
        mode = hdr[40:48]
        size_s = hdr[48:58]
        tail = hdr[58:60]
        name_s = name.rstrip(b" ").rstrip(b"/").decode("utf-8", "replace")
        try:
            size = int(size_s.decode("ascii").strip() or "0")
        except ValueError:
            print("[FAIL] 成员 %d size 字段非数字: %r" % (idx, size_s))
            return 1
        print("  成员 %d: name=%-16r mode=%-8s size=%-10s tail=%r"
              % (idx, name_s, mode.decode("ascii").strip(), size, tail))
        # opkg 严格解析期望：成员名以 / 结尾（Debian 约定）
        name_raw = hdr[0:16]
        has_slash = name_raw.rstrip(b" ")[-1:] == b"/" or name_raw in (b"/               ", b"//              ")
        print("        raw_name=%r  (标准应带尾'/'：%s)" % (name_raw, "是" if has_slash else "否"))
        if not has_slash and name_s not in ("/", "//"):
            print("        [注意] 成员名无尾 '/' —— dpkg/opkg 标准应带 '/'，部分解析器会判 Malformed")
        off += 60 + size
        if size % 2 == 1:
            off += 1
        idx += 1
        if off + 60 > len(blob) and off >= len(blob):
            break
    print("解析结束，下一个偏移: %d / 总字节: %d" % (off, len(blob)))
    return 0

if __name__ == "__main__":
    sys.exit(probe(sys.argv[1]) if len(sys.argv) > 1 else (print("用法: ar_probe.py file.ipk"), 2))

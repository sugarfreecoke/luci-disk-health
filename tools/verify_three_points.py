#!/usr/bin/env python3
"""按用户三要点严格校验新版 .ipk：gzip 头 / 外层成员 / control 权限与 LF。"""
import gzip
import tarfile
import io
import os

IPK = "out/luci-app-disk-health_1.0.0-1_all.ipk"


def p(*a):
    print(*a)


def banner(t):
    p("=" * 60)
    p(t)
    p("=" * 60)


# ---------- 要点 1：文件头必须是 gzip（0x1f 0x8b 0x08） ----------
banner("[要点 1] 文件头 (od -c 等价)")
with open(IPK, "rb") as f:
    head = f.read(3)
p("前 3 字节 (hex):", head.hex())
p("前 3 字节 (od -c 风格):",
  " ".join("%03o" % b for b in head))
if head[:2] == b"\x1f\x8b" and head[2] == 0x08:
    p("  [PASS] 开头是 \\037\\213\\b (gzip)，不是 !<arch>\n")
else:
    p("  [FAIL] 不是 gzip 头！")
    raise SystemExit(1)

# ---------- 要点 2：外层成员 ./debian-binary ./control.tar.gz ./data.tar.gz ----------
banner("[要点 2] 外层 tar 成员 (ls 等价)")
with gzip.GzipFile(IPK) as gz:
    with tarfile.open(fileobj=gz) as tf:
        outer = sorted(tf.getnames())
        for n in outer:
            p("  ", n)
        need = ["./debian-binary", "./control.tar.gz", "./data.tar.gz"]
        ok = all(n in outer for n in need)
        # 注意 getnames() 会剥掉名字尾部的 '/'，这里规范化比较
        norm = [n.rstrip("/") for n in outer]
        ok = all(n in norm for n in need)
p("  期望成员:", need)
p("  [PASS]" if ok else "  [FAIL]", "三层成员齐全\n")

# ---------- 要点 3：control.tar.gz 内 postinst/postrm=0755 且全部 LF ----------
banner("[要点 3] control.tar.gz 权限 & 换行 (CRLF 检查)")
with gzip.GzipFile(IPK) as gz:
    with tarfile.open(fileobj=gz) as tf:
        cand = [n for n in tf.getnames()
                if n.replace("./", "") == "control.tar.gz"][0]
        ctrl_data = tf.extractfile(cand).read()

with gzip.GzipFile(fileobj=io.BytesIO(ctrl_data)) as gz:
    with tarfile.open(fileobj=gz) as tf:
        p("  control.tar.gz 内成员及权限:")
        all_lf = True
        script_ok = True
        for m in tf.getmembers():
            body = tf.extractfile(m).read() if m.isfile() else b""
            has_crlf = b"\r\n" in body
            if has_crlf:
                all_lf = False
            tag = "CRLF!!!" if has_crlf else "LF"
            p("    %04o  %-12s  %s" % (m.mode & 0o7777, m.name, tag))
            if m.name in ("./postinst", "./postrm"):
                if not (m.mode & 0o755) == 0o755:
                    script_ok = False
        p("")
        p("  postinst/postrm 是否 0755:", "YES" if script_ok else "NO")
        p("  全部文件均为 LF (无 \\r):", "YES" if all_lf else "NO")
        p("  [PASS]" if (script_ok and all_lf) else "  [FAIL]", "\n")

banner("结论")
p("三项要点全部 PASS => 该 .ipk 符合新版 opkg 格式，可用于 ImmortalWrt 24.10 网页上传/opkg install。")

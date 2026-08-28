#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仅做 Lua 语法编译校验（load 但不执行），用于部署前快速排雷。
依赖 lupa（LuaJIT 5.1 兼容）。"""
import sys
import lupa

RUNTIME = lupa.LuaRuntime(unpack_returned_tuples=True)

def check(path):
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    # load() 在 Lua 5.1 中编译 chunk 为函数，不执行，因此 require/module 缺失不会报错
    fn = RUNTIME.eval("function(s) return load(s) end")
    res = fn(code)
    ok, err = res if isinstance(res, tuple) else (res, None)
    if ok is None and err is not None:
        print("  [FAIL] %s" % path)
        print("         " + str(err).replace("\n", "\n         "))
        return False
    # lupa 的 load 返回 function 或 (nil, err)
    try:
        is_fn = RUNTIME.eval("type")(ok)
    except Exception:
        is_fn = "nil"
    if is_fn != "function":
        print("  [FAIL] %s (编译未返回函数: %s)" % (path, is_fn))
        return False
    print("  [OK]   %s" % path)
    return True

if __name__ == "__main__":
    files = sys.argv[1:] or [
        "luasrc/model/disk_health.lua",
        "luasrc/controller/disk_health.lua",
        "luasrc/model/cbi/disk_health.lua",
    ]
    all_ok = True
    for f in files:
        if not check(f):
            all_ok = False
    sys.exit(0 if all_ok else 1)

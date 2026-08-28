"""生成 luci-app-disk-health 的应用图标（128x128 PNG）

设计要点：
- 与 iStore 商店应用的视觉风格相符（圆角矩形主体 + 居中图形）
- 硬盘图标（侧面投影）+ 心电波叠加，强调「健康监控」
- 主色：iStoreOS 蓝紫渐变（#6F4EFF -> #A78BFA），强化品牌一致
- 心电图绿色：#22C55E（绿，健康/良好）
"""
from PIL import Image, ImageDraw

SIZE = 128


def hex_to_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


# 渐变色（iStoreOS 主题蓝紫）
BG_TOP = hex_to_rgb("#6F4EFF")
BG_BOT = hex_to_rgb("#A78BFA")
HEALTH_GREEN = hex_to_rgb("#22C55E")
WHITE = (255, 255, 255)
DARK = (40, 40, 60)


def make_gradient(size):
    img = Image.new("RGB", (size, size), BG_TOP)
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(BG_TOP[0] * (1 - t) + BG_BOT[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOT[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOT[2] * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def rounded_mask(size, radius):
    """圆角矩形 alpha mask"""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def draw_disk(img):
    d = ImageDraw.Draw(img, "RGBA")
    # 硬盘主体（圆角矩形）
    body_x0, body_y0 = 28, 36
    body_x1, body_y1 = 100, 92
    # 内层阴影
    d.rounded_rectangle(
        (body_x0, body_y0, body_x1, body_y1), radius=10, fill=(255, 255, 255, 230)
    )
    # 主磁盘矩形
    d.rounded_rectangle(
        (body_x0 + 1, body_y0 + 1, body_x1 - 1, body_y1 - 1),
        radius=9,
        fill=(255, 255, 255, 245),
    )
    # 中心轴
    cx, cy = (body_x0 + body_x1) // 2, (body_y0 + body_y1) // 2
    r = 16
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DARK)
    # 中心点
    d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(255, 255, 255, 200))
    # 三道指示灯（绿/黄/红点，左侧）
    for i, c in enumerate([(34, 197, 94, 255), (250, 204, 21, 255), (239, 68, 68, 255)]):
        ly = body_y0 + 10 + i * 14
        d.ellipse((body_x0 + 8 - 3, ly - 3, body_x0 + 8 + 3, ly + 3), fill=c)


def draw_heartbeat(img):
    """心电波叠加在硬盘上（绿色），强化『健康监控』语义"""
    d = ImageDraw.Draw(img, "RGBA")
    # 波形路径：基准 y=64, 高度变化
    base = 70
    pts = []
    x = 24
    pts.append((x, base))
    x += 6; pts.append((x, base))
    x += 6; pts.append((x, base - 4))
    x += 4; pts.append((x, base - 2))
    x += 4; pts.append((x, base - 18))   # 上
    x += 4; pts.append((x, base + 22))   # 下
    x += 4; pts.append((x, base - 14))
    x += 4; pts.append((x, base + 6))
    x += 4; pts.append((x, base - 6))
    x += 8; pts.append((x, base - 2))
    x += 6; pts.append((x, base + 12))
    x += 6; pts.append((x, base))
    x += 6; pts.append((x, base))
    # 阴影
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=(0, 0, 0, 90), width=4)
    # 主线
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=(34, 197, 94, 255), width=3)


def main():
    img = make_gradient(SIZE)
    # 圆角遮罩
    mask = rounded_mask(SIZE, 24)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    # 重新加载并继续画（在带 alpha 的层上）
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    layer.paste(out, (0, 0))
    draw_disk(layer)
    draw_heartbeat(layer)
    # 最终再过一次圆角
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(layer, (0, 0), mask)
    final.save(
        "out/icon.png", "PNG", optimize=True
    )
    print(f"Wrote out/icon.png ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()

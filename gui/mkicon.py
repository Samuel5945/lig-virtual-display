import math
from PIL import Image, ImageDraw, ImageFilter

SS = 2048
FINAL = 512
N = 5.0

TOP    = (126, 198, 76)
BOTTOM = (54, 115, 20)
DARK   = (28, 28, 30)
WHITE  = (255, 255, 255)

U = SS / 512.0
DX, DY = -22, -14          # 构图居中微调（设计基准 512）

def box(x0, y0, x1, y1):
    return [(x0 + DX) * U, (y0 + DY) * U, (x1 + DX) * U, (y1 + DY) * U]

img = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 1) squircle 遮罩
pts = []
for i in range(1440):
    t = 2 * math.pi * i / 1440
    ct, st = math.cos(t), math.sin(t)
    x = (SS / 2) * math.copysign(abs(ct) ** (2.0 / N), ct)
    y = (SS / 2) * math.copysign(abs(st) ** (2.0 / N), st)
    pts.append((SS / 2 + x, SS / 2 + y))
mask = Image.new("L", (SS, SS), 0)
ImageDraw.Draw(mask).polygon(pts, fill=255)

# 2) 渐变 + 顶部柔光
grad = Image.new("RGB", (1, SS))
for y in range(SS):
    k = (y / (SS - 1)) ** 0.9
    grad.putpixel((0, y), tuple(int(TOP[c] + (BOTTOM[c] - TOP[c]) * k) for c in range(3)))
grad = grad.resize((SS, SS))

sheen = Image.new("L", (SS, SS), 0)
ImageDraw.Draw(sheen).ellipse([-SS*0.25, -SS*0.78, SS*1.25, SS*0.42], fill=44)
sheen = sheen.filter(ImageFilter.GaussianBlur(SS // 12))

bg = grad.copy()
bg.paste(WHITE, (0, 0), sheen)
img.paste(bg, (0, 0), mask)

# 3) 图形
def rr(b, r, fill=None, outline=None, width=0):
    d.rounded_rectangle(b, radius=r*U, fill=fill, outline=outline, width=int(width*U))

# 后面那台（虚拟）
back = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
ImageDraw.Draw(back).rounded_rectangle(
    box(112, 120, 360, 312), radius=28*U,
    fill=(255, 255, 255, 86), outline=(255, 255, 255, 230), width=int(8.5*U))
img.alpha_composite(back)

# 前面那台（实体）
rr(box(178, 182, 428, 378), 28, fill=DARK, outline=(255, 255, 255, 246), width=9.5)
rr(box(212, 218, 394, 248), 10, fill=(255, 255, 255, 228))
rr(box(212, 272, 328, 297), 8.5, fill=(168, 224, 140, 235))
rr(box(344, 272, 394, 297), 8.5, fill=(255, 255, 255, 200))
# 底座
rr(box(288, 378, 318, 402), 7.5, fill=(255, 255, 255, 232))
rr(box(256, 398, 350, 420), 9.5, fill=(255, 255, 255, 232))

out = img.resize((FINAL, FINAL), Image.LANCZOS)
out.save("app.png")
out.save("app.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("已生成：app.png / app.ico")

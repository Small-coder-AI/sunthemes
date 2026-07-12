"""Генерирует icon.ico из того же дизайна, что в приложении (пол-солнца / пол-луны)."""
from PIL import Image, ImageDraw
from pathlib import Path

OUT = Path(__file__).parent / "icon.ico"
SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
margin = SIZE // 16
box = (margin, margin, SIZE - margin, SIZE - margin)
# тёмный полукруг (луна) — слева
d.pieslice(box, 90, 270, fill=(44, 62, 80, 255))
# светлый полукруг (солнце) — справа
d.pieslice(box, -90, 90, fill=(241, 196, 15, 255))

img.save(OUT, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"Сохранено: {OUT}")

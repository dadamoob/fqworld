"""Génère l'icône FQWorld (dégradé Twitch->TikTok + triangle play) en .ico."""
from PIL import Image, ImageDraw

SIZE = 256
img = Image.new("RGB", (SIZE, SIZE))
draw = ImageDraw.Draw(img)
for y in range(SIZE):
    ratio = y / (SIZE - 1)
    draw.line([(0, y), (SIZE - 1, y)],
              fill=(int(0x91 + (0xFF - 0x91) * ratio),
                    int(0x46 + (0x2D - 0x46) * ratio),
                    int(0xFF + (0x74 - 0xFF) * ratio)))
draw.polygon([(96, 72), (96, 184), (192, 128)], fill="white")
img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon.ico généré")

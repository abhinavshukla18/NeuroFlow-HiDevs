from PIL import Image, ImageDraw, ImageFont

img = Image.new("RGB", (1240, 1754), "white")
draw = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("arial.ttf", 48)
except OSError:
    font = ImageFont.load_default(48)
draw.text((100, 200), "NeuroFlow scanned page test.", fill="black", font=font)
draw.text((100, 300), "This text exists only as pixels.", fill="black", font=font)
img.save("scanned.pdf")
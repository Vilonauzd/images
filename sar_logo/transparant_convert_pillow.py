from PIL import Image, ImageDraw

img = Image.open("scoin1.png").convert("RGBA")
w, h = img.size
cx, cy = w // 2, h // 2
radius = min(cx, cy) - 10  # adjust if needed

mask = Image.new("L", (w, h), 0)
draw = ImageDraw.Draw(mask)
draw.ellipse(
    (cx - radius, cy - radius, cx + radius, cy + radius),
    fill=255
)

result = Image.new("RGBA", (w, h))
result.paste(img, (0, 0), mask)

result.save("coin_transparent.png")


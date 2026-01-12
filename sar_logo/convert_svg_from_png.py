#!/usr/bin/env python3
import sys
import os
from PIL import Image
import potrace

def png_jpg_to_svg(input_path: str, output_path: str = None):
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".svg"
    
    # Load and convert image to grayscale
    img = Image.open(input_path).convert("L")
    
    # Optional: apply threshold to improve tracing (e.g., for low-contrast images)
    img = img.point(lambda x: 0 if x < 128 else 255, mode="1")
    
    # Convert to bitmap for potrace
    bmp = potrace.Bitmap(img)
    
    # Trace with moderate precision; adjust parameters as needed
    curve = bmp.trace(
        turdsize=2,        # ignore tiny specks
        alpha_max=1.0,     # smooth corners
        opticurve=True,    # optimize curve fitting
        opttolerance=0.2   # trade-off between fidelity & simplicity
    )
    
    # Generate SVG
    svg = []
    svg.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    svg.append('<svg xmlns="http://www.w3.org/2000/svg" version="1.1"')
    svg.append(f' width="{img.width}" height="{img.height}" viewBox="0 0 {img.width} {img.height}">')
    svg.append('<path d="')

    for path in curve:
        svg.append(f"M {path.start_point.x},{path.start_point.y}")
        for segment in path:
            if segment.is_corner:
                svg.append(f"L {segment.c.x},{segment.c.y}")
                svg.append(f"L {segment.end_point.x},{segment.end_point.y}")
            else:
                svg.append(f"C {segment.c1.x},{segment.c1.y} "
                           f"{segment.c2.x},{segment.c2.y} "
                           f"{segment.end_point.x},{segment.end_point.y}")
        svg.append("z")

    svg.append('" style="fill:black;stroke:none"/>')
    svg.append('</svg>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    
    return output_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python png2svg.py <input.png/jpg> [output.svg]")
        sys.exit(1)
    
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        out_path = png_jpg_to_svg(inp, out)
        print(f"✓ SVG saved to: {out_path}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)

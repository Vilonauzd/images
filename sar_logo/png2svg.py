#!/usr/bin/env python3
import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
from skimage import filters
import svgwrite
import threading
import tempfile
import base64

# -------------------------------
# Core vectorization (from prior logic)
# -------------------------------
def raster_to_svg(img_bgra, output_path):
    h, w = img_bgra.shape[:2]
    if img_bgra.shape[2] == 4:
        bgr = img_bgra[:, :, :3]
        alpha = img_bgra[:, :, 3]
    else:
        bgr = img_bgra
        alpha = np.full((h, w), 255, dtype=np.uint8)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Adaptive binarization
    try:
        thresh = filters.threshold_sauvola(gray, window_size=25, k=0.15)
        binary = gray < thresh
    except:
        thresh = filters.threshold_otsu(gray)
        binary = gray < thresh

    # Cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    binary = cv2.morphologyEx(binary.astype(np.uint8), cv2.MORPH_CLOSE, kernel)

    contours, hierarchy = cv2.findContours(
        binary.astype(np.uint8) * 255,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_TC89_L1
    )

    dwg = svgwrite.Drawing(output_path, size=(f"{w}px", f"{h}px"))
    dwg.viewbox(0, 0, w, h)
    g = dwg.add(dwg.g(stroke="none"))

    min_area = max(4, (w * h) * 0.00005)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area: continue
        epsilon = 0.3 + 0.001 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3: continue
        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        avg_alpha = np.mean(alpha[mask > 0]) / 255.0 if np.any(mask) else 1.0
        avg_bgr = cv2.mean(bgr, mask=mask)[:3]
        color_hex = svgwrite.utils.rgb(*[int(c) for c in avg_bgr[::-1]])
        path_data = ["M " + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts), "z"]
        g.add(dwg.path(d=" ".join(path_data), fill=color_hex, fill_opacity=f"{avg_alpha:.3f}"))

    # Fallback for complex images
    if len(contours) > 200:
        _, buf = cv2.imencode(".png", img_bgra)
        data_url = "image/png;base64," + base64.b64encode(buf).decode()
        dwg.add(dwg.image(href=data_url, insert=(0, 0), size=(w, h)))

    dwg.save()
    return output_path

# -------------------------------
# GUI
# -------------------------------
class RasterToVectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Raster → Vector (High-Fidelity)")
        self.root.geometry("900x600")
        self.root.resizable(True, True)
        self.root.configure(bg="#f0f0f0")

        # State
        self.input_path = None
        self.svg_path = None
        self.preview_size = (380, 280)

        # Layout
        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Drop zone
        self.drop_frame = tk.LabelFrame(main_frame, text="📁 Drop PNG/JPG Here", bg="white", relief="groove")
        self.drop_frame.pack(fill=tk.X, pady=(0, 10))
        self.drop_label = tk.Label(
            self.drop_frame,
            text="📁 Drag & drop an image\nor click to browse",
            bg="white",
            fg="#555",
            font=("Segoe UI", 10),
            height=6,
            cursor="hand2"
        )
        self.drop_label.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.drop_label.bind("<Button-1>", self.browse_file)
        self.drop_frame.drop_target_register("DND_Files")
        self.drop_label.bind("<<Drop>>", self.on_drop)

        # Preview
        preview_frame = ttk.Frame(main_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.orig_label = ttk.Label(preview_frame, text="Original", font=("Segoe UI", 9, "bold"))
        self.orig_label.grid(row=0, column=0, padx=(0, 5))
        self.svg_label = ttk.Label(preview_frame, text="Vectorized", font=("Segoe UI", 9, "bold"))
        self.svg_label.grid(row=0, column=1, padx=(5, 0))

        self.orig_canvas = tk.Canvas(preview_frame, bg="#eee", width=self.preview_size[0], height=self.preview_size[1])
        self.orig_canvas.grid(row=1, column=0, padx=(0, 5))
        self.svg_canvas = tk.Canvas(preview_frame, bg="#eee", width=self.preview_size[0], height=self.preview_size[1])
        self.svg_canvas.grid(row=1, column=1, padx=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        self.export_btn = ttk.Button(btn_frame, text="💾 Export SVG", command=self.export_svg, state="disabled")
        self.export_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.convert_btn = ttk.Button(btn_frame, text="⚡ Convert", command=self.start_conversion, state="disabled")
        self.convert_btn.pack(side=tk.RIGHT, padx=(5, 0))

        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(fill=tk.X, pady=(5, 0))

        # Bind window resize
        self.root.bind("<Configure>", self.on_resize)

    def browse_file(self, _=None):
        path = filedialog.askopenfilename(
            title="Select PNG/JPG",
            filetypes=[("Images", "*.png *.jpg *.jpeg")]
        )
        if path:
            self.load_image(path)

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files and files[0].lower().endswith(('.png', '.jpg', '.jpeg')):
            self.load_image(files[0])

    def load_image(self, path):
        try:
            self.input_path = path
            self.display_image(self.orig_canvas, path)
            self.convert_btn.config(state="normal")
            self.export_btn.config(state="disabled")
            self.svg_path = None
            self.status_var.set(f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{e}")

    def display_image(self, canvas, path, svg_mode=False):
        canvas.delete("all")
        try:
            if svg_mode:
                # Render SVG to PNG via PIL (lightweight)
                from PIL import Image
                import io
                with open(path, "rb") as f:
                    svg_data = f.read()
                # Use Tk SVG? Not built-in → convert via cairo if available, else skip
                # Fallback: show "SVG Preview" text
                canvas.create_text(
                    self.preview_size[0]//2, self.preview_size[1]//2,
                    text="✅ SVG Generated\n(Open in browser to preview)",
                    fill="#0066cc", font=("Segoe UI", 10)
                )
            else:
                img = Image.open(path)
                img.thumbnail(self.preview_size, Image.Resampling.LANCZOS)
                self.tk_img = ImageTk.PhotoImage(img)
                canvas.create_image(
                    self.preview_size[0]//2, self.preview_size[1]//2,
                    anchor="center", image=self.tk_img
                )
        except Exception as e:
            canvas.create_text(
                self.preview_size[0]//2, self.preview_size[1]//2,
                text=f"Preview Error:\n{type(e).__name__}",
                fill="red", font=("Segoe UI", 8)
            )

    def start_conversion(self):
        if not self.input_path:
            return
        self.convert_btn.config(state="disabled")
        self.status_var.set("Converting... (this may take a few seconds)")
        self.root.update()
        threading.Thread(target=self.convert_bg, daemon=True).start()

    def convert_bg(self):
        try:
            # Load image
            img = cv2.imread(self.input_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                raise ValueError("OpenCV failed to read image")

            # Vectorize
            self.svg_path = tempfile.mktemp(suffix=".svg")
            raster_to_svg(img, self.svg_path)

            # Update UI
            self.root.after(0, self.on_convert_success)
        except Exception as e:
            self.root.after(0, lambda: self.on_convert_error(e))

    def on_convert_success(self):
        self.display_image(self.svg_canvas, self.svg_path, svg_mode=True)
        self.export_btn.config(state="normal")
        self.status_var.set("✅ Conversion complete! Click 'Export SVG' to save.")
        self.convert_btn.config(state="normal")

    def on_convert_error(self, e):
        messagebox.showerror("Conversion Failed", str(e))
        self.status_var.set("❌ Conversion failed")
        self.convert_btn.config(state="normal")

    def export_svg(self):
        if not self.svg_path:
            return
        save_path = filedialog.asksaveasfilename(
            title="Save SVG",
            defaultextension=".svg",
            filetypes=[("SVG", "*.svg")],
            initialfile=os.path.splitext(os.path.basename(self.input_path))[0] + ".svg"
        )
        if save_path:
            try:
                with open(self.svg_path, "rb") as src, open(save_path, "wb") as dst:
                    dst.write(src.read())
                messagebox.showinfo("Success", f"SVG saved to:\n{save_path}")
                self.status_var.set(f"Exported: {os.path.basename(save_path)}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))

    def on_resize(self, _=None):
        # Keep preview squares
        w = self.root.winfo_width() - 40
        size = min(380, max(200, (w - 20) // 2))
        self.preview_size = (size, int(size * 0.74))
        self.orig_canvas.config(width=size, height=int(size * 0.74))
        self.svg_canvas.config(width=size, height=int(size * 0.74))

# -------------------------------
# DnD Support (Windows via `tkinterdnd2`)
# -------------------------------
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    class AppWindow(TkinterDnD.Tk):
        pass
except ImportError:
    class AppWindow(tk.Tk):
        def drop_target_register(self, *args): pass

if __name__ == "__main__":
    root = AppWindow()
    if hasattr(root, "drop_target_register"):
        root.drop_target_register(DND_FILES)
    app = RasterToVectorApp(root)
    root.mainloop()
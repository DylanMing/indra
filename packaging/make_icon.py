#!/usr/bin/env python3
"""Draw ``packaging/indra_ocr.ico`` and ``.icns`` (the app icon) with Pillow.

    python packaging/make_icon.py

One rounded square, a white page and four text lines, the last one in cyan: the
line being read.  Drawn large and downsampled, so 16 px stays legible.  The .ico
is for Windows (the exe and the setup), the .icns for the macOS .app bundle.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "indra_ocr.ico"
ICNS = OUT.with_suffix(".icns")
SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
N = 1024


def rounded(size: int, box, radius: int, fill) -> Image.Image:
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, fill=fill)
    return im


def main() -> None:
    base = Image.new("RGBA", (N, N), (0, 0, 0, 0))

    # Background: indigo, a little lighter at the top.
    bg = Image.new("RGBA", (N, N))
    draw = ImageDraw.Draw(bg)
    top, bottom = (99, 102, 241), (67, 56, 202)  # indigo-500 -> indigo-700
    for y in range(N):
        t = y / (N - 1)
        draw.line(
            [(0, y), (N, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,),
        )
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, N - 1, N - 1), radius=230, fill=255)
    base.paste(bg, (0, 0), mask)

    # The page, and the lines on it.
    page = rounded(N, (248, 168, 776, 856), 44, (255, 255, 255, 255))
    base.alpha_composite(page)
    lines = [
        (320, 274, 704, 274, (17, 24, 39, 190)),
        (320, 392, 640, 392, (17, 24, 39, 150)),
        (320, 510, 704, 510, (17, 24, 39, 150)),
        (320, 628, 546, 628, (6, 182, 212, 255)),  # cyan: the line being read
    ]
    draw = ImageDraw.Draw(base)
    for x0, y0, x1, y1, col in lines:
        draw.rounded_rectangle((x0, y0 - 17, x1, y1 + 17), radius=17, fill=col)

    base.save(OUT, sizes=SIZES)
    # Pillow writes the macOS sizes (16..1024) from the 1024 canvas, so the .app
    # bundle gets a Retina icon without iconutil or a Mac in the loop.
    base.save(ICNS)
    previews = Path(tempfile.gettempdir()) / "indra-icon"  # to look at, not committed
    previews.mkdir(exist_ok=True)
    for w, h in SIZES:
        base.resize((w, h), Image.LANCZOS).save(previews / f"icon-{w}.png")
    print(
        f"wrote {OUT} ({OUT.stat().st_size / 1024:.1f} kB) and "
        f"{ICNS.name} ({ICNS.stat().st_size / 1024:.1f} kB); previews in {previews}"
    )


if __name__ == "__main__":
    main()

"""The handful of image operations this project needs, without OpenCV.

The bundle used to carry ``cv2``: an 86 MB binary plus a 31 MB video DLL, for six
operations — decode, encode, resample, rotate, label connected components, and one
``putText`` in the self test's demo page. That was 117 MB of a 352 MB download.

This module keeps the call sites unchanged (they are written against the OpenCV
API: ``cv2.resize``, ``cv2.INTER_AREA``, ``cv2.connectedComponentsWithStats``), and
implements it with Pillow and NumPy:

* ``resize``: Pillow's BOX (area average) and BILINEAR filters for uint8, which is
  what the OCR path feeds them; a NumPy bilinear for float maps.
* ``warpAffine``: Pillow's ``AFFINE`` transform over an edge-padded copy of the
  source, which is ``BORDER_REPLICATE`` without sampling outside the image.
* ``connectedComponentsWithStats``: run-length union-find. A mask of a page is a
  few thousand runs, so it is fast, and the boxes come out discrete — identical
  to OpenCV's, up to the order of the labels (see tests/test_imaging.py).

tests/test_imaging.py compares every operation with OpenCV when it is installed,
so the equivalence is checked rather than assumed; the desktop build excludes
``cv2`` entirely (packaging/indra_ocr.spec) and the package no longer depends on it.
"""

from __future__ import annotations

import math
from io import BytesIO

import numpy as np
from PIL import Image

# The OpenCV constants the call sites pass around.
INTER_NEAREST = 0
INTER_LINEAR = 1
INTER_AREA = 3
BORDER_CONSTANT = 0
BORDER_REPLICATE = 1
IMREAD_GRAYSCALE = 0
IMWRITE_JPEG_QUALITY = 1
IMWRITE_PNG_COMPRESSION = 16
LINE_AA = 16
FONT_HERSHEY_SIMPLEX = 0
CC_STAT_LEFT = 0
CC_STAT_TOP = 1
CC_STAT_WIDTH = 2
CC_STAT_HEIGHT = 3
CC_STAT_AREA = 4

_PIL_FILTERS = {
    INTER_NEAREST: Image.NEAREST,
    INTER_LINEAR: Image.BILINEAR,
    INTER_AREA: Image.BOX,
}

_threads = 0  # cv2.setNumThreads: recorded, because nothing here starts threads


def setNumThreads(n: int) -> None:  # noqa: N802 - the OpenCV spelling
    """Kept for the call sites: the samplers below use no threads of their own."""
    global _threads
    _threads = int(n)


def _dsize(shape, dsize, fx, fy):
    h, w = shape[:2]
    if dsize is None:
        if fx is None and fy is None:
            raise ValueError("resize needs dsize or fx/fy")
        return max(1, int(round(w * (fx or 1.0)))), max(1, int(round(h * (fy or 1.0))))
    return max(1, int(dsize[0])), max(1, int(dsize[1]))


def resize(src: np.ndarray, dsize, fx=None, fy=None, interpolation=INTER_LINEAR):
    """Scale ``src`` to ``dsize`` (w, h), like ``cv2.resize``.

    uint8 goes through Pillow: BOX is an area average when shrinking and BILINEAR
    interpolates when growing, which is what the OCR path asks for. Float maps
    (the centre-line probabilities) take the NumPy bilinear below.
    """
    dw, dh = _dsize(src.shape, dsize, fx, fy)
    h, w = src.shape[:2]
    if (dw, dh) == (w, h):
        return src
    if src.dtype == np.uint8:
        filt = _PIL_FILTERS.get(interpolation, Image.BILINEAR)
        return np.asarray(Image.fromarray(src).resize((dw, dh), filt))
    # Float maps: bilinear with OpenCV's half-pixel centres.
    if interpolation == INTER_NEAREST:
        yi = np.clip(((np.arange(dh) + 0.5) * h / dh).astype(int), 0, h - 1)
        xi = np.clip(((np.arange(dw) + 0.5) * w / dw).astype(int), 0, w - 1)
        return src[yi][:, xi]
    xs = ((np.arange(dw) + 0.5) * w / dw - 0.5)[None, :]
    ys = ((np.arange(dh) + 0.5) * h / dh - 0.5)[:, None]
    return _bilinear_sample(src, xs, ys)


def _bilinear_sample(src: np.ndarray, xs, ys) -> np.ndarray:
    """``out[y, x] = src[ys, xs]`` bilinear, edges clamped.

    ``xs`` and ``ys`` broadcast, so a resize passes a row and a column and a
    rotation passes two full grids.
    """
    h, w = src.shape[:2]
    xs = np.asarray(xs, np.float64)
    ys = np.asarray(ys, np.float64)
    x0f = np.floor(xs)
    y0f = np.floor(ys)
    wx = xs - x0f
    wy = ys - y0f
    x0 = np.clip(x0f.astype(np.int64), 0, w - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y0 = np.clip(y0f.astype(np.int64), 0, h - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    a = src[y0, x0]
    b = src[y0, x1]
    c = src[y1, x0]
    d = src[y1, x1]
    out = (
        a * ((1 - wx) * (1 - wy))
        + b * (wx * (1 - wy))
        + c * ((1 - wx) * wy)
        + d * (wx * wy)
    )
    if src.dtype == np.uint8:
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return out.astype(src.dtype, copy=False)


def getRotationMatrix2D(center, angle: float, scale: float) -> np.ndarray:  # noqa: N802
    """2x3 matrix of a rotation about ``center``, positive angles counter-clockwise."""
    cx, cy = float(center[0]), float(center[1])
    a = math.cos(math.radians(angle)) * scale
    b = math.sin(math.radians(angle)) * scale
    return np.array(
        [[a, b, (1 - a) * cx - b * cy], [-b, a, b * cx + (1 - a) * cy]], np.float64
    )


def warpAffine(  # noqa: N802
    src: np.ndarray,
    M: np.ndarray,
    dsize,
    flags=INTER_LINEAR,
    borderMode=BORDER_CONSTANT,
    borderValue=0,
):
    """``dst(x, y) = src(M * [x, y, 1])``, sampled bilinearly.

    ``BORDER_REPLICATE`` (what the deskew uses) is done by edge-padding the source
    by the overshoot of the rotation, so nothing samples outside the image; the
    corners then repeat the edge instead of turning black.
    """
    dw, dh = _dsize(src.shape, dsize, None, None)
    h, w = src.shape[:2]
    inv = np.linalg.inv(np.vstack([M, [0.0, 0.0, 1.0]]))[:2]
    if src.dtype == np.uint8 and src.ndim == 2:
        # Pillow's transform: 8 ms for an 800x566 thumbnail, and it releases the
        # GIL, so the 35 rotations of the deskew search run on the thread pool
        # (2.5 ms each on four). The NumPy path below does the same in 39 ms.
        pad = 0
        if borderMode == BORDER_REPLICATE:
            corners = np.array(
                [[0, 0, 1], [dw, 0, 1], [0, dh, 1], [dw, dh, 1]], np.float64
            ).T
            xs, ys = inv[0] @ corners, inv[1] @ corners
            over = max(0.0, -xs.min(), -ys.min(), xs.max() - (w - 1), ys.max() - (h - 1))
            pad = min(int(math.ceil(over)) + 1, max(w, h))
        big = np.pad(src, pad, mode="edge") if pad else src
        coeffs = (
            float(inv[0, 0]),
            float(inv[0, 1]),
            float(inv[0, 2]) + pad,
            float(inv[1, 0]),
            float(inv[1, 1]),
            float(inv[1, 2]) + pad,
        )
        filt = _PIL_FILTERS.get(flags, Image.BILINEAR)
        filled = 255 if (borderValue == 255) else 0
        out = Image.fromarray(big).transform(
            (dw, dh), Image.AFFINE, coeffs, resample=filt, fillcolor=filled
        )
        return np.asarray(out)
    # Float maps and constants: interpolate the inverse map directly.
    gy, gx = np.mgrid[0:dh, 0:dw].astype(np.float64)
    xs = inv[0, 0] * gx + inv[0, 1] * gy + inv[0, 2]
    ys = inv[1, 0] * gx + inv[1, 1] * gy + inv[1, 2]
    out = _bilinear_sample(src, xs, ys)
    if borderMode != BORDER_REPLICATE:
        outside = (xs < -0.5) | (xs > w - 0.5) | (ys < -0.5) | (ys > h - 0.5)
        out[outside] = borderValue
    return out


def _to_gray(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr)


def imdecode(buf, flags=IMREAD_GRAYSCALE):  # noqa: N802
    """Decode an image from memory; ``None`` if the bytes are not an image."""
    try:
        img = Image.open(BytesIO(bytes(buf)))
        img.load()
    except Exception:  # noqa: BLE001  (not an image, truncated, unsupported)
        return None
    if flags == IMREAD_GRAYSCALE:
        img = img.convert("L")
    return _to_gray(np.asarray(img))


def imdecodemulti(buf, flags=IMREAD_GRAYSCALE):  # noqa: N802
    """Decode every frame of an image (a multi-page TIFF); ``(ok, frames)``."""
    try:
        img = Image.open(BytesIO(bytes(buf)))
    except Exception:  # noqa: BLE001
        return False, []
    frames = []
    try:
        for i in range(getattr(img, "n_frames", 1)):
            img.seek(i)
            frame = img.convert("L" if flags == IMREAD_GRAYSCALE else "RGB")
            frames.append(np.asarray(frame))
    except Exception:  # noqa: BLE001  (a broken second frame: keep what we have)
        if not frames:
            return False, []
    img.close()
    return True, frames


def imread(path, flags=IMREAD_GRAYSCALE):  # noqa: N802
    try:
        data = open(str(path), "rb").read()
    except OSError:
        return None
    return imdecode(data, flags)


def imencode(ext: str, img: np.ndarray, params=None):  # noqa: N802
    """Encode to JPEG or PNG in memory; ``(ok, array)`` like OpenCV's uint8 buffer."""
    ext = ext if str(ext).startswith(".") else "." + str(ext)
    params = list(params or [])
    quality = 95
    for i in range(0, len(params) - 1, 2):
        if params[i] == IMWRITE_JPEG_QUALITY:
            quality = int(params[i + 1])
    buf = BytesIO()
    try:
        if img.dtype != np.uint8:
            img = np.clip(img, 0, 255).astype(np.uint8)
        if img.ndim == 3:  # OpenCV hands over BGR; Pillow wants RGB
            img = np.ascontiguousarray(img[:, :, ::-1])
        Image.fromarray(img).save(
            buf,
            format="JPEG" if ext.lower() in (".jpg", ".jpeg") else "PNG",
            quality=quality,
        )
    except Exception:  # noqa: BLE001  (an encoder that cannot take this array)
        return False, np.zeros(0, np.uint8)
    return True, np.frombuffer(buf.getvalue(), np.uint8)


def connectedComponentsWithStats(mask, connectivity: int = 8):  # noqa: N802
    """Label the nonzero blobs; ``(n, labels, stats, centroids)`` like OpenCV.

    Labels run in the order the blobs are first met scanning row by row (OpenCV's
    order), background is 0, and ``stats`` holds left, top, width, height and area.
    """
    m = np.ascontiguousarray(mask.astype(bool))
    h, w = m.shape[:2]
    # Runs of foreground pixels, one row at a time. Python lists, not NumPy
    # scalars: this loop walks every run of the mask, and a mask from the
    # detector has thousands.
    edges = np.diff(
        np.concatenate(
            (np.zeros((h, 1), np.int8), m.astype(np.int8), np.zeros((h, 1), np.int8)),
            axis=1,
        ),
        axis=1,
    )
    sr, sc = np.nonzero(edges == 1)
    er, ec = np.nonzero(edges == -1)
    if not np.array_equal(sr, er):  # pragma: no cover  (every run has an end)
        raise ValueError("the mask is not a sequence of runs")
    starts = list(zip(sr.tolist(), sc.tolist()))  # (row, x0)
    ends = ec.tolist()  # x1, in the same order
    parent: list[int] = []

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    runs = []  # (row, x0, x1, id)
    prev_row, prev = -2, []  # the row above, and its runs
    cur_row, cur = -1, []  # the row being read
    slack = 1 if connectivity == 8 else 0
    for (r, x0), x1 in zip(starts, ends):
        if r != cur_row:
            prev_row, prev = cur_row, cur
            cur_row, cur = r, []
        rid = len(parent)
        parent.append(rid)
        # Only the row directly above can touch this one: a blank row ends a blob.
        if cur_row - prev_row == 1:
            for px0, px1, pid in prev:
                if px0 - slack < x1 and x0 < px1 + slack:
                    union(rid, pid)
        runs.append((r, x0, x1, rid))
        cur.append((x0, x1, rid))
    # Canonical labels in the order the blobs were first met.
    canonical: dict[int, int] = {}
    labels = np.zeros((h, w), np.int32)
    for r, x0, x1, rid in runs:
        root = find(rid)
        if root not in canonical:
            canonical[root] = len(canonical) + 1
        labels[r, x0:x1] = canonical[root]
    n = len(canonical) + 1
    stats = np.zeros((n, 5), np.int32)
    centroids = np.zeros((n, 2), np.float64)
    for r, x0, x1, rid in runs:
        lab = canonical[find(rid)]
        st = stats[lab]
        width = x1 - x0
        if st[CC_STAT_WIDTH] == 0:  # first run of the blob
            st[CC_STAT_LEFT], st[CC_STAT_TOP] = x0, r
            st[CC_STAT_WIDTH], st[CC_STAT_HEIGHT] = width, 1
        else:
            right = max(st[CC_STAT_LEFT] + st[CC_STAT_WIDTH], x1)
            st[CC_STAT_LEFT] = min(st[CC_STAT_LEFT], x0)
            st[CC_STAT_TOP] = min(st[CC_STAT_TOP], r)
            st[CC_STAT_WIDTH] = right - st[CC_STAT_LEFT]
            st[CC_STAT_HEIGHT] = max(st[CC_STAT_TOP] + st[CC_STAT_HEIGHT], r + 1) - st[CC_STAT_TOP]
        st[CC_STAT_AREA] += width
        centroids[lab, 0] += (x0 + x1 - 1) / 2.0 * width
        centroids[lab, 1] += r * width
    nonzero = stats[:, CC_STAT_AREA] > 0
    centroids[nonzero] /= stats[nonzero, CC_STAT_AREA][:, None]
    background = ~m
    stats[0, CC_STAT_AREA] = int(background.sum())
    if stats[0, CC_STAT_AREA]:
        ys, xs = np.nonzero(background)
        stats[0, CC_STAT_LEFT], stats[0, CC_STAT_TOP] = int(xs.min()), int(ys.min())
        stats[0, CC_STAT_WIDTH] = int(xs.max() - xs.min() + 1)
        stats[0, CC_STAT_HEIGHT] = int(ys.max() - ys.min() + 1)
        centroids[0] = [float(xs.mean()), float(ys.mean())]
    return n, labels, stats, centroids


def putText(img, text, org, fontFace, fontScale, color, thickness=1, lineType=0):  # noqa: N802
    """Draw text into ``img`` in place (the self test's demo page uses it).

    BGR callers get BGR back: the array is drawn on as an RGB image and written
    the same way round it arrived.
    """
    if img.dtype != np.uint8:
        return img
    from PIL import ImageDraw, ImageFont

    color_bgr = img.ndim == 3
    pil = Image.fromarray(img[:, :, ::-1] if color_bgr else img)
    size = max(8, int(round(20 * float(fontScale))))
    try:
        font = ImageFont.load_default(size=size)
    except (TypeError, OSError):  # Pillow older than 10.1
        font = ImageFont.load_default()
    fill = (
        tuple(int(c) for c in reversed(color)) if color_bgr else int(
            color if isinstance(color, (int, float)) else sum(color) / 3
        )
    )
    ImageDraw.Draw(pil).text(
        (int(org[0]), int(org[1])), str(text), font=font, fill=fill
    )
    drawn = np.asarray(pil)
    img[:, :] = drawn[:, :, ::-1] if color_bgr else drawn
    return img

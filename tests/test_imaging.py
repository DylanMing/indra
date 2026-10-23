"""The imaging layer against OpenCV, and the OCR output against a golden.

Two jobs:

* the operations themselves — resize, rotate, label, decode, encode — are checked
  against real OpenCV when it is installed (it is a test-only dependency now, so
  these comparisons run in CI and skip when the wheel is absent);
* one whole page is read and compared with ``goldens/page.json``, which was
  captured from the build that still shipped OpenCV. That is the "did the OCR
  change" test: same text, same number of lines, boxes within a few pixels.

The page is drawn with Pillow's bundled font, so the fixture is the same picture
on every machine, and no model file is needed for the operation tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from indra_ocr import imaging as im

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "goldens" / "page.json"

try:  # the reference implementation: only for the comparison tests
    import cv2
except ImportError:  # pragma: no cover  (CI installs it in the test extra)
    cv2 = None

needs_cv2 = pytest.mark.skipif(cv2 is None, reason="opencv is not installed")


def page_image() -> np.ndarray:
    """A page with known text; deterministic on every platform."""
    img = Image.new("L", (1000, 1400), 246)
    d = ImageDraw.Draw(img)
    size = 26
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover  (Pillow < 10.1)
        font = ImageFont.load_default()
    d.text((70, 60), "Reading order and boxes", font=font, fill=20)
    lines = [
        "first line of the document",
        "second line with a few more words",
        "third line, close to the one above",
        "",
        "after a blank line: 12345",
        "and the last line of the page",
    ]
    y = 140
    for text in lines:
        if text:
            d.text((70, y), text, font=font, fill=25)
        y += 40
    return np.asarray(img)


# --- the operations ---------------------------------------------------------


def test_resize_area_is_the_block_average():
    """A 4x4 image of four 2x2 blocks: area shrink to 2x2 is their mean."""
    a = np.zeros((4, 4), np.uint8)
    a[:2, :2] = 10
    a[:2, 2:] = 20
    a[2:, :2] = 30
    a[2:, 2:] = 40
    out = im.resize(a, (2, 2), interpolation=im.INTER_AREA)
    assert out.shape == (2, 2)
    assert out.tolist() == [[10, 20], [30, 40]]


def test_resize_keeps_the_shape_it_was_given():
    a = np.full((100, 60), 7, np.uint8)
    assert im.resize(a, (30, 50)).shape == (50, 30)
    assert im.resize(a, None, fx=0.5, fy=0.75).shape == (75, 30)
    assert im.resize(a, (60, 100)) is a, "no scaling, no copy"


def test_resize_float_maps_stay_float_and_clamped():
    a = np.zeros((10, 10), np.float32)
    a[:, :5] = 1.0
    out = im.resize(a, (20, 20), interpolation=im.INTER_LINEAR)
    assert out.shape == (20, 20) and out.dtype == np.float32
    assert out.max() <= 1.0 and out.min() >= 0.0
    assert abs(float(out[:, :2].mean()) - 1.0) < 0.05, "left half stays solid"


@needs_cv2
def test_resize_agrees_with_opencv():
    rng = np.random.default_rng(1)
    a = (rng.random((120, 90)) * 255).astype(np.uint8)

    # An integer shrink by area averaging is the same average in both: rounding only.
    exact = im.resize(a[:90, :90], (30, 30), interpolation=im.INTER_AREA)
    ref = cv2.resize(a[:90, :90], (30, 30), interpolation=cv2.INTER_AREA)
    assert np.abs(exact.astype(np.int16) - ref.astype(np.int16)).max() <= 1

    # A fractional shrink weights the edge pixels differently: same picture,
    # different arithmetic on the borders.
    frac = im.resize(a, (40, 30), interpolation=im.INTER_AREA)
    ref = cv2.resize(a, (40, 30), interpolation=cv2.INTER_AREA)
    diff = np.abs(frac.astype(np.int16) - ref.astype(np.int16))
    assert diff.mean() < 8 and diff.max() <= 64, (diff.mean(), diff.max())

    # Growing is bilinear in both, to the last bit of rounding.
    up = im.resize(a, (180, 240), interpolation=im.INTER_LINEAR)
    ref = cv2.resize(a, (180, 240), interpolation=cv2.INTER_LINEAR)
    assert np.abs(up.astype(np.int16) - ref.astype(np.int16)).max() <= 2


@needs_cv2
def test_rotate_agrees_with_opencv_and_repeats_the_edge():
    rng = np.random.default_rng(2)
    a = (rng.random((120, 90)) * 255).astype(np.uint8)
    M = im.getRotationMatrix2D((45, 60), 3.0, 1.0)
    assert M.shape == (2, 3)
    mine = im.warpAffine(a, M, (90, 120), borderMode=im.BORDER_REPLICATE)
    ref = cv2.warpAffine(a, M, (90, 120), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    diff = np.abs(mine.astype(np.int16) - ref.astype(np.int16))
    assert diff.mean() < 3 and diff.max() <= 32
    # the corners take the edge value rather than black (BORDER_REPLICATE)
    assert mine[0, 0] > 0 and mine[-1, -1] > 0


def test_a_zero_rotation_changes_nothing_but_a_pixel_of_rounding():
    a = np.full((20, 30), 128, np.uint8)
    M = im.getRotationMatrix2D((15, 10), 0.0, 1.0)
    out = im.warpAffine(a, M, (30, 20), borderMode=im.BORDER_REPLICATE)
    assert np.abs(out.astype(int) - 128).max() <= 1


def test_connected_components_labels_and_boxes():
    m = np.zeros((30, 40), np.uint8)
    m[2:10, 3:13] = 1  # a 8x10 box
    m[15:20, 20:25] = 1  # a 5x5 box
    n, labels, stats, centroids = im.connectedComponentsWithStats(m, connectivity=8)
    assert n == 3  # background + two
    boxes = sorted(map(tuple, stats[1:].tolist()))
    assert boxes == [(3, 2, 10, 8, 80), (20, 15, 5, 5, 25)]
    assert labels[2, 3] != 0 and labels[15, 20] != 0
    assert labels[2, 3] != labels[15, 20]
    assert stats[0, im.CC_STAT_AREA] == m.size - 105, "label 0 counts the background"
    assert centroids[1][0] == pytest.approx(7.5) and centroids[1][1] == pytest.approx(5.5)


def test_connectivity_of_four_keeps_a_diagonal_apart():
    m = np.zeros((6, 6), np.uint8)
    m[1, 1] = 1
    m[2, 2] = 1
    assert im.connectedComponentsWithStats(m, connectivity=4)[0] == 3
    assert im.connectedComponentsWithStats(m, connectivity=8)[0] == 2


def test_a_blank_row_separates_two_blobs():
    """Regression: the row above must be forgotten when a row is empty."""
    m = np.zeros((12, 8), np.uint8)
    m[1:4, 1:7] = 1
    m[6:9, 1:7] = 1  # two blank rows between
    n, _, stats, _ = im.connectedComponentsWithStats(m, connectivity=4)
    assert n == 3, stats[1:].tolist()


@needs_cv2
def test_connected_components_agree_with_opencv_on_random_masks():
    rng = np.random.default_rng(3)
    for _ in range(12):
        h, w = (int(v) for v in rng.integers(6, 40, 2))
        m = (rng.random((h, w)) < 0.55).astype(np.uint8)
        for conn in (4, 8):
            n, _, stats, _ = im.connectedComponentsWithStats(m, conn)
            n2, _, stats2, _ = cv2.connectedComponentsWithStats(m, connectivity=conn)
            assert n == n2, (conn, n, n2)
            assert sorted(map(tuple, stats[1:].tolist())) == sorted(
                map(tuple, stats2[1:].tolist())
            )


def test_png_round_trip_is_lossless_and_jpeg_is_not():
    a = np.arange(120, dtype=np.uint8).reshape(10, 12)
    ok, buf = im.imencode(".png", a)
    assert ok and isinstance(buf, np.ndarray)
    back = im.imdecode(buf, im.IMREAD_GRAYSCALE)
    assert np.array_equal(back, a)

    ok, jpg = im.imencode(".jpg", a, [im.IMWRITE_JPEG_QUALITY, 95])
    assert ok and jpg.size < buf.size * 12, "a JPEG, not a raw dump"
    back = im.imdecode(jpg, im.IMREAD_GRAYSCALE)
    assert back.shape == a.shape
    assert np.abs(back.astype(int) - a.astype(int)).mean() < 6, "lossy, but close"


def test_bytes_that_are_not_an_image_decode_to_none():
    assert im.imdecode(b"not an image") is None
    assert im.imdecodemulti(b"not an image") == (False, [])
    assert im.imread("no-such-file.png") is None


def test_multiframe_images_come_out_a_list():
    import io

    a = Image.fromarray(np.full((40, 60), 255, np.uint8))
    b = Image.fromarray(np.zeros((40, 60), np.uint8))
    buf = io.BytesIO()
    a.save(buf, format="TIFF", save_all=True, append_images=[b])
    ok, frames = im.imdecodemulti(buf.getvalue(), im.IMREAD_GRAYSCALE)
    assert ok and len(frames) == 2
    assert frames[0].max() == 255 and frames[1].max() == 0


def test_put_text_draws_into_the_array_it_was_given():
    img = np.full((120, 420, 3), 255, np.uint8)
    before = img.copy()
    im.putText(img, "AB", (10, 30), im.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3, im.LINE_AA)
    assert img.shape == before.shape and img.dtype == np.uint8
    assert (img != before).any(), "something was drawn"
    assert img.min() < 100, "the text is dark"


def test_no_cv2_is_needed_to_read_a_page():
    """Import-time proof: nothing in the package reaches for OpenCV any more."""
    import subprocess
    import sys

    code = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name.split('.')[0] == 'cv2':\n"
        "        raise ImportError('cv2 is not part of the package')\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        "import indra_ocr.pipeline, indra_ocr.viewer, indra_ocr.desktop\n"
        "import indra_ocr.line_mask, indra_ocr.det_post, indra_ocr.parallel\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-800:]
    assert "ok" in r.stdout


# --- one page, against the build that shipped OpenCV -------------------------


@pytest.mark.skipif(not GOLDEN.is_file(), reason="no golden recorded")
def test_a_whole_page_reads_like_it_did_with_opencv():
    """tests/goldens/page.json was made by the cv2 build (961c17f)."""
    from indra_ocr.models import model_dir

    models = model_dir(math=False)
    if models is None:  # pragma: no cover  (no cache and no network)
        pytest.skip("no models")

    from indra_ocr.pipeline import OrtOCR

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    ocr = OrtOCR(models, threads=4)
    page = ocr(page_image())

    assert len(page.lines) == len(golden["lines"]), "line count changed"
    assert [l.text for l in page.lines] == [l["text"] for l in golden["lines"]]
    for got, want in zip(page.lines, golden["lines"]):
        drift = max(abs(a - b) for a, b in zip(got.box, want["box"]))
        assert drift <= 6, (got.text, drift)

"""One page, read exactly like the release that produced the golden.

``tests/goldens/page.json`` was recorded by 1.1.5 (961c17f). Whatever changes in
the pipeline, the same page must come back with the same lines, the same text and
boxes in the same place — this is the test that notices when a refactor of the
pixel code moves a threshold by a pixel and the OCR quietly reads something else.

The page is drawn with Pillow's bundled font, so the fixture is the same picture
on every machine. The test needs the models, and skips without them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "goldens" / "page.json"


def page_image() -> np.ndarray:
    """A page with known text: a heading, a paragraph, a gap, a short line."""
    img = Image.new("L", (1000, 1400), 246)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=26)
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


@pytest.mark.skipif(not GOLDEN.is_file(), reason="no golden recorded")
def test_a_whole_page_reads_like_the_golden():
    from indra_ocr.models import model_dir

    models = model_dir(math=False)
    if models is None:  # pragma: no cover  (no cache and no network)
        pytest.skip("no models")

    from indra_ocr.pipeline import OrtOCR

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    page = OrtOCR(models, threads=4)(page_image())

    assert len(page.lines) == len(golden["lines"]), "line count changed"
    assert [l.text for l in page.lines] == [l["text"] for l in golden["lines"]]
    for got, want in zip(page.lines, golden["lines"]):
        drift = max(abs(a - b) for a, b in zip(got.box, want["box"]))
        assert drift <= 6, (got.text, drift)

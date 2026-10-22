"""Model metadata is UTF-8, whatever code page the console happens to use.

math_meta.json lists tokens such as °, –, ’, ⁄. Reading it with the locale's
encoding (cp936 on a Chinese Windows) raised UnicodeDecodeError, so --math and
the viewer's "Math as LaTeX" switch never worked there.
"""

import json

from indra_ocr.models import read_json

TOKENS = ["\u00b0", "\u2013", "\u2019", "\u2044"]


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_meta_is_read_as_utf8(tmp_path):
    p = _write(tmp_path / "math_meta.json", {"tokens": TOKENS})
    assert read_json(p) == {"tokens": TOKENS}
    assert read_json(str(p))["tokens"] == TOKENS


def test_meta_under_a_non_ascii_path(tmp_path):
    p = _write(tmp_path / "模型.json", {"tokens": TOKENS})
    assert read_json(p)["tokens"] == TOKENS

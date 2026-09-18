"""Phase 9B: conservative multi-pass OCR with block-level merging.

Pass A (the established pipeline) is never altered. Recovery passes fire
only when mandatory-declaration anchors are missing, and their blocks merge
under strict duplicate rules (IoU or shared center; stronger detection
wins; pass A wins ties) so no logical field is ever duplicated.
"""
import numpy as np

from app.ocr.engine import BaseOCREngine, RawOCRResult, RawWord
from app.ocr.multipass import recover_missing_declarations
from app.ocr.parser import parse_blocks


class _ScriptedEngine(BaseOCREngine):
    """Returns a scripted result per call, in call order."""

    def __init__(self, results: list[RawOCRResult]):
        self.results = list(results)
        self.calls = 0

    def extract(self, image: np.ndarray) -> RawOCRResult:
        self.calls += 1
        if self.calls > len(self.results):
            return RawOCRResult(width=800, height=400)
        return self.results[self.calls - 1]


def _words(*triples: tuple[str, int, int], confidence: float = 90.0) -> RawOCRResult:
    words = [
        RawWord(text=t, confidence=confidence, x=x, y=y, width=10 * len(t), height=12, line_number=i + 1, block_number=i + 1)
        for i, (t, x, y) in enumerate(triples)
    ]
    return RawOCRResult(words=words, width=800, height=400)


def _mrp_only() -> RawOCRResult:
    # Tight x-spacing: word gaps within the parser's merge threshold so the
    # line reads as one block, matching real engine output.
    return _words(("MRP", 100, 100), ("Rs.", 136, 100), ("68.00", 166, 100))


def _net_weight_below() -> RawOCRResult:
    # "Net" and "Weight:" share a visual line (4 px gap merges); "52g" is
    # the value block on the line below — the fragmented-label pattern.
    return _words(("Net", 100, 200), ("Weight:", 134, 200), ("52g", 110, 230))


# ---------------------------------------------------------------- pass triggers

def test_no_extra_passes_when_all_anchors_present():
    """Both a mandatory anchor and the net anchor exist → pass A alone."""
    base = parse_blocks(
        _words(("MRP", 100, 100), ("Rs.", 136, 100), ("68.00", 166, 100), ("Net", 100, 200), ("Weight:", 134, 200)),
        1,
    )
    engine = _ScriptedEngine([])

    result = recover_missing_declarations(np.zeros((10, 10), np.uint8), engine, base, 1)

    assert result.passes_run == ["A"]
    assert result.extra_time_ms == 0
    assert engine.calls == 0
    assert [b.source_pass for b in result.blocks] == [None] * len(base)


def test_pass_b_fires_when_net_anchor_missing():
    base = parse_blocks(_mrp_only(), 1)
    engine = _ScriptedEngine([_net_weight_below()])

    result = recover_missing_declarations(np.zeros((10, 10), np.uint8), engine, base, 1)

    assert result.passes_run == ["A", "B"]
    assert engine.calls == 1
    recovered = [b for b in result.blocks if b.source_pass == "B"]
    assert any("Net Weight" in b.text for b in recovered)


def test_pass_c_fires_when_pass_b_still_misses_net_anchor():
    base = parse_blocks(_mrp_only(), 1)
    engine = _ScriptedEngine([_words(("fine", 400, 300)), _net_weight_below()])

    result = recover_missing_declarations(np.zeros((10, 10), np.uint8), engine, base, 1)

    assert result.passes_run == ["A", "B", "C"]
    assert engine.calls == 2


def test_pass_c_skipped_when_pass_b_found_net_anchor():
    base = parse_blocks(_mrp_only(), 1)
    engine = _ScriptedEngine([_net_weight_below()])

    result = recover_missing_declarations(np.zeros((10, 10), np.uint8), engine, base, 1)

    assert result.passes_run == ["A", "B"]


def test_disabled_flag_runs_pass_a_only():
    base = parse_blocks(_mrp_only(), 1)
    engine = _ScriptedEngine([_net_weight_below()])

    result = recover_missing_declarations(np.zeros((10, 10), np.uint8), engine, base, 1, enabled=False)

    assert result.passes_run == ["A"]
    assert engine.calls == 0


# ---------------------------------------------------------------- merge rules

def _pass_b_duplicate_and_new(base_blocks):
    """One block overlapping pass A's MRP block, one genuinely new."""
    dup = parse_blocks(_words(("MRP", 102, 101), confidence=97.0), 1)[0]
    dup.source_pass = "B"
    fresh = parse_blocks(_words(("52g", 110, 230), confidence=96.0), 1)[0]
    fresh.source_pass = "B"
    return [dup, fresh]


def test_duplicate_detection_prefers_stronger_confidence():
    base = parse_blocks(_mrp_only(), 1)  # confidence 90
    extras = _pass_b_duplicate_and_new(base)

    from app.ocr.multipass import _merge_blocks

    out = _merge_blocks([*base], extras)

    assert len(out) == 2  # duplicate collapsed, new coverage appended
    mrp = [b for b in out if "MRP" in b.text][0]
    assert mrp.source_pass == "B"  # 97 > 90 → stronger detection wins
    assert abs(mrp.confidence - 97.0) < 1e-6


def test_tie_prefers_pass_a_block():
    from app.ocr.multipass import _merge_blocks

    base = parse_blocks(_words(("MRP", 100, 100), confidence=90.0), 1)
    extra = parse_blocks(_words(("MRP", 100, 100), confidence=90.0), 1)[0]
    extra.source_pass = "B"

    out = _merge_blocks([*base], [extra])

    assert len(out) == 1
    assert out[0].source_pass is None  # established pipeline kept on tie


def test_center_containment_collapses_cross_scale_duplicate():
    """A remapped recovery box much LARGER than the base block can fall under
    the IoU threshold while still containing it — the shared-center rule
    must catch the duplicate (base's stronger read kept)."""
    from app.ocr.multipass import _merge_blocks

    base = parse_blocks(_words(("MRP", 100, 100), confidence=96.0), 1)
    # A large remapped block swallowing the base block (IoU ~0.02).
    extra = parse_blocks(_words(("MRP Rs. 68.00", 50, 60), confidence=95.0), 1)[0]
    extra.bbox = extra.bbox.model_copy(update={"width": 200, "height": 100})
    extra.source_pass = "C"

    out = _merge_blocks([*base], [extra])

    assert len(out) == 1
    assert out[0].source_pass is None  # 96 > 95 → pass A's read kept


def test_pass_a_blocks_never_replaced_by_weaker_detection():
    from app.ocr.multipass import _merge_blocks

    base = parse_blocks(_words(("MRP", 100, 100), confidence=96.0), 1)
    extra = parse_blocks(_words(("MRP", 100, 100), confidence=50.0), 1)[0]
    extra.source_pass = "B"

    out = _merge_blocks([*base], [extra])

    assert len(out) == 1
    assert out[0].source_pass is None
    assert abs(out[0].confidence - 96.0) < 1e-6


def test_merged_result_keeps_single_logical_declaration_per_region():
    """The end-to-end property: two passes seeing the same '52g' produce ONE
    block — extraction can never create duplicate net-quantity fields."""
    base = parse_blocks(_words(("Net", 100, 200), ("Weight:", 150, 200), confidence=90.0), 1)
    # Pass B sees the same anchor + value at higher confidence.
    engine = _ScriptedEngine([
        RawOCRResult(
            words=[
                *_words(("Net", 100, 200), ("Weight:", 150, 200), confidence=96.0).words,
                *_words(("52g", 110, 230), confidence=96.0).words,
            ],
            width=800,
            height=400,
        )
    ])

    result = recover_missing_declarations(np.zeros((10, 10), np.uint8), engine, base, 1)

    net_lines = [b for b in result.blocks if "Net" in b.text or "52g" in b.text]
    assert len(net_lines) <= 2  # anchor line + value line, not four blocks
    assert sum(1 for b in net_lines if "52g" in b.text) == 1
    assert all("52g" not in b.text or b.source_pass == "B" for b in net_lines)

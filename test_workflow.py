"""Automated checks: validation, retries, rendering, export, and a headless UI run.

Run:  python test_workflow.py     (or: pytest test_workflow.py)
"""
import json
import os
import xml.dom.minidom

import ai_engine
from ai_engine import AIEngine, AIEngineError, TransientAIError
from exporter import export_pdf, export_png, export_svg
from fishbone import render_svg
from models import AIResponseError, CATEGORY_KEYS, Cause, ProblemInput, parse_fishbone_response

SAMPLE = ProblemInput(
    statement="On Sewing Line 3, the seam puckering defect rate reached 8.4% over the last two weeks "
    "on Style Polo-902, against the company standard threshold of 2.0%."
)


def causes_from_demo():
    resp = parse_fishbone_response(ai_engine.make_demo_provider()("", ""))
    return {k: [Cause(id=f"{k}{i}", text=t, verified=(i == 0)) for i, t in enumerate(getattr(resp, k))] for k in CATEGORY_KEYS}


def test_parsing():
    ok = parse_fishbone_response('```json\n{"problem":"x","man":["a","A","b"],"machine":null}\n```')
    assert ok.man == ["a", "b"] and ok.machine == []          # fences, dedupe, null -> []
    for bad in ["", "not json", "[1,2]", '{"man": []}', '{"man": {"a": 1}}']:
        try:
            parse_fishbone_response(bad)
            raise AssertionError(f"should have failed: {bad!r}")
        except AIResponseError:
            pass


def test_retry_and_errors():
    calls = {"n": 0}
    delays = []

    def flaky(_s, _u):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientAIError("429 rate limit")
        return json.dumps({"man": ["ok cause"]})

    eng = AIEngine(flaky, max_retries=3, base_delay=1, sleep=delays.append)
    assert eng.generate_causes(SAMPLE).man == ["ok cause"]
    assert calls["n"] == 3 and len(delays) == 2 and delays[1] > delays[0] * 1.5   # exponential backoff

    def always_down(_s, _u):
        raise TransientAIError("503")

    try:
        AIEngine(always_down, max_retries=2, sleep=lambda d: None).generate_causes(SAMPLE)
        raise AssertionError("expected AIEngineError")
    except AIEngineError as exc:
        assert "temporarily unavailable" in str(exc)

    try:
        AIEngine(lambda s, u: "garbage", max_retries=1, sleep=lambda d: None).generate_causes(SAMPLE)
        raise AssertionError("expected AIEngineError")
    except AIEngineError as exc:
        assert "unusable" in str(exc)


def test_render_and_export():
    svg = render_svg(SAMPLE.statement, causes_from_demo())
    xml.dom.minidom.parseString(svg)                                 # well-formed XML
    assert "PROBLEM / EFFECT" in svg and "Fabric stretch variation" in svg
    assert export_svg(svg).startswith(b"<svg")
    png = export_png(svg)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pdf = export_pdf(svg)
    assert pdf[:5] == b"%PDF-"
    out = os.environ.get("FISHBONE_OUT", ".")
    for name, data in (("sample.svg", svg.encode()), ("sample.png", png), ("sample.pdf", pdf)):
        with open(os.path.join(out, name), "wb") as fh:
            fh.write(data)


def test_stress_layout():
    long_text = "Extremely long cause description that keeps going about fabric tension and operator habits " * 3
    causes = {k: [Cause(id=f"{k}{i}", text=long_text if i % 2 else f"Short cause {i} <&> 'quotes'") for i in range(8)]
              for k in CATEGORY_KEYS}
    causes["environment"] = []                                         # empty category
    svg = render_svg("P" * 400, causes)
    xml.dom.minidom.parseString(svg)
    assert export_png(svg)[:4] == b"\x89PNG"
    out = os.environ.get("FISHBONE_OUT", ".")
    with open(os.path.join(out, "stress.png"), "wb") as fh:
        fh.write(export_png(svg))


def test_ui_workflow():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("app.py", default_timeout=60).run()
    assert not at.exception
    at.checkbox(key="demo_mode").set_value(True).run()
    labels = [b.label for b in at.button]
    at.button[labels.index("Load sample problem")].click().run()
    at.button[[b.label for b in at.button].index("✨ Generate causes with AI")].click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    texts = [t.value for t in at.text_input if t.label == "Cause"]
    assert len(texts) >= 15, len(texts)

    # edit a cause, delete one, add one, move one -> state survives reruns
    first = [t for t in at.text_input if t.label == "Cause"][0]
    first.set_value("EDITED CAUSE").run()
    assert "EDITED CAUSE" in [t.value for t in at.text_input if t.label == "Cause"]
    n_before = len([t for t in at.text_input if t.label == "Cause"])
    at.button(key=[b.key for b in at.button if b.key and b.key.startswith("del_")][1]).click().run()
    assert len([t for t in at.text_input if t.label == "Cause"]) == n_before - 1
    at.text_input(key="new_man").set_value("Added by user").run()
    at.button(key="add_man").click().run()
    assert "Added by user" in [t.value for t in at.text_input if t.label == "Cause"]
    assert "EDITED CAUSE" in [t.value for t in at.text_input if t.label == "Cause"]

    mv = [s for s in at.selectbox if s.key and s.key.startswith("mv_")][0]
    mv.set_value("environment").run()
    assert not at.exception

    # regenerate one category
    at.button(key="regen_machine").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert any("Alternative idea" in t.value for t in at.text_input)

    # reset
    at.button[[b.label for b in at.button].index("Reset all")].click().run()
    assert not [t for t in at.text_input if t.label == "Cause"]


def test_missing_key_message():
    from streamlit.testing.v1 import AppTest

    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)
    at = AppTest.from_file("app.py", default_timeout=60).run()
    labels = [b.label for b in at.button]
    at.button[labels.index("Load sample problem")].click().run()
    at.button[[b.label for b in at.button].index("✨ Generate causes with AI")].click().run()
    assert any("No Gemini API key" in e.value for e in at.error)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)

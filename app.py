"""Fishbone AI – Streamlit user interface and workflow."""
from __future__ import annotations

import uuid

import streamlit as st

import ai_engine
from ai_engine import AIEngine, AIEngineError, ConfigError
from exporter import ExportError, export_pdf, export_png, export_svg
from fishbone import render_svg, svg_size
from models import CATEGORIES, CATEGORY_KEYS, Cause, ProblemInput

st.set_page_config(page_title="Fishbone AI", page_icon="🐟", layout="wide")

SAMPLE = {
    "statement": (
        "On Sewing Line 3, the seam puckering defect rate reached 8.4% over the last two weeks "
        "on Style Polo-902, against the company standard threshold of 2.0%."
    ),
    "process": "Sewing Line 3",
    "product": "Style Polo-902",
    "actual": "8.4% seam puckering defect rate (last two weeks)",
    "target": "2.0% maximum",
    "observations": "",
}
FIELD_KEYS = list(SAMPLE.keys())

# ---------------------------------------------------------------- styling --
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; max-width: 1400px;}
      .fb-hero {background: linear-gradient(135deg, #0B2545 0%, #13315C 100%);
                color: #fff; padding: 1.4rem 1.8rem; border-radius: 12px; margin-bottom: 1.2rem;}
      .fb-hero h1 {color: #fff; margin: 0 0 .25rem 0; font-size: 1.9rem;}
      .fb-hero p {color: #C9D6EA; margin: 0; font-size: 1rem;}
      h2, h3 {color: #0B2545;}
      div[data-testid="stVerticalBlockBorderWrapper"] {border-color: #C9D6EA;}
    </style>
    <div class="fb-hero">
      <h1>Fishbone AI</h1>
      <p>Intelligent root cause analysis &amp; Ishikawa (Fishbone) chart generator.
      AI proposes <b>hypotheses</b>; your team verifies them.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ state --
ss = st.session_state
ss.setdefault("causes", {k: [] for k in CATEGORY_KEYS})
ss.setdefault("generated", False)
ss.setdefault("flash", None)
for _f in FIELD_KEYS:
    ss.setdefault(f"in_{_f}", "")
ss.setdefault("headline", "")


def new_cause(text: str, verified: bool = False) -> dict:
    return {"id": uuid.uuid4().hex[:10], "text": text, "verified": verified}


def total_causes() -> int:
    return sum(len(v) for v in ss.causes.values())


# -------------------------------------------------------------- callbacks --
def cb_load_sample() -> None:
    for k, v in SAMPLE.items():
        ss[f"in_{k}"] = v


def cb_reset() -> None:
    ss.causes = {k: [] for k in CATEGORY_KEYS}
    ss.generated = False
    for k in FIELD_KEYS:
        ss[f"in_{k}"] = ""
    ss.headline = ""
    ss.flash = None


def cb_clear_causes() -> None:
    ss.causes = {k: [] for k in CATEGORY_KEYS}
    ss.generated = False


def cb_delete(key: str, cid: str) -> None:
    ss.causes[key] = [c for c in ss.causes[key] if c["id"] != cid]


def cb_move(cid: str, src: str) -> None:
    dest = ss.get(f"mv_{cid}", src)
    if dest == src:
        return
    moving = next((c for c in ss.causes[src] if c["id"] == cid), None)
    if moving is None:
        return
    ss.causes[src] = [c for c in ss.causes[src] if c["id"] != cid]
    ss.causes[dest].append(moving)


def cb_add(key: str) -> None:
    text = " ".join(str(ss.get(f"new_{key}", "")).split())
    if text:
        ss.causes[key].append(new_cause(text[:160]))
    ss[f"new_{key}"] = ""


# ------------------------------------------------------------ AI plumbing --
def get_engine():
    """Build an AIEngine from configuration, or raise ConfigError."""
    if ss.get("demo_mode"):
        return AIEngine(ai_engine.make_demo_provider(), max_retries=0)
    key = ai_engine.get_api_key(st.secrets)
    if not key:
        raise ConfigError(
            "No Gemini API key found. Add GEMINI_API_KEY to .streamlit/secrets.toml or set it as an "
            "environment variable (see README), or tick 'Demo mode' in the sidebar."
        )
    model = ai_engine.get_model_name(st.secrets)
    return AIEngine(ai_engine.make_gemini_provider(key, model))


def current_problem() -> ProblemInput:
    return ProblemInput(**{k: ss[f"in_{k}"] for k in FIELD_KEYS})


# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("Settings")
    has_key = bool(ai_engine.get_api_key(st.secrets))
    st.write("**Gemini API key:** " + (" configured" if has_key else "❌ not found"))
    st.write(f"**Model:** `{ai_engine.get_model_name(st.secrets)}`")
    st.checkbox(
        "Demo mode (no API call)",
        key="demo_mode",
        help="Uses a built-in sample response so you can try the app offline. Not real analysis.",
    )
    st.divider()
    st.caption(
        "AI-generated causes are **hypotheses**. Confirm those with supporting evidence using "
        "the *Evidence confirmed* checkbox; they appear as filled dots on the diagram."
    )

# ------------------------------------------------------- 1. problem input --
st.subheader("1 · Describe the problem")
st.text_area(
    "Problem statement *",
    key="in_statement",
    height=100,
    placeholder="e.g. On Sewing Line 3, the seam puckering defect rate reached 8.4% ...",
)
c1, c2 = st.columns(2)
c1.text_input("Process / department", key="in_process", placeholder="e.g. Sewing Line 3")
c2.text_input("Product / style", key="in_product", placeholder="e.g. Style Polo-902")
c3, c4 = st.columns(2)
c3.text_input("Actual performance", key="in_actual", placeholder="e.g. 8.4% defect rate")
c4.text_input("Target / standard", key="in_target", placeholder="e.g. 2.0% maximum")
st.text_area(
    "Relevant observations or supporting data (optional)",
    key="in_observations",
    height=80,
    placeholder="Only facts you actually know. The AI will not invent data.",
)

b1, b2, b3, b4 = st.columns([2, 1.4, 1.4, 1.2])
generate = b1.button("Generate causes with AI", type="primary", width="stretch")
b2.button("Load sample problem", on_click=cb_load_sample, width="stretch")
b3.button("Start blank diagram", on_click=cb_clear_causes, width="stretch",
          help="Clear causes and add them manually.")
b4.button("Reset all", on_click=cb_reset, width="stretch")

if generate:
    problem = current_problem()
    if not problem.statement.strip():
        st.error("Please enter a problem statement first.")
    else:
        try:
            engine = get_engine()
            with st.spinner("Generating potential causes…"):
                resp = engine.generate_causes(problem)
            ss.causes = {k: [new_cause(t) for t in getattr(resp, k)] for k in CATEGORY_KEYS}
            ss.generated = True
            ss.flash = ("success", f"Generated {total_causes()} potential causes. Review and edit them below.")
        except (ConfigError, AIEngineError) as exc:
            st.error(str(exc))
        except Exception as exc:  # last-resort guard so the app never crashes
            st.error(f"Unexpected error while generating causes: {exc}")

if ss.flash:
    getattr(st, ss.flash[0])(ss.flash[1])
    ss.flash = None
if ss.generated:
    st.info(
        "These causes are **hypotheses generated by AI**, not confirmed root causes. "
        "Verify each one with data or observation before acting."
    )

# --------------------------------------------------- 2. editable categories --
st.subheader("2 · Review and edit causes")
st.caption("Edit text, tick *Evidence confirmed*, move causes between categories, or delete them. "
           "The diagram below updates automatically.")


def render_category(key: str) -> None:
    label = CATEGORIES[key]
    items = ss.causes[key]
    with st.container(border=True):
        h1, h2 = st.columns([3, 2])
        h1.markdown(f"**{label}** · {len(items)}")
        if h2.button(" Regenerate", key=f"regen_{key}", width="stretch",
                     help="Replace unconfirmed causes in this category with new suggestions."):
            problem = current_problem()
            if not problem.statement.strip():
                st.error("Enter a problem statement first.")
            else:
                try:
                    engine = get_engine()
                    kept = [c["text"] for c in items if c["verified"]]
                    replaced = [c["text"] for c in items if not c["verified"]]
                    with st.spinner(f"Regenerating {label}…"):
                        fresh = engine.regenerate_category(problem, key, replaced, kept)
                    ss.causes[key] = [c for c in items if c["verified"]] + [new_cause(t) for t in fresh]
                    st.rerun()
                except (ConfigError, AIEngineError) as exc:
                    st.error(str(exc))
        for c in items:
            cid = c["id"]
            c["text"] = st.text_input("Cause", value=c["text"], key=f"t_{cid}",
                                      label_visibility="collapsed", max_chars=160)
            a, b, d = st.columns([2.2, 2.6, 0.9])
            c["verified"] = a.checkbox("Evidence confirmed", value=c["verified"], key=f"v_{cid}")
            b.selectbox("Move to", CATEGORY_KEYS, index=CATEGORY_KEYS.index(key),
                        format_func=lambda k: CATEGORIES[k], key=f"mv_{cid}",
                        label_visibility="collapsed", on_change=cb_move, args=(cid, key))
            d.button("🗑", key=f"del_{cid}", on_click=cb_delete, args=(key, cid), help="Delete this cause")
        n1, n2 = st.columns([4, 1])
        n1.text_input("Add a cause", key=f"new_{key}", placeholder="Add a cause…",
                      label_visibility="collapsed", max_chars=160)
        n2.button(" Add", key=f"add_{key}", on_click=cb_add, args=(key,), width="stretch")


left, right = st.columns(2)
for i, k in enumerate(CATEGORY_KEYS):
    with (left if i % 2 == 0 else right):
        render_category(k)

# ------------------------------------------------------------ 3. preview --
st.subheader("3 · Fishbone diagram")
statement = ss.in_statement.strip()
st.text_input(
    "Problem text shown on the diagram (optional – defaults to the problem statement)",
    key="headline",
    max_chars=230,
)
headline = ss.headline.strip() or statement

if not headline:
    st.info("Enter a problem statement to see the diagram.")
else:
    cause_models = {k: [Cause(**c) for c in ss.causes[k]] for k in CATEGORY_KEYS}
    svg = render_svg(headline, cause_models)
    try:
        st.image(svg, width="stretch")
    except TypeError:
        st.image(svg)

    # ------------------------------------------------------- 4. export --
    st.subheader("4 · Export")
    w, h = svg_size(svg)
    d1, d2, d3 = st.columns(3)
    try:
        d1.download_button("⬇ Download SVG", export_svg(svg), "fishbone.svg", "image/svg+xml",
                           width="stretch")
    except ExportError as exc:
        d1.error(str(exc))
    try:
        d2.download_button("⬇ Download PNG", export_png(svg), "fishbone.png", "image/png",
                           width="stretch")
    except ExportError as exc:
        d2.error(str(exc))
    try:
        d3.download_button("⬇ Download PDF", export_pdf(svg), "fishbone.pdf", "application/pdf",
                           width="stretch")
    except ExportError as exc:
        d3.error(str(exc))
    st.caption(f"Exports match the preview exactly ({w}×{h} px base size; PNG is rendered at 2× scale).")

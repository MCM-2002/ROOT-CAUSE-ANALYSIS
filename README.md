# Fishbone AI – Root Cause Analysis & Fishbone Chart Generator

Describe a problem in plain language, let Gemini propose **hypotheses** for the six Fishbone categories (6M),
edit and confirm them, then export a professional Ishikawa diagram as PNG, SVG or PDF.

## Quick start

```bash
cd fishbone_ai
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

No API key yet? Tick **Demo mode** in the sidebar to try the whole workflow offline with built-in sample data.

## Configure the Gemini API key

1. Create a key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Either copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and set `GEMINI_API_KEY`,
   or set an environment variable:
   - macOS/Linux: `export GEMINI_API_KEY="your-key"`
   - Windows PowerShell: `$env:GEMINI_API_KEY="your-key"`
3. Optional: choose another model with `GEMINI_MODEL` (default `gemini-2.5-flash`).

`secrets.toml` is listed in `.gitignore`. The key is never shown in the UI (the sidebar only says configured / not found).

## Sample problem for testing

> On Sewing Line 3, the seam puckering defect rate reached 8.4% over the last two weeks on Style Polo-902,
> against the company standard threshold of 2.0%.

Click **Load sample problem**, then **Generate causes with AI**.

## Using the app

1. Enter the problem (only the statement is required).
2. Generate causes. All are labelled as hypotheses.
3. Edit text, add, delete, move between categories, tick **Evidence confirmed**, or **Regenerate** a single
   category (confirmed causes are kept). The diagram updates live; confirmed causes show as filled dots.
4. Download SVG, PNG or PDF. Exports are built from the same SVG as the preview.

## Architecture

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI, session state, callbacks |
| `ai_engine.py` | Provider abstraction (`(system, user) -> text`), Gemini provider, retry with exponential backoff, error classification, demo provider |
| `prompts.py` | System prompt and generation / regeneration prompts |
| `models.py` | Pydantic models, tolerant JSON extraction, validation and cleaning (dedupe, length caps, missing categories → empty) |
| `fishbone.py` | Pure function `render_svg(problem, causes)`; wraps text and grows branches so labels do not overlap |
| `exporter.py` | SVG bytes; PNG/PDF via CairoSVG, falling back to svglib + ReportLab |
| `test_workflow.py` | Parsing, retry, render, export and headless UI tests |

To switch AI provider, add a function with the `(system_prompt, user_prompt) -> str` signature and pass it to `AIEngine`.

## Troubleshooting

- **PNG/PDF export fails on Windows/macOS**: CairoSVG needs the native Cairo library
  (macOS: `brew install cairo`; Windows: install GTK runtime). Without it the app falls back to svglib/ReportLab.
- **Rate limit / overloaded**: the app retries up to 3 times with backoff, then shows a plain-language message.

## Tests

```bash
python test_workflow.py
```

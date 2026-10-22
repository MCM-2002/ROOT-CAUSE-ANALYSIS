"""Prompts for cause generation."""
from models import CATEGORIES

SYSTEM_PROMPT = """You are an experienced Lean / Quality Assurance / Operational Excellence \
facilitator helping a team brainstorm POTENTIAL causes for a problem using an Ishikawa \
(Fishbone) diagram with the six standard categories (6M): Man, Machine, Method, Material, \
Measurement, and Mother Nature (Environment).

Rules:
- Every cause is a HYPOTHESIS that must be verified; never present one as confirmed.
- Never invent measurements, data, inspection results, names, or facts not in the input.
- Be specific and relevant to the stated process and product, but keep each cause under 15 words.
- Avoid repeated, overlapping, or generic filler suggestions across categories.
- Give 2 to 5 causes per category. Use an empty array [] if no reasonable suggestion exists.
- Respond with ONLY a JSON object, no markdown and no commentary.

JSON schema:
{
  "problem": "short restatement of the problem (max 20 words)",
  "man": ["..."],
  "machine": ["..."],
  "method": ["..."],
  "material": ["..."],
  "measurement": ["..."],
  "environment": ["..."]
}
"""


def build_generation_prompt(context: str) -> str:
    return (
        "Generate potential causes for the following problem.\n\n"
        f"{context}\n\n"
        "Return only the JSON object described in the instructions."
    )


def build_regeneration_prompt(context: str, category_key: str, existing: list, kept: list) -> str:
    label = CATEGORIES[category_key]
    existing_txt = "\n".join(f"- {c}" for c in existing) or "(none)"
    kept_txt = "\n".join(f"- {c}" for c in kept) or "(none)"
    return (
        "Generate NEW potential causes for ONE category of a Fishbone diagram.\n\n"
        f"{context}\n\n"
        f"Category: {label} (JSON key: \"{category_key}\")\n"
        f"Causes the user is keeping (do not repeat or rephrase):\n{kept_txt}\n"
        f"Causes previously suggested and now being replaced (suggest different ideas):\n{existing_txt}\n\n"
        f"Return a JSON object with the key \"{category_key}\" holding 2 to 5 new hypotheses, "
        "and set every other category to an empty array."
    )

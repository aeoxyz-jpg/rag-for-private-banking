"""Generate style-seed exemplars with the smart LLM (Codex) and cache them to
rm_assistant/synth/style_seeds.json. Run once; the cached seeds are committed so the
corpus build is reproducible without re-invoking Codex.
Run: `uv run scripts/build/gen_style_seeds.py`"""
import json

from rm_assistant.models.factory import get_smart_llm
from rm_assistant.synth.notes import SEEDS_PATH

PROMPT = """Write 4 short, highly realistic private-banking CRM documents as style exemplars
for a synthetic dataset. Vary them: one terse meeting note, one call transcript snippet,
one pre-meeting brief, one complaint record. Authentic RM voice, concrete but fictional.
Return ONLY a JSON array, each item {"kind","text"} with kind in
[note,transcript,brief,complaint]. No prose, no markdown fences."""


def main() -> None:
    raw = get_smart_llm().complete(PROMPT)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    seeds = json.loads(raw)
    SEEDS_PATH.write_text(json.dumps(seeds, indent=2, ensure_ascii=False))
    print(f"Wrote {len(seeds)} style seeds -> {SEEDS_PATH}")


if __name__ == "__main__":
    main()

"""LLM-as-judge with a fixed rubric (spec §5.3). Scores an answer for faithfulness
(grounded in the evidence, no fabrication) and correctness (matches the reference)."""
from __future__ import annotations

import json
import re

from .. import config
from ..models.ollama import OllamaLLM

_SYS = "You are a strict evaluation judge. Output ONLY a JSON object, no prose."

_RUBRIC = """Score the ANSWER on two axes from 0.0 to 1.0:
- faithfulness: is every claim supported by the EVIDENCE? (1.0 = fully grounded, 0.0 = fabricated)
- correctness: does the ANSWER correctly address the QUESTION given the REFERENCE? (1.0 = correct)
Return ONLY: {"faithfulness": <float>, "correctness": <float>, "reason": "<one short sentence>"}"""

_JSON = re.compile(r"\{.*\}", re.DOTALL)


def judge(question: str, answer: str, reference: str, evidence: str = "",
          model: str = config.REASON_MODEL) -> dict:
    prompt = (f"QUESTION:\n{question}\n\nREFERENCE (ground truth):\n{reference}\n\n"
              f"EVIDENCE (what the system retrieved/computed):\n{evidence or reference}\n\n"
              f"ANSWER:\n{answer}\n\n{_RUBRIC}")
    raw = OllamaLLM(model).complete(prompt, system=_SYS, temperature=0.0)
    m = _JSON.search(raw)
    try:
        d = json.loads(m.group(0)) if m else {}
        return {"faithfulness": float(d.get("faithfulness", 0.0)),
                "correctness": float(d.get("correctness", 0.0)),
                "reason": str(d.get("reason", ""))[:200]}
    except (ValueError, AttributeError):
        return {"faithfulness": 0.0, "correctness": 0.0, "reason": "judge parse failed"}

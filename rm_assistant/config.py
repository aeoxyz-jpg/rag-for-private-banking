"""Central config. Stack is deployment-agnostic (spec §8); defaults are local-first.

Override anything via environment (.env is auto-loaded). The model layer reads the
role-based settings here so the rest of the code never hard-codes a provider.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- paths ---
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RM_DATA_DIR", ROOT / "data"))
BERKA_RAW_DB = Path(os.getenv("RM_BERKA_RAW_DB", DATA_DIR / "berka_raw.db"))  # raw source mirror
DB_PATH = Path(os.getenv("RM_DB_PATH", DATA_DIR / "rm.db"))  # unified warehouse (§3.3)
CHROMA_DIR = Path(os.getenv("RM_CHROMA_DIR", DATA_DIR / "chroma"))

# --- model roles (hybrid stack) ---
# fast  -> high-volume cheap work (batch synthesis, smoke): local Ollama
# smart -> low-volume high-quality (LLM-judge, final answers): codex | anthropic | ollama
# embed -> always local bge-m3
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
FAST_LLM = os.getenv("RM_FAST_LLM", "qwen2.5:3b-instruct")
SYNTH_MODEL = os.getenv("RM_SYNTH_MODEL", "deepseek-v4-flash:cloud")  # bulk note synthesis (Ollama cloud)
REASON_MODEL = os.getenv("RM_REASON_MODEL", "deepseek-v4-flash:cloud")  # text-to-SQL + answer synthesis (M2)
SMART_PROVIDER = os.getenv("RM_SMART_PROVIDER", "codex")  # codex | anthropic | ollama
SMART_MODEL = os.getenv("RM_SMART_MODEL", "")  # provider-specific; "" = provider default
EMBED_MODEL = os.getenv("RM_EMBED_MODEL", "bge-m3:latest")
EMBED_DIM = int(os.getenv("RM_EMBED_DIM", "1024"))  # bge-m3

# --- Berka source: CTU public read-only MariaDB (relational.fel.cvut.cz) ---
BERKA = {
    "host": os.getenv("BERKA_HOST", "relational.fel.cvut.cz"),
    "port": int(os.getenv("BERKA_PORT", "3306")),
    "user": os.getenv("BERKA_USER", "guest"),
    "password": os.getenv("BERKA_PASSWORD", "ctu-relational"),
    "database": os.getenv("BERKA_DB", "financial"),
}
BERKA_TABLES = ["district", "account", "client", "disp", "card", "loan", "order", "trans"]

SEED = int(os.getenv("RM_SEED", "42"))  # reproducible builds (spec §3.6)

# --- M1 synthesis parameters ---
N_RMS = int(os.getenv("RM_N_RMS", "12"))           # synthetic relationship managers
N_COMPANIES = int(os.getenv("RM_N_COMPANIES", "40"))  # employer nodes for Q5 graph
CORPUS_SUBSET = int(os.getenv("RM_CORPUS_SUBSET", "300"))  # clients getting LLM notes
NOTES_PER_CLIENT = (3, 8)                           # inclusive range
N_KB_DOCS = int(os.getenv("RM_N_KB_DOCS", "16"))    # global policy/product KB docs (Q8)

# --- Phase-2 wealth-graph dataset (greenfield, relationship-rich) ---
WEALTH_DB = Path(os.getenv("RM_WEALTH_DB", DATA_DIR / "wealth.db"))           # relational projection
WEALTH_GRAPH_DIR = Path(os.getenv("RM_WEALTH_GRAPH_DIR", DATA_DIR / "wealth_graph"))  # graph export
WEALTH_TRUTH = Path(os.getenv("RM_WEALTH_TRUTH", DATA_DIR / "wealth_graph" / "graph_truth.json"))

WG = {  # scale knobs (tunable; defaults sized for rich structure but fast builds/tests)
    "households": int(os.getenv("RM_WG_HOUSEHOLDS", "120")),
    "entities": int(os.getenv("RM_WG_ENTITIES", "200")),
    "trusts": int(os.getenv("RM_WG_TRUSTS", "40")),
    "accounts": int(os.getenv("RM_WG_ACCOUNTS", "400")),
    "prospects": int(os.getenv("RM_WG_PROSPECTS", "30")),
    "rms": int(os.getenv("RM_WG_RMS", "8")),
}
WG_UBO_THRESHOLD = float(os.getenv("RM_WG_UBO_THRESHOLD", "0.25"))  # FATF-style effective-ownership cutoff

# --- Phase-2 fair KG experiment (kgx) ---
WEALTH_KUZU = Path(os.getenv("RM_WEALTH_KUZU", DATA_DIR / "wealth_graph" / "graph.kuzu"))
KGX_RECORDS = Path(os.getenv("RM_KGX_RECORDS", DATA_DIR / "kgx_records.json"))
KGX_N_PER_CATEGORY = int(os.getenv("RM_KGX_N_PER_CATEGORY", "20"))
KGX_MAX_RETRIES = int(os.getenv("RM_KGX_MAX_RETRIES", "2"))

# --- Phase-3a semantic-layer (E) vs text-to-SQL (B) validation (semx) ---
SEMX_PARAPHRASES = int(os.getenv("RM_SEMX_PARAPHRASES", "6"))   # NL phrasings per variant
SEMX_SAMPLES = int(os.getenv("RM_SEMX_SAMPLES", "4"))           # repeats per (engine, question)
SEMX_RECORDS = Path(os.getenv("RM_SEMX_RECORDS", DATA_DIR / "semx_records.json"))

# --- Phase-3d reranking (RRF vs RRF+LLM-reranker) validation (rerankx) ---
# LLM-as-reranker: the dedicated Qwen3-Reranker GGUFs are broken/embedding-only on Ollama 0.30.8,
# so a general instruct model serves as a pointwise relevance judge (see spec §3).
RERANK_MODEL = os.getenv("RM_RERANK_MODEL", "qwen2.5:3b-instruct")
RERANK_POOL = int(os.getenv("RM_RERANK_POOL", "20"))          # candidate pool size to rerank
RERANK_HARD_N = int(os.getenv("RM_RERANK_HARD_N", "36"))      # hard-set question count
RERANKX_RECORDS = Path(os.getenv("RM_RERANKX_RECORDS", DATA_DIR / "rerankx_records.json"))

# --- Router (F) routing-accuracy validation (routerx) ---
ROUTING_GOLD = Path(os.getenv("RM_ROUTING_GOLD", ROOT / "rm_assistant/eval/gold/routing.json"))
ROUTERX_RECORDS = Path(os.getenv("RM_ROUTERX_RECORDS", DATA_DIR / "routerx_records.json"))

# --- Trained cross-encoder reranker arm (rerankx, Phase-3d extension) ---
RERANK_CE_MODEL = os.getenv("RM_RERANK_CE_MODEL", "BAAI/bge-reranker-v2-m3")

# --- Sensitivity sweeps (data-knob robustness; model held fixed) ---
SWEEP_MODELS = os.getenv("RM_SWEEP_MODELS", "deepseek-v4-flash:cloud,glm-5.2:cloud").split(",")
RERANK_HARD_MIN_NOTES = int(os.getenv("RM_RERANK_HARD_MIN_NOTES", "3"))  # distractor-density knob (min notes per client; siblings = notes-1)

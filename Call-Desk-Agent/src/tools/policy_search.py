"""Tool 1 — Policy Search (LangChain hybrid retrieval + LLM answer generation).

Pipeline (built once at import time):

  1. LOAD + CHUNK   - read the 5 policy .txt files, split with LangChain's
                      RecursiveCharacterTextSplitter into tagged Documents
                      ({source_file, call_type, chunk_id}).
  2. ROUTE          - route_query_to_call_type(query): keyword map, first match
                      wins, None when nothing matches (no guessing, no LLM).
  3. BUILD INDEXES  - per call_type: a FAISS vector store (HuggingFace MiniLM
                      embeddings) + a BM25Retriever, combined into an
                      EnsembleRetriever (reciprocal-rank fusion). Cached at load,
                      plus a None bucket over all chunks.
  4. FUSE           - EnsembleRetriever fuses the dense + sparse rankings; we keep
                      the top-k (config: retrieval.top_k_chunks).
  5. DEV LOGGING    - every query prints routed type + top-3 of BM25, FAISS (with
                      scores), and the fused ensemble result. Kept in on purpose.
  6. LLM ANSWER     - get_llm_client(config) returns a provider-agnostic
                      generate(prompt)->str backed by a LangChain chat model; the
                      fused chunks are the ONLY allowed context.

Everything is LangChain: langchain_huggingface (embeddings), langchain_community
(FAISS, BM25Retriever), langchain_classic (EnsembleRetriever), langchain_openai /
langchain_google_genai / langchain_anthropic (chat models). All tunables live in
config.json. Only the active provider's chat package is imported.

Public API:
    search_policy(query) -> str
    search_policy_with_context(query, call_type=None) -> dict
"""

from __future__ import annotations

import logging

import hashlib
import json
import os
import re
import urllib.request
from typing import Callable

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Shared loader: imports .env (API keys) and config.json exactly once.
from src.config import CONFIG, REPO_ROOT

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Paths, config
# --------------------------------------------------------------------------- #

POLICY_DIR = REPO_ROOT / "data" / "policies"
# Persisted FAISS indexes live here (gitignored — a rebuildable cache, not source).
INDEX_DIR = REPO_ROOT / "data" / "faiss_index"

# Filename -> call_type. These are the only 5 documents in the corpus.
FILE_TO_CALL_TYPE: dict[str, str] = {
    "replacement_policy.txt": "replacement",
    "repair_sla.txt": "repair",
    "logistics_guidelines.txt": "logistics",
    "device_support.txt": "device",
    "escalation_policy.txt": "escalation",
}

# Config-driven tunables (config.json is the source of truth).
CHUNK_SIZE = CONFIG["chunking"]["chunk_size"]
CHUNK_OVERLAP = CONFIG["chunking"]["chunk_overlap"]
EMBED_MODEL_NAME = CONFIG["embedding_model"]
RRF_K = CONFIG["retrieval"]["rrf_k"]          # EnsembleRetriever fusion constant
TOP_K = CONFIG["retrieval"]["top_k_chunks"]   # chunks handed to the LLM
RETRIEVE_K = 5                                 # candidates each sub-retriever returns

# Query-keyword -> call_type routing table. Order matters: first matching group
# wins. Keep the keyword sets disjoint enough that the first hit is the right one.
ROUTING_RULES: list[tuple[tuple[str, ...], str]] = [
    (("replace", "replacement", "exchange", "swap"), "replacement"),
    (("repair", "fix", "broken", "service centre", "service center"), "repair"),
    (("return", "refund", "logistics", "shipping", "prepaid label"), "logistics"),
    (("setup", "device", "screen share", "configuration", "connectivity"), "device"),
    (("escalate", "escalation", "manager", "complaint", "senior agent"), "escalation"),
]


def _tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens — used as the BM25 preprocessor."""
    return re.findall(r"[a-z0-9]+", text.lower())


# --------------------------------------------------------------------------- #
# Step 1 — LOAD + CHUNK
# --------------------------------------------------------------------------- #

def load_and_chunk() -> list[Document]:
    """Load the 5 policy files and split them into tagged LangChain Documents."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    docs: list[Document] = []
    for filename, call_type in FILE_TO_CALL_TYPE.items():
        text = (POLICY_DIR / filename).read_text(encoding="utf-8")
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if not piece:
                continue
            docs.append(
                Document(
                    page_content=piece,
                    metadata={
                        "chunk_id": len(docs),
                        "source_file": filename,
                        "call_type": call_type,
                    },
                )
            )
    return docs


CHUNKS: list[Document] = load_and_chunk()


# --------------------------------------------------------------------------- #
# Step 2 — METADATA ROUTING (query -> call_type)
# --------------------------------------------------------------------------- #

def route_query_to_call_type(query: str) -> str | None:
    """Map a query to a call_type via a keyword table, or None if no match.

    Pure and independently testable — no retriever access, no LLM. When this
    returns None the caller searches across ALL chunks instead of one doc.
    """
    q = query.lower()
    for keywords, call_type in ROUTING_RULES:
        if any(kw in q for kw in keywords):
            log.info(f"[policy_search] routed to {call_type}")
            return call_type
    log.info("[policy_search] no match, searching all docs")
    return None


# --------------------------------------------------------------------------- #
# Step 3 — BUILD RETRIEVERS PER SCOPED CHUNK SET (cached at module load)
# --------------------------------------------------------------------------- #

# One shared embedding model (MiniLM), cosine via normalized vectors.
_EMBED = HuggingFaceEmbeddings(
    model_name=EMBED_MODEL_NAME,
    encode_kwargs={"normalize_embeddings": True},
)


def _corpus_fingerprint() -> str:
    """Hash of everything that affects the embeddings: model, chunking, sources.

    A change to any of these invalidates the persisted FAISS indexes so they are
    rebuilt instead of silently serving stale vectors.
    """
    h = hashlib.sha256()
    h.update(EMBED_MODEL_NAME.encode())
    h.update(f"{CHUNK_SIZE}:{CHUNK_OVERLAP}".encode())
    for filename in sorted(FILE_TO_CALL_TYPE):
        h.update((POLICY_DIR / filename).read_bytes())
    return h.hexdigest()[:16]


def _scope_dir(call_type: str | None) -> str:
    """On-disk folder for one scope's FAISS index (None -> the all-docs bucket)."""
    return str(INDEX_DIR / (call_type or "_all"))


class ScopedRetriever:
    """Dense (FAISS) + sparse (BM25) retrievers over one scoped chunk set,
    combined with an EnsembleRetriever (reciprocal-rank fusion).

    The FAISS index (the expensive, embedding-backed part) is persisted to disk
    and reloaded when ``reuse`` is True; BM25 is cheap and rebuilt in memory.
    """

    def __init__(self, docs: list[Document], call_type: str | None, reuse: bool) -> None:
        self.docs = docs
        k = min(RETRIEVE_K, len(docs))
        scope_dir = _scope_dir(call_type)

        # Dense: reload the saved index when valid, else build + persist it.
        # allow_dangerous_deserialization is safe: we generated this file locally.
        if reuse and os.path.isdir(scope_dir):
            self.vectorstore = FAISS.load_local(
                scope_dir, _EMBED, allow_dangerous_deserialization=True
            )
        else:
            self.vectorstore = FAISS.from_documents(docs, _EMBED)
            self.vectorstore.save_local(scope_dir)
        self.faiss_retriever = self.vectorstore.as_retriever(search_kwargs={"k": k})

        # Sparse: BM25 with a lowercase tokenizer to match query casing.
        self.bm25_retriever = BM25Retriever.from_documents(
            docs, preprocess_func=_tokenize
        )
        self.bm25_retriever.k = k

        # Hybrid: reciprocal-rank fusion of the two rankings.
        self.ensemble = EnsembleRetriever(
            retrievers=[self.bm25_retriever, self.faiss_retriever],
            weights=[0.5, 0.5],
            c=RRF_K,
        )


def _build_index_cache() -> dict[str | None, ScopedRetriever]:
    """Build one ScopedRetriever per call_type (+ a None bucket over all chunks).

    Reuses the persisted FAISS indexes when the corpus fingerprint matches the
    saved manifest; otherwise rebuilds every index and rewrites the manifest.
    """
    fingerprint = _corpus_fingerprint()
    manifest_path = INDEX_DIR / "manifest.json"
    reuse = False
    if manifest_path.exists():
        try:
            reuse = json.loads(manifest_path.read_text())["fingerprint"] == fingerprint
        except (json.JSONDecodeError, KeyError, OSError):
            reuse = False

    action = "loading" if reuse else "building + saving"
    log.info(f"[policy_search] {action} FAISS indexes at {INDEX_DIR} (fingerprint {fingerprint})")

    cache: dict[str | None, ScopedRetriever] = {}
    for call_type in FILE_TO_CALL_TYPE.values():
        scoped = [d for d in CHUNKS if d.metadata["call_type"] == call_type]
        cache[call_type] = ScopedRetriever(scoped, call_type, reuse)
    cache[None] = ScopedRetriever(CHUNKS, None, reuse)  # unrouted -> whole corpus

    if not reuse:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "embedding_model": EMBED_MODEL_NAME,
                    "chunk_size": CHUNK_SIZE,
                    "chunk_overlap": CHUNK_OVERLAP,
                },
                indent=2,
            )
        )
    return cache


INDEX_CACHE: dict[str | None, ScopedRetriever] = _build_index_cache()


def rebuild_indexes() -> None:
    """Rebuild chunks + retrievers from the current CONFIG values.

    Lets a caller (e.g. the test notebook) change ``CONFIG["chunking"]`` at
    runtime and see the effect on retrieval without restarting the process.
    """
    global CHUNK_SIZE, CHUNK_OVERLAP, CHUNKS, INDEX_CACHE
    CHUNK_SIZE = CONFIG["chunking"]["chunk_size"]
    CHUNK_OVERLAP = CONFIG["chunking"]["chunk_overlap"]
    CHUNKS = load_and_chunk()
    INDEX_CACHE = _build_index_cache()


# --------------------------------------------------------------------------- #
# Step 5 — DEV LOGGING helpers + retrieval
# --------------------------------------------------------------------------- #

def _fmt(doc: Document) -> str:
    preview = doc.page_content[:60].replace("\n", " ")
    return f"id={doc.metadata['chunk_id']} [{doc.metadata['source_file']}] {preview!r}"


def _log_docs(label: str, docs: list[Document]) -> None:
    log.info(f"[policy_search] {label} top-3:")
    for rank, doc in enumerate(docs[:3], start=1):
        log.info(f"    {rank}. {_fmt(doc)}")


def _log_scored(label: str, scored: list[tuple[Document, float]]) -> None:
    log.info(f"[policy_search] {label} top-3:")
    for rank, (doc, score) in enumerate(scored[:3], start=1):
        log.info(f"    {rank}. score={score:.4f} {_fmt(doc)}")


def _retrieve(query: str, call_type: str | None) -> list[Document]:
    """Run the hybrid retriever over the scoped set and return the top-k Documents.

    Emits the dev log for the BM25 ranking, the FAISS ranking (with distance
    scores), and the fused ensemble result so disagreement stays visible.
    """
    sr = INDEX_CACHE[call_type]

    _log_docs("list A (BM25)", sr.bm25_retriever.invoke(query))
    scored = sr.vectorstore.similarity_search_with_score(
        query, k=min(RETRIEVE_K, len(sr.docs))
    )
    _log_scored("list B (FAISS)", scored)

    fused = sr.ensemble.invoke(query)
    _log_docs("Ensemble (RRF) fused", fused)

    return fused[:TOP_K]


# --------------------------------------------------------------------------- #
# Step 6 — LLM CLIENT ABSTRACTION + ANSWER GENERATION (LangChain chat models)
# --------------------------------------------------------------------------- #

ANSWER_INSTRUCTION = (
    "You are a customer-support policy assistant. Answer the user's question "
    "using ONLY the policy context provided below. If the context does not "
    "contain the answer, say so explicitly (e.g. \"The policy documents provided "
    "do not cover this.\") — do NOT fill in from general knowledge."
)


def _require_env_key(provider: str, api_key_env: str) -> str:
    """Return the API key from the env, or raise clearly at load time."""
    key = os.environ.get(api_key_env)
    if not key:
        raise RuntimeError(
            f"Active provider '{provider}' requires environment variable "
            f"'{api_key_env}', but it is not set. Add it to .env or export it "
            f"before importing policy_search."
        )
    return key


def _check_reachable(provider: str, base_url: str) -> None:
    """Fail clearly at load time if a local OpenAI-compatible server is down."""
    probe = base_url.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(probe, timeout=3) as resp:  # noqa: S310
            if resp.status >= 500:
                raise RuntimeError(f"HTTP {resp.status}")
    except Exception as exc:  # noqa: BLE001 - surface any failure as one clear error
        raise RuntimeError(
            f"Active provider '{provider}' endpoint {base_url} is not reachable "
            f"({exc}). Start the local server (e.g. LM Studio) and load a model "
            f"first."
        ) from exc


def get_llm_client(config: dict) -> Callable[[str], str]:
    """Return a provider-agnostic ``generate(prompt) -> str`` for the active provider.

    Backed by a LangChain chat model. Fails at call time (module load) on a
    missing API key or an unreachable local endpoint — never mid-query. Only the
    active provider's chat package is imported.
    """
    provider = config["active_provider"]
    pconf = config["providers"][provider]
    model = pconf["model"]
    temperature = pconf["temperature"]

    if provider == "gemini":
        key = _require_env_key(provider, pconf["api_key_env"])
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_output_tokens=pconf["max_output_tokens"],
            google_api_key=key,
        )

    elif provider in ("openai", "local_lmstudio"):
        # Both speak the OpenAI Chat API. local_lmstudio needs no key; its
        # base_url must end in /v1 (normalized here) for the client to work.
        from langchain_openai import ChatOpenAI

        if provider == "openai":
            key = _require_env_key(provider, pconf["api_key_env"])
            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=pconf["max_tokens"],
                api_key=key,
            )
        else:
            base_url = pconf["base_url"].rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
            _check_reachable(provider, base_url)
            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=pconf["max_tokens"],
                base_url=base_url,
                api_key="not-needed",
            )

    elif provider == "anthropic":
        key = _require_env_key(provider, pconf["api_key_env"])
        try:
            from langchain_anthropic import ChatAnthropic
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "active_provider 'anthropic' needs the langchain-anthropic "
                "package: pip install langchain-anthropic"
            ) from exc

        llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=pconf["max_tokens"],
            api_key=key,
        )

    else:
        raise ValueError(f"Unknown active_provider '{provider}' in config.json")

    def generate(prompt: str) -> str:
        log.info(f"[policy_search] answer served by {provider} / {model}")
        return (llm.invoke(prompt).content or "").strip()

    return generate


# Build the client at module load so a bad/missing key fails here, not mid-query.
_GENERATE: Callable[[str], str] = get_llm_client(CONFIG)


def _build_prompt(query: str, docs: list[Document]) -> str:
    """Assemble the answer-generation prompt from the retrieved chunks."""
    context = "\n\n".join(
        f"[{i}] (source: {d.metadata['source_file']})\n{d.page_content}"
        for i, d in enumerate(docs, start=1)
    )
    return (
        f"{ANSWER_INSTRUCTION}\n\n"
        f"Policy context:\n{context}\n\n"
        f"Question: {query}\n\nAnswer:"
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def search_policy_with_context(
    query: str, call_type: str | None = None, generate_answer: bool = True
) -> dict:
    """Same pipeline as search_policy, but for callers that already know the
    call_type (e.g. from a call record) and need the raw chunks + routing info.

    When ``call_type`` is provided it is used directly, skipping routing;
    otherwise the query is routed. Returns
    ``{"answer": str, "chunks_used": list[str], "sources": list[str],
    "routed_call_type": str | None}`` — ``sources`` is the de-duplicated list of
    policy files the chunks came from, so callers can cite them.

    ``generate_answer=False`` skips the LLM answer generation and returns
    ``answer=""`` — for callers (e.g. the QA scorer) that only need the retrieved
    chunks. This avoids a wasted (and, on a local reasoning model, slow) LLM call.
    """
    if call_type is None:
        routed = route_query_to_call_type(query)
    elif call_type in INDEX_CACHE:
        routed = call_type
        log.info(f"[policy_search] caller-supplied call_type={routed} (routing skipped)")
    else:
        log.warning(
            f"[policy_search] caller-supplied call_type={call_type!r} is unknown; "
            f"falling back to all-docs search"
        )
        routed = None

    docs = _retrieve(query, routed)
    log.info(
        f"[policy_search] query={query!r} "
        f"routed={routed if routed is not None else 'unrouted'}"
    )

    answer = _GENERATE(_build_prompt(query, docs)) if generate_answer else ""
    return {
        "answer": answer,
        "chunks_used": [d.page_content for d in docs],
        "sources": sorted({d.metadata["source_file"] for d in docs}),
        "routed_call_type": routed,
    }


def search_policy(query: str) -> str:
    """Search policy documents using hybrid (BM25 + FAISS + RRF) retrieval,
    routed by call_type when inferable. Returns answer generated from top-3
    fused chunks."""
    return search_policy_with_context(query)["answer"]

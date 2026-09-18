"""Tool 4 — Order Lookup (structured filtering over the order tables).

Answers the customer-facing questions the QA tools can't: *where is my order,
what is its status, when will it arrive, did my refund go through*. Turns a
natural-language request into structured filters, applies them with pandas to
three joined tables, and returns a formatted string of matches.

Data (standalone from ``calls.csv`` — its own customers), joined on ``order_id``:

    data/orders.csv     one row per order  (customer, item, amount, payment, status)
    data/shipments.csv  one row per shipped order  (carrier, tracking, ETA, delivery)
    data/returns.csv    one row per return/refund  (reason, return + refund status)

Two-stage extraction, cheapest first — same shape as Tool 2 (call_lookup), so the
two tools behave identically and only their vocabularies differ:

  STAGE 1  regex/enum prefilter (no LLM). Resolves order_id, customer, status,
           category, carrier, payment_status, a row limit + sort order, and the
           unambiguous dates ("today", "yesterday", "last N days").
  STAGE 2  LangChain structured-output LLM fallback, invoked ONLY on fuzzy date
           language regex can't resolve ("this week", "last month", "recent") OR
           when Stage 1 matched nothing. The model is bound with
           ``.with_structured_output(OrderFilters)``; every closed-vocabulary
           field is a real Enum, so out-of-vocabulary values are structurally
           impossible. Regex-resolved fields always win on merge.

Like Tool 2, the chat client is built LAZILY via ``lru_cache`` — a plain
``order 5012`` lookup must work with the LLM provider down, so importing this
module never touches the provider. Every path returns a string; it never raises.

Public API:
    lookup_orders(query) -> str
"""

from __future__ import annotations

import logging

import re
from datetime import date, timedelta
from enum import Enum
from functools import lru_cache
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator

# Shared loader: imports .env (API keys) and config.json exactly once.
from src.config import CONFIG, REPO_ROOT

# Reuse Tool 2's provider switch rather than adding a fourth verbatim copy of it
# (policy_search / qa_scorer / graph each carry their own). Importing call_lookup
# is cheap and builds no client: its LLM is lru_cache'd and lazy, exactly like
# this module's, so `import order_lookup` still never touches the provider.
from src.tools.call_lookup import _build_chat_model

log = logging.getLogger(__name__)

ORDERS_CSV = REPO_ROOT / "data" / "orders.csv"
SHIPMENTS_CSV = REPO_ROOT / "data" / "shipments.csv"
RETURNS_CSV = REPO_ROOT / "data" / "returns.csv"

MAX_LIMIT = 40      # never return more than the whole (40-row) dataset
DEFAULT_LIMIT = 10  # applied only to a wholly unfiltered request ("show my orders")

# Fuzzy date phrases regex cannot resolve safely — the trigger for Stage 2.
_FUZZY_DATE_RE = re.compile(
    r"\b(this week|last week|this month|last month|recent)\b", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Closed vocabularies as Enums — used by the Pydantic schema so out-of-vocab
# values are structurally impossible, not merely discouraged in the prompt.
# --------------------------------------------------------------------------- #

class CustomerName(str, Enum):
    neha = "Neha Gupta"
    arjun = "Arjun Mehta"
    kavya = "Kavya Iyer"
    rohit = "Rohit Nair"
    ananya = "Ananya Bose"
    vikram = "Vikram Rao"
    meera = "Meera Joshi"
    sanjay = "Sanjay Pillai"
    divya = "Divya Menon"
    karan = "Karan Malhotra"
    tanvi = "Tanvi Desai"
    farhan = "Farhan Qureshi"


class OrderStatus(str, Enum):
    placed = "placed"
    packed = "packed"
    shipped = "shipped"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"
    returned = "returned"


class Category(str, Enum):
    kitchen = "kitchen"
    audio = "audio"
    mobile = "mobile"
    computing = "computing"
    wearable = "wearable"


class Carrier(str, Enum):
    bluedart = "BlueDart"
    delhivery = "Delhivery"
    ekart = "Ekart"
    indiapost = "IndiaPost"


class PaymentStatus(str, Enum):
    paid = "paid"
    pending = "pending"
    refunded = "refunded"
    failed = "failed"


class RefundStatus(str, Enum):
    not_started = "not_started"
    processing = "processing"
    completed = "completed"
    denied = "denied"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class OrderFilters(BaseModel):
    """Structured query shared by both stages; every field but sort_order is
    optional (None = don't filter on it)."""

    order_id: Optional[str] = None
    customer_name: Optional[CustomerName] = None
    status: Optional[OrderStatus] = None
    category: Optional[Category] = None
    carrier: Optional[Carrier] = None
    payment_status: Optional[PaymentStatus] = None
    refund_status: Optional[RefundStatus] = None
    date_from: Optional[str] = Field(default=None, description="inclusive, YYYY-MM-DD")
    date_to: Optional[str] = Field(default=None, description="inclusive, YYYY-MM-DD")
    limit: Optional[int] = Field(default=None, description=f"max rows, capped at {MAX_LIMIT}")
    sort_order: SortOrder = SortOrder.desc

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, v: Optional[int]) -> Optional[int]:
        # Clamp (not reject) so an over-eager LLM value degrades gracefully.
        if v is None:
            return None
        return max(1, min(int(v), MAX_LIMIT))

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def _normalize_date(cls, v: Optional[str]) -> Optional[str]:
        # LLMs often return a full datetime ("2026-08-15T00:00:00Z"); keep only
        # the YYYY-MM-DD part so string comparison against the CSV dates is exact.
        if v is None:
            return None
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
        return m.group(1) if m else None

    def describe(self) -> str:
        parts = [
            f"{k}={v.value if isinstance(v, Enum) else v}"
            for k, v in self.model_dump().items()
            if v is not None and k != "sort_order"
        ]
        parts.append(f"sort_order={self.sort_order.value}")
        return ", ".join(parts)

    def is_empty(self) -> bool:
        """True when nothing at all was resolved (no filter, no limit) — the
        'show me my orders' case, which gets DEFAULT_LIMIT applied."""
        return all(
            v is None for k, v in self.model_dump().items() if k != "sort_order"
        )


# --------------------------------------------------------------------------- #
# Stage 1 — regex / enum prefilter (no LLM)
# --------------------------------------------------------------------------- #

def _match_enum(query: str, enum_cls: type[Enum]) -> Optional[str]:
    # Word-boundary match on each member value. Underscored values are matched
    # against natural spacing too ("out_for_delivery" <- "out for delivery").
    q = query.lower()
    for member in enum_cls:
        pattern = re.escape(member.value.lower()).replace("_", "[ _]")
        if re.search(rf"\b{pattern}\b", q):
            return member.value
    return None


def _match_customer(query: str) -> Optional[str]:
    # Full name first ("Neha Gupta"), then the first name alone ("Neha") — every
    # first name in the dataset is unique, so this is unambiguous.
    full = _match_enum(query, CustomerName)
    if full:
        return full
    q = query.lower()
    for member in CustomerName:
        first = member.value.split()[0].lower()
        if re.search(rf"\b{re.escape(first)}\b", q):
            return member.value
    return None


def _extract_order_id(query: str) -> Optional[str]:
    # "order 5012", "#5012", "ORD-5012" -> "ORD-5012". The ord/order/# prefix is
    # REQUIRED: order dates ("2026-09-01") and rupee amounts ("7999") are also
    # four digits, and a bare \d{4} claimed them as order ids — worse, matching
    # anything makes _needs_llm False, so Stage 2 never got to fix it. A bare
    # number now falls through to Stage 2, which is what Stage 1 is supposed to
    # do with anything ambiguous.
    # NB: the \b belongs INSIDE the ord branch — "#" is a non-word character, so
    # a leading \b would never hold before it and "#5012" would not match.
    m = _ORDER_ID_RE.search(query)
    return f"ORD-{int(m.group(1)):04d}" if m else None


_ORDER_ID_RE = re.compile(r"(?:\bord(?:er)?[\s#-]*|#)(\d{4})\b", re.IGNORECASE)


def focus_order_id(texts: list[str]) -> Optional[str]:
    """The order a conversation is currently about: the single order id named
    in the most recent text that names any (user questions say "order 5027",
    tool replies say "[ORD-5027]"). A text naming several orders (a list reply)
    means there is no single focus, so it returns None rather than guessing."""
    for text in reversed(texts):
        ids = {f"ORD-{int(n):04d}" for n in _ORDER_ID_RE.findall(text)}
        if ids:
            return ids.pop() if len(ids) == 1 else None
    return None


def _extract_limit_and_order(query: str) -> tuple[Optional[int], Optional[str]]:
    # "first N" -> earliest N (asc); "last/top N" -> most recent N (desc).
    # A number followed by "day(s)" is a date range, not a row limit.
    m = re.search(r"\b(last|top|first)\s+(\d+)\b(?!\s+days?\b)", query, re.IGNORECASE)
    if not m:
        return None, None
    order = "asc" if m.group(1).lower() == "first" else "desc"
    return int(m.group(2)), order


def _extract_simple_dates(query: str) -> tuple[Optional[str], Optional[str]]:
    # Only the unambiguous relative dates; anything fuzzy is left to the LLM.
    q = query.lower()
    today = date.today()
    if re.search(r"\btoday\b", q):
        iso = today.isoformat()
        return iso, iso
    if re.search(r"\byesterday\b", q):
        iso = (today - timedelta(days=1)).isoformat()
        return iso, iso
    m = re.search(r"\blast\s+(\d+)\s+days?\b", q)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat(), today.isoformat()
    return None, None


def _regex_filters(query: str) -> dict:
    """Stage 1: return only the fields regex resolved (absent keys = unmatched)."""
    order_id = _extract_order_id(query)
    if order_id:
        # An explicit order id identifies exactly one row, so every other word in
        # the sentence is the QUESTION, not a filter. Without this, "When will
        # ORD-5033 be delivered?" also matched status=delivered — and ORD-5033 is
        # out_for_delivery, so the answer was "No matching orders found."
        return {"order_id": order_id}

    limit, order = _extract_limit_and_order(query)
    date_from, date_to = _extract_simple_dates(query)
    # A status word next to fuzzy date language is usually a verb, not a filter
    # ("orders PLACED this week" is about the week, not about status=placed).
    # Stage 2 runs anyway on fuzzy dates, so let the LLM judge it there.
    fuzzy = bool(_FUZZY_DATE_RE.search(query))
    candidates = {
        "customer_name": _match_customer(query),
        "status": None if fuzzy else _match_enum(query, OrderStatus),
        "category": _match_enum(query, Category),
        "carrier": _match_enum(query, Carrier),
        "payment_status": _match_enum(query, PaymentStatus),
        "refund_status": _match_enum(query, RefundStatus),
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "sort_order": order,
    }
    return {k: v for k, v in candidates.items() if v is not None}


def _needs_llm(query: str, regex_fields: dict) -> bool:
    # Escalate on fuzzy date language, or when regex resolved nothing at all.
    return bool(_FUZZY_DATE_RE.search(query)) or not regex_fields


# --------------------------------------------------------------------------- #
# Stage 2 — LangChain structured-output LLM fallback (client cached once)
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _structured_llm():
    # Built once, on first Stage-2 use, and cached. Lazy so a deterministic
    # lookup never constructs the client (and never fails when the LLM is down).
    # Honors the active provider's `structured_output_method` /
    # `structured_output_model` exactly as Tool 2 and Tool 3 do.
    pconf = CONFIG["providers"][CONFIG["active_provider"]]
    method = pconf.get("structured_output_method")
    kwargs = {"method": method} if method else {}
    model = _build_chat_model(CONFIG, model=pconf.get("structured_output_model"))
    return model.with_structured_output(OrderFilters, **kwargs)


_EXTRACTION_PROMPT = (
    "You extract structured search filters from a customer's order-status "
    "request (where is my order, what is its status, when will it arrive, what "
    "happened to my refund). Fill only the fields you are confident about; leave "
    "the rest null. Resolve any relative or fuzzy dates against the current date. "
    "Never guess values for the closed-vocabulary fields.\n\n"
    "Current date: {today}\n"
    "Already resolved by prior parsing (do NOT change these): {resolved}\n\n"
    "Request: {query}"
)


def _llm_filters(query: str, regex_fields: dict) -> Optional[OrderFilters]:
    # Returns an OrderFilters from the structured-output model, or None on any
    # failure (logged) so the tool degrades to the regex-only result.
    try:
        prompt = _EXTRACTION_PROMPT.format(
            today=date.today().isoformat(),
            resolved=regex_fields or "nothing",
            query=query,
        )
        result = _structured_llm().invoke(prompt)
        return result if isinstance(result, OrderFilters) else None
    except Exception as exc:  # noqa: BLE001 - never let the LLM crash the tool
        log.warning(f"[order_lookup] LLM extraction failed, using regex result: {exc}")
        return None


def _resolve_filters(query: str) -> OrderFilters:
    # Run Stage 1, escalate to Stage 2 when needed, and merge with regex winning.
    regex_fields = _regex_filters(query)
    log.info(f"[order_lookup] stage 1 -> {regex_fields or '(no match)'}")

    if not _needs_llm(query, regex_fields):
        log.info("[order_lookup] stage 2 skipped (deterministic answer)")
        return OrderFilters(**regex_fields)

    log.info("[order_lookup] stage 2 -> querying structured-output LLM")
    llm_result = _llm_filters(query, regex_fields)
    if llm_result is None:
        return OrderFilters(**regex_fields)

    # Merge: LLM fills gaps, regex-confirmed fields always take precedence.
    merged = llm_result.model_dump(mode="json")
    merged.update(regex_fields)
    return OrderFilters(**merged)


# --------------------------------------------------------------------------- #
# Data + filtering (pandas)
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _load_df() -> pd.DataFrame:
    # The three tables left-joined on order_id, loaded once and cached. Every
    # column is read as a string (dates stay ISO, so lexical == chronological);
    # a missing shipment/return leaves those columns as "" rather than NaN, so
    # the formatter can test them with a plain truthiness check.
    orders = pd.read_csv(ORDERS_CSV, dtype=str).fillna("")
    shipments = pd.read_csv(SHIPMENTS_CSV, dtype=str).fillna("")
    returns = pd.read_csv(RETURNS_CSV, dtype=str).fillna("")
    df = orders.merge(shipments, on="order_id", how="left").merge(
        returns, on="order_id", how="left"
    )
    return df.fillna("")


def _apply_filters(df: pd.DataFrame, f: OrderFilters) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if f.order_id:
        mask &= df["order_id"] == f.order_id
    if f.customer_name:
        mask &= df["customer_name"] == f.customer_name.value
    if f.status:
        mask &= df["status"] == f.status.value
    if f.category:
        mask &= df["category"] == f.category.value
    if f.carrier:
        mask &= df["carrier"] == f.carrier.value
    if f.payment_status:
        mask &= df["payment_status"] == f.payment_status.value
    if f.refund_status:
        mask &= df["refund_status"] == f.refund_status.value
    if f.date_from:
        mask &= df["order_date"] >= f.date_from
    if f.date_to:
        mask &= df["order_date"] <= f.date_to

    out = df[mask].sort_values(
        ["order_date", "order_id"], ascending=f.sort_order == SortOrder.asc
    )
    if f.limit is not None:
        out = out.head(f.limit)
    return out


def _money(value: str) -> str:
    try:
        return f"Rs {int(float(value)):,}"
    except (TypeError, ValueError):
        return f"Rs {value}"


def _pretty(value: str) -> str:
    return str(value).replace("_", " ")


def _format_order(r) -> str:
    """One order as a header line plus optional shipment / return lines. The
    sub-lines appear only when that table actually had a row for this order."""
    lines = [
        f"[{r.order_id}] {r.order_date} — {r.customer_name} — {r.item} x{r.quantity} "
        f"— {_money(r.amount)} ({r.payment_method}, {r.payment_status})",
        f"    Status: {_pretty(r.status)}",
    ]
    if r.tracking_id:
        eta = f", ETA {r.eta_date}" if r.eta_date else ""
        delivered = f", delivered {r.delivered_date}" if r.delivered_date else ""
        where = f" — last seen {r.last_location}" if r.last_location else ""
        lines.append(
            f"    Shipment: {r.carrier} {r.tracking_id} ({_pretty(r.ship_status)}) "
            f"— shipped {r.ship_date}{eta}{delivered}{where}"
        )
    if r.return_id:
        refund_when = f" on {r.refund_date}" if r.refund_date else ""
        lines.append(
            f"    Return: {r.return_id} {_pretty(r.return_status)} "
            f"({r.return_reason}) — refund {_money(r.refund_amount)} "
            f"{_pretty(r.refund_status)}{refund_when}"
        )
    return "\n".join(lines)


def _format_results(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "No matching orders found."
    return "\n\n".join(_format_order(r) for r in rows.itertuples(index=False))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def lookup_orders(query: str, focus_order_id: Optional[str] = None) -> str:
    """Parse a natural-language order question into structured filters, apply
    them to the joined order/shipment/return tables, and return the matching
    orders formatted as a short status block each.

    Stage 1 (regex/enum) answers most questions with no network call; the
    structured-output LLM (Stage 2) is consulted only for fuzzy dates or when
    regex matched nothing. Always returns a string — on any failure it logs and
    returns either the regex-only result or a plain-English error message.

    ``focus_order_id`` is the order the conversation is already about (see
    ``focus_order_id``); a request that resolves no filters of its own ("when can
    I expect the return?") is answered about that order instead of dumping a
    DEFAULT_LIMIT slice of unrelated orders.
    """
    filters = _resolve_filters(query)
    if filters.is_empty():
        if focus_order_id:
            # ponytail: any filter-less follow-up pins to the focus order, so
            # "show me all my orders" after discussing one returns just that one;
            # widen by naming a customer/status/date. Add an "all/every" escape
            # if that bites.
            filters.order_id = focus_order_id
        else:
            # Nothing was asked for specifically — show a recent slice rather
            # than dumping the whole table.
            filters.limit = DEFAULT_LIMIT
    log.info(f"[order_lookup] filters -> {filters.describe()}")
    try:
        rows = _apply_filters(_load_df(), filters)
    except Exception as exc:  # noqa: BLE001 - surface as a message, never a trace
        log.warning(f"[order_lookup] filtering failed: {exc}")
        return f"Sorry, the order lookup could not be completed: {exc}"
    log.info(f"[order_lookup] query={query!r} matched {len(rows)} order(s)")
    return _format_results(rows)


if __name__ == "__main__":  # manual smoke test — run from the repo root
    for q in (
        "where is order 5031",
        "what is the status of ORD-5012",
        "show me Neha's orders",
        "which orders are out for delivery",
        "did my refund for order 5027 go through",
        "orders placed this week",
    ):
        print("\n" + "=" * 70 + f"\nQUERY: {q}\n" + "=" * 70)
        print(lookup_orders(q))

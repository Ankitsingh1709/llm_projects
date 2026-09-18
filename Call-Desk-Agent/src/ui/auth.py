"""Mock sign-in for the Streamlit UI: decides who gets the Supervisor role.

There is no real user store — this is a course demo. Supervisor accounts live in
``data/supervisors.csv`` (``email,password``); anyone can edit that sheet by
hand. The UI's sign-in form is reached only via "Continue as a supervisor" and
rejects anything that does not resolve to ``"Supervisor"``; customers enter
through a separate no-account button (there is nothing customer-specific to
protect — see the ponytail note in ``src/agent/graph.py`` on the absence of
per-customer identity). ``set_password`` backs the "Forgot password?" flow.
"""

from __future__ import annotations

import csv
import hmac

from src.config import REPO_ROOT

# ponytail: plaintext mock credentials in a CSV, and a password reset that only
# asks for the email (no verification code). If this ever faces real users,
# hash the column and add an emailed reset token.
SUPERVISORS_CSV = REPO_ROOT / "data" / "supervisors.csv"

_FIELDS = ["email", "password"]


def _norm(email: str) -> str:
    return email.strip().lower()


def load_accounts() -> dict[str, str]:
    """{email: password} from the sheet; {} if the sheet is missing. Re-read on
    every call (tiny file) so a reset is visible immediately."""
    try:
        with open(SUPERVISORS_CSV, newline="", encoding="utf-8") as fh:
            return {_norm(r["email"]): r["password"] for r in csv.DictReader(fh) if r.get("email")}
    except FileNotFoundError:
        return {}


def resolve_role(email: str, password: str) -> str:
    """'Supervisor' when email + password match a sheet row, else 'Customer'."""
    expected = load_accounts().get(_norm(email))
    if expected is not None and hmac.compare_digest(expected.encode(), password.encode()):
        return "Supervisor"
    return "Customer"


def email_exists(email: str) -> bool:
    return _norm(email) in load_accounts()


def set_password(email: str, new_password: str) -> bool:
    """Rewrite the sheet with a new password for ``email``. False if unknown."""
    accounts = load_accounts()
    key = _norm(email)
    if key not in accounts:
        return False
    accounts[key] = new_password
    with open(SUPERVISORS_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows({"email": e, "password": p} for e, p in accounts.items())
    return True

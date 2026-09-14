# Synthetic Dataset Notes

`data/calls.csv` holds 50 fabricated call records (CALL-1001 to CALL-1050) written deliberately as
**33 good calls and 17 bad calls**, so the QA scorer in Step 4 can be checked against known answers.
In the 33 good calls the agent does everything the rubric asks for: opens with a greeting and their
own name, verifies identity with an order ID, account name, registered email, or mobile number,
explicitly acknowledges the customer's problem, names the call type being logged
(replacement / repair / logistics / device / escalation), offers a resolution whose numbers match the
matching file in `data/policies/` — the 90-day window and 3-5 business day dispatch for replacements,
the 24-hour acknowledgement and 7 or 14 business day SLA for repairs, the prepaid label and 5-7
business day refund for logistics, the emailed troubleshooting guide and premium screen share for
device, the 2-hour senior-agent assignment and 24-hour SLA for escalation — keeps a professional
tone, and closes by summarising the outcome and thanking the customer. Each of the 17 bad calls
breaks at least one of those on purpose, and the broken parameter varies across them so no single
failure mode dominates: some skip the greeting and open mid-sentence, some never verify identity and
say so outright ("Not bothered, I'll just log it as a general damage report"), some end abruptly with
the agent dropping the call or leaving the chat while the customer is still asking a question, some
use dismissive language that blames the customer ("That's on you, honestly", "stop worrying about
it"), several combine two or three of these, and two calls additionally violate policy — CALL-1026
approves a replacement for self-inflicted drop damage without proof of purchase and promises
next-day dispatch instead of 3-5 business days, and CALL-1047 approves a replacement roughly five
months after purchase, outside the 90-day window, again promising a 48-hour dispatch. Everything
else in the file — names, order IDs, ticket numbers, phone digits — is invented, and the dates all
fall inside the 30 days before 2026-08-23.

## Ground-truth answer key

| call_id | agent | call_type | intended failure(s) |
|---|---|---|---|
| CALL-1006 | Rahul | repair | no greeting |
| CALL-1010 | James | replacement | no identity verification |
| CALL-1013 | Amit | repair | no proper closure (call ends mid-question) |
| CALL-1016 | Rahul | device | dismissive tone |
| CALL-1020 | James | device | no greeting + no identity verification |
| CALL-1022 | Priya | escalation | dismissive tone + no proper closure |
| CALL-1026 | Rahul | replacement | no identity verification + policy violation (misuse damage approved, no proof of purchase, wrong dispatch SLA) |
| CALL-1028 | Amit | logistics | no greeting + dismissive tone |
| CALL-1029 | Sara | escalation | no proper closure (agent cuts the call short) |
| CALL-1030 | James | replacement | no identity verification + dismissive tone + no proper closure |
| CALL-1032 | Sara | repair | no greeting |
| CALL-1035 | Amit | escalation | no identity verification |
| CALL-1038 | James | device | no proper closure (agent ends chat mid-question) |
| CALL-1041 | Priya | device | dismissive tone |
| CALL-1044 | Rahul | logistics | no greeting + no proper closure |
| CALL-1047 | Sara | replacement | no identity verification + policy violation (approved outside the 90-day window, no proof of purchase, 48-hour dispatch promised) |
| CALL-1050 | Amit | replacement | dismissive tone + no proper closure |

All 33 remaining call_ids are intended to score as passes on every rubric parameter.

---

## Order tables (Tool 4 — Order Lookup)

Three synthetic tables, joined on `order_id`, backing the customer-facing order
questions ("where is my order", "when will it arrive", "did my refund go through").
They are **standalone from `calls.csv`** — their own 12 customers, no `call_id`
linkage — so neither dataset constrains the other.

| file | rows | one row per | columns |
|---|---|---|---|
| `orders.csv` | 40 (`ORD-5001`–`ORD-5040`) | order | `order_id, customer_name, customer_email, order_date, item, category, quantity, amount, payment_method, payment_status, status` |
| `shipments.csv` | 33 | order that left the warehouse | `order_id, shipment_id, carrier, tracking_id, ship_date, eta_date, delivered_date, ship_status, last_location` |
| `returns.csv` | 8 | return/refund case | `order_id, return_id, return_reason, requested_date, return_status, refund_amount, refund_status, refund_date` |

Closed vocabularies (mirrored as Python `Enum`s in `src/tools/order_lookup.py`, so
an LLM cannot invent a value):

- `status` — `placed, packed, shipped, out_for_delivery, delivered, cancelled, returned`
- `category` — `kitchen, audio, mobile, computing, wearable`
- `carrier` — `BlueDart, Delhivery, Ekart, IndiaPost`
- `payment_status` — `paid, pending, refunded, failed`
- `return_status` — `requested, approved, rejected, completed`
- `refund_status` — `not_started, processing, completed, denied`
- `ship_status` — `in_transit, out_for_delivery, delivered, returned_to_origin`

Dates run `2026-08-02` → `2026-09-07`, so "recent" / "last N days" queries return
rows against a "today" of early September 2026. Every customer's **first name is
unique**, which is what lets Stage-1 regex resolve "Neha's orders" without an LLM.

Orders worth demoing (each exercises a different join shape):

| order_id | why |
|---|---|
| `ORD-5037` | packed, never shipped — order row only, no shipment/return lines |
| `ORD-5031` | in transit — shipment line with an ETA and a last-known location, no delivery date |
| `ORD-5033` | out for delivery today |
| `ORD-5027` | all three tables: delivered, return approved, refund still `processing` |
| `ORD-5006` | return **rejected** (raised after 21 days) → `refund_status = denied` |
| `ORD-5013` | full return round-trip: delivered, returned to origin, refund completed |
| `ORD-5017` | cancelled with `payment_status = failed` — no shipment, no return |

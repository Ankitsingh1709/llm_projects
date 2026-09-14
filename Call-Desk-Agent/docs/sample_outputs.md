# Sample outputs

Captured by running the compiled graph (`src/agent/graph.py`) with provider `gemini` (model `models/gemini-2.5-flash`). Dev logs suppressed. Each block shows the role, the user request, the answer, and the `tool_trace` the graph recorded.

## Supervisor: “What is the replacement window?”

**Tools used:** `policy`

```text
A product is eligible for replacement only if the request is raised within 90 days of the original date of purchase.

_Sources: replacement_policy.txt_
```

<details><summary>tool_trace</summary>

```python
[{'tool': 'policy', 'source_file': 'data/policies/', 'llm_degraded': False}]
```
</details>

## Supervisor: “Show me Rahul's last 3 calls”

**Tools used:** `lookup`

```text
[CALL-1001] 2026-08-22 — Rahul — replacement (inbound, phone, 7 min)
[CALL-1034] 2026-08-20 — Rahul — device (inbound, phone, 10 min)
[CALL-1006] 2026-08-17 — Rahul — repair (outbound, phone, 5 min)
```

<details><summary>tool_trace</summary>

```python
[{'tool': 'lookup', 'call_ids': ['CALL-1001', 'CALL-1034', 'CALL-1006'], 'source_file': 'data/calls.csv', 'llm_degraded': False}]
```
</details>

## Supervisor: “Look up call 1016 and score it”

**Tools used:** `lookup → score`

```text
#### QA Scorecard — CALL-1016
*Category: inbound — weights sum to 100*

| Parameter | Result | Weight | Why |
|:--|:--:|:--:|:--|
| greeting | ✅ PASS | 10 | The agent greeted the customer with "Hi, support chat, Rahul here." in the first turn. |
| identity_verification | ✅ PASS | 15 | The agent asked for the customer's account name and registered email to verify identity. |
| problem_acknowledgement | ❌ FAIL | 10 | The agent did not explicitly acknowledge the customer's issue, instead immediately attributing it to the customer's wiring. |
| call_classification | ✅ PASS | 5 | The agent correctly identified the issue as a "device support query" which aligns with a router disconnecting. |
| solution_offered | ✅ PASS | 15 | The agent offered a concrete next step by stating, "I'm logging it as a device support query and sending the troubleshooting guide." |
| policy_compliance | ✅ PASS | 15 | The agent's action of sending a basic troubleshooting guide on first contact aligns with policy 3. |
| professional_tone | ❌ FAIL | 15 | The agent used rude and dismissive language such as "stop overthinking it" and "read it properly this time." |
| proper_closure | ❌ FAIL | 5 | The agent closed the chat abruptly and impolitely with "Anything else? No? Chat closed." without a proper summary. |
| sla_met | ❌ FAIL | 10 | SLA not met per call record |

**Weighted score: 60/100 (60%) — FAIL**  
⚠️ _professional_tone FAIL → automatic FAIL_
```

<details><summary>tool_trace</summary>

```python
[{'tool': 'lookup', 'call_ids': ['CALL-1016'], 'source_file': 'data/calls.csv', 'llm_degraded': False}, {'tool': 'score', 'call_id': 'CALL-1016', 'source_file': 'data/calls.csv + data/policies/', 'llm_degraded': False}]
```
</details>

## Customer: “Where is my order 5031?”

**Tools used:** `order`

```text
[ORD-5031] 2026-09-01 — Meera Joshi — Wireless Charger Pad x1 — Rs 1,499 (upi, paid)
    Status: shipped
    Shipment: Ekart TRK-EK-3319701 (in transit) — shipped 2026-09-02, ETA 2026-09-06 — last seen Bhopal transit point
```

<details><summary>tool_trace</summary>

```python
[{'tool': 'order', 'source_file': 'data/orders.csv + shipments.csv + returns.csv', 'llm_degraded': False}]
```
</details>

## Customer: “Show me call 1042”

**Tools used:** `(none — refused)`

```text
I can only help with company policy, product questions, and your order status. Call records and QA scores are available to supervisors only.
```

<details><summary>tool_trace</summary>

```python
[]
```
</details>

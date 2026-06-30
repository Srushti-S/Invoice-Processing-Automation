# Live tool-call trace — evidence of real function-calling

This captures an actual run of the same invoice through (a) the offline **mock**
reasoner and (b) a **live LLM** (Groq, `llama-3.3-70b`), showing that the case's
"function calling / tool use, structured outputs, self-correction loops" capabilities
are genuinely exercised — not simulated. Captured 2026-06-30.

> Groq is used here only because no `XAI_API_KEY` was on hand; the `LLMReasoner` code
> path is identical for xAI Grok (only `base_url`/`model` differ), so wiring
> `XAI_API_KEY` exercises the exact same tool loop.

## Command

```bash
# offline mock (default)
python main.py --invoice_path=data/invoices/invoice_1003.txt --mock-llm

# live LLM — real function-calling
python main.py --invoice_path=data/invoices/invoice_1003.txt --provider groq
```

## Result — INV-1003 (the "Fraudster LLC" invoice)

| | Mock (offline, default) | Live LLM (Groq) |
|---|---|---|
| `extraction_method` | `heuristic` | `llm:groq` (structured extraction via `function_calling`) |
| **tool calls** | none | 2 real calls (below) |
| `fraud_signals` | 4 (deterministic) | 7 (4 deterministic + 3 model-added) |
| rationale / reflection | templated | model-written |
| **decision / risk** | **REJECT / 100** | **REJECT / 100** (identical) |

### The real tool calls the model made (live)

```
check_inventory('FakeItem') -> FakeItem: stock=0, in_catalog=True
recompute_total()           -> recomputed=100000.0, stated=100000.0, delta=0.0
```

The model autonomously chose to call `check_inventory` and `recompute_total` (bound via
`llm.bind_tools(...)` in `invoice_ai/llm.py`), their results were fed back as tool
messages, and it then returned a structured risk verdict (`with_structured_output`).

## Why the decision is identical in both modes

This is the core design invariant, shown live: the **pay/no-pay decision is deterministic
code**. Turning the LLM on makes the reasoning richer and tool-verified (it added 3 extra
fraud signals and confirmed stock and the math with tools), but the model's risk
contribution is **clamped to `[0,40]` and one-directional** — it can only raise caution,
never release a payment. So the outcome (REJECT, risk 100/100) is the same offline and
online: the LLM cannot cause a wrong payment.

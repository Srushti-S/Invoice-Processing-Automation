# Live tool-call trace

A run of the same invoice through the offline mock reasoner and through a live LLM
(Groq, llama-3.3-70b), so the two can be compared side by side. Captured 2026-06-30.

Groq is used here because there was no xAI key on hand. The LLMReasoner code path is the
same for Grok (only the base URL and model name differ), so an XAI_API_KEY runs the same
tool loop.

## Command

```bash
# offline mock (default)
python main.py --invoice_path=data/invoices/invoice_1003.txt --mock-llm

# live LLM
python main.py --invoice_path=data/invoices/invoice_1003.txt --provider groq
```

## Result: INV-1003 (the "Fraudster LLC" invoice)

| | Mock (offline, default) | Live LLM (Groq) |
|---|---|---|
| extraction | heuristic | llm:groq (structured, via function calling) |
| tool calls | none | 2 (below) |
| fraud signals | 4 (deterministic) | 7 (4 deterministic + 3 from the model) |
| rationale / reflection | templated | model-written |
| decision / risk | REJECT / 100 | REJECT / 100 |

Tool calls the model made:

```
check_inventory('FakeItem') -> FakeItem: stock=0, in_catalog=True
recompute_total()           -> recomputed=100000.0, stated=100000.0, delta=0.0
```

The model called check_inventory and recompute_total (bound with llm.bind_tools in
invoice_ai/llm.py), got their results back as tool messages, and returned a structured
risk verdict.

## Why the decision is the same either way

The pay/no-pay logic is deterministic Python, so the outcome does not depend on the
model. Running with an LLM makes the reasoning richer and tool-verified (it added 3 fraud
signals and checked stock and the math with tools), but its risk contribution is capped
at [0,40] and can only raise caution. So INV-1003 rejects at risk 100 whether it runs
offline or online.

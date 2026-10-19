# Model Usage Report — final full-dataset run

Generated: 2026-10-19 08:29:32 UTC
Requests processed: 250
Configured MODEL_PROVIDER: `none (deterministic engine)`
Text model (TEXT_MODEL): `-`
Vision model (VISION_MODEL): `-`

The run that produced the submitted `output.csv` used the deterministic
finance engine for every decision. Real LLM/VLM providers are integrated
through `buy_or_wait/llm.py` (OpenAI, Anthropic, and Google are supported)
and are invoked automatically for message/image evidence whenever
`MODEL_PROVIDER` and the matching API key are present in the environment;
extractions are cached by content hash so no evidence is ever sent twice.
No provider was configured for this run, so 0 model calls were made.

## Per-model usage

| provider:model | calls | input tokens | output tokens | total tokens | est. cost (USD) |
|---|---|---|---|---|---|
| (none — no provider configured) | 0 | 0 | 0 | 0 | $0.00 |

## Overall

- Model calls: 0
- Input tokens: 0
- Output tokens: 0
- Total tokens: 0
- Estimated total cost: $0.000000
- Average tokens per request: 0.0
- Average cost per request: $0.00000000

## Cache statistics

Evidence extractions are cached per (source content hash). Image facts are
cached in `code/.cache/image_facts.json`; message facts are memoised per
message id in-process. Cache hits never trigger a provider call.

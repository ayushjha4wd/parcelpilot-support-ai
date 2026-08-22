# Deploy

The whole app (API + built UI) runs from one container. Three easy options.

## Option A — Hugging Face Docker Space (free, recommended)

1. Create a new **Space** → SDK: **Docker** → blank.
2. Push this repo to the Space (or connect the GitHub repo).
3. In **Settings → Variables and secrets**, add a secret:
   - `HF_TOKEN` = your Hugging Face token (Read scope is enough for inference).
   - (optional) `LLM_MODEL`, `LLM_PROVIDER`, etc.
4. The Space builds the `Dockerfile` and serves on port `7860`. Done.

> The app defaults to `LLM_PROVIDER=huggingface` and the HF router, so on a Space
> you only need `HF_TOKEN`.

## Option B — Render / Railway

- New **Web Service** from the repo, environment **Docker**.
- Set env vars from `.env.example` (at minimum a provider key).
- Render provides `$PORT`; the container already respects it.

## Option C — Local Docker

```bash
docker build -t parcelpilot-ai .
docker run -p 7860:7860 -e HF_TOKEN=hf_xxx parcelpilot-ai
# open http://localhost:7860
```

## Switching LLM provider

Set `LLM_PROVIDER` to one of `huggingface | openai | groq | gemini` and supply
the matching key (`HF_TOKEN` / `OPENAI_API_KEY` / `GROQ_API_KEY` /
`GEMINI_API_KEY`). Optionally pin `LLM_MODEL`. No code changes.

## Swapping in the official data pack

Replace `backend/app/data/ParcelPilot_Assessment_Data.xlsx` and the PDFs in
`backend/app/data/documents/`, then either restart or call
`POST /api/reload-data`. The loader adapts to the workbook's actual schema.

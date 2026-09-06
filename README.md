# Agentic RFP Evaluation and Supplier Ranking

Streamlit application for evaluating synthetic supplier RFP PDFs with an LLM, validating the returned scorecards, calculating deterministic weighted scores and peer benchmarks, and producing an explainable leaderboard.

## Architecture

1. **Streamlit UI** — criteria, supplier upload/metadata, leaderboard, and run details.
2. **Orchestrator** — controls setup → PDF extraction → LLM evaluation → validation → scoring → benchmarking → ranking → SQLite persistence.
3. **Document tool** — extracts PDF text with `pypdf`.
4. **Evaluation agent** — asks an OpenRouter-compatible JSON LLM for criterion scores, justification, evidence, risks, and summary.
5. **Validation tool** — ignores unexpected criteria, clips out-of-range scores, and fills missing active criteria with zero plus warnings.
6. **Ranking tool** — deterministic business rules only; the LLM never calculates the final rank.
7. **SQLite** — stores criteria, runs, and complete supplier result JSON.

## Scoring rules

- Absolute weighted score = `sum((criterion score / max score) * criterion weight)`.
- Criterion benchmark = highest valid supplier score for that criterion.
- Criterion gap = supplier score − benchmark.
- Relative performance = `(supplier score / benchmark) * 100`, with zero-safe handling.
- PPI = weighted average of criterion relative-performance percentages.
- Tie-break order: higher PPI → earlier submission date → higher historical experience rating → supplier name ascending.

## Local setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed_db.py
```

Create `.env` from `.env.example` and set `OPENROUTER_API_KEY`. `OPENROUTER_MODEL` can also be set there.

Run:

```bash
streamlit run app.py
```

## Tests

```bash
pytest -q
python -m compileall -q app.py database.py llm.py orchestrator.py ranking.py tools.py seed_db.py
```

## Streamlit Community Cloud

1. Push the repository to GitHub.
2. Open Streamlit Community Cloud and create an app from the GitHub repository.
3. Select `main` and `app.py` as the entrypoint.
4. In Advanced settings, add the following secrets:

```toml
OPENROUTER_API_KEY = "your-key"
OPENROUTER_MODEL = "openai/gpt-5.4-mini"
# Optional LangSmith tracing
LANGSMITH_API_KEY = "your-key"
LANGSMITH_TRACING = "true"
LANGSMITH_PROJECT = "Agentic-RFP-Evaluation"
```

The app reads secrets from Streamlit Cloud or environment variables locally. Never commit `.env` or `secrets.toml`.

## Important deployment note

The project uses SQLite because it is required by the classroom brief. Streamlit Community Cloud does **not** guarantee persistence of local file storage. This is acceptable for a classroom demonstration, but a production multi-user application should move persistent run data to a hosted database.

## Synthetic data

The `data/` folder contains four fictional proposals: Apex Systems, BrightPath Tech, NexaWorks, and Orbit Digital. They are classroom-only synthetic documents.

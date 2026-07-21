FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir \
    "psycopg[binary]==3.3.4" \
    "rdflib==7.6.0" \
    .

COPY config/ config/
COPY queries/ queries/
COPY results/final/campaign.json results/final/summary.csv results/final/
COPY results/final/advisor_evaluation.csv live-demo/ui/data/advisor_evaluation.csv
COPY results/final/summary.csv live-demo/ui/data/summary.csv
COPY live-demo/ui/ live-demo/ui/
COPY sql/ sql/

CMD ["dm-demo", "--help"]

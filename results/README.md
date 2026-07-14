# Benchmark evidence layout

- `final/` is the sole accepted paired campaign used for cross-backend timing,
  advisor evaluation, and report claims.
- `archive/` preserves superseded paired campaigns for reproducibility checks;
  archived timings are not merged with `final/`.
- `edo/` preserves Edoardo's PostgreSQL-only validation and historical evidence;
  it supports correctness and plan analysis but is not a second paired campaign.

Only a correctness-gated candidate with the frozen dataset and instance hashes
may replace `final/`.

# Controlled campaign preflight

- Pre-campaign code/config commit: `8b2051adb2d724b2576ac27b04e5bc20ebcf7977`.
- Test suite: 16 passed in 0.68 seconds.
- Dataset SHA-256: `3e8b08752eecf0fff56f5b1bcf1fcad0bbb717d9d40e0a169761569e53050e4c`.
- Instances SHA-256: `6b9e2b659ef172935ad3c3c609aa5ef6d9f7ac5e4f7b7b36c1a109d40dc82cad`.
- Official source MD5 reverified: `0f361aac50ce087524d5ac4bcf25cad2`.
- Fresh PostgreSQL and Fuseki containers loaded from one canonical extract.
- PostgreSQL, canonical CSV, and metadata counts agree: 42,051 publications,
  66,390 persons, and 173,986 authorships.
- Fuseki counts agree and the graph contains 475,002 triples.
- Colima allocation verified from both host configuration and guest `nproc`:
  10 vCPUs, 8 GiB RAM.
- Both services healthy; only project containers running; AC power attached.
- Frozen execution policy: first + 2 warm-ups + 5 measured runs, 300-second
  timeout, interleaved backend order, no mid-campaign changes.

# Pilot timing preflight

Captured on 2026-07-13 immediately before the accepted PostgreSQL campaign.

- Local preflight time: approximately 19:42 Europe/Rome.
- Power: AC attached; battery 76% and not charging.
- System memory free: 44% at the first post-extraction check.
- Load averages after a 30-second settling interval: 3.11, 3.73, 5.30.
- The six-hour canonical extraction had completed before this preflight.
- No extraction, tests, execution-plan collection, or diagnostics overlapped the
  accepted timed campaign.
- Visible background activity was limited to the Codex/terminal interface,
  WindowServer, and existing desktop helper processes. The host was not claimed
  to be fully idle; this is an experimental limitation.
- PostgreSQL reported version 17.10, `shared_buffers=128MB`, `work_mem=4MB`, and
  `jit=on`.

The timing boundary includes query execution and complete result retrieval. A
first execution is recorded separately, followed by two warm-ups and five
measured repetitions for every instance.

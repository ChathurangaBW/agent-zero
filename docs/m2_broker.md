# M2 broker — managed assessment gates

Tracked M2 exit note for the evidence-backed web assessment broker
(`plugins/_web_pentest/`). It records the commercial broker rules enforced
in code and the M2 exit checklist verified by
`pytest tests/test_web_pentest_engine.py`.

## 1. Scope gates (exact origin + excluded paths)

- Engagements declare exact `origins` plus optional `support_origins`
  (identity-health only) and `excluded_paths`.
- Every entry point enforces the same gate via
  `helpers/security.py:scope_check` / `enforce_scope`:
  - `Service.add_surface` (`helpers/service.py`) — excluded paths rejected.
  - `Service.compare` — excluded URLs rejected before any observation.
  - `Transport.request` (`helpers/transport.py`, context `request`) —
    direct requests, redirects (`redirect`), identity-health
    (`support_origins` only) and scope-rejection audit (`scope_rejected`).
  - `BrowserExecutor` (`helpers/browser.py`) — preflight `browser_navigate`
    / `callback` checks plus per-subrequest `browser_subrequest` and final
    `browser_final` enforcement.
  - `Transport.check_callback` / `Service.check_callback` (`callback`) and
    OAST `base_url` flagging (`base_url_in_scope`, outside scope stays usable
    for external collaborator infrastructure).

## 2. Budget and deadline (per-step)

- `Store.reserve_request` is the single budget authority; concurrent workers
  cannot overdraw it.
- `Transport.request` reserves once per managed request and emits
  `budget_exhausted` / `deadline_exceeded` audit events fail-closed.
- `BrowserExecutor.run` reserves **once per browser step** (navigate, fill,
  click, wait, callback) plus once per allowed subrequest, re-checks the
  engagement deadline per step, and emits `budget_exhausted` /
  `deadline_exceeded` / `browser_blocked` events. Exhausted or cancelled
  engagements and past-deadline flows never touch Chromium.
- `Service.set_deadline` / `cancel_engagement` and `Store.budget_status`
  (`blocked`, `deadline_expired`, `remaining`) are the operator controls.

## 3. Evidence (mtime + digest authority + retention)

- `EvidenceVault.write` content-addresses encrypted (`digest.enc`) and
  redacted (`redacted_digest.json`) files, aligns file mtimes to the write
  clock, and `Store.artifact` re-aligns both files to the DB record's
  `created` so the mtime sweep agrees with the DB cutoff
  (`helpers/store.py:artifact`, `helpers/evidence.py:write`).
- `Store.purge_expired` is digest-authoritative:
  - DB rows are the authority. Digests still referenced by retained
    (unexpired) rows form `keep_digests`.
  - `vault.remove_record_files(..., keep_digests)` skips shared
    content-addressed files (ref-count via the retained set), so expiring
    one of two redaction-shared records keeps the shared
    `redacted_digest.json` readable.
  - `vault.purge(..., keep_digests)` sweeps only orphan/legacy files by
    mtime; retained stems survive even with an old mtime.
  - Returns `deleted_records`, `deleted_files`, `retention_days`, `cutoff`,
    plus `retained: bool` and `retained_count` (`helpers/store.py`).
- Retention window defaults to `RETENTION_DAYS = 30`
  (`helpers/security.py:is_retained`, `retention_cutoff`).

## 4. Isolation

External network adapters (nuclei/katana/httpx binary, sqlmap, dalfox,
ffuf, testssl, interactsh-client) execute only inside an explicit Linux
sandbox (`A0_WEB_PENTEST_SANDBOX=1` on POSIX/Linux); otherwise
`assert_isolated` fails closed. Semgrep remains local read-only.

## 5. M2 exit checklist

1. Service `add_surface` / `compare` enforce `excluded_paths`.
2. Browser per-step budget + per-step deadline gates.
3. Evidence mtime alignment (vault write + artifact re-align).
4. `Store.purge_expired` returns `retained: bool` (+ `retained_count`).
5. Digest-authoritative `keep_digests` ref-count purge (DB authority,
   shared-digest safe, orphan mtime sweep).
6. Tracked doc (this file) + AGENTS references.
7. Regression tests + green suite:
   - `test_browser_per_step_budget_exhaustion`
   - `test_excluded_surface_and_compare_are_blocked`
   - `test_retention_mtime_and_shared_digest_refcount`

## Verification

Run in the framework Python:

```bash
pytest tests/test_web_pentest_engine.py -q
```

Expect 91 passed.

Log (`python -m pytest tests/test_web_pentest_engine.py -q`):

```text
91 passed in 19.32s
```

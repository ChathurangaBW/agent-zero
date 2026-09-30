# Web Pentest Skills Integration

No logic changes. Mapping-only integration doc for the 9-skill commercial pentest-skills port.

Skill paths:
- `plugins/_web_pentest/skills/web-recon/SKILL.md`
- `plugins/_web_pentest/skills/web-exploit/SKILL.md`
- `plugins/_web_pentest/skills/web-report/SKILL.md`

## 1. 9-skill mapping (test_modules.py:50-123, methodology 21-40, catalogue 34-44)

`helpers/test_modules.py:50-123` defines `SKILL_MODULES` — 8 commercial pentest-skills (+ report) mapped to catalogue modules. Ported from crazyMarky pentest-skills + ai-penetration-testing leaders; each skill declares trigger + toolchain + analysis, an automation label (executable vs guided) and its typed verifier:

| Skill | test_ids | toolchain | automation | verifier | trigger |
|---|---|---|---|---|---|
| recon-ports | MAP-01, CONFIG-01 | nmap, httpx | candidate_generation | RECON/v1 | map open ports and exposed services for an in-scope origin |
| recon-subdomains | MAP-01 | subfinder, httpx, katana | candidate_generation | RECON/v1 | enumerate subdomains and virtual hosts for an in-scope domain |
| recon-dirs | MAP-01, CONFIG-01 | ffuf, gobuster, katana | candidate_generation | RECON/v1 | discover hidden paths and files under an in-scope origin |
| recon-fingerprint | MAP-01, CONFIG-01, SOURCE-01 | httpx, wappalyzer-cli, semgrep | implemented | RECON/v1 | fingerprint server, framework and headers for an in-scope URL |
| exploit-sqli | INJ-01, BLIND-01 | sqlmap, interactsh-client | candidate_generation | INJ/v1 | test SQL injection parameters with baseline and negative controls |
| exploit-xss | XSS-01 | dalfox, browser | candidate_generation | XSS/v1 | test reflected, stored and DOM cross-site scripting contexts |
| exploit-lfi | FILE-01 | ffuf, nuclei | guided | FILE/v2 | test local file inclusion and path traversal boundaries |
| exploit-filedownload | FILE-01 | nuclei, transport | guided | FILE/v2 | test arbitrary file download and upload parser boundaries |
| pentest-report | CHAIN-01, CONFIG-01 | proof-capsule, report-capsule | implemented | CHAIN/v1 | compile confirmed findings, candidates and coverage into a replayable report |

`helpers/methodology.py:21-40` defines `SKILL_WORKFLOWS` — the SKILL.md pattern (trigger + toolchain + analysis) for the 8 commercial pentest-skills plus the report skill. Methodology cards reference these so agents pick the right toolchain and prove every finding with a verifier. Keys: recon-ports, recon-subdomains, recon-dirs, recon-fingerprint, exploit-sqli, exploit-xss, exploit-lfi, exploit-filedownload, pentest-report (lines 21-40).

`helpers/catalogue.py:34-44` defines `SKILL_COVERAGE` — commercial skill coverage (crazyMarky pentest-skills + ai-penetration-testing leaders) mapped onto the stable catalogue. Schema stays v2: this map is advisory and never changes CATALOGUE row counts (lines 34-44):
- recon-ports: (MAP-01, CONFIG-01)
- recon-subdomains: (MAP-01,)
- recon-dirs: (MAP-01, CONFIG-01)
- recon-fingerprint: (MAP-01, CONFIG-01, SOURCE-01)
- exploit-sqli: (INJ-01, BLIND-01)
- exploit-xss: (XSS-01,)
- exploit-lfi: (FILE-01,)
- exploit-filedownload: (FILE-01,)
- pentest-report: (CHAIN-01, CONFIG-01)

Analysis rule per skill (from test_modules.py:50-123): correlate candidates with managed-request observations; confirm with fresh managed requests, never scanner severity alone. Baseline 404 behaviour first; require normal baseline + injected delta + negative control; blind trials need correlated OAST IDs; separate confirmed findings from candidates with verification record + replayable proof capsule.

## 2. Verifiers (test_modules 20-29, service 338/354/514/554, controller 39)

`helpers/test_modules.py:20-29` defines `VERIFIERS` — typed verifiers: every catalogue test declares its independent verifier. AUTHZ-01/v2 is the only fully automatic confirmer; the rest are prove-every-finding verifiers (fresh controls + proof-capsule replay):
- MAP-01: RECON/v1, AUTHZ-01: AUTHZ-01/v2, AUTHZ-02/03/04: AUTHZ/v1
- AUTHN-01/02, SESS-01: SESSION/v1, ORIGIN-01: ORIGIN/v1
- INJ-01: INJ/v1, XSS-01: XSS/v1, FILE-01: FILE/v2, API-01/02: API/v1, API-03: None
- BLIND-01: BLIND/v1, LOGIC-01: LOGIC/v1, RACE-01: RACE/v1
- HTTP-01: HTTP/v1, HTTP-02: None, CONFIG-01: RECON/v1, CHAIN-01: CHAIN/v1, SOURCE-01: SOURCE/v1

Service bindings:
- `helpers/service.py:338` — `compare(owner, engagement, owner_identity, restricted_identity, url, marker, ...)` differential control runner backing AUTHZ/v1.
- `helpers/service.py:354` — `verify(owner, engagement, finding_id)` typed-verifier dispatcher; findings remain candidates until a typed verifier reruns fresh controls. Generic check completion cannot confirm a finding.
- `helpers/service.py:514` — `verdict(owner, engagement, capsule_id, identity, marker, control_identity)` capsule verdict with control identity.
- `helpers/service.py:554` — `verify_generic(owner, engagement, finding_id, capsule_id, identity, control_identity, marker)` generic proof-capsule replay verifier.

`helpers/controller.py:39` — `specialist_plan(owner, engagement)` exposes the skill-aware assessment plan to the web_pentester profile tool.

## 3. Isolation (security 47/57/99/74, transport, sessions, adapters Broker/150)

- `helpers/security.py:47` — `scope_check(url, allowed_origins, excluded_paths=())` pure scope predicate.
- `helpers/security.py:57` — `enforce_scope(url, allowed_origins, excluded_paths=(), context="request")` fail-closed enforcement; surfaces, compare URLs, managed requests, redirects, browser flows and callbacks reject excluded paths fail-closed.
- `helpers/security.py:74` — `isolation_status()` reports managed HTTP isolation posture.
- `helpers/security.py:99` — `assert_isolated(tool="adapter")` guard; standard browser and unrestricted terminal tools are outside managed HTTP isolation and scope enforcement.
- `helpers/transport.py` — exact-origin HTTP execution: managed requests enforce exact scheme, host and port, count against the engagement budget and do not follow redirects. Credential values never enter tool/API arguments; identity headers reference environment variables named `A0_WEB_PENTEST_*`.
- `helpers/sessions.py` — isolated identities: owner binding, redaction, request budgets, negative controls preserved per identity.
- `helpers/adapters.py:Broker` — `Broker` class (line 22) fronting `AdapterRegistry` (line 61, `self.broker = Broker()` line 79); toolchains route via adapters Broker/150 (transport/sqlmap/dalfox/nuclei/ffuf/httpx/katana/subfinder/semgrep/interactsh-client/browser/proof-capsule/report-capsule). TOOLCHAINS map (test_modules.py:31-44): MAP-01 [nmap, httpx, katana, ffuf, subfinder], AUTHZ-* [transport], AUTHN [transport, browser], INJ-01 [sqlmap, nuclei], XSS-01 [dalfox, nuclei→browser], FILE-01 [ffuf, nuclei], API [httpx, katana], BLIND-01 [interactsh-client], SOURCE-01 [semgrep, httpx].

## 4. Discovery (discovery 58/63/111/137/150/184/212, service 268/419/425/432-442)

- `helpers/discovery.py:58` — `DiscoveryEngine` class.
- `helpers/discovery.py:63` — `crawl(owner, engagement, identity_id, seeds, max_pages, max_depth)` bounded crawl feeding MAP-01 coverage.
- `helpers/discovery.py:111` — `import_openapi(owner, engagement, document, source)` operator-supplied API surface import.
- `helpers/discovery.py:137` — `fingerprint(owner, engagement, identity_id, url)` header/meta observation (recon-fingerprint).
- `helpers/discovery.py:150` — `enumerate_dirs(owner, engagement, identity_id, base_url, wordlist, max_words)` hidden-path discovery with 404 baseline (recon-dirs).
- `helpers/discovery.py:184` — `enumerate_subdomains(owner, engagement, identity_id, candidates)` untrusted-candidate subdomain enumeration; out-of-scope names stay blocked with audit (recon-subdomains).
- `helpers/discovery.py:212` — `enumerate_ports(owner, engagement, host, ports)` port/service candidate generation (recon-ports).

Service facades:
- `helpers/service.py:268` — `add_surface(owner, engagement, url, method, description)` records discovered surface against engagement scope.
- `helpers/service.py:419` — `skill_map(owner)` catalogue→skill coverage view.
- `helpers/service.py:425` — `skill_workflow(owner, skill)` trigger/toolchain/analysis card for one skill.
- `helpers/service.py:432-442` — `recon_ports` (432) → `discovery.enumerate_ports`; `recon_subdomains` (435) → `enumerate_subdomains`; `recon_dirs` (438) → `enumerate_dirs`; `recon_fingerprint` (441) → `fingerprint` (lines 432-442).

## 5. Capsule (evidence 191, service 444/464/473/622, store 543)

- `helpers/evidence.py:191` — `to_mitmproxy(content)` capsule/evidence export helper; evidence file mtimes track the DB record clock; retention purges are digest-authoritative (`keep_digests` from retained rows, shared-digest safe).
- `helpers/service.py:444` — `proof_capsule(owner, engagement, evidence_id, title, test_id)` builds a replayable proof capsule; every confirmed item links a verification record and a replayable proof capsule.
- `helpers/service.py:464` — `report_capsule(owner, engagement)` compiles confirmed findings, candidates and coverage into a replayable report (pentest-report skill toolchain: proof-capsule, report-capsule).
- `helpers/service.py:473` — `capsule_replay(owner, engagement, capsule_id, identity, mutations, attempt_id)` fresh-control replay backing prove-every-finding verifiers.
- `helpers/service.py:622` — `report(owner, engagement)` final report assembly separating confirmed findings from candidates.
- `helpers/store.py:543` — `coverage(owner, engagement)` methodology accounting view; coverage is methodology accounting, never a security score or a claim of complete vulnerability recall. Runtime state and evidence stay under `usr/web_pentest`.

## Verification

pytest:
```
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 18.37s
```
Command: `python -m pytest tests/test_web_pentest_engine.py -q` — 91 passed log.

Diff stat:
```
 docs/guides/web-pentesting.md                      |   2 +
 plugins/_web_pentest/AGENTS.md                     |   4 +
 .../prompts/agent.system.main.specifics.md         |  10 +
 .../prompts/agent.system.tool.web_assessment.md    |  18 +-
 plugins/_web_pentest/helpers/catalogue.py          |  19 +
 plugins/_web_pentest/helpers/inventory.py          |  41 +-
 plugins/_web_pentest/helpers/methodology.py        |  43 +-
 plugins/_web_pentest/helpers/security.py           |  84 ++-
 plugins/_web_pentest/helpers/service.py            | 497 +++++++++++++-
 plugins/_web_pentest/helpers/store.py              | 351 +++++++++-
 plugins/_web_pentest/helpers/transport.py          | 327 +++++++--
 plugins/_web_pentest/integration.py                |   4 +-
 plugins/_web_pentest/plugin.yaml                   |   2 +-
 tests/test_web_pentest_engine.py                   | 744 ++++++++++++++++++++-
 14 files changed, 2030 insertions(+), 116 deletions(-)
```

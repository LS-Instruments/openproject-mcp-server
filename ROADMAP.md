# openproject-mcp-server — Modernization Roadmap

> Status: **DRAFT for review** · Author: architecture review (LS Instruments fork) · Context: the
> project is now an independently-maintained ("sail-alone") fork and has an explicit mandate to
> modernize to best-practice architecture **even at the cost of breaking changes**, since there is no
> upstream-compatibility constraint.

This roadmap is grounded in a four-part audit of the *current* code (architecture, testing, API
coverage, distribution & documentation), not on assumptions. Where the audits found something that
contradicts folklore about the repo, the finding wins.

---

## 1. North Star

A small, **modern, fully-typed, well-tested Python service** that exposes the OpenProject API v3 to
MCP clients, is:

- **layered** (transport → typed API gateways → service/domain logic → thin tool adapters → presentation),
- **safe by construction** (typed settings & secrets, real auth on network transports, typed errors,
  no lost-update races),
- **installable in one line** (`uvx op-mcp` / a published Docker image), and
- **guarded by CI** (lint, types, coverage gate, hermetic integration tests) with **auto-generated,
  never-drifting docs**.

## 2. How to read this

Five workstreams (A–E). Work is sequenced into **waves** (§4) by dependency and risk, not by
workstream — because the "break things" refactors (Workstream A) are only safe *after* a test safety
net exists (Workstream B). Each workstream has a Definition of Done (§5) and a prioritized backlog
(§6). §7 lists the immediate next actions; §8 lists things we will deliberately **not** build.

## 3. Current-state scorecard

| Pillar | Grade | One-line assessment |
|---|---|---|
| **A. Architecture** | **D+** | Works and is better than the legacy monolith, but a 1,701-line god-object client, an **unenforced-auth security hole**, session-per-request, an import-time global (no DI), a split input-model convention, and 3.2k lines of dead shadow code. |
| **B. Testing & CI** | **D** | Good pockets of unit tests, but **no CI at all**, ~15–20% coverage (unmeasured), half the tests aren't even pytest-collected, and the only integration tests need a live instance + secrets. |
| **C. API coverage** | **B–** | Broad already (72 tools across most core domains), but missing the *correctness enablers* (WP schema/`form`/`available_*`, watchers) and high-value reads (queries, notifications). |
| **D. Distribution** | **F** | **Not installable** — no console entry point, `src` package layout, entrypoints not in the wheel, version 1.0.0-vs-2.0.0 split, root-running stdio Docker image, no publish, no tags. |
| **E. Documentation** | **D** | README exists but its tool catalog is materially wrong (claims 40, reality 71; a *phantom* documented tool; dead links); **no `LICENSE` file**; no contributor/architecture/changelog docs. |

**Cross-cutting root cause:** too much is **hand-maintained and has drifted** — the tool catalog, the
version string, `requirements.txt`, the docs. The highest-leverage theme across D and E is
**automation & single-source-of-truth**.

## 4. Guiding principles

1. **Safety net before the chainsaw.** Do not start the aggressive re-architecture until CI + a
   hermetic integration harness + characterization tests exist. You cannot "break a lot of things"
   responsibly without a net.
2. **Automate the drift away.** Single-source the version; auto-generate the tool catalog from the
   registered `@mcp.tool` set; tag-driven releases. Kill hand-maintained duplicates.
3. **One resource per PR** for API expansion (Workstream C) — small, independently testable, live-verified.
4. **Fork-divergence is explicit.** These are breaking changes aimed at *our* trunk, not upstream PRs.
   The narrow-upstream-PR discipline no longer applies to Workstreams A/B/D/E.
5. **Verify feasibility before promising.** Several API items (project archive, cost entries, meetings)
   need a live smoke before we commit estimates; wiki-content and story-points are **not in the API**.

## 5. Definitions of Done (per workstream)

- **A. Architecture:** `mypy --strict` + `ruff` clean; `client.py` split into per-domain gateways over
  one pooled transport; typed `Settings`/`SecretStr`; injected client (no import-time global); typed
  error taxonomy; no bare `except`; single input-model convention; legacy monolith deleted.
- **B. Testing:** one pytest suite; coverage measured with an enforced floor (→ 80% on `src/`, `client.py`
  & `formatting.py` prioritized); hermetic integration (testcontainers/CI service container); a few
  MCP-protocol e2e; all of it green in CI on every PR.
- **C. API coverage:** all P0 + P1 gaps shipped, each with unit + live-smoke; a published, honest
  "what's covered / what's intentionally not" matrix.
- **D. Distribution:** `uvx op-mcp` and `pipx install` work; one `--transport` CLI; multi-stage non-root
  image on GHCR; tag-driven PyPI (OIDC) + image publish; single-sourced version; CHANGELOG.
- **E. Documentation:** `LICENSE` shipped; auto-generated tool reference; mkdocs-material site
  (architecture, deploy, auth/security) on GH Pages; CONTRIBUTING; no dead links.

## 6. Workstream backlogs (prioritized)

### A. Architecture & code quality
| Pri | Initiative | Evidence / notes |
|---|---|---|
| **P0/Sec** | Fix the **auth hole**: enforce `APIKeyAuth` on the HTTP/SSE transports (FastMCP `auth=`/middleware) **or** remove `auth.py` and stop logging "API Keys loaded". Today it accepts all callers. | `openproject-mcp-http.py`, `src/auth.py` (zero call sites) |
| **P0** | **Correctness:** never default `lockVersion` to 0 after a *failed* fetch (5× bare `except:`); add 409-conflict retry to read-modify-write updates. Lost-update risk for concurrent edits. | `client.py:845,1014,1078,1102,1248`, `update_work_package` |
| **P0** | Delete the **3,213-line legacy monolith** and runtime-dead `as_model`; drop the `get_work_package_children` back-compat alias. | `openproject-mcp.legacy.py`, `utils/inputs.py:45`, `client.py:1164` |
| **P1** | **Pooled HTTP client:** one long-lived session (migrate to `httpx.AsyncClient`), collapse the 3 duplicated request bodies, add lifecycle/`aclose()`. Kills per-request TLS handshakes. | `client.py:82-88, 1496-1502, 1600-1606` |
| **P1** | **Typed config + DI:** `pydantic-settings` `Settings`, `SecretStr` for the key, injected client/context instead of the import-time global + `get_client()` service-locator (also unblocks unit testing). | `server.py:30-60` |
| **P1** | **Break up the god-object:** split 57 methods into per-domain resource gateways over a transport core; extract the 16× `_embedded` guard into `normalize_collection()`; move `_format_error_message` out of transport. | `client.py` (1,701 LOC / 57 methods) |
| **P1** | **Unify input models:** standardize on flat `Annotated` params for *all* tools (recommended, per the documented rationale) or convert `work_packages.py` back — pick one; delete `CoercibleModel` only after client-compat is re-verified. | `work_packages.py:16-20` vs 8 other modules |
| **P2** | **Service/domain layer:** move filter-JSON & payload/`_links` construction out of tools *and* client into `src/services/*`; tools become validate→call→format adapters. | filter-building smeared across tools + client |
| **P2** | **Exception taxonomy:** `OpenProjectError → Auth/NotFound/Conflict/Transport`, mapped from status once; typed responses (`TypedDict`/models) instead of `Dict`. | `client.py:121,129-146` |
| **P2** | Adopt **`ruff`** (replace flake8) + **`mypy --strict`**; fix metadata drift (version, author, `py38`→`py310`). | `pyproject.toml` |

### B. Testing & CI
| Pri | Initiative |
|---|---|
| **P0** | Stand up **GitHub Actions CI** (push/PR): ruff + black `--check` + mypy + `pytest` + coverage on a 3.10/3.11/3.12 matrix. Nothing is enforced today. |
| **P0** | Add **coverage measurement** (`pytest-cov`); publish the honest baseline; set a floor to stop backsliding. |
| **P0** | Fix dead static-analysis config (flake8 in `pyproject` is silently ignored; black `py38`); add **pre-commit**. |
| **P1** | **Migrate the 8 root `test_*.py` scripts into `tests/`** as real pytest (`assert`-based); delete manual PASS/FAIL harnesses & brittle count/docs assertions (`test_tools.py` currently always exits 0). |
| **P1** | **Unit-test `client.py`** — `_request()` retry/error-hints/auth/proxy/SSL + top methods (mocked aiohttp). Biggest untested surface. Backfill `formatting.py`, `report_formatter.py`, `weekly_reports.py`, `auth.py`, and the `format_error` path of every tool ("tools never raise" tripwire). |
| **P1** | **Hermetic integration tier:** testcontainers locally + a GH Actions **service-container** OpenProject; retarget the 3 existing smokes at the ephemeral URL; run nightly/on-label (`@pytest.mark.integration`). *(Note: the ephemeral-Docker harness currently exists only as throwaway scratchpad scripts — it is not in the repo.)* |
| **P2** | **Contract tests** with frozen OP HAL fixtures (WP, collection, the 422 `PropertyIsReadOnly` the code special-cases). A few **MCP-protocol e2e** via in-memory `fastmcp.Client`. Ratchet coverage → 80%. |

### C. OpenProject API coverage (one resource per PR)
| Pri | Gap | Value | Feasibility |
|---|---|---|---|
| **P0** | Register **`get_work_package`** tool (client method already exists; no tool wraps it — and the README documents it as if it exists). | High | Confirmed |
| **P0** | WP **`schema` / `form` / `available_*`** (assignees, watchers, statuses/transitions, versions, relation candidates) — the biggest enabler of *correct* agentic writes (stop guessing IDs). | High | Confirmed |
| **P0** | **Watchers** — list/add/remove on a WP. | High | Confirmed |
| **P1** | **Queries** (saved filters) list/get/execute · **Notifications** list + mark-read · **Custom-field discovery** via `/schemas` · **Categories** CRUD · **Versions** full CRUD (add get/update/delete) · comment **edit/delete**. | High | Confirmed |
| **P2** | **Groups + principals** search · project **copy/archive** · **custom actions** execute · **documents** read · **budgets** read · **users** admin CRUD · **views**. | Med | Copy/archive & cost = **verify** |
| **P3** | Boards/Grids · file links & storages · **meetings (verify — not in v3 index)** · config/help-texts. | Low | mixed |
| **—** | **Do NOT scope:** wiki page *content* (read-only metadata only) · **story points** (no first-class field; custom-field-only). | — | **Not-in-API** |

### D. Distribution & release
| Pri | Initiative |
|---|---|
| **P0** | **Make it installable:** rename to an importable package `openproject_mcp/`; add `[project.scripts]` `op-mcp = "openproject_mcp.cli:main"`; **collapse the 3 entrypoints into one CLI with `--transport {stdio,http,sse}`**. Unblocks `uvx op-mcp` + clean MCP config. |
| **P0** | **Single-source the version** (kill 1.0.0-vs-2.0.0); fill real authors + `[project.urls]`. |
| **P1** | **Rewrite the Dockerfile:** multi-stage `uv` build, pinned `python:3.12-slim`, non-root `USER`, **HTTP** CMD + `EXPOSE` + `HEALTHCHECK /health`, install from lockfile. |
| **P1** | **Release pipeline:** GH Actions on tag → build wheel → publish to **PyPI (OIDC/Trusted Publishing)** + push image to **GHCR**. |
| **P2** | Adopt **release-please / python-semantic-release** (Conventional Commits already in use) → auto tags + CHANGELOG; retire hand-maintained `requirements.txt` in favor of the lockfile. |

### E. Documentation
| Pri | Initiative |
|---|---|
| **P0** | Ship the **`LICENSE`** (+ `NOTICE`) — drafts ready in `licensing/`, **gated on the pending legal risk-memo sign-off** (`licensing/01-RISK-DECISION-memo.md`). The one gap that is a compliance blocker, not polish. |
| **P0** | **Auto-generate the tool catalog** from the registered `@mcp.tool` set — permanently fixes the undercount (40→71), ~15 undocumented tools, the *phantom* `get_work_package`, and the broken numbering. Repoint/remove the 4 dead README links + the upstream MseeP badge; fix stale `black openproject-mcp.py` commands. |
| **P2** | **mkdocs-material** site (architecture, deployment, auth/security, auto-generated tool + client reference) on GH Pages; add **CONTRIBUTING.md** (from the workflow) + auto-fed **CHANGELOG.md**. |
| **P3** | i18n structure (canonical English `docs/`, translations under `docs/vi/`). |

## 7. Sequenced plan (waves)

**Wave 0 — Stabilize the floor (fast; critical + safety net).**
CI scaffold + coverage baseline + ruff/mypy/pre-commit (B-P0); fix the **auth hole** and the
**lockVersion lost-update** risk (A-P0); delete the legacy monolith + dead code (A-P0);
single-source version + metadata (D-P0); ship **LICENSE** once the memo is signed (E-P0);
auto-generate the tool catalog + fix README links (E-P0); register **`get_work_package`** (C-P0).
*Exit criterion: every PR runs lint+types+tests+coverage in CI.*

**Wave 1 — Build the net wider, then re-architect (highest risk).**
First extend tests: hermetic integration harness + characterization tests of current behavior +
`client.py` unit coverage (B-P1). *Then*, behind that net: pooled `httpx` client, typed
settings/DI, split the god-object into gateways, unify input models, exception taxonomy (A-P1).
Migrate the root test scripts as you touch each module (B-P1).

**Wave 2 — Service layer & typing polish.**
`src/services/*`, typed responses, ruff/mypy-strict clean, contract + a few MCP e2e tests (A-P2, B-P2).

**Wave 3 — Distribution.**
`op-mcp` CLI + package rename, Dockerfile rewrite, PyPI+GHCR publish pipeline, semantic-release (D).

**Wave 4 — API expansion (continuous, value-ordered).**
C-P0 (schema/`available_*`, watchers) → C-P1 (queries, notifications, CF discovery, categories,
versions CRUD, comment edit/delete) → C-P2. One resource per PR, each unit-tested + live-smoked.

**Wave 5 — Docs site.**
mkdocs-material, CONTRIBUTING, CHANGELOG, i18n (E-P2/P3).

*Waves 3–5 can run partly in parallel with Wave 4 once Wave 2 lands.*

## 8. Explicitly out of scope (so we don't promise the impossible)
- **Wiki page content** write/read of body — OpenProject v3 exposes wiki as read-only metadata only (confirmed by prior spike).
- **Story points** as a first-class field — not exposed via API v3 (custom-field-only, if configured).
- **Meetings / boards / cost-entry write / project archive** — feasibility **unverified**; smoke-test against the live instance before scoping.

## 9. Housekeeping items already known (fold into the above)
- `report_formatter.py:66` `float("PT4H")` crash — same ISO-8601 duration bug as list-time-entries; reuse `_hours_to_float` (→ B-P1 backfill + a shared util).
- `pyproject.toml` `fastmcp>=2.0.0` is **uncapped** (main); should be `<3` like `requirements.txt` (→ A-P2 metadata / D).

---

### Suggested first 6 tickets (Wave 0)
1. `ci: add GitHub Actions (ruff+black+mypy+pytest+coverage, py3.10–3.12)`
2. `security(http): enforce APIKeyAuth on network transports (or remove the false advertisement)`
3. `fix(client): stop defaulting lockVersion to 0 on failed fetch; add 409 retry`
4. `chore: delete legacy monolith + dead as_model/auth; single-source version & metadata`
5. `feat(work_packages): register get_work_package tool`
6. `docs: auto-generate tool catalog; fix LICENSE/dead links` (LICENSE pending legal sign-off)

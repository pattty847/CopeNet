# Tool output audit

| tool | preview | renderable | body | shown | kept |
|---|---|---|---|---|---|
| `files.edit` | diff | ok | 503 | 88 | 18% |
| `files.read` | file_read | ok_by_sniffing | 577 | 225 | 39% |
| `files.rg` | repo_search | ok_by_sniffing | 4168 | 1038 | 25% |
| `files.write` | diff | ok | 515 | 88 | 17% |
| `market.backtest` | raw | ok | 22609 | 4000 | 18% |
| `market.compare` | raw | ok | 675 | 897 | 133% |
| `market.dashboard` | raw | ok | 31716 | 4000 | 13% |
| `market.evidence` | raw | ok | 25770 | 4000 | 16% |
| `market.financials` | raw | ok | 107143 | 4000 | 4% |
| `market.ticker` | raw | ok | 19439 | 3992 | 20% |
| `memory.read` | raw | ok | 293 | 313 | 107% |
| `memory.write` | raw | ok | 708 | 778 | 110% |
| `persona.author` | raw | ok | 319 | 371 | 116% |
| `plan.write` | plan | ok | 100 | 88 | 88% |
| `shell.exec` | raw | ok_by_sniffing | 373 | 47 | 13% |
| `user.remember` | raw | ok | 512 | 560 | 109% |
| `web.fetch` | raw | ok | 285 | 309 | 108% |
| `web.search` | web_search | ok | 1289 | 1287 | 100% |

## Renders only because the client guesses the shape

- `files.read` — backend sends no `type`; the client infers `file_read` from field names. Renaming a field breaks it silently.
- `files.rg` — backend sends no `type`; the client infers `repo_search` from field names. Renaming a field breaks it silently.
- `shell.exec` — backend sends no `type`; the client infers `raw` from field names. Renaming a field breaks it silently.

## Keeps less than half the body — worth a look, not automatically wrong

A low number is fine when the projection *is* the useful view: a diff is the point of `files.write`, and `shell.exec` deliberately keeps stdout and drops its metadata. It is a problem when the dropped part is the answer — which is what `market.compare` did when it kept only ticker symbols.

- `market.financials` — keeps 4% (4000 of 107143 chars)
- `market.dashboard` — keeps 13% (4000 of 31716 chars)
- `shell.exec` — keeps 13% (47 of 373 chars)
- `market.evidence` — keeps 16% (4000 of 25770 chars)
- `files.write` — keeps 17% (88 of 515 chars)
- `files.edit` — keeps 18% (88 of 503 chars)
- `market.backtest` — keeps 18% (4000 of 22609 chars)
- `market.ticker` — keeps 20% (3992 of 19439 chars)
- `files.rg` — keeps 25% (1038 of 4168 chars)
- `files.read` — keeps 39% (225 of 577 chars)

## What each tool shows

### `files.edit`

Edited file audit_probe.txt (1 replacement, +1/-1).

```
--- a/audit_probe.txt
+++ b/audit_probe.txt
@@ -1 +1 @@
-audit probe
+audit probe edited
```

### `files.read`

Read file README.md.

```
{"path": "README.md", "content": "# Audit workspace\n\nline 1\nline 2\nline 3\n\n\n[Read truncated at char 40 (~1KB). Use offset=40 to continue, or pass start_line/end_line to read by line.]", "startLine": 1, "totalLines": 8}
```

### `files.rg`

Found 189 matches for pattern via ripgrep; returning 20. [Showing matches 1-20. Total found: 189. Use offset=20 to continue.]

```
{"matches": [{"path": "~/Programming/CopeNet/src/copenet/core/tools/builtin_readonly.py", "line": 27, "text": "# from the manifest. artifact.create remains deferred. memory.* returned only", "column": 46}, {"path": "~/Programming/CopeNet/src/copenet/core/tools/builtin_readonly.py", "line": 90, "text": "    \"\"\"Built-in tool implementations used by the default regi
```

### `files.write`

Wrote file audit_probe.txt (+1/-1).

```
--- a/audit_probe.txt
+++ b/audit_probe.txt
@@ -1 +1 @@
-audit probe edited
+audit probe
```

### `market.backtest`

Backtest: AAPL, MSFT vs VOO completed. Portfolio Return: 25.03%

```
{
  "portfolioSeries": [
    {
      "date": "2024-01-02",
      "value": 100000.0
    },
    {
      "date": "2024-01-03",
      "value": 99589.24
    },
    {
      "date": "2024-01-04",
      "value": 98600.37
    },
    {
      "date": "2024-01-05",
      "value": 98378.12
    },
    {
      "date": "2024-01-08",
      "value": 100493.47
    },
    {
      "date": "2024-01-09",
      "value": 
```

### `market.compare`

Compared AAPL, MSFT

```
{
  "asOf": "2026-08-03T00:24:18.287814Z",
  "rows": [
    {
      "symbol": "AAPL",
      "name": "AAPL",
      "last": 308.91,
      "changePct": -7.24,
      "r1wPct": -7.2398,
      "r4wPct": 0.0907,
      "r13wPct": 10.3715,
      "r26wPct": 19.2708,
      "r52wPct": 53.2441,
      "rYtdPct": 19.3214,
      "vol13wPct": 33.1941,
      "drawdown52wPct": -7.4399,
      "rsi14": 62.0507,
      "
```

### `market.dashboard`

Market dashboard — regime: risk-off

```
{
  "asOf": "as of Sun 9:45AM ET market refresh",
  "briefing": {
    "status": "stale",
    "data": {
      "headline": "Risk-Off tape, with breadth at 0%.",
      "summary": "Computed facts show VIX at 16.0 and 46 recent SEC evidence item(s). This is an orientation read, not a forecast.",
      "changed": [
        {
          "text": "breadth -> 0%",
          "tone": "down"
        }
      ],

```

### `market.evidence`

AAPL SEC evidence: 15 items; 2 buys / 7 sells

```
{
  "symbol": "AAPL",
  "evidence": [
    {
      "type": "Insider",
      "symbol": "AAPL",
      "headline": "LEVINSON ARTHUR D (Director) sold 149,527 shares",
      "source": "SEC Form 4",
      "tone": "down",
      "url": "https://www.sec.gov/Archives/edgar/data/320193/000114036126020298/",
      "t": 1778025600,
      "value": 42550898.39,
      "price": 284.57,
      "shares": 149527.0
   
```

### `market.financials`

AAPL quarterly revenue: 72 point-in-time observations

```
{
  "symbol": "AAPL",
  "cik": "320193",
  "entityName": "Apple Inc.",
  "metric": "revenue",
  "label": "Revenue",
  "frequency": "quarterly",
  "basis": "canonical",
  "alignment": "availability",
  "asOf": null,
  "normalizationVersion": 3,
  "observations": [
    {
      "periodStart": "2008-03-30",
      "periodEnd": "2008-06-28",
      "availableAt": "2009-07-22",
      "value": 7464000000.0
```

### `market.ticker`

AAPL: $308.91 (-7.24%)

```
{
  "symbol": "AAPL",
  "name": "AAPL",
  "last": "$308.91",
  "change": "-7.24%",
  "tone": "down",
  "series": {
    "daily": [
      {
        "t": 1778025600,
        "o": 281.6605,
        "h": 287.7649,
        "l": 280.8113,
        "c": 287.2453,
        "v": 58336100
      },
      {
        "t": 1778112000,
        "o": 289.0037,
        "h": 291.8611,
        "l": 285.5169,
        "c":
```

### `memory.read`

Loaded 0 memory items.

```
{
  "items": [],
  "count": 0,
  "query": null,
  "category": null,
  "workspaceRoot": "/var/folders/ph/qy_xvqpn2197nshk2fn3jj7m0000gn/T/tmpwqsuv2he/workspace",
  "scope": "identity_memory",
  "accessAction": "read",
  "policyDecision": "allowed",
  "policySummary": "Memory is a user-visible continuity layer."
}
```

### `memory.write`

Proposed a memory draft: “Audit probe entry” — awaiting your approval.

```
{
  "item": {
    "id": "memory-041e2abd-861c-4bcd-9eb6-e00761cc6414",
    "category": "project_convention",
    "title": "Audit probe entry",
    "summary": "Audit probe entry",
    "detail": "Written by tool_output_audit.",
    "tags": [],
    "source": "model_proposed",
    "confidence": 0.7,
    "createdAt": "2026-08-03T00:24:19.961672+00:00",
    "updatedAt": "2026-08-03T00:24:19.961672+00:00
```

### `persona.author`

Authored persona 'Audit Probe' (1 file written).

```
{
  "persona": {
    "id": "audit-probe",
    "displayName": "Audit Probe",
    "active": false,
    "scope": "global",
    "fileCount": 6,
    "writtenFiles": [
      "core/SOUL.md"
    ]
  },
  "scope": "persona",
  "accessAction": "write",
  "policyDecision": "allowed",
  "policySummary": "Persona files are user-visible identity content, editable in Persona Home."
}
```

### `plan.write`

Plan: 0/1 done — now: Audit tool previews

```
{"type": "plan", "items": [{"content": "Audit tool previews", "status": "in_progress"}]}
```

### `shell.exec`

Ran full-access shell command.

```
{"preview": "$ ls\nREADME.md\naudit_probe.txt"}
```

### `user.remember`

Proposed a USER.md update to “preferences” — awaiting your approval.

```
{
  "proposal": {
    "id": "usernote-3f1a717d-6926-4572-a960-ffae3db870f4",
    "targetSection": "preferences",
    "summary": "Audit probe",
    "body": "Written by tool_output_audit.",
    "status": "draft",
    "createdAt": "2026-08-03T00:24:19.971356+00:00",
    "updatedAt": "2026-08-03T00:24:19.971356+00:00",
    "lastSessionKey": "tool-output-audit"
  },
  "scope": "operator_identity",
  "a
```

### `web.fetch`

Approval required: fetch 'example.com' is not on the trusted fetch allowlist

```
{
  "command": null,
  "target": "https://example.com",
  "policyDecision": "approval_required",
  "policySummary": "Barricade: 'example.com' is not on the fetch allowlist (extend it via COPNET_WEB_FETCH_ALLOWLIST).",
  "barricade": {
    "reason": "fetch_not_allowlisted",
    "hostname": "example.com"
  }
}
```

### `web.search`

3 web results for 'CopeNet agent harness' — top: The Complete Guide to Agent Harness: What It Is and Why It Matters

```
{"type": "web_search", "query": "CopeNet agent harness", "results": [{"title": "The Complete Guide to Agent Harness: What It Is and Why It Matters", "url": "https://harness-engineering.ai/blog/agent-harness-complete-guide/", "snippet": "The harness is moat.\" The gap between an agent that demos well and one that runs reliably in production is almost entirely a harness engineering problem. This gui
```

# CopeNet Research Lab V1

**Status:** Draft design outline for operator review

**Date:** 2026-07-21

**Product position:** Company understanding first; investment underwriting second

**Execution model:** Evidence-first, asynchronous Fleet investigation

## 1. Product thesis

Research Lab is a company-understanding workflow that can produce an investment-underwriting
conclusion. It is not a stock picker.

The workflow starts with a ticker or company name, builds a decision-grade evidence record,
uses two models for independent judgment and adversarial review, and saves a durable dossier.
Its central capital-allocation question is:

> Why should this company replace money that could remain in VOO, VTI, a sector ETF, or a
> stronger peer?

Research Lab succeeds when the operator understands the company substantially better. A valid
and useful conclusion is:

> Fascinating company. No compelling reason to own the stock.

Curiosity does not create an obligation to concentrate capital.

## 2. V1 goals

V1 must:

1. Explain how the company works before discussing valuation.
2. Separate reported facts, deterministic calculations, assumptions, and model interpretations.
3. Preserve a source-linked, immutable evidence snapshot for every completed investigation.
4. Give GPT and Claude the same factual substrate while preserving independent judgment.
5. Allow targeted source verification and structured requests for missing evidence.
6. Challenge the company against passive and peer alternatives.
7. Produce a saved, searchable dossier with a draft thesis the operator may approve later.
8. Run asynchronously and durably without requiring the operator to watch it.
9. Report missing, stale, or conflicting evidence honestly instead of filling gaps with prose.

## 3. V1 non-goals

V1 will not:

- rank or screen the market for stocks to buy;
- trade, size positions, or mutate brokerage accounts;
- produce a magic opportunity score;
- promise that a company will outperform over a fixed horizon;
- treat model output as the operator's approved thesis;
- continuously refresh old reports;
- automate post-earnings thesis updates;
- build a generalized workflow framework before this workflow proves useful;
- guarantee a 5–10 minute completion time.

Thesis timelines, earnings revisits, Market Monitor triggers, outcome calibration, and debate
history are future integrations, not V1 requirements.

## 4. Core product principles

### 4.1 Company understanding comes first

The investigation explains the business model, customers, segments, industry structure,
capital intensity, competitive position, and major dependencies before it evaluates the stock.

### 4.2 Display the executive summary first; generate it last

No early recommendation is allowed to anchor the research. Analysts complete the investigation,
cross-examination, and synthesis before the executive summary is produced.

### 4.3 Every claim has a type

Research Lab uses five explicit claim classes:

- **Reported fact:** directly supported by a primary or identified secondary source.
- **Calculated metric:** produced by deterministic code from recorded inputs.
- **Explicit assumption:** chosen for a scenario or valuation and never presented as fact.
- **Analyst interpretation:** model reasoning over identified evidence and assumptions.
- **Unresolved claim:** material but not adequately supported by the available evidence.

### 4.4 The benchmark is the control group

The workflow does not ask only whether the company is good. It asks whether the investment case
clears the incremental concentration, uncertainty, and valuation risk relative to doing nothing.

### 4.5 Missing stays missing

Conflicts are preserved, stale evidence is marked, and extraction warnings remain visible. The
system does not silently merge incompatible values or invent precision.

### 4.6 Slow is acceptable; invisible or irrecoverable is not

The run may take as long as its evidence requirements justify. It must checkpoint progress,
surface its current stage, support cancellation, survive process restarts, and never silently
duplicate a paid model turn.

## 5. Intake contract

### Required

- `query`: ticker symbol or company name.

### Optional

- `research_lens`: a question or hypothesis that shapes analyst attention without narrowing the
  evidence collected;
- `primary_benchmark`: operator override, normally VOO or VTI;
- `sector_benchmark`: operator override;
- `peer_benchmarks`: one or more operator-selected peers.

Examples:

- `UHAL`
- `UHAL` with lens `Why have margins weakened, and is the decline structural?`
- `GOOG` with lens `What conditions would need to hold for this to outperform XLK over ten years?`

Blank benchmark fields trigger deterministic candidate selection. The workflow records the
selected benchmarks and its selection rationale before evidence collection begins.

## 6. High-level architecture

```text
Intake
  -> company and benchmark resolution
  -> core evidence build
  -> deterministic evidence audit
  -> frozen evidence snapshot v1
  -> independent GPT and Claude analyst passes
  -> structured supplementary evidence requests
  -> shared evidence supplements and analyst updates
  -> reveal barrier
  -> cross-examination
  -> final synthesis
  -> executive summary generated last
  -> immutable dossier and proposed thesis draft
```

The factual substrate is shared. Judgment remains independent. Analysts may verify supplied
sources and request supplements, but they may not invisibly replace the corpus with private
browsing results.

## 7. Stage contracts

### Stage 1: Resolution

**Input:** intake record.

**Output:** canonical research subject and benchmark plan.

Resolution records:

- canonical company name;
- ticker and share class;
- exchange and currency;
- sector and industry;
- public-company identifiers when available;
- primary, sector, and peer benchmarks;
- benchmark-selection rationale;
- ambiguity warnings.

If company identity remains ambiguous, the run pauses for operator resolution rather than
researching the wrong security.

### Stage 2: Evidence Builder

**Input:** resolved subject and benchmark plan.

**Output:** versioned core evidence corpus.

The builder gathers, when available:

- SEC filings and material filing events;
- financial statements and normalized financial history;
- business segments and geography;
- earnings releases, presentations, and guidance;
- split-adjusted market data;
- valuation inputs;
- insider activity with transaction classes kept distinct;
- peer and benchmark data;
- relevant industry and regulatory sources;
- source metadata and extraction warnings.

Collection is tool- and code-led. A model may assist with document interpretation, but it does
not become the unrecorded source of facts.

### Stage 3: Evidence Audit

**Input:** core evidence corpus.

**Output:** audit findings and a frozen evidence snapshot.

Deterministic checks include:

- statement relationships reconcile where the source permits;
- reporting periods and currencies align;
- split-adjusted OHLCV remains consistent with the Market Monitor invariant;
- duplicate observations are linked rather than double-counted;
- conflicting values are preserved and classified;
- stale sources are flagged;
- missing fields remain explicit;
- derived values can be reproduced from stored inputs;
- every material item has source and retrieval metadata.

Audit failures do not automatically kill a run. Material failures either pause the run for a
retry/operator decision or flow forward as visible limitations, depending on severity.

### Stage 4: Independent Analyst Pass

**Input:** identical frozen snapshot for both Fleet participants, plus the optional lens.

**Output:** two private analyst memoranda and structured evidence requests.

Each analyst independently covers:

- company and business-model understanding;
- products, customers, suppliers, segments, and geography;
- industry structure and competitive position;
- business quality, moat, switching costs, and capital intensity;
- recent developments;
- financial health and capital allocation;
- valuation assumptions and scenarios;
- strongest bull case;
- strongest bear case;
- benchmark hurdle;
- material unknowns;
- evidence accepted, challenged, or requested.

Neither analyst sees the other's memorandum before the reveal barrier.

### Stage 5: Supplementary Evidence

**Input:** structured analyst requests.

**Output:** shared, versioned supplements or explicit unavailable results.

An evidence request contains:

```json
{
  "claim": "Storage occupancy is improving",
  "reason": "The latest filing gives only year-end occupancy",
  "requestedSourceType": "latest earnings release or supplemental",
  "materiality": "high",
  "wouldChange": "business momentum assessment"
}
```

The coordinator deduplicates compatible requests. The Evidence Builder performs retrieval and
appends a supplement visible to both analysts. Both analysts may amend their private memorandum
after receiving it.

An analyst may independently open a linked source to verify a quoted number or inspect context.
That check is recorded as source verification. Broad untracked browsing and private replacement
of core evidence are prohibited.

V1 uses a bounded supplement loop: one coordinated request round by default, with one additional
round only when a high-materiality conflict remains. This prevents an unbounded research loop
while allowing rigorous follow-up.

### Stage 6: Reveal and Cross-Examination

**Input:** finalized private memoranda and shared evidence corpus.

**Output:** attributed challenges and responses.

After both memoranda commit, the reveal barrier opens. Each analyst must challenge the other on:

- missing evidence;
- weak or hidden assumptions;
- overconfidence;
- alternative interpretations;
- valuation logic;
- benchmark selection and hurdle logic;
- unresolved contradictions.

Cross-examination is evidence-addressable: challenges reference claim and evidence identifiers,
not only prose quotations. V1 uses one challenge-and-response round per analyst.

### Stage 7: Synthesis

**Input:** evidence corpus, both memoranda, and cross-examination.

**Output:** final dossier content.

Synthesis records:

- areas of agreement;
- areas of disagreement;
- unresolved questions;
- company-understanding conclusion;
- benchmark-hurdle conclusion;
- conclusion-changing events;
- proposed thesis and kill criteria;
- separate confidence levels for understanding and investment conclusion.

The synthesizer cannot erase disagreements or convert an unresolved claim into a fact. The
executive summary is generated only after this stage is complete.

### Stage 8: Persisted Dossier

**Input:** all run outputs.

**Output:** immutable, searchable Research Lab dossier.

The dossier stores the evidence snapshot identifier, all supplements, calculation records,
model/runtime identities, prompt/protocol version, analyst memoranda, cross-examination, final
report, audit limitations, and proposed thesis draft.

## 8. Evidence model

### 8.1 Evidence item

Each evidence item records at minimum:

- stable `evidence_id`;
- subject/company identifier;
- source title and source type;
- source URL, accession number, or equivalent source identifier;
- publisher or filing entity;
- retrieval timestamp;
- publication/filing date;
- reporting period;
- raw value or bounded excerpt reference;
- normalized value and unit when applicable;
- reported/calculated/estimated classification;
- freshness status;
- extraction method;
- extraction warnings;
- snapshot version.

Primary sources are preferred. Secondary sources must be labeled and must not silently override
primary filings.

### 8.2 Claim record

Every material report claim records:

- stable `claim_id`;
- exact claim text;
- claim class;
- supporting and contradicting evidence identifiers;
- analyst or deterministic producer;
- confidence;
- freshness;
- unresolved limitations.

### 8.3 Calculation record

Every derived financial or valuation result records:

- stable `calculation_id`;
- formula name and version;
- exact formula or deterministic implementation identifier;
- input values and units;
- source or assumption identifier for every input;
- output value and unit;
- calculation timestamp;
- warnings.

Models may select, challenge, and explain assumptions. Deterministic code computes CAGR, margins,
dilution, free cash flow, enterprise value, normalized earnings, DCF/reverse DCF, sensitivity
tables, benchmark hurdles, and scenario outcomes.

### 8.4 Conflict record

Conflicting observations remain separate and are joined by a conflict record containing the
competing evidence identifiers, likely reason, materiality, and resolution status.

## 9. Benchmark hurdle contract

The benchmark challenge is a transparent assessment, not a score. It asks:

- Why not keep the capital in VOO or VTI?
- Why not use the sector ETF?
- Why not own a stronger or more diversified peer?
- What concentration and company-specific risk is introduced?
- What operational and valuation assumptions are required for plausible outperformance?
- How strong is the evidence supporting those assumptions?
- What excess-return hurdle is being assumed, and why?

The dossier includes a table shaped like:

| Dimension | Company | Benchmark | Status | Evidence/assumption |
|---|---|---|---|---|
| Diversification | Concentrated | Broad | Benchmark advantage | Reported structure |
| Expected growth | Scenario range | Market baseline | Unresolved | Explicit assumptions |
| Valuation risk | Assessed range | Distributed | Company/benchmark advantage | Calculated |
| Business quality | Analyst assessment | Aggregate | Company/benchmark advantage | Evidence-linked interpretation |
| Required excess return | Explicit hurdle | Control | Must be justified | Calculation record |
| Hurdle conclusion | Cleared / not cleared / unresolved | Default | Analyst conclusion | Claim record |

The workflow states what must occur for plausible outperformance. It does not present a long-term
forecast as an established fact.

## 10. Dossier structure

The final report is displayed in this order:

1. Executive summary, generated last.
2. Company identity and investigation scope.
3. How the business works.
4. Products, segments, customers, suppliers, and geography.
5. Industry structure and competition.
6. Recent developments.
7. Financial health and capital allocation.
8. Valuation and scenario analysis.
9. Strongest bull case.
10. Strongest bear case.
11. Fleet cross-examination.
12. Benchmark hurdle.
13. Material unknowns.
14. Proposed thesis and kill criteria.
15. Final conclusion and confidence.
16. Evidence and calculation appendix.

Every factual table includes its reporting period and source. Row-level sources are required when
rows come from different origins; one table-level source is allowed only when the entire table is
derived from one clearly identified dataset.

## 11. Conclusion language

V1 uses these conclusions:

- **Benchmark hurdle cleared**
- **Merits continued observation**
- **Promising, but unresolved**
- **Interesting business — weak investment case**
- **Evidence insufficient**
- **Pass**

The report separately states:

- `company_understanding_confidence`: high, medium, or low;
- `investment_conclusion_confidence`: high, medium, or low.

These values may differ substantially. They are evidence sufficiency judgments, not statistical
probabilities.

## 12. Proposed thesis and kill criteria

The workflow produces a proposed thesis containing:

- bull conditions;
- bear conditions;
- key assumptions;
- observable milestones;
- kill criteria;
- evidence that would change the conclusion.

It remains model-authored draft content inside the dossier. It does not enter the operator's
durable thesis ledger until the operator explicitly approves or edits it. Thesis-ledger storage
and automated monitoring are outside V1 unless required merely to preserve that approval boundary.

## 13. Durable run state

A Research Lab run is a first-class durable workflow record, not one long HTTP or WebSocket
request. It records:

- `run_id` and research subject;
- intake and resolution output;
- current stage and stage attempt;
- evidence snapshot and supplement versions;
- participant model/runtime identities;
- committed outputs for each stage;
- queued evidence requests;
- error and retry history;
- cancellation state;
- created, updated, and completed timestamps;
- protocol and prompt versions.

Suggested stage states:

```text
queued
resolving
building_evidence
auditing_evidence
analyzing_independently
collecting_supplements
awaiting_reveal
cross_examining
synthesizing
persisting
completed
completed_with_limitations
paused_for_operator
failed
cancelled
```

Each paid or side-effecting stage uses an idempotency key. After a restart, the coordinator reads
the last committed stage output and resumes from the next safe boundary. It never assumes an
interrupted provider call can be silently replayed; ambiguous attempts require an explicit retry
record.

The operator may close the app. Reconnect reads durable state and continues showing progress.

## 14. Failure and limitation behavior

- Ambiguous company identity pauses before evidence collection.
- A temporarily unavailable source is retried within a bounded policy, then recorded as missing.
- A failed analyst lane does not fabricate a two-model consensus. The run pauses for retry or may
  complete with an explicit single-analyst limitation after operator approval.
- Conflicting financial values remain visible until resolved.
- Missing evidence lowers the relevant confidence and may force `Evidence insufficient`.
- Cancellation stops scheduling new work; already committed evidence and outputs remain available.
- Partial runs are retained for diagnosis and possible continuation.
- No stage may claim completion without a committed, inspectable output record.

## 15. Minimum V1 UI

Research Lab lives as a dedicated Workflows workbench, not a disguised chat window.

### Hub card

- Research Lab title and purpose;
- start-new-investigation action;
- recent investigation status;
- completed dossier count.

### Intake

- ticker/company field;
- optional research-lens field;
- collapsible benchmark overrides;
- selected benchmark preview and rationale after resolution;
- start action.

### Active run

- company identity;
- durable stage timeline;
- GPT and Claude lane status without exposing private pre-reveal reasoning;
- current evidence counts, conflicts, and missing-source warnings;
- elapsed time without an unreliable completion estimate;
- cancel and safe retry actions;
- clear indication that the operator may leave.

### Completed dossier

- executive summary and conclusion;
- section navigation;
- visible claim-type badges;
- expandable evidence and calculation receipts;
- Fleet agreement/disagreement view;
- benchmark hurdle table;
- unresolved questions;
- proposed thesis with future approve/edit affordance clearly distinguished from operator-owned
  memory;
- immutable snapshot metadata.

### Investigation library

V1 includes a basic searchable list by company, ticker, date, conclusion, and run status. Rich
thesis timelines and automated comparisons between report versions are deferred.

## 16. Integration boundaries

- Business logic and durable workflow coordination belong under `src/copenet/core/`.
- Provider adapters remain thin; Research Lab protocol does not live in provider code.
- Existing Market tools and SEC evidence paths should be reused through explicit contracts.
- All OHLCV collection preserves the existing split-adjusted invariant.
- Fleet's independent-first reveal barrier remains authoritative for analyst isolation.
- Workflow RPCs expose normalized internal DTOs; validation occurs at RPC/provider/source trust
  boundaries rather than being repeated through the internal flow.
- The React Workflows surface consumes real workflow state and does not infer stage completion from
  streamed prose.

Exact module and RPC names belong in the implementation plan after this design is approved.

## 17. Verification strategy

### Deterministic evidence tests

- company/share-class resolution and ambiguity handling;
- source metadata completeness;
- period and currency alignment;
- conflict preservation;
- missing-value behavior;
- split-adjusted price integrity;
- reproducible calculation outputs;
- benchmark-selection defaults and overrides.

### Coordinator tests

- identical core snapshot delivered to both analysts;
- no peer memorandum visible before reveal;
- structured evidence requests are deduplicated and shared;
- bounded supplement rounds;
- restart resumes from the last committed boundary;
- ambiguous provider attempts are not silently rerun;
- failed lane cannot become false consensus;
- cancellation stops new scheduling while preserving prior outputs.

### Report contract tests

- executive summary generated after synthesis;
- all material claims carry claim class and evidence references;
- calculations carry formula and input provenance;
- disagreements and unresolved claims survive synthesis;
- every factual table contains the required source scope;
- proposed thesis remains unapproved by default;
- conclusion and both confidence fields are present.

### End-to-end acceptance scenario

Run a clean UHAL investigation with and without a research lens. Verify that both analysts receive
the same frozen corpus, at least one structured supplement can be fulfilled, cross-examination
occurs only after reveal, the benchmark challenge compares against selected controls, and a saved
dossier remains readable after server restart.

## 18. V1 completion criteria

V1 is complete when an operator can:

1. Enter a ticker or company and optionally provide a lens or benchmark overrides.
2. Leave the app while the investigation continues durably.
3. Return to an honest stage history and either a completed dossier or an actionable limitation.
4. Trace every material factual claim and calculation to recorded evidence or assumptions.
5. See two independent analyses, their cross-examination, and preserved disagreements.
6. Understand the company without being pushed toward owning it.
7. See whether the investment case cleared a transparent benchmark hurdle.
8. Save the dossier and distinguish its proposed thesis from operator-approved belief.

## 19. Deferred roadmap

After V1 proves repeat use:

1. Operator approval/edit flow for the durable thesis ledger.
2. Market Monitor and earnings-event handoff into Research Lab.
3. Evidence-delta revisits against prior snapshots.
4. Thesis and kill-criteria monitoring.
5. Versioned thesis timeline.
6. Fleet debate replay and model-change history.
7. Outcome calibration for model conclusions and operator decisions.
8. Scheduled or event-driven refreshes with explicit cost and source policies.

These features should build on saved V1 dossiers rather than expanding V1 before its core loop is
useful.

## 20. Chosen defaults for implementation planning

- One-click asynchronous workflow, not stage-by-stage operator steering.
- Ticker/company required; research lens optional.
- Benchmark overrides optional; deterministic selection with recorded rationale is the default.
- Shared frozen evidence corpus plus independent model judgment.
- Selective source integrity checks and structured supplementary requests.
- One normal supplement round and one exceptional high-materiality round.
- One cross-examination challenge-and-response round per analyst.
- Executive summary generated last.
- Deterministic valuation math with explicit assumptions.
- Transparent benchmark hurdle, never a composite opportunity score.
- Immutable saved dossier.
- Proposed thesis remains model-authored until explicitly approved by the operator.

# Pat Profile v1 — Frontend Contract

**Status:** Frontend shell built. Backend RPC not yet shipped.  
**Frontend lane lead:** Claude  
**Backend owner:** Codex

---

## What the frontend has built

All surfaces are typed, honest, and operational. They render correct empty states until the backend pushes real data. Nothing is faked in the production operator flow — only the dev-mode skeleton trigger (clearly labeled, easily stripped).

### Files created (frontend lane)

| File | Purpose |
|---|---|
| `src/components/profile/ProfileStatusCard.tsx` | Compact operator surface — profile active, top priority, recent changes, changelog count |
| `src/components/profile/ReturnBriefing.tsx` | 4-section "I'm back" re-entry shell |
| `src/components/profile/ProfileChangelog.tsx` | Receipt-style timeline of profile mutations |
| `src/components/HomePage.tsx` | Integrated ProfileStatusCard (right rail) + ReturnBriefing (above hero) |
| `src/components/RightPanel.tsx` | Section 7 in Runtime tab: subtle profile indicator |
| `src/runtime/types.ts` | Re-exports all Pat Profile + briefing types |
| `src/types/backend.ts` | Source of truth for wire types (see below) |
| `src/store/useAppStore.ts` | `patProfile`, `returnBriefing`, `profileChangelog` slices |
| `src/runtime/adapter.ts` | `usePatProfile`, `useReturnBriefing`, `useProfileChangelog` hooks |

---

## Wire types — what the backend must provide

All source types in `src/copenet/host/frontend/src/types/backend.ts`.

### `PatProfile`

```typescript
interface PatProfile {
  profileId: string;
  displayName: string;         // e.g. "Patrick Cope"
  active: boolean;
  source: PatProfileSource;    // 'explicit' | 'inferred' | 'session_observation'
  priorities: PatProfilePriority[];
  goals: PatProfileGoal[];
  tonePreference: PatProfileTonePreference;
  noiseFilters: string[];
  lastUpdatedAt: string;       // ISO
  changelogCount: number;      // total entries ever written to changelog
}
```

### `ProfileChangelogItem`

```typescript
interface ProfileChangelogItem {
  id: string;
  kind: ProfileChangelogChangeKind;
  summary: string;
  detail?: string | null;
  source: PatProfileSource;
  rationale?: string | null;
  triggeredBySessionKey?: string | null;
  changedAt: string;           // ISO
}
```

### `ReturnBriefingPayload`

```typescript
interface ReturnBriefingPayload {
  briefingId: string;
  generatedAt: string;
  attentionItems: BriefingAttentionItem[];
  activityItems: BriefingActivityItem[];
  watchItems: BriefingWatchItem[];
  noticeText: string | null;
  noticeSource?: string | null;
}
```

See `backend.ts` for the full sub-type definitions.

---

## Expected backend RPCs / push events

| Event / RPC | Payload | Triggers |
|---|---|---|
| `profile:loaded` push event | `PatProfile` | Store: `setPatProfile(profile)` |
| `profile:changed` push event | `ProfileChangelogItem` | Store: `prependProfileChangelogItem(item)` |
| `profile:changelog:loaded` push event | `ProfileChangelogItem[]` | Store: `setProfileChangelog(changelog)` |
| `briefing:ready` push event | `ReturnBriefingPayload` | Store: `setReturnBriefing(payload)` |
| `briefing:dismissed` (optional RPC) | `{ briefingId }` | Backend acknowledges dismiss |

**Note:** The frontend does not yet wire any of these events in `wsClient.ts`. That is the backend integration step — Codex should add the event handlers in `wsClient.ts` when the backend pushes these events.

---

## Dev trigger (remove when backend ships)

`HomePage.tsx` includes a clearly labeled "Dev — Preview briefing" trigger that seeds `DEV_SKELETON_FOR_TEST` into the return briefing store. This:
- Is only visible on desktop
- Disappears once a real briefing is in the store
- Uses a const exported from `ReturnBriefing.tsx` for the skeleton data
- Has zero effect on production operator flow

**Strip list when backend ships:**
1. Remove `DEV_SKELETON_FOR_TEST` export from `ReturnBriefing.tsx`
2. Remove the dev trigger block in `HomePage.tsx`
3. Remove `devMode` prop from `ReturnBriefing` if unused

---

## Taste constraints (per Codex spec)

- Profile surfaces: sparse, high-signal, operator system surface — not consumer settings
- Briefing: re-entry ritual feel, not dashboard widget dump
- Agents right-rail profile indicator: tiny and honest — single line, no card explosion
- Empty states are explicit: "No profile overlay yet" / "No profile changes yet"
- No phantom data — hooks return real store state only

---

## Merge notes

- `useAppStore.ts` — new slices appended at the end; no existing slices reorganized
- `RightPanel.tsx` — section 7 appended after section 6 in runtime tab; no other layout changes
- `HomePage.tsx` — profile surfaces added in right rail and above hero; existing layout untouched
- `adapter.ts` — new hooks added before `useInboxItems`; no existing hooks modified

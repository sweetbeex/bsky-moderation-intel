Notification hub tab badges do not narrow with the person search

## What happens

The segmented control's per-tab badge reads `counts[t.key]` and renders whenever
it is greater than zero (`src/routes/notification-hub/+page.svelte:3285`). That
badge sits in the same toolbar as the "Filter by person" search box, and the
control stays on screen while the search is open (`:3647`).

`counts` is computed in `deriveHubView` before any filtering is applied:

```ts
// src/routes/notification-hub/hub-view.ts:246-261
counts.all = groups.length + inAppEntries.length;
for (const g of groups) {
  for (const t of tabs) {
    if (t.key === 'collabs') continue;
    if (t.reasons && t.reasons.includes(g.reason)) counts[t.key] += 1;
  }
  ...
}
```

The search is applied much later, to `listEntries`, at `:324-331`, after the
conversation/reaction lanes are built. So `counts` never sees the query.

Meanwhile the render blocks and the keyboard walk both read `flatOrder`, which is
derived from `searchFiltered`. Two answers to the same question: "how many rows
are in this tab?"

## Reproduce

Measured against `dev/bee` at `e32a26bd2` by driving `deriveHubView` with three
mention rows and reading `counts.mentions` against `flatOrder.length`:

- `searchQuery: ''` -> badge 3, rows 3
- `searchQuery: 'zed'` (matches 1 of 3) -> badge **3**, rows **1**
- `searchQuery: 'zzzznomatch'` -> badge **3**, rows **0**

The last case is the clearest: the creator types a name that matches nobody, the
list correctly says `No one matching "..." in this filter.` (`:4686`), and the
badge beside it still reads 3.

## Why this is the one worth fixing

Every other filter stays consistent, because the badge and the rows are hidden
together or because the count is recomputed against the filtered set:

- `dismissed`, `hideInteracted`, `awaitingOnly` measured drift **0** in the same
  probe, because `displayed`/`flatOrder` already exclude them and the badge is
  only shown on the unfiltered default view in practice.
- `hideViaRepost` and `hideInteracted` get dedicated `*Hidden` deltas computed
  from the same pipeline with one filter relaxed (`:299-306`), so those numbers
  cannot drift by construction.

Search is the only filter with no such coupling, and it is the only one that
leaves a visibly wrong number next to an empty list.

## Suggested fix

Count from the same array the blocks render, so there is one answer:

```ts
const visibleKeys = new Set(searchFiltered.map(r => r.key));
// ...then add per-tab counts only for groups whose key is in visibleKeys
```

and drop the separate pre-filter accumulation, or move the search above the count
so the count is computed on the filtered set. Either way the badge and the rows
should read from one list.

## Notes

- Verified on `dev/bee` `e32a26bd2`. `hub-view.ts` is where PR #6848 moved this
  logic; #6848 was closed unmerged, and the canonical-selector refactor it was
  trying to land never happened. The `counts` vs `flatOrder` split it set out to
  close is still here.
- The existing suite asserts `counts` only in unfiltered states
  (`hub-view.test.ts:306, 321-324, 342, 390`), which is why this survived.
- The in-app lane also contributes to `counts.all` but has no per-tab badge
  contribution, so the "All" tab can credit rows no tab shows.
- Not a crash and not data loss: the badge is informational. But it is the
  number a creator uses to decide whether to switch tabs, and it is wrong exactly
  when the list is empty.
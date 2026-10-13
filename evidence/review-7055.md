## Regression risk + test coverage review

Verdict: **REQUEST_CHANGES**

Base: `dev/bee` @ `e32a26bd2`. Head: `c3c9d9e9b`. Three blocking findings, two of them
about irreversible deletions. The daily trigger and job wiring are correct; the
problem is what the new trigger now reaches.

---

### B1 (blocking) - this PR removes the only guard that made an empty rule inert

`matchesCriteria` returning `true` for an empty criteria set is correct on its
own and is already merged (#6932). The exposure is that this PR removes the
guard that used to keep that state unreachable in practice.

Removed in this PR, `src/routes/api/cleanup/autodelete/preview/+server.ts:121-127`:

```ts
const activeCriteria = Object.values(rule.criteria).filter(Boolean);
if (activeCriteria.length === 0) {
  return json({ error: 'No criteria selected. Enable at least one criterion to preview.' }, { status: 400 });
}
```

Before this PR an empty rule was inert twice over: the preview refused to run, and
nothing invoked the sweep (verified: `dev/bee`'s `job-queue.ts` has zero
references to the new queue). This PR adds the nightly trigger, so the second
protection disappears exactly when the first one does.

Now: `hasConfiguredCriterion({})` is `false` (`autodelete-scanner.ts:165-169`),
`matchesCriteria(popularPost, {}, 'all')` is `true` (`:232`), and the sweep
enqueues every post past `min_age_days`. Measured with the real scanner:

```
matchesCriteria({}, all)                    = true
matchesCriteria({hashtags: []}, all)        = false   <- deliberate no-match, intact
age-only matched 3 of 3 posts
```

and end to end through `runAutodeleteDailySweep`, a rule persisted with
`criteria: {}` and `min_age_days: 90` queues all 3 of its matching posts for
`cleanup.delete-posts`.

Nothing on the save path rejects an empty criteria set. `POST
/api/cleanup/autodelete` (`+server.ts:158`) does
`const criteria = parseCriteria(body.criteria)` and inserts it; the only gate is a
delete-scope check, which a rule with nothing ticked passes trivially.

This is the intersection that matters: the deletes run unattended on the
creator's token with no user present.

**Needed:** either restore a server-side guard on save (reject an empty criteria
set when `enabled` is true, or coerce it to disabled), or require an explicit
`age_only: true` flag rather than inferring intent from an empty object. An
explicit opt-in is better than a heuristic, because "no criteria" and "delete
everything past 90 days" are the same bytes on the wire today.

---

### B2 (blocking) - `last_run_deleted` is hardcoded to 0, so the tab and the operator summary always say nothing was deleted

`src/lib/server/autodelete-daily-sweep.ts:149-159`:

```ts
const deleted = 0;
execute(`UPDATE autodelete_rules SET last_run_at = NOW(), last_run_deleted = $2 WHERE user_did = $1`, [did, deleted])
```

The scan found `uris.length` posts and queued them, then the rule is stamped with
zero. Measured:

```
queued: 4  reported: 0
last_run_deleted written as: 0
```

This carries over from the old schedule endpoint (`dev/bee`'s
`schedule/+server.ts:151` has the same `const deleted = 0`), so it is pre-existing,
but it becomes materially worse here: before, the endpoint was never called, so the
number nobody read was always zero. Now it runs daily and it is the only signal a
creator or operator has.

**Needed:** report `uris.length` (or the job's actual result) into
`last_run_deleted` and `totalDeleted`. If the intent is "deleted means confirmed by
the worker", then say so in the column or the UI, because right now the Automation
tab reads as "ran, deleted nothing" on a run that queued four posts.

---

### B3 (blocking) - a failed rule is never stamped, so its "last ran" goes stale while the docstring promises otherwise

Same file, docstring at `:86-89`:

> One creator's failure never stops the rest, and `last_run_at` is stamped either
> way so the Automation tab can show a truthful "last ran" even when nothing
> matched.

The `catch` at `:167-171` pushes `{ did, deleted: 0, error }` and continues. The
`last_run_at` write is inside the `try`, after the scan, so a creator whose scan
throws gets no stamp at all. Measured:

```
last_run_at writes on failure: 0
```

So the tab shows the last *successful* run, indefinitely, for a creator whose sweep
has been failing daily. The docstring asserts the opposite. Either move the stamp
into the `finally` (or the loop tail) so failures also advance it, or correct the
comment and surface the failure in the UI.

---

### What is done well

- **Job wiring is right.** `initAutodeleteDailySweepHandler()` is called from
  `job-queue.ts:487-488` at the same module scope as the sibling jobs
  (`:510` session-cleanup, `:624` churn-sweep), not buried inside an init function.
- **The advisory lock is correct and documented.** Key `8472634908`, checked
  against the enumerated set of existing keys, with `localConcurrency: 1` and a
  `finally` release. At most one sweep runs cluster-wide.
- **Cron slot is clear of existing windows** (`37 3 * * *` vs the 02:30-06:30 list),
  with the reasoning in the file.
- **Schedule idempotency** relies on pg-boss upserting by queue name per boot,
  which matches the sibling jobs' pattern.
- **`like_floor` is threaded through correctly.** `row.like_floor ?? 0` reaches
  the scanner, and `isProtectedByLikeFloor` (`autodelete-scanner.ts:411-417`) is
  applied *after* the criteria match, so a protected post is never queued. The
  settings endpoint also writes the `like_floor` column now rather than only the
  legacy pair, which is what had been silently disabling the protection on every
  save.
- **Criteria parser is a genuine improvement.** `parseAutodeleteCriteria` keeps
  `engagement_floor`, `engagement_ceiling` and `hashtags` (lowercased, filtered),
  which the old parser in the schedule endpoint had been dropping, and it still
  refuses to accept a `like_floor` smuggled into the criteria blob (verified:
  `parseAutodeleteCriteria({ like_floor: '999' })` -> `{}`).
- **Tier gate for `has_nsfw_label`** is checked per rule before scanning, and
  degrades to skip rather than delete when the tier lookup fails.
- **One creator's failure cannot stop the sweep**, and the shared-module split
  (`autodelete-daily-sweep.ts` vs the pg-boss wrapper) means the operator endpoint
  and the scheduled job cannot drift.

### Test coverage

`autodelete-daily-sweep.test.ts` (+251) and `jobs/autodelete-daily-sweep.test.ts`
(+109) cover the sweep loop, the empty-ruleset short circuit, the nsfw tier skip,
per-creator error isolation, the advisory lock, and the cron expression. That is
good structure.

The gap is that no test asserts a *number that reaches a human*. Specifically
uncovered, and each of these would have caught a finding above:

- `last_run_deleted` / `totalDeleted` when the scan returns matches (B2)
- `last_run_at` on the error path (B3)
- the interaction of an empty criteria set with the delete queue (B1)

Note that B1 is not reachable by unit-testing `matchesCriteria` in isolation,
because that behaviour is correct. It is only visible when you compose it with the
removal of the save/preview guard and the addition of the trigger, which is
precisely the kind of thing a test per file will not catch.

---

### Reproduction used

Probes were written against a clean worktree at `origin/fix/autodelete-daily-trigger`
with `node_modules` linked from the main checkout, run with `npx vitest run`, then
deleted. Nothing was committed and no branch was pushed; the worktree is removed.
The probe files are `/tmp/zz-probe-7055.test.ts` (mocked sweep) and
`/tmp/zz-probe-b41.test.ts` (real scanner).
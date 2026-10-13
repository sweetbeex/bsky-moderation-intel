Intake promo reopen has no test for the 409 guard against an unrecognised status

## The gap

`POST /api/internal/intake/handle` guards its promo reopen with:

```ts
if (!isDone) {
  return json({ error: `Cannot reopen from status '${existing.status}'` }, { status: 409 });
}
```

where `isDone` is `PROMO_DONE_STATUSES = ['reviewed', 'used', 'declined']`.

The endpoint's contract tests cover the pending -> reviewed write, the reopen of a
`reviewed` row, the no-op reopen of an already-`pending` row, and the guard
against overwriting a `declined` row. None of them exercises the 409 itself.
Deleting the `if (!isDone)` branch outright leaves all 16 tests green on
`dev/bee` at `e32a26bd2` (verified by mutation).

## Why the branch is load-bearing

`promo_submissions.status` is `TEXT NOT NULL DEFAULT 'pending'` with no CHECK
constraint (`src/lib/server/schema/postgres-schema.sql:291`), so the database
does not constrain the vocabulary. And the admin UI's own setter is untyped:

```ts
async function updatePromoStatus(id: string, status: string)
```

driven by a `<select>` whose options are `reviewed` / `used` / `declined`, plus
a "Reset" button that writes `pending` (`src/routes/admin/+page.svelte:407-409`,
`:1039`). Any other value that has ever been written to the column (a partial
backfill, a script, a future option) is a status where "an admin acted" is
unknown, and the guard is exactly what stops a reopen from silently overwriting
it with `pending`.

Without the guard, a second tap on such a row rewrites it to `pending` and
returns `200 ok:true` rather than a 409, so the queue state changes on a tap that
the API said was not allowed.

## Suggested test

One case in `src/routes/api/internal/intake/handle/server.test.ts`:

```ts
it('refuses to reopen from a status that does not mean an admin acted', async () => {
  queryOne.mockResolvedValue({ id: PROMO_ID, status: 'migrated_2024' });

  const res = await POST({
    request: makeRequest({ kind: 'promo', id: PROMO_ID, handled: false }),
    locals: makeLocals(),
  } as never);

  expect(res!.status).toBe(409);
  expect(execute).not.toHaveBeenCalled();
});
```

The suite already mocks `queryOne`, so this needs no new fixture.

## Notes

- Mutation result on `dev/bee` `e32a26bd2`: `if (!isDone)` -> `if (false)` leaves
  16/16 green.
- The two sibling guards that were unproven at the time #6784 was reviewed have
  since been covered (the `typeof handled !== 'boolean'` check and the feedback
  reopen path both now fail when broken). This is the last one outstanding.
- Low severity: it needs a status outside the UI's own vocabulary to reach. Worth
  fixing because the branch is the only thing standing between a bad row and a
  silent state change, and because it costs one test.

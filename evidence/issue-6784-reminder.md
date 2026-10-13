Promo reopen re-notifies on the next reminder run instead of after 24h

## What happens

`POST /api/internal/intake/handle` (added in #6784) lets an admin reopen a promo
submission by tapping "Mark handled" a second time. The reopen writes:

```sql
UPDATE promo_submissions SET status = 'pending', reviewed_at = NULL WHERE id = $2
```

It does not touch `last_reminder_at`. The reminder worker selects rows on:

```sql
WHERE p.status = 'pending'
  AND p.submitted_at < NOW() - INTERVAL '24 hours'
  AND (p.last_reminder_at IS NULL OR p.last_reminder_at < NOW() - INTERVAL '24 hours')
```

So a submission that was already reminded once, then marked handled, then
reopened satisfies all three clauses immediately. The next worker run re-notifies
it, instead of waiting out `REMINDER_INTERVAL` again.

The reopen path exists to put a submission back in the queue, so being picked up
is correct. Being picked up *the same hour it was just marked handled* is the
bug: it re-announces to the admin group a decision that was just reversed, and it
burns one of the bounded `MAX_REMINDERS_PER_RUN = 100` slots per row.

## Reproduce

1. Let a promo submission sit pending past 24h so the worker reminds it
   (`last_reminder_at` is now set).
2. In Telegram, tap "Mark handled" (`status` -> `reviewed`).
3. Tap it again to reopen (`status` -> `pending`).
4. On the next worker run, the row is notified again immediately rather than
   after 24h, because `last_reminder_at` is still older than the interval.

## Suggested fix

Include the reset in the same statement as the reopen, so the two cannot drift:

```sql
UPDATE promo_submissions
   SET status = 'pending', reviewed_at = NULL, last_reminder_at = NULL
 WHERE id = $1
```

Resetting to NULL puts the row on the same footing as a fresh submission, which
is what "reopen" means for the worker. The `notification_error` column is
adjacent: it currently carries the last failure reason forward onto a row that is
no longer in a failed state, so it is worth clearing in the same statement.

## Notes

- Verified on `dev/bee` at `e32a26bd2`. Both `UPDATE promo_submissions`
  statements in `src/routes/api/internal/intake/handle/+server.ts:122` and
  `:144` leave `last_reminder_at` alone; `src/lib/server/promo-reminders.ts:52`
  is the gate.
- No test covers it. The endpoint's suite asserts the status write and the
  reopen target, but nothing asserts `last_reminder_at`, which is why this
  survived review.
- The `handled -> reviewed` path is unaffected in practice, because it moves the
  row *out* of the worker's `status = 'pending'` filter entirely. Only reopen is
  affected.

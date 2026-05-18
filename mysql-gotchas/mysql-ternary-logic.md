# MySQL's Ternary Logic & the NULL Trap

## How I Found This

It started with a production bug that took longer than it should have to debug.

We had a reporting query that was returning fewer rows than expected. No exceptions, no
query errors, no red flags in the logs — just quietly incomplete data making its way into
a downstream report. After a couple of hours ruling out data integrity issues and caching
problems, I finally traced it back to this filter:

```sql
WHERE status != 'inactive'
```

Turns out, rows where `status` was `NULL` were being excluded. Not because they were
inactive — they were never confirmed to be *anything*. But MySQL was dropping them anyway,
without a word.

That's when I fell into the rabbit hole of MySQL's three-valued logic. One thing led to
another and I ended up on [Bug #117168](https://bugs.mysql.com/bug.php?id=117168) on the
official MySQL tracker — still open as of January 2025 — where MySQL's own NULL-safe
operator `<=>` turns out to have the same class of problem.

I'm writing this down so I don't have to rediscover it next time.

---

## Wait, why does this happen?

Most of us come to SQL thinking in terms of `TRUE` and `FALSE`. That's how basically
every programming language works. SQL is different though — it uses what's called
**three-valued logic (3VL)**, where there's a third possible result: `UNKNOWN`.

The rule is simple but easy to forget:

> **Any expression involving `NULL` evaluates to `UNKNOWN` — not `TRUE`, not `FALSE`.**

And here's the part that bites you: the `WHERE` clause only keeps rows where the
condition is strictly `TRUE`. Rows that evaluate to `FALSE` *and* rows that evaluate to
`UNKNOWN` are both silently dropped.

So when you write `status != 'inactive'` and `status` is `NULL`, MySQL evaluates that
as `UNKNOWN` — and the row disappears. No warning. No error. Just gone.

```sql
NULL = NULL     -- UNKNOWN
NULL != 30      -- UNKNOWN
NULL > 0        -- UNKNOWN
NULL = 'active' -- UNKNOWN
```

None of these are `TRUE`, so none of these rows make it through a `WHERE` clause.

---

## The patterns that actually get you

### 1. Simple inequality filter

This one got me in production:

```sql
-- looks fine, silently drops NULLs
SELECT * FROM users WHERE age != 30;
```

If `age` is `NULL` for a user, that row is gone. The fix is annoying but necessary:

```sql
SELECT * FROM users WHERE age != 30 OR age IS NULL;
```

And yes, `IS NULL` is the only correct way to check for NULL — `= NULL` always returns
`UNKNOWN`, never `TRUE`.

---

### 2. NOT IN with a nullable subquery

This is the one that tends to really surprise people. If you write something like:

```sql
SELECT * FROM orders WHERE user_id NOT IN (SELECT user_id FROM banned_users);
```

...and `banned_users.user_id` has even a single `NULL` in it, **this query returns zero
rows**. Not fewer rows. Zero.

The reason: `NOT IN` expands into a chain of `!=` comparisons. One of those comparisons
hits `NULL`, returns `UNKNOWN`, and since `UNKNOWN` isn't `TRUE`, the whole thing
collapses. The safest rewrite is `NOT EXISTS`:

```sql
SELECT * FROM orders o
WHERE NOT EXISTS (
  SELECT 1 FROM banned_users b WHERE b.user_id = o.user_id
);
```

Or if you want to stick with `NOT IN`, at least filter out the NULLs:

```sql
SELECT * FROM orders
WHERE user_id NOT IN (
  SELECT user_id FROM banned_users WHERE user_id IS NOT NULL
);
```

---

### 3. CASE expressions that don't account for NULL

The simple form of `CASE` is another silent offender:

```sql
-- NULL status never matches any branch
CASE status
  WHEN 'active'   THEN 1
  WHEN 'inactive' THEN 0
END
```

When `status` is `NULL`, the comparison `NULL = 'active'` is `UNKNOWN`, so it never
matches. The result of the whole expression is also `NULL` — not even an `ELSE` branch
would save you with the simple `CASE` form.

Switch to the searched form and handle NULL explicitly:

```sql
CASE
  WHEN status IS NULL     THEN -1
  WHEN status = 'active'  THEN 1
  ELSE 0
END
```

---

### 4. COUNT(*) vs COUNT(column) — these are not the same

```sql
SELECT
  COUNT(*)      AS total_rows,
  COUNT(salary) AS rows_with_salary
FROM employees;
```

`COUNT(*)` counts every row. `COUNT(salary)` silently skips rows where `salary` is
`NULL`. So if 10 out of 100 employees have no salary recorded, you get 100 and 90.

The same applies to `AVG` — it divides by the number of non-NULL values, not the total
row count, which inflates the average if nulls are common. Worth being deliberate about:

```sql
SELECT
  COUNT(*)                  AS total_employees,
  COUNT(salary)             AS employees_with_salary,
  COUNT(*) - COUNT(salary)  AS no_salary_recorded,
  AVG(salary)               AS avg_ignoring_nulls,
  SUM(salary) / COUNT(*)    AS avg_treating_nulls_as_zero
FROM employees;
```

---

### 5. LEFT JOIN quietly becoming an INNER JOIN

This one is subtle. You do a `LEFT JOIN` because you want to keep all customers even if
they have no orders. Then you add a `WHERE` filter on the orders table:

```sql
SELECT c.name, o.order_id
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id
WHERE o.status != 'cancelled';
```

The `LEFT JOIN` introduces `NULL` for `o.status` when there's no matching order. Then
the `WHERE` clause hits `NULL != 'cancelled'`, evaluates to `UNKNOWN`, and drops the
row — which is exactly what you were trying to avoid. Your `LEFT JOIN` is now effectively
an `INNER JOIN`.

The fix is to move the condition into the `JOIN` itself:

```sql
SELECT c.name, o.order_id
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id AND o.status != 'cancelled';
```

---

## A note on AND / OR with UNKNOWN

The interaction between `UNKNOWN` and logical operators isn't always intuitive:

| A | B | A AND B | A OR B |
|---|---|---------|--------|
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

A couple of things worth internalizing:

- `FALSE AND UNKNOWN` is `FALSE` — if one side is definitely false, the AND is false
  regardless of what the other side is.
- `TRUE OR UNKNOWN` is `TRUE` — if one side is definitely true, the OR is true
  regardless.
- Everything else involving UNKNOWN stays UNKNOWN.

---

## The bug that confirmed this isn't just a gotcha

While going down this rabbit hole I came across
[Bug #117168](https://bugs.mysql.com/bug.php?id=117168), filed January 2025, still open.

`<=>` is MySQL's NULL-safe equality operator — the "official" fix for the `= NULL`
problem. It returns `TRUE` when both sides are `NULL`, unlike `=` which returns
`UNKNOWN`. So in theory, you'd reach for `<=>` when you need NULL-safe comparisons.

But Bug #117168 shows it breaks with multi-column ROW comparisons:

```sql
CREATE TABLE t1 (col_smallint SMALLINT, col_int INT, col_float FLOAT);
INSERT INTO t1 (col_smallint, col_int, col_float) VALUES (NULL, 3, NULL);

-- this returns the row, but it shouldn't
-- col_int is 3 here, not 1 — the comparison should fail
SELECT col_smallint, col_int, col_float
FROM t1
WHERE (col_smallint, col_int, col_float) <=> (SELECT NULL, 1, NULL);
```

The NULL columns (`col_smallint`, `col_float`) get handled correctly by `<=>`, but the
non-NULL column (`col_int = 3` vs the expected `1`) gets ignored entirely. The row
matches when it shouldn't.

So even MySQL's own NULL-safe operator has this class of bug. It's not just us writing
bad queries — the engine itself has open issues around NULL handling.

---

## The one question to always ask

*"What happens to this query when this column is NULL?"*

If you can't answer that immediately, you probably need to add explicit NULL handling.
MySQL won't tell you when something slips through — it'll just silently return wrong data
and let you figure it out in production.

---

## References

- [MySQL Bug #117168 — NULL-safe `<=>` with ROW values](https://bugs.mysql.com/bug.php?id=117168)
- [MySQL 8.4 docs — Comparison Functions and Operators](https://dev.mysql.com/doc/en/comparison-operators.html)
- [MySQL 8.4 docs — Logical Operators](https://dev.mysql.com/doc/en/logical-operators.html)
- [Modern SQL — Three-Valued Logic](https://modern-sql.com/concept/three-valued-logic)
- [DEV Community — Four Pitfalls of SQL NULL Processing](https://dev.to/pawsql/four-pitfalls-of-sql-processing-with-null-values-1o88)

# Architecture & optimisation decisions

## 1. Overview

```
Browser ── React (Vite, TanStack Query) ──/api──► Django REST Framework ──► PostgreSQL 16
                                                   │  services.py (business rules, locking)
                                                   │  JWT auth · role permissions · tenant scoping
```

- **Backend:** Django 5.2 + DRF. Views stay thin; business rules live in `breaks/services.py`
  so they are reusable from tests, the data generator and future background jobs.
- **Database:** PostgreSQL 16 with `btree_gist` (exclusion constraint, GiST indexes) and
  `pg_trgm` (substring search).
- **Frontend:** React + React Router + TanStack Query, one lazily-loaded chunk per screen.
- **Runtime:** Docker Compose; Gunicorn (4 workers × 4 threads) for benchmarks.

## 2. Multi-tenancy

Shared tables with an `organisation_id` on every tenant-owned row.

| Layer | Mechanism |
|---|---|
| Authentication | JWT; the user is reloaded from the DB on every request (role claims in the token are UI hints only) |
| Authorisation | `IsManager` / `IsEmployee` / `IsTenantUser` permission classes; secure-by-default `IsAuthenticated` |
| Data scoping | `TenantScopedQuerysetMixin` filters every queryset by `request.user.organisation_id`; fails closed (no org → no data) |
| Employee scope | Employee endpoints filter by `employee_id = request.user.id` |
| No ID leakage | Other tenants' objects return **404** (not 403); `/api/policy/` has no ID at all; bulk review reports foreign IDs as `not_found` |
| Frontend | React Query cache cleared on logout so a second user never sees cached data |

## 3. Data model

`Organisation 1─1 BreakPolicy`, `Organisation 1─* User (role)`, `User 1─* BreakRequest`.

Deliberate denormalisation on `BreakRequest`:
- `organisation_id` (also derivable from the employee) lets every tenant query use one
  composite index without joining 100k users.
- `end_at` and `break_date` (derivable from `start_at` + duration) make overlap, "on break at T",
  and per-day queries simple, indexable predicates.
- No default `Meta.ordering`: each endpoint orders explicitly, so counts/aggregates never pay for a sort.

## 4. Indexes (designed from the query patterns)

| Index | Serves |
|---|---|
| `(employee_id, start_at)` | Employee history; per-day policy checks |
| `(organisation_id, start_at)` | Queue without status filter |
| `(organisation_id, status, start_at) INCLUDE (duration_minutes, employee_id, break_date)` | Queue by status, register, summary and daily stats as **index-only scans** |
| Partial GiST `(organisation_id, tstzrange(start_at, end_at))` WHERE APPROVED | "Who is on break at T", capacity checks |
| `(organisation_id, role)` on users | Users per org |
| GIN trigram on `UPPER(first_name / last_name / username)` | Case-insensitive substring search (matches the SQL Django generates for `icontains`) |

Redundant single-column FK indexes were removed (`db_index=False`), since composite indexes cover them.
Evidence: `docs/query-plans.md` (EXPLAIN ANALYZE on 1M rows, including a with/without-index comparison).

## 5. Integrity: database constraints

| Rule | Constraint |
|---|---|
| No overlapping active breaks per employee | `EXCLUDE USING gist (employee_id WITH =, tstzrange(start_at,end_at,'[)') WITH &&) WHERE status IN (PENDING, APPROVED)` |
| No duplicate submissions | Partial `UNIQUE (employee_id, client_request_id)` |
| Valid policies | `CHECK` min ≥ 1, min ≤ max, max ≤ daily allowance, limits ≥ 1 |
| Valid requests | `CHECK` duration > 0, end > start |
| Users belong to a tenant | `CHECK` superuser OR organisation NOT NULL |

Half-open ranges `[)` allow back-to-back breaks. Constraint names are mapped to clean API errors (409).

## 6. Concurrency

| Race | Solution |
|---|---|
| Two overlapping submissions at once | Exclusion constraint (atomic in Postgres) |
| Double-click / network retry | Client-generated idempotency key; replay returns the original request (200) |
| Per-day limits (check-then-act) | `SELECT … FOR NO KEY UPDATE` on the employee's user row: same-employee submissions serialise, different employees stay parallel |
| Max employees on break at once (manual + auto approval) | `SELECT … FOR UPDATE` on the organisation's `BreakPolicy` row; capacity computed as **peak** overlap with a sweep line over approved breaks found via the GiST index |
| Two managers reviewing the same request | Rows locked `FOR UPDATE`; only still-`PENDING` rows change; Postgres re-checks the predicate after waiting |
| Lost update on the policy form | Optimistic locking (`version` column → 409) + row lock for same-instant saves |
| Deadlocks | One global lock order: user row → policy row → break-request rows (sorted by id) |

Rejections and PENDING submissions never take the organisation lock, so contention is limited to the
operations that actually change capacity.

Verified by: `backend/tests/test_concurrency.py` (real threads + barrier), the Locust contention test, and
`benchmarks/integrity_checks.sql` run over the full dataset after load.

## 7. API performance

- Constant query counts per endpoint (`select_related`, `.only()`, aggregation in SQL). Asserted by a
  test and measured per request via the `X-Query-Count` header.
- Pagination chosen per use case: **offset** for the approval queue (bounded per tenant, needs sort
  options + page numbers); **keyset/cursor** for the ever-growing register (constant speed at any depth,
  no `COUNT`).
- Analytics are single aggregate queries (`COUNT`, `SUM`, `COUNT DISTINCT`, `GROUP BY break_date`);
  date ranges are capped (366 days); list sizes capped (`max_page_size = 100`, bulk ≤ 100 IDs).
- Persistent DB connections (`CONN_MAX_AGE`), Gunicorn gthread workers, light Postgres tuning
  (`shared_buffers`, `random_page_cost` for SSD).

## 8. Data generation

`generate_data` streams rows into PostgreSQL with `COPY` from a Python generator (flat memory),
respects every constraint (one break per employee per day; capacity tracked in 5-minute buckets, so
over-capacity "approvals" become rejections), hashes the shared password once, uses a fixed seed for
reproducibility, and finishes with `VACUUM ANALYZE`.

## 9. Frontend

- TanStack Query: cache keyed by request; `keepPreviousData` for smooth paging; `useInfiniteQuery` for
  cursor pagination; `setQueryData` after PUT, `invalidateQueries` after list-changing mutations
  (`onSettled`, so a 409 also refreshes stale views).
- Filters, sort and paging live in the URL (`useUrlParams`): reload-safe and shareable.
- Debounced search (one request per pause) + `AbortSignal` cancellation of stale requests.
- `React.memo` rows with stable callbacks: toggling one checkbox re-renders one row.
- Code splitting per page (`React.lazy`); hand-written SVG chart (no chart library).
- Tokens: access token in memory, refresh token in `sessionStorage`, single-flight refresh on 401.
- Pessimistic UI for approvals (the server's capacity decision is authoritative).

## 10. Testing

- **pytest:** unit (sweep line), API behaviour, tenant isolation, N+1 guard, and real-thread
  concurrency tests (`transaction=True`, `threading.Barrier`).
- **Vitest:** API client error handling and single-flight token refresh.
- **CI:** GitHub Actions runs both suites against PostgreSQL 16.

## 11. Assumptions, trade-offs and future work

- One time zone for all organisations (`Asia/Colombo`); a per-organisation time zone is a natural extension.
- Lowering `max_concurrent_breaks` does not revoke existing approvals; it only blocks new ones.
- Approvals within one organisation are serialised by the policy-row lock (short transactions);
  if needed, finer-grained locking (per day) or `SERIALIZABLE` with retries could raise throughput.
- Production hardening: refresh token in an `httpOnly` cookie, login throttling, Redis caching for
  historical analytics, read replicas for analytics, PgBouncer for connection pooling,
  monthly partitioning of `breaks_breakrequest` beyond tens of millions of rows.
- Benchmarks ran on a single laptop with the load generator on the same machine; absolute numbers
  are conservative, and the trend across 10/50/100 clients is the meaningful result.
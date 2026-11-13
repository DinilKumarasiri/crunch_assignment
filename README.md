# Multi-Tenant Break Management System

![tests](https://github.com/DinilKumarasiri/break-management/actions/workflows/tests.yml/badge.svg)

Employee break management for multiple organisations: managers configure break policies and approve
requests; employees request breaks and track their status. Built for performance, concurrency safety
and tenant isolation at scale (1M+ break requests).

**Stack:** Django 5.2 · Django REST Framework · PostgreSQL 16 · React (Vite) · TanStack Query · Docker

## Quick start

Requirements: Docker Desktop (4 GB+ memory recommended).

```bash
git clone https://github.com/DinilKumarasiri/crunch_assignment.git
cd break-management
cp .env.example .env
docker compose up -d --build              # migrations run automatically
docker compose exec backend python manage.py seed_demo
```

Open **http://localhost:5173**

| Role | Username | Password |
|---|---|---|
| Manager | `acme_manager` | `password123` |
| Employee | `acme_emp1` … `acme_emp6` | `password123` |
| Manager (other tenant) | `globex_manager` | `password123` |

### Large dataset (50 orgs · 100k employees · 100 managers · 1M requests)

```bash
docker compose exec backend python manage.py generate_data          # a few minutes
docker compose exec backend python manage.py generate_data --reset  # regenerate
```
Generated users: `gen_o01_m1` (manager), `gen_o01_e00001` (employee), … password `password123`.

## Screens

1. **Break policy** (manager): durations, daily allowance, requests per day, advance notice,
   max employees on break at once, approval required. Optimistic locking prevents lost updates.
2. **My breaks** (employee): submit requests (validated against the policy, idempotent), view history.
3. **Approval queue** (manager): search, filters, sorting, pagination, single and bulk approve/reject.
4. **Break register & analytics** (manager): approved records (cursor pagination), totals, who is on
   break at a given time, daily statistics chart.

## Tests

```bash
docker compose exec backend pytest                                   # backend suite
docker compose exec backend pytest --cov=accounts --cov=breaks       # with coverage
docker compose exec frontend npm test                                # frontend suite
```

Includes real-thread concurrency tests: parallel submissions for the same slot, daily-limit races,
double-clicks, parallel approvals and auto-approvals against the capacity limit, and opposite-order
bulk reviews (deadlock check). Coverage: **⟨XX⟩%** of backend code.

## Performance

Benchmarked with Locust against Gunicorn (4 workers × 4 threads), `DEBUG=0`, 1M break requests.
Full results: [`benchmarks/results/RESULTS.md`](benchmarks/results/RESULTS.md) ·
query plans: [`docs/query-plans.md`](docs/query-plans.md).

| Concurrent clients | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---:|---:|---:|---:|---:|
| 10  | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ | 0 |
| 50  | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ | 0 |
| 100 | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ | 0 |

- Database queries per request stay constant under load (typically 2–4 per endpoint).
- A contention test (100 clients, one organisation, the same time slots) produced **0 policy
  violations**, verified by [`benchmarks/integrity_checks.sql`](benchmarks/integrity_checks.sql)
  over the full dataset ([output](benchmarks/results/integrity.txt)).
- ⟨One sentence on the bottleneck you saw in `docker stats`, e.g. "Throughput plateaus at ~N req/s
  with the backend container CPU-bound; Postgres stayed below X% CPU."⟩

Run the benchmarks yourself:
```bash
docker compose -f docker-compose.yml -f docker-compose.bench.yml up -d --build db backend
./benchmarks/run.sh
docker compose up -d   # back to dev mode
```

## Architecture & key decisions

Details: [`docs/architecture.md`](docs/architecture.md). In short:

- **Tenant isolation:** shared schema with `organisation_id`; a queryset mixin scopes every query to
  the user's organisation and fails closed; other tenants' objects return 404.
- **Integrity in the database:** an exclusion constraint makes overlapping breaks impossible; a
  partial unique constraint makes submissions idempotent; check constraints guard policies.
- **Concurrency:** row locks with a single global lock order (employee → policy → requests);
  capacity is enforced as *peak* overlap under an organisation-level lock; optimistic locking on
  the policy.
- **Query performance:** composite, covering (`INCLUDE`), partial GiST and trigram indexes designed
  from the query patterns; constant query counts; offset pagination for the bounded queue and
  keyset pagination for the growing register; analytics as single SQL aggregates.
- **Frontend:** TanStack Query caching, URL-driven filters, debounced and cancellable search,
  memoised rows, per-screen code splitting, single-flight token refresh.

## API

| Method | Endpoint | Who |
|---|---|---|
| POST | `/api/auth/login/`, `/api/auth/refresh/` | anyone |
| GET | `/api/auth/me/` | logged in |
| GET | `/api/users/` | manager |
| GET / PUT | `/api/policy/` | read: all · write: manager |
| GET / POST | `/api/my/break-requests/` | employee |
| GET | `/api/break-requests/?status=&search=&date_from=&date_to=&ordering=&page=` | manager |
| POST | `/api/break-requests/{id}/approve/`, `/reject/` | manager |
| POST | `/api/break-requests/bulk-review/` | manager |
| GET | `/api/register/`, `/summary/`, `/on-break/?at=`, `/daily-stats/` | manager |

Every response carries `X-Query-Count` and `X-Response-Time-Ms` headers.

## Project structure

```
backend/
  accounts/        Organisation, User, auth, permissions, tenant mixin, seed_demo
  breaks/          policy & break models, services (rules + locking), API, generate_data
  config/          settings, pagination, middleware (query counter), exception handler
  tests/           pytest suite (incl. concurrency)
  scripts/         manual smoke-test scripts used during development
frontend/src/
  api/             fetch client (token refresh), React Query hooks
  auth/            auth context, route guards
  pages/           the four screens + login
  components/      layout, pagination, chart, shared UI
benchmarks/        Locust load tests, run script, integrity checks, results
docs/              architecture notes, query plans
```

## Assumptions

- All organisations share one time zone (`Asia/Colombo`).
- Lowering the on-break limit keeps existing approvals and blocks new ones.
- The frontend is intentionally simple; the focus is performance, scalability and correctness.

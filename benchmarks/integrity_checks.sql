-- Run after a load test. Every query must return ZERO rows / zero count.
\timing on

\echo '1) Overlapping active breaks for the same employee:'
SELECT a.employee_id, a.id AS break_a, b.id AS break_b
FROM breaks_breakrequest a
JOIN breaks_breakrequest b
  ON b.employee_id = a.employee_id AND a.id < b.id
 AND a.start_at < b.end_at AND b.start_at < a.end_at
WHERE a.status IN ('PENDING', 'APPROVED') AND b.status IN ('PENDING', 'APPROVED')
LIMIT 10;

\echo '2) Moments where approved breaks exceed max_concurrent_breaks:'
-- The peak always occurs at some break's start, so checking every distinct start is enough.
WITH starts AS (
    SELECT DISTINCT organisation_id, start_at
    FROM breaks_breakrequest WHERE status = 'APPROVED'
)
SELECT s.organisation_id, s.start_at, count(*) AS on_break, p.max_concurrent_breaks
FROM starts s
JOIN breaks_breakpolicy p ON p.organisation_id = s.organisation_id
JOIN breaks_breakrequest o
  ON o.organisation_id = s.organisation_id AND o.status = 'APPROVED'
 AND tstzrange(o.start_at, o.end_at, '[)') && tstzrange(s.start_at, s.start_at, '[]')
GROUP BY s.organisation_id, s.start_at, p.max_concurrent_breaks
HAVING count(*) > p.max_concurrent_breaks
LIMIT 10;

\echo '3) Employee-days over max_requests_per_day:'
SELECT b.employee_id, b.break_date, count(*) AS requests, p.max_requests_per_day
FROM breaks_breakrequest b
JOIN breaks_breakpolicy p ON p.organisation_id = b.organisation_id
WHERE b.status IN ('PENDING', 'APPROVED')
GROUP BY b.employee_id, b.break_date, p.max_requests_per_day
HAVING count(*) > p.max_requests_per_day
LIMIT 10;

\echo '4) Requests whose organisation differs from the employee''s organisation:'
SELECT count(*) AS mismatched
FROM breaks_breakrequest b
JOIN accounts_user u ON u.id = b.employee_id
WHERE b.organisation_id <> u.organisation_id;
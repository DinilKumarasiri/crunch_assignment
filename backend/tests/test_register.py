import pytest

from helpers import client_for, create_break, future_day

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample(employee, employee2):
    day0, day1 = future_day(3), future_day(4)
    create_break(employee, day0, "10:00", 30)
    create_break(employee2, day0, "10:15", 30)
    create_break(employee, day1, "09:00", 20)
    create_break(employee2, day1, "14:00", 40)
    create_break(employee2, future_day(5), "10:00", 15, status="PENDING")  # must never count
    return day0, day1


def test_summary_totals(manager, sample):
    day0, day1 = sample
    res = client_for(manager).get("/api/register/summary/", {"date_from": day0, "date_to": day1})
    assert res.data == {"total_breaks": 4, "total_minutes": 120, "total_hours": 2.0, "unique_employees": 2}


def test_summary_respects_search(manager, sample):
    day0, day1 = sample
    res = client_for(manager).get("/api/register/summary/",
                                  {"date_from": day0, "date_to": day1, "search": "emma"})
    assert (res.data["total_breaks"], res.data["total_minutes"]) == (2, 70)


@pytest.mark.parametrize("moment, expected", [("10:20", 2), ("10:30", 1), ("10:50", 0)])
def test_on_break_at_a_moment(manager, sample, moment, expected):
    day0, _ = sample
    res = client_for(manager).get("/api/register/on-break/", {"at": f"{day0}T{moment}"})
    assert res.data["count"] == expected


def test_daily_stats_fill_empty_days(manager, sample):
    day0, day1 = sample
    day2 = future_day(5)
    res = client_for(manager).get("/api/register/daily-stats/", {"date_from": day0, "date_to": day2})
    rows = [(str(d["date"]), d["breaks"], d["total_minutes"]) for d in res.data["days"]]
    assert rows == [(day0, 2, 60), (day1, 2, 60), (day2, 0, 0)]


def test_daily_stats_range_is_capped(manager):
    res = client_for(manager).get("/api/register/daily-stats/",
                                  {"date_from": "2020-01-01", "date_to": "2026-01-01"})
    assert res.status_code == 400


def test_register_is_cursor_paginated_and_approved_only(manager, sample):
    client = client_for(manager)
    first = client.get("/api/register/", {"page_size": 3}).data
    assert len(first["results"]) == 3
    assert first["next"] and "count" not in first
    second = client.get(first["next"]).data
    rows = first["results"] + second["results"]
    assert len(rows) == 4
    assert {r["status"] for r in rows} == {"APPROVED"}


def test_other_organisation_sees_nothing(other_manager, sample):
    day0, day1 = sample
    res = client_for(other_manager).get("/api/register/summary/", {"date_from": day0, "date_to": day1})
    assert res.data["total_breaks"] == 0
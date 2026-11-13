"""Pure-function tests for the capacity sweep line (no database)."""
from datetime import datetime, timedelta, timezone

from breaks.services import fits_capacity, peak_concurrency

T0 = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)


def iv(start_minute, end_minute):
    return T0 + timedelta(minutes=start_minute), T0 + timedelta(minutes=end_minute)


def test_no_intervals_means_zero():
    assert peak_concurrency([], *iv(0, 60)) == 0


def test_separate_intervals_peak_at_one():
    assert peak_concurrency([iv(0, 10), iv(20, 30)], *iv(0, 30)) == 1


def test_back_to_back_intervals_do_not_overlap():
    assert peak_concurrency([iv(0, 30), iv(30, 60)], *iv(0, 60)) == 1


def test_nested_intervals():
    assert peak_concurrency([iv(0, 60), iv(10, 20), iv(15, 25)], *iv(0, 60)) == 3


def test_intervals_are_clipped_to_the_window():
    # iv(0,10) ends exactly where the window starts, so it doesn't count.
    assert peak_concurrency([iv(0, 10), iv(5, 15)], *iv(10, 20)) == 1


def test_capacity_uses_peak_not_total_overlap():
    busy = [iv(0, 10), iv(20, 30)]                # overlaps the candidate twice, never together
    assert fits_capacity(iv(0, 30), busy, capacity=2) is True
    assert fits_capacity(iv(0, 30), busy, capacity=1) is False
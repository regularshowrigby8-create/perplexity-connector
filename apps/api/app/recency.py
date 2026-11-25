"""The recency window — every search answer lives inside it.

The rule, stated once and enforced everywhere:

* **older than the window is cut** — a result whose best clock says it is more
  than `window_days` old (default **730**, two years) is not returned at all.
  Not sorted last, not labelled: cut.
* **further ahead than a few months is cut** — a date more than `future_days`
  ahead (default **120**) is a broken clock on a page, not a document from the
  future, so it goes with the old ones.
* **undated is kept** — a page with no clock anywhere is not evidence of age.
  These are the uploads with no date in their headers, the /uploads/2019/03/
  PDFs whose only date is in the path, the notices behind portal searches. We
  saw them now; the window is about what the site says, not about what it
  withholds. They are counted separately as `undated_kept` so the ledger stays
  honest.

The best clock is taken in this order: `published_at` (a parsed publication
time), `published` (the raw string the page gave), `first_seen` (when this
engine first found it). `first_seen` is deliberately last: a page published in
2011 and first seen today is a 2011 page.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from . import freshness
from .config import settings

KEEP = "keep"
OLD = "older-than-window"
FUTURE = "dated-in-the-future"
UNDATED = "undated"


def _stamp(hit: Any):
    """The best clock a hit has, as a datetime (or None)."""
    if isinstance(hit, dict):
        return (freshness.parse(hit.get("published_at"))
                or freshness.parse(hit.get("published"))
                or freshness.parse(hit.get("first_seen")))
    return (freshness.parse(getattr(hit, "published_at", None))
            or freshness.parse(getattr(hit, "published", None))
            or freshness.parse(getattr(hit, "first_seen", None)))


@dataclass(frozen=True)
class Window:
    days: int = 730
    future_days: int = 120

    @classmethod
    def current(cls) -> "Window":
        return cls(days=int(settings.window_days), future_days=int(settings.future_days))

    @property
    def seconds(self) -> int:
        return self.days * 86400

    @property
    def future_seconds(self) -> int:
        return self.future_days * 86400

    def classify(self, hit: Any, now=None) -> str:
        stamp = _stamp(hit)
        if stamp is None:
            return UNDATED
        age = freshness.age_seconds(stamp, now)
        if age is None:
            return UNDATED
        if age > self.seconds:
            return OLD
        if -age > self.future_seconds:
            return FUTURE
        return KEEP

    def keeps(self, hit: Any, now=None) -> bool:
        return self.classify(hit, now) in (KEEP, UNDATED)

    def as_meta(self) -> dict[str, Any]:
        return {
            "window_days": self.days,
            "future_days": self.future_days,
            "window": f"{self.days} days",
            "statement": (f"results from the last {self.days} days, plus anything dated up to "
                          f"{self.future_days} days ahead; older and wildly future-dated results are cut"),
        }

    def summary(self) -> str:
        if self.days % 365 == 0:
            return f"the last {self.days // 365} year{'s' if self.days > 365 else ''}"
        if self.days % 30 == 0:
            return f"the last {self.days // 30} months"
        return f"the last {self.days} days"


def apply(hits: Iterable[Any], window: Window | None = None, now=None
          ) -> tuple[list[Any], dict[str, Any]]:
    """Keep what is inside the window, count what was cut and why."""
    win = window or Window.current()
    kept: list[Any] = []
    cut_older = cut_future = undated = 0
    for hit in hits:
        verdict = win.classify(hit, now)
        if verdict == OLD:
            cut_older += 1
        elif verdict == FUTURE:
            cut_future += 1
        else:
            if verdict == UNDATED:
                undated += 1
            kept.append(hit)
    return kept, {
        "window_days": win.days,
        "future_days": win.future_days,
        "cut_older": cut_older,
        "cut_future": cut_future,
        "undated_kept": undated,
        "kept": len(kept),
    }

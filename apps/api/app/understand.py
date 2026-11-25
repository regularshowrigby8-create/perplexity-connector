"""Read the question before fetching anything.

Every search is parsed into an `Understanding` first: what the person is
looking for (a form, a dataset, a tender, a repository…), what the subject
phrases are, which place or organisation they named, which file type they
asked for, which years they mentioned, what they want excluded — and whether
that request can be honoured at all inside the recency window the engine
enforces (asking for 2016 on an engine that only returns the last two years is
a conflict worth saying out loud, not a silent zero).

The keyword half is RAKE (vendored in `app/vendor/rake_keyword`, MIT), which
scores phrases by word degree and frequency without a model file or a download.
Everything else is a taxonomy and a handful of rules, so it runs in
microseconds and cannot fail in a new and interesting way.

Nothing here changes the meaning of a result: the words a hit is matched against
are still the words that were typed. The understanding steers *retrieval*
(where to look), *ordering* (a small nudge towards the kind of thing asked for)
and *wording* (what the page says it understood).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

_STOPLIST = Path(__file__).resolve().parent / "vendor" / "rake_keyword" / "resources" / "SmartStoplist.txt"
_rake = None


def _rake_engine():
    """RAKE, built once per process — it reads a ~600-line stop list."""
    global _rake
    if _rake is None:
        from .vendor.rake_keyword import RAKE
        _rake = RAKE(str(_STOPLIST))
    return _rake


# ---------------------------------------------------------------- taxonomy
# (id, human label, cues, lens it suggests, file types it implies)
KINDS: list[tuple[str, str, tuple[str, ...], str | None, tuple[str, ...]]] = [
    ("form", "a form or application",
     ("application form", "apply", "application", "form", "forms", "questionnaire",
      "registration", "expression of interest", "eoi"),
     "applications", ()),
    ("tender", "a tender, grant or funding call",
     ("call for proposals", "request for proposals", "tender", "rfp", "rfq", "grant",
      "grants", "funding", "procurement", "bid", "scholarship", "fellowship", "vacancy"),
     "opportunities", ()),
    ("dataset", "a dataset or spreadsheet",
     ("dataset", "datasets", "open data", "spreadsheet", "csv", "xlsx", "geojson",
      "statistics", "indicator", "json"),
     "datasets", ("csv", "xlsx", "json", "geojson")),
    ("document", "a document or report",
     ("report", "policy", "guideline", "manual", "study", "assessment", "brief",
      "white paper", "paper", "review", "pdf", "docx"),
     "files", ("pdf", "docx")),
    ("legal", "a law, regulation or notice",
     ("gazette", "regulation", "regulations", "act", "law", "judgment", "judgement",
      "decree", "bill", "notice", "advert", "announcement", "circular"),
     "exposed", ()),
    ("code", "code or a repository",
     ("github", "gitlab", "repository", "repo", "source code", "library", "package",
      "sdk", "npm", "pypi", "documentation"),
     None, ("zip", "gz")),
    ("media", "video or audio",
     ("video", "youtube", "podcast", "mp3", "mp4", "audio", "webinar", "recording"),
     None, ("mp3", "mp4")),
    ("job", "a job or consultancy",
     ("job", "jobs", "vacancy", "vacancies", "career", "recruitment", "internship",
      "consultancy", "consultant"),
     "opportunities", ()),
    ("place", "a place, office or contact",
     ("address", "office", "campus", "map", "directions", "contact", "phone"),
     None, ()),
]

# A small gazetteer: enough to notice that a place was named without pretending
# to be a geocoder. Matched case-insensitively on word boundaries.
PLACES = (
    "kenya", "uganda", "tanzania", "rwanda", "ethiopia", "nigeria", "ghana", "senegal",
    "south africa", "zimbabwe", "zambia", "malawi", "mozambique", "botswana", "namibia",
    "egypt", "morocco", "tunisia", "algeria", "sudan", "somalia", "djibouti", "eritrea",
    "cameroon", "ivory coast", "côte d'ivoire", "mali", "niger", "burkina faso", "benin",
    "togo", "liberia", "sierra leone", "gambia", "guinea", "chad", "congo", "angola",
    "india", "pakistan", "bangladesh", "nepal", "sri lanka", "indonesia", "philippines",
    "vietnam", "thailand", "malaysia", "singapore", "china", "japan", "korea", "australia",
    "new zealand", "united kingdom", "england", "scotland", "wales", "ireland", "france",
    "germany", "spain", "portugal", "italy", "netherlands", "belgium", "denmark", "sweden",
    "norway", "finland", "poland", "czechia", "austria", "switzerland", "greece", "turkey",
    "ukraine", "russia", "canada", "united states", "usa", "mexico", "brazil", "argentina",
    "chile", "colombia", "peru", "ecuador", "bolivia", "venezuela", "cuba", "haiti",
    "nairobi", "mombasa", "kisumu", "kampala", "dodoma", "dar es salaam", "kigali", "addis ababa",
    "lagos", "accra", "dakar", "johannesburg", "cape town", "harare", "lusaka", "lilongwe",
    "maputo", "gaborone", "windhoek", "cairo", "casablanca", "khartoum", "mogadishu",
    "london", "manchester", "paris", "berlin", "madrid", "rome", "amsterdam", "brussels",
    "geneva", "zurich", "vienna", "stockholm", "oslo", "helsinki", "warsaw", "prague",
    "new york", "washington", "boston", "chicago", "san francisco", "los angeles", "toronto",
    "ottawa", "sydney", "melbourne", "auckland", "tokyo", "seoul", "beijing", "shanghai",
    "delhi", "mumbai", "bangalore", "karachi", "lahore", "dhaka", "colombo", "kathmandu",
    "jakarta", "manila", "bangkok", "hanoi", "kuala lumpur", "dubai", "doha", "riyadh",
)

FILE_WORDS = ("pdf", "docx", "doc", "xlsx", "xls", "csv", "tsv", "json", "geojson", "zip",
              "rar", "7z", "tar", "gz", "apk", "exe", "iso", "mp3", "mp4", "epub", "rtf",
              "pptx", "ppt", "odt", "ods", "xml", "sql", "db", "kml", "shp", "txt", "md")

RELATIVE_WINDOWS = {
    "today": 1, "this morning": 1, "yesterday": 1, "this week": 7, "last week": 7,
    "this month": 30, "last month": 30, "this year": 365, "last year": 365,
    "past week": 7, "past month": 30, "past year": 365, "recent": 30, "latest": 30,
    "new": 30, "breaking": 1,
}

_NEGATIVE = re.compile(r"(?:^|\s)-(?P<word>[\w\u00c0-\u024f]+)")
_QUOTED = re.compile(r'"([^"]{2,120})"|“([^”]{2,120})”|\'([^\']{2,80})\'')
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")


@dataclass
class Understanding:
    query: str
    subject: str = ""                       # the query with type/filler words taken out
    phrases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    kind: str = ""
    kind_label: str = ""
    kind_score: float = 0.0
    kind_cue: str = ""
    suggested_lens: str | None = None
    file_types: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    orgs: list[str] = field(default_factory=list)
    quoted: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    asked_days: int | None = None
    window_days: int = 730
    future_days: int = 120
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ wording
    def summary(self) -> str:
        bits: list[str] = []
        if self.kind_label:
            bits.append(self.kind_label)
        if self.phrases:
            bits.append("about “" + self.phrases[0] + "”")
        elif self.subject:
            bits.append("about “" + self.subject[:60] + "”")
        extras = []
        if self.places:
            extras.append("in " + ", ".join(place.title() for place in self.places[:2]))
        if self.orgs:
            extras.append("from " + ", ".join(self.orgs[:2]))
        if self.file_types:
            extras.append("as " + " / ".join(self.file_types[:3]))
        if extras:
            bits.append(" ".join(extras))
        window = f"inside the last {self.window_days} days"
        bits.append(window)
        text = ", ".join(bits[:2]) + ((" — " + bits[2]) if len(bits) > 2 else "")
        return text[0].upper() + text[1:] if text else ""

    def as_meta(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "subject": self.subject,
            "phrases": self.phrases[:6],
            "keywords": self.keywords[:10],
            "kind": self.kind,
            "kind_label": self.kind_label,
            "kind_score": round(self.kind_score, 2),
            "kind_cue": self.kind_cue,
            "suggested_lens": self.suggested_lens,
            "file_types": self.file_types,
            "places": self.places,
            "orgs": self.orgs,
            "quoted": self.quoted,
            "negatives": self.negatives,
            "years": self.years,
            "asked_days": self.asked_days,
            "window_days": self.window_days,
            "future_days": self.future_days,
            "warnings": self.warnings,
            "summary": self.summary(),
            "engine": "rules + RAKE (vendored)",
            "note": ("what the search was read as, before any source was asked; "
                     "the words matched against a result are still the words that were typed"),
        }

    def relevance_bonus(self, hit: Any) -> float:
        """A small nudge towards the kind of thing that was asked for.

        Small on purpose: accuracy is the first ordering key, and this only
        breaks ties in favour of the artefact the person described.
        """
        if not self.kind:
            return 0.0
        text = " ".join(str(getattr(hit, field, "") or "") for field in ("url", "title", "kind", "file_ext")).lower()
        cues = next((cues for key, _label, cues, _lens, _types in KINDS if key == self.kind), ())
        return 6.0 if any(cue in text for cue in cues[:6]) else 0.0


def _cue_pattern(cue: str) -> str:
    """Cues are stems: 'guideline' has to match 'guidelines', 'grant' 'grants'."""
    return r"\b" + re.escape(cue) + r"(?:s|es)?\b"


def _find_kind(lowered: str) -> tuple[str, str, str, float, str | None, tuple[str, ...]]:
    best = ("", "", "", 0.0, None, ())
    for key, label, cues, lens, types in KINDS:
        for cue in cues:
            if re.search(_cue_pattern(cue), lowered):
                score = min(1.0, 0.45 + 0.1 * len(cue.split()) + 0.02 * len(cue))
                if score > best[3]:
                    best = (key, label, cue, score, lens, types)
    return best


def _proper_nouns(query: str) -> list[str]:
    """Capitalised runs, taken as names. "World Bank" is one name, not "Bank"."""
    words = re.findall(r"[\w'’-]+", query)
    out: list[str] = []
    current: list[str] = []
    for index, word in enumerate(words):
        capitalised = bool(word[:1].isupper())
        joined = bool(current)
        if capitalised and (index > 0 or joined or (index + 1 < len(words)
                                                    and words[index + 1][:1].isupper())):
            current.append(word)
        else:
            if current:
                out.append(" ".join(current))
            current = []
    if current:
        out.append(" ".join(current))
    return [item for item in out if len(item) > 2 and not item.isdigit()][:4]


def read(query: str) -> Understanding:
    """Parse one search into an Understanding. Never raises, never slow."""
    raw = (query or "").strip()
    understood = Understanding(query=raw, window_days=int(settings.window_days),
                               future_days=int(settings.future_days))
    if not raw:
        return understood

    lowered = raw.lower()
    key, label, cue, score, lens, types = _find_kind(lowered)
    understood.kind, understood.kind_label, understood.kind_cue = key, label, cue
    understood.kind_score = score
    understood.suggested_lens = lens
    understood.file_types = list(types)

    for word in FILE_WORDS:
        if re.search(r"\b" + word + r"\b", lowered) and word not in understood.file_types:
            understood.file_types.append(word)

    understood.places = [place for place in PLACES
                         if re.search(r"\b" + re.escape(place) + r"\b", lowered)][:4]
    understood.orgs = [name for name in _proper_nouns(raw)
                       if name.lower() not in understood.places
                       and name.lower() not in {"pdf", "csv", "excel"}]

    understood.quoted = [next(group for group in match.groups() if group)
                         for match in _QUOTED.finditer(raw)][:3]
    understood.negatives = [match.group("word") for match in _NEGATIVE.finditer(raw)][:6]
    understood.years = sorted({int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", raw)})[:4]

    for phrase, days in RELATIVE_WINDOWS.items():
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            understood.asked_days = days if understood.asked_days is None else min(understood.asked_days, days)

    # phrases: RAKE on the query itself, then drop the type words from them
    try:
        engine = _rake_engine()
        ranked = engine.exec(raw.replace("\n", " "))[:8]
    except Exception:
        ranked = []
    phrases: list[str] = []
    for phrase, _score in ranked:
        words_in = [word for word in phrase.split() if not word.startswith("-")]
        cleaned = " ".join(word for word in words_in
                           if word not in FILE_WORDS and word not in {"form", "forms", "pdf"}
                           and word not in understood.negatives)
        cleaned = cleaned.strip(" -")
        if cleaned and len(cleaned) > 2 and cleaned not in phrases:
            phrases.append(cleaned)
    understood.phrases = phrases[:5]
    understood.keywords = [word for word in re.findall(r"[a-zà-ÿ0-9][a-zà-ÿ0-9\-]{2,}", lowered)
                           if word not in FILE_WORDS][:12]
    understood.subject = phrases[0] if phrases else " ".join(understood.keywords[:6])

    # ---- conflicts worth saying out loud
    now_year = datetime.now(timezone.utc).year
    oldest_allowed = now_year - max(1, understood.window_days // 365)
    stale_years = [year for year in understood.years if year < oldest_allowed]
    if stale_years:
        understood.warnings.append(
            f"{', '.join(str(y) for y in stale_years)} is outside the {settings.window_days}-day window "
            f"the engine enforces — those results are cut, so this search can only return "
            f"{oldest_allowed} onwards")
    if understood.asked_days and understood.asked_days > understood.window_days:
        understood.warnings.append(
            f"asked for the last {understood.asked_days} days, the window is {understood.window_days}")

    return understood

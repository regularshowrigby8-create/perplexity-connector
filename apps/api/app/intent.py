"""What the query is actually asking for.

Typing `apk` is not a search for the word "apk" — it is a request for APK files.
Typing `mediafire` is not a search for that word either; it is a request for
MediaFire. The old pipeline treated both as plain text, so `apk` matched
academic papers that happen to mention the token and `water` returned whatever
the federation had, in whatever shape.

This module reads the *shape* of a query before anything is crawled:

    parse("minecraft apk")            -> query "minecraft",  types ("apk",…)
    parse("apk")                      -> query "",           types ("apk",…)
    parse("budget csv mediafire")     -> query "budget",     types ("csv",),
                                         hosts ("mediafire.com",)

Two deliberate rules:

1. A type word is a *filter*, applied because it was typed. Nothing else is
   filtered, capped or folded — the rest of the engine's policy is untouched.
2. A host word is a *pointer*, not a filter. It aims the crawl at that host's
   own search (MediaFire, APKPure, archive.org …) and lifts those results up the
   order. It never makes the result set smaller, because a host we cannot reach
   should not turn into "no results".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# word -> the extensions it means. Families are deliberately generous: "zip"
# means any archive, "video" means any video container, and so on, because a
# person typing "zip" would not be upset to receive a .7z.
TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "pdf": ("pdf",),
    "apk": ("apk", "xapk", "apkm", "apks", "aab"),
    "exe": ("exe", "msi", "msix"),
    "dmg": ("dmg", "pkg"),
    "iso": ("iso", "img", "bin", "nrg"),
    "zip": ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"),
    "rar": ("rar",),
    "doc": ("doc", "docx", "odt", "rtf"),
    "word": ("doc", "docx", "odt", "rtf"),
    "xls": ("xls", "xlsx", "ods"),
    "excel": ("xls", "xlsx", "ods"),
    "spreadsheet": ("xls", "xlsx", "ods", "csv"),
    "ppt": ("ppt", "pptx", "odp"),
    "slides": ("ppt", "pptx", "odp"),
    "csv": ("csv", "tsv"),
    "json": ("json", "jsonl", "ndjson", "geojson"),
    "xml": ("xml", "rss", "atom", "kml"),
    "sql": ("sql", "db", "sqlite", "sqlite3", "mdb", "bak", "dump"),
    "sqlite": ("sqlite", "sqlite3", "db"),
    "epub": ("epub", "mobi", "azw3", "fb2", "djvu"),
    "ebook": ("epub", "mobi", "azw3", "fb2", "djvu", "pdf"),
    "mp3": ("mp3", "flac", "wav", "m4a", "ogg", "opus", "aac", "wma"),
    "audio": ("mp3", "flac", "wav", "m4a", "ogg", "opus", "aac", "wma"),
    "mp4": ("mp4", "mkv", "avi", "mov", "webm", "m4v", "flv", "wmv"),
    "video": ("mp4", "mkv", "avi", "mov", "webm", "m4v", "flv", "wmv"),
    "torrent": ("torrent",),
    "srt": ("srt", "vtt", "sub", "ass"),
    "psd": ("psd", "ai", "xd", "sketch", "fig"),
    "svg": ("svg",),
    "gif": ("gif", "webp"),
    "font": ("ttf", "otf", "woff", "woff2"),
    "txt": ("txt", "md", "log", "nfo"),
    "log": ("log",),
    "code": ("py", "js", "ts", "go", "rs", "java", "c", "cpp", "sh", "rb"),
    "rom": ("rom", "nes", "sfc", "gba", "gbc", "nds", "iso", "cia", "3ds"),
    "ipa": ("ipa",),
    "deb": ("deb",),
    "rpm": ("rpm",),
    "appimage": ("appimage",),
}

# word -> host domains it points at. The crawl goes there; a failure to reach it
# is reported, never turned into a smaller result set.
HOST_WORDS: dict[str, tuple[str, ...]] = {
    "mediafire": ("mediafire.com",),
    "mega": ("mega.nz", "mega.co.nz"),
    "drive": ("drive.google.com", "docs.google.com"),
    "dropbox": ("dropbox.com",),
    "onedrive": ("1drv.ms", "onedrive.live.com"),
    "archive": ("archive.org", "web.archive.org"),
    "github": ("github.com", "objects.githubusercontent.com"),
    "gitlab": ("gitlab.com",),
    "apkpure": ("apkpure.com", "apkpure.net"),
    "apkmirror": ("apkmirror.com",),
    "uptodown": ("uptodown.com",),
    "fdroid": ("f-droid.org",),
    "f-droid": ("f-droid.org",),
    "4shared": ("4shared.com",),
    "zippyshare": ("zippyshare.com",),
    "sourceforge": ("sourceforge.net",),
    "pixeldrain": ("pixeldrain.com",),
    "gofile": ("gofile.io",),
    "catbox": ("catbox.moe",),
    "itch": ("itch.io",),
    "huggingface": ("huggingface.co",),
    "zenodo": ("zenodo.org",),
    "aws": ("s3.amazonaws.com",),
    "s3": ("s3.amazonaws.com",),
}

# "google drive" is two tokens but one host.
PHRASE_HOSTS: dict[str, tuple[str, ...]] = {
    "google drive": ("drive.google.com",),
    "internet archive": ("archive.org",),
    "source forge": ("sourceforge.net",),
    "f droid": ("f-droid.org",),
}

# A page on these hosts *is* the file of that type, even when the URL has no
# extension: an APKPure app page is an APK, a F-Droid package page is an APK.
HOST_TYPE_HINTS: dict[str, str] = {
    "apkpure.com": "apk",
    "apkpure.net": "apk",
    "apkmirror.com": "apk",
    "f-droid.org": "apk",
    "uptodown.com": "apk",
    "mediafire.com": "",
    "drive.google.com": "",
    "mega.nz": "",
}

SPLIT = re.compile(r"[^a-z0-9.\-]+")


@dataclass
class Intent:
    text: str                                   # exactly what was typed
    query: str = ""                             # the words left to match
    types: list[str] = field(default_factory=list)      # extension filter
    hosts: list[str] = field(default_factory=list)      # where to aim the crawl
    matched: list[str] = field(default_factory=list)    # words that were consumed

    @property
    def wants_files(self) -> bool:
        return bool(self.types or self.hosts)

    def as_meta(self) -> dict:
        return {
            "text": self.text,
            "query": self.query,
            "types": self.types,
            "hosts": self.hosts,
            "matched": self.matched,
        }


def _normalise(word: str) -> str:
    return word.strip().strip(".").lower()


def parse(text: str) -> Intent:
    """Read the shape out of a query. Never invents a filter it was not given."""
    raw = text or ""
    lowered = raw.lower().replace("_", " ")
    intent = Intent(text=raw)

    # two-word host names first, so "google drive" is not "google" + "drive"
    for phrase, domains in PHRASE_HOSTS.items():
        if phrase in lowered:
            intent.hosts.extend(domains)
            intent.matched.append(phrase)
            lowered = lowered.replace(phrase, " ")

    words = [w for w in SPLIT.split(lowered) if w]
    kept: list[str] = []
    for word in words:
        key = _normalise(word)
        if key in TYPE_WORDS:
            intent.types.extend(TYPE_WORDS[key])
            intent.matched.append(word)
            continue
        if key in HOST_WORDS:
            intent.hosts.extend(HOST_WORDS[key])
            intent.matched.append(word)
            continue
        kept.append(word)

    intent.query = " ".join(kept).strip()
    intent.types = list(dict.fromkeys(intent.types))
    intent.hosts = list(dict.fromkeys(intent.hosts))
    return intent


def host_dork(query: str, hosts: list[str], cap: int = 6) -> str:
    """A query aimed at the hosts, for engines that only understand text."""
    if not hosts:
        return query
    sites = " OR ".join(f"site:{domain}" for domain in hosts[:cap])
    return f"{query} ({sites})".strip()


def extension_of(url: str) -> str:
    """The extension a file URL actually carries, if any."""
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    tail = path.rsplit("/", 1)[-1]
    if "." not in tail:
        return ""
    return tail.rsplit(".", 1)[-1].lower()[:8]


def matches_type(ext: object, domain: str, url: str, types: list[str]) -> bool:
    """Is this result the kind of file that was asked for?"""
    wanted = {t.lower() for t in types}
    found = str(ext or "").lower()
    if found and found in wanted:
        return True
    if not found:
        from_url = extension_of(url or "")
        if from_url and from_url in wanted:
            return True
    for host, hinted in HOST_TYPE_HINTS.items():
        if hinted and hinted in wanted and (domain or "").endswith(host):
            return True
    return False


def filter_by_type(hits: list, types: list[str]) -> tuple[list, int]:
    """Keep only the type that was asked for, and say how many were set aside.

    This is the one filter in the engine, and it only exists because the query
    asked for it (`apk`, `pdf report`, `csv mediafire`). No type word in the
    query, no filter: everything comes back as before.
    """
    if not types:
        return hits, 0
    kept = [hit for hit in hits
            if matches_type(getattr(hit, "file_ext", None),
                            getattr(hit, "domain", "") or "",
                            getattr(hit, "url", "") or "", types)]
    return kept, len(hits) - len(kept)


def boost_hosts(hits: list, hosts: list[str]) -> tuple[list, int]:
    """Lift results from the named hosts, in order, without dropping the rest."""
    if not hosts:
        return hits, 0
    wanted = tuple(hosts)

    def on_host(hit) -> bool:
        domain = getattr(hit, "domain", "") or ""
        return any(domain.endswith(host) for host in wanted)

    lifted = [hit for hit in hits if on_host(hit)]
    rest = [hit for hit in hits if not on_host(hit)]
    for hit in lifted:
        meta = getattr(hit, "meta", None)
        if isinstance(meta, dict):
            meta["host_match"] = True
    return [*lifted, *rest], len(lifted)

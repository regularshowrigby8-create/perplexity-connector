"""Dispatch layer over the parsing/extraction half of the arsenal."""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field

from .arsenal import available_ids

_READY = available_ids()
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ParsedPage:
    url: str
    title: str = ""
    links: list[str] = field(default_factory=list)
    text: str = ""
    text_engine: str = ""
    link_engine: str = ""


def _title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        return re.sub(r"\s+", " ", TAG_RE.sub("", m.group(1))).strip()[:200]
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    return re.sub(r"\s+", " ", TAG_RE.sub("", m.group(1))).strip()[:200] if m else ""


def parse_links(html: str, base: str) -> tuple[list[str], str]:
    from urllib.parse import urljoin, urlsplit

    found: list[str] = []
    engine = "regex"
    try:
        if "selectolax" in _READY:
            try:
                from selectolax.lexbor import LexborHTMLParser as HTMLParser
            except ImportError:
                from selectolax.parser import HTMLParser  # type: ignore

            tree = HTMLParser(html)
            for node in tree.css("a[href]"):
                href = node.attributes.get("href") or ""
                if href:
                    found.append(urljoin(base, href))
            engine = "selectolax"
        elif "parsel" in _READY:
            from parsel import Selector

            for href in Selector(text=html).css("a::attr(href)").getall():
                found.append(urljoin(base, href))
            engine = "parsel"
        elif "bs4" in _READY:
            from bs4 import BeautifulSoup

            for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                found.append(urljoin(base, a["href"]))
            engine = "bs4"
        else:
            for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
                found.append(urljoin(base, href))
    except Exception:
        found = [urljoin(base, h) for h in re.findall(r'href=["\']([^"\']+)["\']', html, re.I)]
        engine = "regex"

    out: list[str] = []
    seen: set[str] = set()
    for url in found:
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme not in ("http", "https") or not parts.netloc:
            continue
        clean = url.split("#", 1)[0]
        if clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out, engine


def extract_text(html: str, url: str) -> tuple[str, str]:
    """Try the extraction chain in order; return (text, engine_used)."""
    html = html[:1_800_000]

    if "trafilatura" in _READY:
        try:
            import trafilatura

            text = trafilatura.extract(html, url=url, include_comments=False,
                                       include_tables=True, favor_precision=True)
            if text and len(text) > 120:
                return text.strip(), "trafilatura"
        except Exception:
            pass

    if "readability" in _READY:
        try:
            from readability import Document

            summary = Document(html).summary()
            text = re.sub(r"\s+", " ", TAG_RE.sub(" ", summary)).strip()
            if len(text) > 120:
                return text, "readability"
        except Exception:
            pass

    if "justext" in _READY:
        try:
            import justext

            paras = justext.justext(html, justext.get_stoplist("English"))
            text = "\n".join(p.text for p in paras if not p.is_boilerplate)
            if len(text) > 120:
                return text, "justext"
        except Exception:
            pass

    if "newspaper" in _READY:
        try:
            from newspaper import Article

            art = Article(url)
            art.download(input_html=html)
            art.parse()
            if art.text and len(art.text) > 120:
                return art.text, "newspaper3k"
        except Exception:
            pass

    if "boilerpy3" in _READY:
        try:
            from boilerpy3 import extractors

            text = extractors.ArticleExtractor().get_content(html)
            if text and len(text) > 120:
                return text.strip(), "boilerpy3"
        except Exception:
            pass

    if "html2text" in _READY:
        try:
            import html2text as h2t

            text = h2t.HTML2Text().handle(html)
            if len(text) > 80:
                return text.strip(), "html2text"
        except Exception:
            pass

    if "bs4" in _READY:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
            return text, "bs4"
        except Exception:
            pass

    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html)).strip(), "regex"


def file_text(data: bytes, filename: str, mime: str | None = None) -> tuple[str, str]:
    """Extract text from a downloaded file using the files tier of the arsenal."""
    name = filename.lower()
    if data[:5] == b"%PDF-" or name.endswith(".pdf"):
        if "pypdf" in _READY:
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(data))
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:60])
                if len(text.strip()) > 30:
                    return text.strip(), "pypdf"
            except Exception:
                pass
        if "pdfminer" in _READY:
            try:
                from pdfminer.high_level import extract_text as pdfminer_extract

                text = pdfminer_extract(io.BytesIO(data))
                if len(text.strip()) > 30:
                    return text.strip(), "pdfminer.six"
            except Exception:
                pass
        return "", ""

    if name.endswith((".xlsx", ".xlsm")) and "openpyxl" in _READY:
        try:
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            rows = []
            for sheet in wb.worksheets[:4]:
                for row in list(sheet.iter_rows(values_only=True))[:400]:
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        rows.append(" | ".join(cells))
            return "\n".join(rows), "openpyxl"
        except Exception:
            return "", ""

    if name.endswith(".docx") and "docx" in _READY:
        try:
            import docx

            doc = docx.Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return text, "python-docx"
        except Exception:
            return "", ""

    if name.endswith((".zip", ".jar", ".docx", ".xlsx", ".pptx")):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()[:120]
                texts = []
                for info in zf.infolist()[:6]:
                    if info.file_size < 400_000 and info.filename.lower().endswith(
                            (".txt", ".csv", ".json", ".md", ".html", ".xml")):
                        try:
                            texts.append(f"[{info.filename}]\n" +
                                         zf.read(info).decode("utf-8", "replace")[:20_000])
                        except Exception:
                            continue
                listing = "Archive contents: " + ", ".join(names)
                return (listing + ("\n\n" + "\n\n".join(texts) if texts else "")), "zipfile"
        except Exception:
            return "", ""

    if name.endswith((".csv", ".tsv", ".json", ".jsonl", ".txt", ".md", ".xml", ".yml", ".yaml",
                      ".sql", ".log", ".env", ".ini", ".conf")):
        try:
            return data.decode("utf-8", "replace")[:200_000], "text/decode"
        except Exception:
            return "", ""

    if name.endswith((".html", ".htm")):
        return extract_text(data.decode("utf-8", "replace"), "")

    return "", ""


def meta_extract(html: str) -> dict:
    """Structured metadata: JSON-LD, OpenGraph, feeds."""
    out: dict = {}
    if "extruct" in _READY:
        try:
            import extruct

            data = extruct.extract(html, syntaxes=["json-ld", "opengraph"])
            if data.get("json-ld"):
                out["json_ld"] = len(data["json-ld"])
                first = data["json-ld"][0]
                for key in ("name", "title", "description"):
                    if first.get(key):
                        out.setdefault("title", str(first[key])[:200])
                        break
            og = data.get("opengraph") or []
            if og:
                props = og[0].get("properties") or {}
                out.setdefault("title", (props.get("og:title") or [""])[0][:200])
                out["og_site"] = (props.get("og:site_name") or [""])[0]
        except Exception:
            pass
    if "feedparser" in _READY and ("<rss" in html[:2000] or "<feed" in html[:2000]):
        try:
            import feedparser

            feed = feedparser.parse(html)
            out["feed_items"] = len(feed.entries)
            out["feed_title"] = getattr(feed.feed, "title", "")
        except Exception:
            pass
    return out

import html
import re
from urllib.error import URLError
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from miskit.tool import Tool

_USER_AGENT = "MiskitWebSearch/0.1 (+https://github.com/RetroTho/miskit)"

_RESULT_LINK_RE = re.compile(
    r"""<a[^>]*?\b(?:href="(?P<h1>//duckduckgo\.com/l/\?[^"]+)"[^>]*class='result-link'"""
    r"""|class='result-link'[^>]*href="(?P<h2>//duckduckgo\.com/l/\?[^"]+)")[^>]*>(?P<title>.*?)</a>""",
    re.DOTALL | re.IGNORECASE,
)

_SNIPPET_RE = re.compile(
    r"<td class='result-snippet'>(.*?)</td>",
    re.DOTALL | re.IGNORECASE,
)


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web with DuckDuckGo and return a short list of results "
        "(title, URL, and snippet). Useful for facts, docs, news, or anything not in conversation context."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
        },
        "required": ["query"],
    }

    def __init__(self, max_results=5, timeout=30):
        self.max_results = max_results
        self.timeout = timeout

    def run(self, arguments):
        query = str(arguments.get("query", "")).strip()
        if not query:
            return "Web search requires a query."

        url = "https://lite.duckduckgo.com/lite/?q=" + quote_plus(query)
        request = Request(url, headers={"User-Agent": _USER_AGENT})

        try:
            with urlopen(request, timeout=self.timeout) as response:
                page = response.read().decode("utf-8", errors="replace")
        except URLError as error:
            return f"Web search failed: {error.reason if hasattr(error, 'reason') else error}"

        results = _parse_lite_results(page, self.max_results)
        if not results:
            return "No web search results found."

        lines = []
        for index, entry in enumerate(results, start=1):
            lines.append(f"{index}. {entry['title']}")
            lines.append(f"   URL: {entry['url']}")
            lines.append(f"   {entry['snippet']}")
            lines.append("")
        return "\n".join(lines).rstrip()


def _strip_markup(fragment):
    text = html.unescape(fragment)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split()).strip()


def _destination_url(href):
    href = href.replace("&amp;", "&")
    match = re.search(r"uddg=([^&]+)", href)
    if not match:
        return None
    target = unquote(match.group(1))
    hostname = urlparse(target).hostname
    if not hostname:
        return None
    hostname = hostname.lower()
    # Skip sponsored/DuckDuckGo internal redirects; organic results leave DDG hosts.
    if hostname == "duckduckgo.com" or hostname.endswith(".duckduckgo.com"):
        return None
    return target


def _parse_lite_results(page, max_results):
    results = []
    seen = set()

    for match in _RESULT_LINK_RE.finditer(page):
        href = match.group("h1") or match.group("h2")
        title = _strip_markup(match.group("title"))
        target = _destination_url(href)
        if not target or not title or target in seen:
            continue

        snippet_match = _SNIPPET_RE.search(page, match.end(), match.end() + 4000)
        snippet = _strip_markup(snippet_match.group(1)) if snippet_match else ""

        seen.add(target)
        results.append({"title": title, "url": target, "snippet": snippet})
        if len(results) >= max_results:
            break

    return results


def create_tool(config, services=None):
    max_results = int(config.get("maxResults", 5))
    timeout = float(config.get("timeout", 30))
    return WebSearchTool(max_results=max_results, timeout=timeout)

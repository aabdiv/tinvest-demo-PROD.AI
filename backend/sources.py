"""Bounded reading of public news pages; video URLs require a transcript."""
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Нужна публичная ссылка http:// или https:// без логина и пароля.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Этот порт ссылки не поддерживается.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("Не удалось найти сайт. Вставьте текст новости.") from exc
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Можно читать только публичные сайты.")
    return parsed


def video_url(url):
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ("tiktok.com", "youtube.com", "youtu.be", "rutube.ru"))


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def read_article(url):
    if video_url(url):
        return {"url": url, "status": "needs_transcript", "text": "", "notice": "Для видео нужен текст или расшифровка. Сама ссылка не содержит доступного нам содержания ролика."}
    try:
        with httpx.Client(timeout=10, follow_redirects=False, headers={"User-Agent": "PortfolioResearch/1.0"}) as client:
            for _ in range(4):
                public_url(url)
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type and "text/plain" not in content_type:
                        raise ValueError("У ссылки нет доступного текста статьи.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 1_000_000:
                            raise ValueError("Статья слишком большая. Вставьте нужный отрывок.")
                    text = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                    if "text/html" in content_type:
                        parser = ArticleParser()
                        parser.feed(text)
                        text = "\n".join(parser.parts)
                    text = re.sub(r"[ \t]+", " ", text).strip()[:16000]
                    if len(text) < 100:
                        raise ValueError("Сайт не отдал текст статьи. Вставьте его вручную.")
                    return {"url": url, "status": "read", "text": text, "notice": "Текст страницы прочитан. Достоверность новости отдельно не проверена."}
            raise ValueError("Слишком много перенаправлений. Вставьте текст новости.")
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return {"url": url, "status": "unavailable", "text": "", "notice": str(exc) if isinstance(exc, ValueError) else "Сайт не отдал статью. Вставьте текст новости вручную."}

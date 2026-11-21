"""Notify a Discord channel when Dokkaebi's World news posts appear.

Source: munpa.kr, an unofficial fan aggregator, linking back to official Kakao Games posts.
"""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("📢 공지사항", "notice", "https://munpa.kr/news?b=notice"),
    ("🎁 이벤트", "event", "https://munpa.kr/news?b=event&ended=1"),
]
STATE_FILE = Path("seen_posts.json")
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"].strip().removesuffix("/github")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DokkaebiDiscordNotifier/1.0)"}


def fetch_posts():
    posts = []
    for label, board, source in SOURCES:
        response = requests.get(source, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        count = 0
        for anchor in soup.select("a[href]"):
            link = urljoin(source, anchor["href"])
            parsed = urlparse(link)
            params = parse_qs(parsed.query)

            if parsed.hostname == "bbs.kakaogames.com":
                valid = (
                    parsed.path.startswith("/ko/1329429/")
                    and f"/{board}/detail" in parsed.path
                    and bool(params.get("id"))
                )
            elif parsed.hostname in {"forum.kakaogames.com", "m-forum.kakaogames.com"}:
                valid = (
                    parsed.path.startswith("/dokkaebi/postView/")
                    and params.get("code") == [board]
                    and bool(params.get("id"))
                )
            else:
                valid = False

            title = anchor.get_text(" ", strip=True)
            if valid and title:
                posts.append((label, title, link))
                count += 1
        if count == 0:
            raise RuntimeError(f"게시글을 읽지 못했습니다. 사이트 구조 확인 필요: {source}")

    # Remove duplicate entries (e.g., featured posts that also appear in the list).
    return list(dict.fromkeys(posts))


def send_discord(message=None, post=None):
    payload = {
        "username": "도깨비의세계 새소식",
        "allowed_mentions": {"parse": []},
    }
    if message:
        payload["content"] = message
    if post:
        label, title, url = post
        payload["embeds"] = [{
            "title": title[:256],
            "url": url,
            "description": label + " · 공식 글 바로가기",
            "color": 0x5865F2,
        }]
    response = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    response.raise_for_status()


def save_state(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    posts = fetch_posts()
    current_urls = {url for _, _, url in posts}

    if not STATE_FILE.exists():
        # Avoid dumping all old news into Discord on the first run.
        send_discord(message="✅ 도깨비의세계 공지·이벤트 알림 연결 완료! 이제 새 글부터 전송됩니다.")
        save_state(current_urls)
        print(f"Initialized with {len(current_urls)} existing posts")
        return

    seen = set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    new_posts = [post for post in reversed(posts) if post[2] not in seen]
    for post in new_posts:
        send_discord(post=post)
        seen.add(post[2])
        # Save after each successful notification.
        save_state(seen)
        print(f"Sent: {post[1]}")
    print(f"Found {len(new_posts)} new posts")


if __name__ == "__main__":
    main()

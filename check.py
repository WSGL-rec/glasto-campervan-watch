"""Watch Glastonbury's website for the 2027 campervan / accommodation sale announcement.

Runs in GitHub Actions every 5 minutes. When it finds something, it opens a
GitHub issue that @mentions the owner, so GitHub emails them and pushes a
notification to the GitHub mobile app.
"""

import html
import json
import os
import re
import sys
import time
import urllib.request

NEWS_URL = "https://www.glastonburyfestivals.co.uk/news/"
INFO_URL = "https://www.glastonburyfestivals.co.uk/info/"
STATE_FILE = "state.json"
OWNER_HANDLE = "@WSGL-rec"

KEYWORDS = re.compile(
    r"campervan|camper van|caravan|accommodation|worthy view|sticklinch|tipi",
    re.I,
)
# Wording on the info page while no sale date has been announced.
BASELINE_PHRASE = re.compile(r"later\s+in\s+(the\s+)?autumn", re.I)

SKIP_SLUGS = {"page", "category", "author", "feed", "tag"}
UA = "Mozilla/5.0 (glasto-campervan-watch; personal alert bot, checks every 5 min)"


def fetch(url):
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Could not fetch {url}: {last_err}")


def to_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def news_posts(page):
    """Return {slug: title} for news post links on the news page."""
    posts = {}
    pattern = re.compile(
        r'<a[^>]+href="https?://(?:www\.)?glastonburyfestivals\.co\.uk/news/([a-z0-9-]+)/?"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    for slug, inner in pattern.findall(page):
        if slug in SKIP_SLUGS:
            continue
        title = to_text(inner)
        if title and len(title) > len(posts.get(slug, "")):
            posts[slug] = title
        else:
            posts.setdefault(slug, title)
    return posts


def post_content(slug):
    page = fetch(f"{NEWS_URL}{slug}/")
    title_m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", page) or re.search(
        r"(?is)<title>(.*?)</title>", page
    )
    title = to_text(title_m.group(1)) if title_m else slug.replace("-", " ")
    body_m = re.search(r'(?is)<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>(.*)', page) or re.search(
        r"(?is)<article[^>]*>(.*?)</article>", page
    )
    body = to_text(body_m.group(1))[:6000] if body_m else ""
    return title, body


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def open_issue(title, body):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print(f"[dry run] would open issue: {title}\n{body}")
        return
    data = json.dumps({"title": title, "body": body}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Opened issue:", json.load(r)["html_url"])


def alert(state, key, title, lines):
    alerted = state.setdefault("alerted", [])
    if key in alerted:
        print("Already alerted:", key)
        return
    body = "\n".join(
        [
            f"{OWNER_HANDLE} 🚨 **Glastonbury campervan / accommodation update spotted**",
            "",
            *lines,
            "",
            "Buy at https://glastonbury.seetickets.com (you need your general admission booking reference).",
            "Official news page: " + NEWS_URL,
        ]
    )
    open_issue(f"🚐 GLASTONBURY CAMPERVAN TICKETS – {title}"[:240], body)
    alerted.append(key)


def main():
    state = load_state()

    if os.environ.get("TEST_ALERT") == "1":
        open_issue(
            "🚐 TEST – Glastonbury campervan alert",
            f"{OWNER_HANDLE} This is a test. If you got this as an email and a GitHub app "
            "notification, your alerts are working. Nothing has been announced yet. "
            "You can close this issue.",
        )
        return

    if os.environ.get("SIMULATE_UPDATE") == "1":
        # Runs the real alert path with a made-up post; nothing is saved.
        alert(
            {},
            "simulated",
            "[SIMULATED] Accommodation goes on sale Thursday 12th November",
            [
                "⚠️ **SIMULATED TEST – this is not a real announcement.** "
                "A real alert will look exactly like this.",
                "",
                f"**New post:** [Accommodation goes on sale Thursday 12th November]({NEWS_URL})",
                "",
                "> For those who secured a Glastonbury 2027 ticket in the sales earlier this month, "
                "bookings for caravan/campervan tickets, onsite tipis and the official offsite "
                "pre-erected campsites will open at 12 noon (GMT) on Thursday 12th November.",
            ],
        )
        return

    first_run = "seen" not in state

    try:
        news = news_posts(fetch(NEWS_URL))
    except RuntimeError as e:
        print("WARNING:", e)
        news = None

    try:
        info_text = to_text(fetch(INFO_URL))
    except RuntimeError as e:
        print("WARNING:", e)
        info_text = None

    # --- News page: any new post about campervans / accommodation ---
    if news:
        seen = set(state.get("seen", []))
        new_slugs = [s for s in news if s not in seen]
        print(f"News posts on page: {len(news)}, new: {len(new_slugs)}")
        if not first_run:
            for slug in new_slugs:
                try:
                    title, body = post_content(slug)
                except RuntimeError as e:
                    print("WARNING:", e)
                    continue  # retry next run (not marked seen)
                title = news.get(slug) or title
                print("New post:", title)
                if KEYWORDS.search(title) or KEYWORDS.search(body):
                    m = KEYWORDS.search(body)
                    snippet = ""
                    if m:
                        start = max(0, m.start() - 250)
                        snippet = body[start : m.end() + 350]
                    alert(
                        state,
                        f"news:{slug}",
                        title,
                        [
                            f"**New post:** [{title}]({NEWS_URL}{slug}/)",
                            "",
                            f"> {snippet}" if snippet else "",
                        ],
                    )
                seen.add(slug)
        else:
            seen.update(new_slugs)
        state["seen"] = sorted(seen | set(news))

    # --- Info page: 'later in the autumn' wording disappears ---
    if info_text and re.search(r"campervan", info_text, re.I):
        count = len(BASELINE_PHRASE.findall(info_text))
        print("'later in the autumn' mentions on info page:", count)
        baseline = state.get("info_baseline")
        if baseline is None:
            state["info_baseline"] = count
        elif count < baseline:
            m = re.search(r"(?i)campervan/caravan tickets[^.]{0,300}\.", info_text)
            alert(
                state,
                "info:wording-changed",
                "Info page wording changed",
                [
                    "The campervan section on the official info page no longer says "
                    "tickets will go on sale 'later in the autumn'. A date may have been added.",
                    "",
                    f"> {m.group(0)}" if m else "",
                    "",
                    f"Check: {INFO_URL}#accommodation",
                ],
            )

    if first_run:
        print("First run: baseline saved, no alerts sent.")
    save_state(state)


if __name__ == "__main__":
    sys.exit(main())

"""
Scholar News - 매일 자동 논문 수집 & HTML 뉴스레터 생성
arXiv + Semantic Scholar API 사용 (무료, API 키 불필요)
"""

import os
import json
import time
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

from config import KEYWORDS, PAPERS_PER_KEYWORD, ARXIV_DAYS, DOCS_DIR, SITE_TITLE, SITE_SUBTITLE

# ─────────────────────────────────────────────
# 1. 데이터 수집
# ─────────────────────────────────────────────

def fetch_arxiv(keyword: str, max_results: int = PAPERS_PER_KEYWORD) -> list[dict]:
    """arXiv API에서 최신 논문 가져오기 (관련 카테고리만)"""
    # 농업/원격탐사/이미지처리/생물 관련 카테고리만 검색
    CAT_FILTER = "(cat:cs.CV OR cat:eess.IV OR cat:eess.SP OR cat:q-bio.QM OR cat:cs.LG)"
    query = urllib.parse.quote(f"{CAT_FILTER} AND all:{keyword}")
    url = (
        f"http://export.arxiv.org/api/query"
        f"?search_query={query}"
        f"&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        cutoff = datetime.now(timezone.utc) - timedelta(days=ARXIV_DAYS)
        papers = []

        for entry in root.findall("atom:entry", ns):
            published_str = entry.find("atom:published", ns).text[:10]
            published_dt = datetime.fromisoformat(published_str).replace(tzinfo=timezone.utc)
            if published_dt < cutoff:
                continue

            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
            link = entry.find("atom:id", ns).text.strip()
            authors = [
                a.find("atom:name", ns).text
                for a in entry.findall("atom:author", ns)
            ]

            papers.append({
                "title": title,
                "abstract": abstract,
                "url": link,
                "authors": authors[:4],  # 최대 4명
                "published": published_str,
                "source": "arXiv",
                "citations": None,
            })
        return papers

    except Exception as e:
        print(f"  [arXiv 오류] '{keyword}': {e}")
        return []


def fetch_semantic_scholar(keyword: str, limit: int = PAPERS_PER_KEYWORD) -> list[dict]:
    """Semantic Scholar API에서 논문 가져오기"""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": keyword,
        "fields": "title,abstract,authors,year,publicationDate,citationCount,externalIds,openAccessPdf",
        "limit": limit,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])

        papers = []
        cutoff_year = datetime.now().year - 1  # 작년 이후

        for p in data:
            year = p.get("year") or 0
            if year < cutoff_year:
                continue

            pub_date = p.get("publicationDate") or str(year)
            authors = [a["name"] for a in p.get("authors", [])[:4]]

            # 링크 결정: openAccess > DOI > S2 페이지
            pdf = p.get("openAccessPdf")
            ext_ids = p.get("externalIds") or {}
            if pdf and pdf.get("url"):
                link = pdf["url"]
            elif ext_ids.get("DOI"):
                link = f"https://doi.org/{ext_ids['DOI']}"
            else:
                link = f"https://www.semanticscholar.org/paper/{p['paperId']}"

            papers.append({
                "title": p.get("title", "").strip(),
                "abstract": (p.get("abstract") or "Abstract not available.").strip(),
                "url": link,
                "authors": authors,
                "published": pub_date[:10] if len(pub_date) >= 10 else pub_date,
                "source": "Semantic Scholar",
                "citations": p.get("citationCount"),
            })
        return papers

    except Exception as e:
        print(f"  [Semantic Scholar 오류] '{keyword}': {e}")
        return []


def collect_all_papers() -> dict[str, list[dict]]:
    """모든 키워드에 대해 arXiv + Semantic Scholar 수집, 중복 제거"""
    results = {}
    seen_titles = set()

    for kw in KEYWORDS:
        print(f"\n[수집 중] {kw}")
        papers = []

        arxiv = fetch_arxiv(kw)
        print(f"  arXiv: {len(arxiv)}건")
        time.sleep(1)

        ss = fetch_semantic_scholar(kw)
        print(f"  Semantic Scholar: {len(ss)}건")
        time.sleep(1.5)

        for p in arxiv + ss:
            title_key = p["title"].lower()[:60]
            if title_key not in seen_titles and p["title"]:
                seen_titles.add(title_key)
                papers.append(p)

        results[kw] = papers
        print(f"  → 최종 {len(papers)}건 (중복 제거 후)")

    return results


# ─────────────────────────────────────────────
# 2. HTML 생성
# ─────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #222; }
header { background: linear-gradient(135deg, #1a3a5c, #2e6da4); color: white; padding: 36px 24px 28px; text-align: center; }
header h1 { font-size: 1.8rem; font-weight: 700; letter-spacing: 0.5px; }
header p { margin-top: 8px; font-size: 0.95rem; opacity: 0.85; }
.date-badge { display: inline-block; margin-top: 12px; background: rgba(255,255,255,0.2); border-radius: 20px; padding: 4px 16px; font-size: 0.85rem; }
.container { max-width: 900px; margin: 0 auto; padding: 24px 16px 60px; }
.keyword-section { margin-bottom: 36px; }
.keyword-title { font-size: 1.05rem; font-weight: 700; color: #1a3a5c; border-left: 4px solid #2e6da4; padding-left: 12px; margin-bottom: 14px; }
.paper-card { background: white; border-radius: 10px; padding: 18px 20px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border: 1px solid #e8edf2; }
.paper-title { font-size: 0.97rem; font-weight: 600; margin-bottom: 6px; }
.paper-title a { color: #1a3a5c; text-decoration: none; }
.paper-title a:hover { text-decoration: underline; color: #2e6da4; }
.paper-meta { font-size: 0.78rem; color: #666; margin-bottom: 8px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
.badge-arxiv { background: #fff0f0; color: #c0392b; border: 1px solid #f5c6c6; }
.badge-ss { background: #e8f4fd; color: #1a6fa8; border: 1px solid #b3d7f0; }
.paper-abstract { font-size: 0.83rem; color: #444; line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.no-papers { color: #999; font-size: 0.87rem; padding: 12px; }
footer { text-align: center; color: #aaa; font-size: 0.78rem; padding: 24px; }
.nav-link { display: inline-block; margin: 0 8px; color: #2e6da4; text-decoration: none; font-size: 0.85rem; }
.nav-link:hover { text-decoration: underline; }
"""


def paper_card_html(paper: dict) -> str:
    source = paper["source"]
    badge_cls = "badge-arxiv" if source == "arXiv" else "badge-ss"
    authors_str = ", ".join(paper["authors"]) if paper["authors"] else "Unknown"
    if len(paper["authors"]) == 4:
        authors_str += " et al."
    citations = f"· 피인용 {paper['citations']}회" if paper.get("citations") is not None else ""
    abstract = paper["abstract"][:300] + "..." if len(paper["abstract"]) > 300 else paper["abstract"]

    return f"""
    <div class="paper-card">
      <div class="paper-title"><a href="{paper['url']}" target="_blank">{paper['title']}</a></div>
      <div class="paper-meta">
        <span class="badge {badge_cls}">{source}</span>
        <span>{paper['published']}</span>
        <span>{authors_str}</span>
        {f'<span>{citations}</span>' if citations else ''}
      </div>
      <div class="paper-abstract">{abstract}</div>
    </div>"""


def generate_daily_html(results: dict[str, list[dict]], date_str: str) -> str:
    sections = ""
    total = 0
    for kw, papers in results.items():
        cards = "".join(paper_card_html(p) for p in papers) if papers else '<p class="no-papers">오늘 새 논문 없음</p>'
        total += len(papers)
        sections += f"""
        <div class="keyword-section">
          <div class="keyword-title">🔍 {kw}</div>
          {cards}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{SITE_TITLE} — {date_str}</title>
  <style>{CSS}
#google_translate_element {{ margin-top: 12px; }}
.goog-te-gadget {{ color: rgba(255,255,255,0.7) !important; font-size: 0.75rem !important; }}
.goog-te-gadget select {{ background: rgba(255,255,255,0.15); color: white; border: 1px solid rgba(255,255,255,0.4); border-radius: 6px; padding: 4px 8px; font-size: 0.82rem; cursor: pointer; }}
</style>
</head>
<body>
  <header>
    <h1>📰 {SITE_TITLE}</h1>
    <p>{SITE_SUBTITLE}</p>
    <div class="date-badge">{date_str} · 총 {total}건</div>
    <div id="google_translate_element"></div>
  </header>
  <script>
  function googleTranslateElementInit() {{
    new google.translate.TranslateElement({{pageLanguage: 'en', includedLanguages: 'ko', autoDisplay: false}}, 'google_translate_element');
  }}
  </script>
  <script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
  <div class="container">
    <p style="text-align:right; margin-bottom:16px;">
      <a class="nav-link" href="index.html">← 전체 목록</a>
    </p>
    {sections}
  </div>
  <footer>자동 생성 by Scholar News · {date_str}</footer>
</body>
</html>"""


def update_index_html(docs_dir: str):
    """docs/index.html — 날짜별 뉴스레터 목록 자동 갱신"""
    newsletters = sorted(
        [f for f in os.listdir(docs_dir) if f.endswith(".html") and f != "index.html"],
        reverse=True,
    )
    items = ""
    for fname in newsletters:
        date_label = fname.replace(".html", "")
        items += f'<li><a href="{fname}">📄 {date_label}</a></li>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{SITE_TITLE}</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #222; }}
    header {{ background: linear-gradient(135deg, #1a3a5c, #2e6da4); color: white; padding: 40px 24px; text-align: center; }}
    header h1 {{ font-size: 2rem; }}
    header p {{ margin-top: 10px; opacity: 0.85; }}
    .container {{ max-width: 600px; margin: 40px auto; padding: 0 16px; }}
    ul {{ list-style: none; }}
    li {{ margin-bottom: 12px; }}
    li a {{ display: block; background: white; padding: 14px 20px; border-radius: 10px; text-decoration: none; color: #1a3a5c; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border: 1px solid #e8edf2; }}
    li a:hover {{ background: #e8f4fd; }}
    footer {{ text-align: center; color: #aaa; font-size: 0.78rem; padding: 32px; }}
    #google_translate_element {{ margin-top: 12px; }}
    .goog-te-gadget {{ color: rgba(255,255,255,0.7) !important; font-size: 0.75rem !important; }}
    .goog-te-gadget select {{ background: rgba(255,255,255,0.15); color: white; border: 1px solid rgba(255,255,255,0.4); border-radius: 6px; padding: 4px 8px; font-size: 0.82rem; cursor: pointer; }}
  </style>
</head>
<body>
  <header>
    <h1>📰 {SITE_TITLE}</h1>
    <p>{SITE_SUBTITLE}</p>
    <div id="google_translate_element"></div>
  </header>
  <script>
  function googleTranslateElementInit() {{
    new google.translate.TranslateElement({{pageLanguage: 'en', includedLanguages: 'ko', autoDisplay: false}}, 'google_translate_element');
  }}
  </script>
  <script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
  <div class="container">
    <h2 style="margin-bottom:20px; color:#1a3a5c;">뉴스레터 목록</h2>
    <ul>{items}</ul>
  </div>
  <footer>Scholar News · Hoonsoo Lee (CBNU / UIUC)</footer>
</body>
</html>"""

    with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("  index.html 업데이트 완료")


# ─────────────────────────────────────────────
# 3. GitHub 자동 push
# ─────────────────────────────────────────────

def git_push(date_str: str):
    cmds = [
        ["git", "add", "docs/"],
        ["git", "commit", "-m", f"newsletter: {date_str}"],
        ["git", "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [git 경고] {' '.join(cmd)}\n  {result.stderr.strip()}")
        else:
            print(f"  ✓ {' '.join(cmd)}")


# ─────────────────────────────────────────────
# 4. 메인
# ─────────────────────────────────────────────

def main():
    # GitHub Actions에서 실행 시 UTC 기준 → KST 변환
    is_ci = os.environ.get("CI") == "true"
    if is_ci:
        date_str = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f" Scholar News 실행 — {date_str} {'(GitHub Actions)' if is_ci else '(로컬)'}")
    print(f"{'='*50}")

    # docs 폴더 생성
    os.makedirs(DOCS_DIR, exist_ok=True)

    # 논문 수집
    results = collect_all_papers()

    # 오늘 뉴스레터 HTML 저장
    daily_html = generate_daily_html(results, date_str)
    daily_path = os.path.join(DOCS_DIR, f"{date_str}.html")
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_html)
    print(f"\n✓ 뉴스레터 저장: {daily_path}")

    # 인덱스 업데이트
    update_index_html(DOCS_DIR)

    # 로컬 실행 시에만 git push (GitHub Actions는 워크플로우가 처리)
    if not is_ci:
        print("\n[GitHub push 중...]")
        git_push(date_str)

    print(f"\n완료! 사이트: https://hoonsoolee.github.io/Scholar_news/")


if __name__ == "__main__":
    main()

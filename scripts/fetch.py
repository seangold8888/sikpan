# -*- coding: utf-8 -*-
"""오늘의 구내식당 메뉴판 사진과 식당 정보를 수집한다.

출처: https://koreaward-6.github.io/ 가 가산 구내식당들의 카카오톡 채널 게시물을
      매일 취합해 한 페이지로 올려둔다. 여기서 식당명·주소·길찾기 링크·메뉴판
      이미지 주소를 뽑아 쓴다.

결과: data/sources.json  (식당 목록 + 메뉴판 사진 주소)
      cache/img/<id>.jpg  (판독용 사본. 사이트는 카카오 CDN 주소를 그대로 쓰므로
                           이 사본은 저장소에 넣지 않는다)
"""
import hashlib
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_URL = "https://koreaward-6.github.io/"
UA = "Mozilla/5.0 (compatible; gasan-lunch/1.0; +https://github.com/seangold8888/gasan-lunch)"

CARD_RE = re.compile(
    r"<div class='cafeteria-card'>(.*?)</div>\s*(?=<div class='cafeteria-card'>|</div>)",
    re.S,
)
NAME_RE = re.compile(r"class='name-link' href='([^']*)'[^>]*>\s*(.*?)\s*</a>", re.S)
ADDR_RE = re.compile(r"class='address-link' href='([^']*)'[^>]*>\s*(.*?)\s*</a>", re.S)
IMG_RE = re.compile(r"class='menu-image' src='([^']*)'")
DATE_RE = re.compile(r'<div class="date">\s*(.*?)\s*</div>', re.S)


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    return raw if binary else raw.decode("utf-8", "replace")


def slug(name):
    """식당명을 안정적인 파일명 id 로. 한글이 섞이므로 해시를 접미사로 붙인다."""
    ascii_part = re.sub(r"[^a-z0-9]+", "", name.lower())[:12]
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{ascii_part}_{h}" if ascii_part else h


def main():
    html = get(SRC_URL)

    m = DATE_RE.search(html)
    source_date = m.group(1) if m else None

    cards = []
    for block in CARD_RE.findall(html):
        nm = NAME_RE.search(block)
        if not nm:
            continue
        channel, name = nm.group(1), re.sub(r"\s+", " ", nm.group(2))
        im = IMG_RE.search(block)
        ad = ADDR_RE.search(block)
        cards.append(
            {
                "id": slug(name),
                "ko": name,
                "channel": channel,
                "directions": ad.group(1) if ad else None,
                "address": re.sub(r"\s+", " ", ad.group(2)) if ad else None,
                "imgUrl": im.group(1) if im else None,
            }
        )

    if not cards:
        print("ERROR: no cafeteria cards parsed - source layout may have changed", file=sys.stderr)
        return 2

    imgdir = ROOT / "cache" / "img"
    imgdir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for c in cards:
        if not c["imgUrl"]:
            c["img"] = None
            c["sha"] = None
            continue
        try:
            blob = get(c["imgUrl"], binary=True)
        except Exception as e:  # 한 곳이 실패해도 나머지는 계속
            print(f"  ! {c['ko']}: download failed ({e})", file=sys.stderr)
            c["img"], c["sha"] = None, None
            continue
        c["sha"] = hashlib.sha256(blob).hexdigest()
        fn = f"{c['id']}.jpg"
        (imgdir / fn).write_bytes(blob)
        c["img"] = fn
        ok += 1

    out = {
        "sourceUrl": SRC_URL,
        "sourceDate": source_date,
        "restaurants": cards,
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "sources.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"parsed {len(cards)} cafeterias, downloaded {ok} menu photos (source date: {source_date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

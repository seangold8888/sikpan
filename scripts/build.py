# -*- coding: utf-8 -*-
"""수집한 정보와 판독 결과를 합쳐 docs/index.html 을 만든다.

--inline 을 주면 사진을 파일 안에 박아 넣은 사본을 dist/artifact.html 로 함께 만든다.
바깥 주소를 못 부르는 곳(예: 아티팩트)에 올릴 때 쓴다.
"""
import base64
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KST = datetime.timezone(datetime.timedelta(hours=9))

# 메뉴 이름에서 매운 음식을 짐작한다. 어디까지나 참고 표시이고, 페이지에도 그렇게 적어둔다.
SPICY_KW = ["고추장", "매콤", "매운", "얼큰", "불닭", "청양", "칠리", "마파", "짬뽕",
            "떡볶이", "김치찌", "닭볶음탕", "부대찌개", "닭개장", "제육", "낙지볶음", "쭈꾸미"]

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def source_date_to_iso(text):
    """'2026년 08월 27일 (목)' -> date, 못 읽으면 None"""
    if not text:
        return None
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


MD_RE = re.compile(r"(\d{1,2})\s*[월/]\s*(\d{1,2})")


def board_covers_today(date_shown, today):
    """메뉴판에 적힌 날짜가 오늘인지 본다.

    실제로 어제 메뉴가 그대로 걸려 있거나 내일 것이 먼저 올라오는 일이 있어서,
    믿고 갔다가 헛걸음하지 않도록 확인한다. 날짜를 못 읽으면 None(판단 보류).
    """
    if not date_shown:
        return None
    found = [(int(a), int(b)) for a, b in MD_RE.findall(date_shown)]
    if not found:
        return None
    if (today.month, today.day) in found:
        return True
    # 주간 식단표는 '8월 24일 ~ 8월 28일' 처럼 범위로 적힌다.
    if len(found) >= 2:
        try:
            lo = datetime.date(today.year, *found[0])
            hi = datetime.date(today.year, *found[-1])
            if lo <= today <= hi:
                return True
        except ValueError:
            pass
    return False


MONTH_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_md(text):
    """메뉴판에 적힌 날짜를 한국어/영어 두 가지로. 못 읽으면 원문 그대로."""
    m = MD_RE.search(text or "")
    if not m:
        return (text or ""), (text or "")
    mo, day = int(m.group(1)), int(m.group(2))
    return f"{mo}월 {day}일", f"{MONTH_EN[mo] if 1 <= mo <= 12 else mo} {day}"


def main():
    src = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    places_file = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    places = places_file.get("places", {})
    extras = places_file.get("extras", [])
    cache = ROOT / "cache" / "ocr"

    now = datetime.datetime.now(KST)
    today = now.date()
    sdate = source_date_to_iso(src.get("sourceDate"))

    out = []
    for r in src["restaurants"]:
        p = places.get(r["id"], {})
        ocr = {}
        if r.get("sha"):
            f = cache / f"{r['sha']}.json"
            if f.exists():
                try:
                    ocr = json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    ocr = {}

        items = []
        for it in ocr.get("items", []):
            ko = it.get("ko", "")
            items.append({
                "ko": ko,
                "en": it.get("en", ""),
                "main": bool(it.get("main")),
                "spicy": any(k in ko for k in SPICY_KW),
            })

        shown = ocr.get("date_shown")
        off = board_covers_today(shown, today) is False
        bd_ko, bd_en = fmt_md(shown) if off else (None, None)

        out.append({
            "id": r["id"],
            "ko": r["ko"],
            "boardDate": bd_ko,
            "boardDateEn": bd_en,
            "en": p.get("en"),
            "gloss": p.get("gloss"),
            "address": r.get("address"),
            "addressEn": p.get("addressEn"),
            "directions": r.get("directions"),
            "channel": r.get("channel"),
            "img": r.get("imgUrl"),
            "price": p.get("price") or ocr.get("price"),
            "pick": p.get("pick"),
            "hoursKo": p.get("hoursKo") or ocr.get("hours"),
            "hoursEn": p.get("hoursEn") or p.get("hoursKo") or ocr.get("hours"),
            "tipKo": p.get("tipKo"),
            "tipEn": p.get("tipEn"),
            "notes": ocr.get("notes") if not items else None,
            "items": items,
        })

    for e in extras:
        out.append({
            "id": e["id"], "ko": e["ko"], "en": e.get("en"), "gloss": e.get("gloss"),
            "address": e.get("address"), "addressEn": e.get("addressEn"),
            "directions": e.get("directions"), "channel": None, "img": None,
            "price": e.get("price"), "pick": e.get("pick"),
            "hoursKo": e.get("hoursKo"), "hoursEn": e.get("hoursEn"),
            "tipKo": e.get("tipKo"), "tipEn": e.get("tipEn"),
            "notes": None, "manual": True, "items": [],
        })

    # 추천이 붙은 곳을 앞에, 그다음 오늘 메뉴가 제대로 올라온 곳, 그다음 나머지.
    out.sort(key=lambda r: (r.get("pick") or 99, not r["items"], bool(r.get("boardDate")), r["ko"]))

    payload = {
        "dateKo": f"{today.year}년 {today.month}월 {today.day}일 {WEEKDAY_KO[today.weekday()]}요일",
        "dateEn": today.strftime("%A, %B %-d, %Y") if sys.platform != "win32"
                  else today.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "sourceDate": src.get("sourceDate"),
        "sourceIsOld": bool(sdate and sdate != today),
        "builtAt": now.strftime("%Y-%m-%d %H:%M KST"),
        "restaurants": out,
    }

    tpl = (ROOT / "scripts" / "page.html").read_text(encoding="utf-8")
    html = tpl.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    dest = ROOT / "docs" / "index.html"
    dest.write_text(html, encoding="utf-8")

    withmenu = sum(1 for r in out if r["items"])
    offdate = [r["ko"] for r in out if r.get("boardDate")]
    print(f"built {dest} — {len(out)} places, {withmenu} with a menu, "
          f"{round(dest.stat().st_size / 1024, 1)} KB"
          + (f"  [source page dated {src.get('sourceDate')}]" if payload["sourceIsOld"] else ""))
    if offdate:
        print(f"  boards not dated today: {', '.join(offdate)}")

    if "--inline" in sys.argv:
        imgdir = ROOT / "cache" / "img"
        by_id = {r["id"]: r for r in src["restaurants"]}
        for r in payload["restaurants"]:
            local = by_id.get(r["id"], {}).get("img")
            p = imgdir / local if local else None
            if p and p.exists():
                r["img"] = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
            else:
                r["img"] = None
        art = ROOT / "dist"
        art.mkdir(exist_ok=True)
        dest2 = art / "artifact.html"
        dest2.write_text(
            tpl.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            encoding="utf-8",
        )
        print(f"built {dest2} with photos embedded — {round(dest2.stat().st_size / 1024, 1)} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())

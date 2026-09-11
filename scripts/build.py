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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import menu_stats
import recommend

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


def load_dish_images():
    """요리 참고 사진 사전. 메뉴 이름 속 키워드로 찾되, 긴 키워드가 먼저 이긴다.
    (돼지불고기가 '불고기'보다 '돼지불고기' 항목에 잡히도록)"""
    f = ROOT / "data" / "dish_images.json"
    if not f.exists():
        return [], {}
    d = json.loads(f.read_text(encoding="utf-8"))["dishes"]
    kws = sorted(((kw, key) for key, v in d.items() for kw in v.get("match", [])),
                 key=lambda x: -len(x[0]))
    imgs = {k: {"thumb": v["thumb"], "page": v["page"],
                "license": v.get("license", ""), "author": v.get("author", "")}
            for k, v in d.items()}
    return kws, imgs


def match_dish(ko, kws):
    flat = ko.replace(" ", "")
    for kw, key in kws:
        if kw in flat:
            return key
    return None


def nearby_payload(cafes):
    """근처 일반식당(data/nearby.json, 서울시 인허가 공공데이터)을 페이지에 싣기 좋게 줄인다.

    한 곳을 [이름, 업종 번호, 동쪽 m, 북쪽 m] 네 칸으로. m 는 기준 건물에서 잰 값이고, 환산 상수는
    page.html 의 GM_MX·GM_MY 와 같아야 브라우저가 위경도로 정확히 되돌린다.
    구내식당과 같은 곳(이름이 겹치고 80m 안)은 뺀다 — 이미 카드로 보인다.
    """
    import math
    import re
    f = ROOT / "data" / "nearby.json"
    if not f.exists():
        return None
    nb = json.loads(f.read_text(encoding="utf-8"))
    o = nb["origin"]
    mx, my = 111320 * math.cos(math.radians(37.478)), 111000
    key = lambda s: re.sub(r"[^0-9a-z가-힣]", "", (s or "").lower())
    cafe_keys = [(key(c["ko"].split()[0]), c["lat"], c["lng"]) for c in cafes
                 if c.get("ko") and c.get("lat") is not None]
    groups, gi, rows, dropped = [], {}, [], 0
    for p in nb["places"]:
        pk = key(p["name"])
        if any(len(k) >= 3 and (k in pk or pk in k)
               and math.hypot((p["lng"] - lo) * mx, (p["lat"] - la) * my) < 80 for k, la, lo in cafe_keys):
            dropped += 1
            continue
        g = p.get("group") or "기타"
        if g not in gi:
            gi[g] = len(groups)
            groups.append(g)
        rows.append([p["name"].replace(",", " "), gi[g],
                     round((p["lng"] - o["lng"]) * mx), round((p["lat"] - o["lat"]) * my)])
    return {"o": {"n": o["n"], "lat": o["lat"], "lng": o["lng"]}, "src": nb.get("source"),
            "url": nb.get("sourceUrl"), "fetched": nb.get("fetched"), "dropped": dropped,
            "g": groups, "p": rows}


def main():
    src = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    places_file = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    # 식당 좌표. 한 번 구해 둔 값이라 없으면 지도만 빠지고 나머지는 그대로 돈다.
    coords_file = ROOT / "data" / "coords.json"
    coords_all = json.loads(coords_file.read_text(encoding="utf-8")) if coords_file.exists() else {}
    coords = coords_all.get("places", {})
    # 도로·철길·랜드마크(OSM). 지도 밑그림이라 없어도 페이지는 돈다.
    streets_file = ROOT / "data" / "streets.json"
    streets = json.loads(streets_file.read_text(encoding="utf-8")) if streets_file.exists() else None
    places = places_file.get("places", {})
    extras = places_file.get("extras", [])
    cache = ROOT / "cache" / "ocr"

    dish_kws, dish_imgs = load_dish_images()
    used_dishes = set()

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
            dish = match_dish(ko, dish_kws)
            if dish:
                used_dishes.add(dish)
            items.append({
                "ko": ko,
                "en": it.get("en", ""),
                "main": bool(it.get("main")),
                "spicy": any(k in ko for k in SPICY_KW),
                "dish": dish,
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
            "walkMin": p.get("walkMin"),
            "lat": coords.get(r["id"], {}).get("lat"),
            "lng": coords.get(r["id"], {}).get("lng"),
            "stats": menu_stats.summarize(items, p.get("price") or ocr.get("price"),
                                          ocr.get("notes")) if items else None,
        })

    for e in extras:
        out.append({
            "id": e["id"], "ko": e["ko"], "en": e.get("en"), "gloss": e.get("gloss"),
            "address": e.get("address"), "addressEn": e.get("addressEn"),
            "directions": e.get("directions"), "channel": None, "img": None,
            "price": e.get("price"), "pick": e.get("pick"),
            "hoursKo": e.get("hoursKo"), "hoursEn": e.get("hoursEn"),
            "tipKo": e.get("tipKo"), "tipEn": e.get("tipEn"),
            "notes": None, "manual": True, "items": [], "walkMin": e.get("walkMin"),
            "lat": coords.get(e["id"], {}).get("lat"),
            "lng": coords.get(e["id"], {}).get("lng"),
        })

    # 오늘 하루를 요약하는 숫자들. 값을 모르는 곳은 빼고 계산하고, 몇 곳 기준인지 함께 적는다.
    menus = [r for r in out if r["items"]]
    priced = [r for r in menus if r.get("price")]
    rare = menu_stats.rarity([r["items"] for r in menus])
    # 밥·김치·샐러드처럼 어디나 있는 것이 겹치는 건 정보가 아니다. 요리가 겹칠 때만 보여준다.
    STAPLE = ("밥", "김치", "샐러드", "깍두기", "음료", "숭늉", "차")
    overlap = [{"ko": k, "n": n} for k, n in rare.most_common(10)
               if n >= 2 and not any(w in k for w in STAPLE)][:3]
    best_per_item = min(priced, key=lambda r: r["stats"]["wonPerItem"]) if priced else None
    most_mains = max(menus, key=lambda r: r["stats"]["mains"]) if menus else None
    today_numbers = {
        "places": len(menus),
        "avgItems": round(sum(r["stats"]["count"] for r in menus) / len(menus), 1) if menus else None,
        "pricedPlaces": len(priced),
        "bestPerItem": {"ko": best_per_item["ko"], "en": best_per_item.get("en"),
                        "won": best_per_item["stats"]["wonPerItem"]} if best_per_item else None,
        "mostMains": {"ko": most_mains["ko"], "en": most_mains.get("en"),
                      "n": most_mains["stats"]["mains"]} if most_mains else None,
        "overlap": overlap,
    }

    # 추천 점수의 재료. 오늘 메뉴가 제대로 올라온 곳만 대상으로 한다.
    pool = [r for r in out if r["items"] and not r.get("boardDate")]
    axes = recommend.build(pool)

    # 추천이 붙은 곳을 앞에, 그다음 오늘 메뉴가 제대로 올라온 곳, 그다음 나머지.
    out.sort(key=lambda r: (r.get("pick") or 99, not r["items"], bool(r.get("boardDate")), r["ko"]))

    payload = {
        "dateKo": f"{today.year}년 {today.month}월 {today.day}일 {WEEKDAY_KO[today.weekday()]}요일",
        "dateEn": today.strftime("%A, %B %-d, %Y") if sys.platform != "win32"
                  else today.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "sourceDate": src.get("sourceDate"),
        # 묵은 판 판정은 브라우저가 KST 기준으로 한다. 빌드 시점에 굳혀 두면
        # 자동 갱신이 멈춘 동안 옛 메뉴판이 오늘 것처럼 보인다.
        "sourceDateIso": sdate.isoformat() if sdate else None,
        "station": coords_all.get("station"),
        "streets": ({k: streets[k] for k in ("roads", "rails", "stations", "landmarks", "buildings", "_attribution") if k in streets}
                    if streets else None),
        "sourceIsOld": bool(sdate and sdate != today),
        "builtAt": now.strftime("%Y-%m-%d %H:%M KST"),
        "todayNumbers": today_numbers,
        "dishImages": {k: v for k, v in dish_imgs.items() if k in used_dishes},
        "axes": axes,
        "restaurants": out,
        "nearby": nearby_payload(out),
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
        # 요리 참고 사진도 파일 안에 박는다. 아티팩트는 바깥 이미지를 못 부른다.
        thumbdir = ROOT / "cache" / "dishthumbs"
        for k, v in payload["dishImages"].items():
            t = thumbdir / f"{k}.jpg"
            if t.exists():
                v["thumb"] = "data:image/jpeg;base64," + base64.b64encode(t.read_bytes()).decode()
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

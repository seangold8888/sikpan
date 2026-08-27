# -*- coding: utf-8 -*-
"""오늘 상태를 data/history/YYYY-MM-DD.json 으로 적어 둔다.

가성비·재방문 주기 같은 통계는 하루치로는 안 나온다. 오늘부터 쌓아야
한 달 뒤에 "이 집은 목요일마다 치킨" 같은 말을 근거를 갖고 할 수 있다.
같은 날 여러 번 돌면 그날 파일을 덮어쓴다 - 가장 늦게 본 상태가 남는다.
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import menu_stats

ROOT = pathlib.Path(__file__).resolve().parent.parent
KST = datetime.timezone(datetime.timedelta(hours=9))


def main():
    src = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    places = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))["places"]
    cache = ROOT / "cache" / "ocr"
    today = datetime.datetime.now(KST).date()

    day = []
    for r in src["restaurants"]:
        if not r.get("sha"):
            continue
        f = cache / f"{r['sha']}.json"
        if not f.exists():
            continue
        ocr = json.loads(f.read_text(encoding="utf-8"))
        items = ocr.get("items", [])
        if not items:
            continue
        p = places.get(r["id"], {})
        price = p.get("price") or ocr.get("price")
        day.append({
            "id": r["id"],
            "ko": r["ko"],
            "price": price,
            "dateShown": ocr.get("date_shown"),
            "items": [{"ko": i["ko"], "en": i.get("en"), "main": bool(i.get("main"))} for i in items],
            "stats": menu_stats.summarize(items, price, ocr.get("notes")),
        })

    if not day:
        print("nothing to archive")
        return 0

    hist = ROOT / "data" / "history"
    hist.mkdir(exist_ok=True)
    out = hist / f"{today.isoformat()}.json"
    out.write_text(json.dumps({"date": today.isoformat(), "restaurants": day},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"archived {len(day)} menus -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

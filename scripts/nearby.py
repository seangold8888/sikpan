# -*- coding: utf-8 -*-
"""반경 안 일반식당 목록 수집 (카카오 로컬 API) → data/nearby.json

기준 건물에서 1km 안의 음식점(FD6)과 카페(CE7)를 모은다. 화면은 도보 5/10/15분으로 거르므로
가장 넓은 15분(≈1km)까지 담아 둔다.

카카오 로컬 검색은 질의 하나에 45건까지만 돌려준다. 그래서 원을 4개의 작은 원으로 쪼개 가며
각 원의 결과가 45건 미만이 될 때까지 나눈다. 같은 가게가 여러 원에 걸리므로 id 로 합친다.

필요: 환경변수 KAKAO_REST_KEY (developers.kakao.com → 내 애플리케이션 → 앱 키 → REST API 키).
값은 저장소에 적지 않는다.
"""
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "nearby.json"
KEY = os.environ.get("KAKAO_REST_KEY")

ORIGIN_NAME = "갑을그레이트밸리"
RADIUS = 1000          # m. 도보 15분까지
CAP = 45               # 카카오 로컬 검색의 질의당 최대 노출 건수
MIN_TILE = 60          # m. 이보다 작은 원은 더 안 쪼갠다(한 건물에 45곳 넘게 몰린 경우)
GROUPS = {"FD6": "음식점", "CE7": "카페"}
EXCLUDE_WORDS = ("술집",)   # 결정: 술집·호프 제외. 배달 전문은 업종으로 못 가리므로 손으로 표시한다

requests_made = 0


def origin():
    streets = json.loads((ROOT / "data" / "streets.json").read_text(encoding="utf-8"))
    b = next(x for x in streets["buildings"] if x["n"] == ORIGIN_NAME)
    return {"n": b["n"], "lat": b["p"][0], "lng": b["p"][1]}


def dist_m(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def kakao(params):
    global requests_made
    url = "https://dapi.kakao.com/v2/local/search/category.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {KEY}"})
    for attempt in range(4):
        try:
            requests_made += 1
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            body = e.read().decode("utf-8", "replace")[:200]
            sys.exit(f"카카오 API 오류 {e.code}: {body}")
        finally:
            time.sleep(0.1)


def search(code, lat, lng, r):
    """원 하나. (문서 목록, 전체 건수). 전체 건수가 CAP 를 넘으면 잘린 것이다."""
    docs, total = [], 0
    for page in (1, 2, 3):
        data = kakao({"category_group_code": code, "x": f"{lng:.7f}", "y": f"{lat:.7f}",
                      "radius": int(r), "page": page, "size": 15, "sort": "distance"})
        total = data["meta"]["total_count"]
        docs += data["documents"]
        if data["meta"]["is_end"]:
            break
    return docs, total


def collect(code, lat, lng, r, seen, out):
    docs, total = search(code, lat, lng, r)
    if total > CAP and r > MIN_TILE:
        # 4개 원으로 덮는다: 중심 (±r/2, ±r/2), 반지름 r/√2 — 각 사분면 정사각형을 온전히 덮는다.
        d_lat = (r / 2) / 111320
        d_lng = (r / 2) / (111320 * math.cos(math.radians(lat)))
        for sy in (-1, 1):
            for sx in (-1, 1):
                collect(code, lat + sy * d_lat, lng + sx * d_lng, r / math.sqrt(2), seen, out)
        return
    for d in docs:
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        out.append(d)


def main():
    if not KEY:
        sys.exit("KAKAO_REST_KEY 환경변수가 없다. developers.kakao.com 에서 REST API 키를 받아 넣을 것.")
    o = origin()
    print(f"기준: {o['n']} {o['lat']:.6f},{o['lng']:.6f}  반경 {RADIUS}m")
    places = []
    for code, label in GROUPS.items():
        seen, raw = set(), []
        collect(code, o["lat"], o["lng"], RADIUS, seen, raw)
        print(f"  {label}: {len(raw)}곳 (요청 누계 {requests_made})")
        for d in raw:
            cat = d.get("category_name", "")
            if any(w in cat for w in EXCLUDE_WORDS):
                continue
            lat, lng = float(d["y"]), float(d["x"])
            dm = dist_m(o["lat"], o["lng"], lat, lng)
            if dm > RADIUS:
                continue
            parts = [p.strip() for p in cat.split(">")]
            places.append({
                "id": d["id"], "name": d["place_name"], "group": code,
                "category": cat, "kind": parts[1] if len(parts) > 1 else label,
                "lat": lat, "lng": lng, "dist": round(dm),
                "address": d.get("road_address_name") or d.get("address_name") or "",
                "phone": d.get("phone") or "", "url": d.get("place_url") or "",
            })
    places.sort(key=lambda p: p["dist"])
    OUT.write_text(json.dumps({
        "origin": o, "radius": RADIUS,
        "fetched": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="minutes"),
        "source": "Kakao Local API (category search)", "count": len(places), "places": places,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n저장: {OUT.relative_to(ROOT)}  {len(places)}곳  (요청 {requests_made}회)")
    for lim in (350, 700, 1000):
        sub = [p for p in places if p["dist"] <= lim]
        kinds = {}
        for p in sub:
            kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
        top = ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:10])
        print(f"≤{lim:4d}m: {len(sub):3d}곳 | {top}")


if __name__ == "__main__":
    main()

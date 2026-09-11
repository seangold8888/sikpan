# -*- coding: utf-8 -*-
"""반경 안 일반식당 목록 (서울시 인허가 공공데이터) → data/nearby.json

출처: 서울 열린데이터광장 「일반음식점 인허가 정보」·「휴게음식점 인허가 정보」, 공공누리 제1유형(출처표시).
카카오 로컬 API 결과는 저장이 금지돼 있어 쓰지 않는다(design/NEARBY.md).

- 금천구·구로구 서비스만 받는다(1km 반경이 두 구에 걸친다). 서쪽 안양천 건너 광명시는 서울 데이터가 아니고
  걸어서 점심 먹으러 갈 거리가 아니라 뺀다.
- 영업 중(영업/정상)만 남기고, 기준 건물에서 RADIUS 안만 저장한다.
- 좌표는 EPSG:5174(Bessel 중부원점 TM). 위경도로 바꾸는 계산을 직접 한다 — Actions 러너에 pyproj 없이 돌도록.

필요: 환경변수 SEOUL_OPEN_KEY (data.seoul.go.kr 일반 인증키). 값은 저장소에 적지 않는다.
"""
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "nearby.json"
KEY = os.environ.get("SEOUL_OPEN_KEY")

ORIGIN_NAME = "갑을그레이트밸리"
ORIGIN_ADDR = "디지털로9길 32"   # 좌표 변환 검증용: 이 주소의 가게들은 기준 건물 위에 떨어져야 한다
RADIUS = 1000
PAGE = 1000                      # 서울 열린데이터 한 번 요청 최대 건수
SERVICES = {                     # 서비스명: 인허가 종류
    "LOCALDATA_072404_GC": "일반음식점", "LOCALDATA_072404_GR": "일반음식점",
    "LOCALDATA_072405_GC": "휴게음식점", "LOCALDATA_072405_GR": "휴게음식점",
}
# 결정(2026-09-11): 술집·호프 제외. 휴게음식점 중 편의점·키즈카페는 식당이 아니라 뺀다.
EXCLUDE_KINDS = {"호프/통닭", "정종/대포집/소주방", "감성주점", "라이브카페", "간이주점", "편의점", "키즈카페"}
# 인허가 업태가 '기타 휴게음식점'·'일반조리판매'인 곳에 PC방·스크린골프·편의점이 섞여 있다. 이름으로 거른다.
EXCLUDE_NAME = re.compile(r"호프|포차|주점|PC|피씨|피시방|골프|노래|볼링|당구|만화|스크린|코인|지에스25|GS25|(?<![A-Za-z])CU(?![A-Za-z])|씨유|"
                          r"세븐일레븐|이마트24|미니스톱", re.I)

# 돌려먹기 축에 쓰는 업종 묶음. 인허가 업태를 먼저 보고, '기타' 계열이면 이름의 낱말로 정한다.
KIND_GROUP = {
    "한식": "한식", "냉면집": "한식", "탕류(보신용)": "한식", "횟집": "한식", "식육(숯불구이)": "고기",
    "중국식": "중식", "일식": "일식", "복어취급": "일식", "경양식": "양식", "패밀리레스트랑": "양식",
    "분식": "분식", "김밥(도시락)": "분식", "뷔페식": "뷔페", "외국음식전문점(인도,태국등)": "아시아",
    "패스트푸드": "패스트푸드", "통닭(치킨)": "치킨",
    "커피숍": "카페", "다방": "카페", "전통찻집": "카페", "떡카페": "카페", "아이스크림": "카페", "제과점영업": "카페",
}
NAME_GROUP = [   # 위에서부터 먼저 걸리는 것
    ("카페", r"커피|카페|cafe|coffee|빈스|바나프레소|매머드|메가엠지씨|컴포즈|이디야|스타벅스|투썸|할리스|폴바셋|요거트|케이크|베이커리|디저트|공차|빙수|과일|주스"),
    ("중식", r"마라|짜장|짬뽕|중화|반점|양꼬치|훠궈"),
    ("일식", r"스시|초밥|라멘|카츠|돈까스|돈가스|우동|이자카야|규동|덮밥|텐동|소바"),
    ("아시아", r"쌀국수|PHO|포베이|타이|태국|인도|커리|카레|베트남|반미|딤섬"),
    ("분식", r"김밥|김가네|떡볶이|분식|토스트|핫도그|꽈배기|호떡|순대"),
    ("양식", r"파스타|피자|버거|샌드|샐러드|salad|포케|브런치|스테이크|타코|멕시칸|델리"),
    ("고기", r"삼겹|갈비|고기|돈|냉삼|곱창|막창|한우|숯불"),
    ("한식", r"국밥|한상|찌개|백반|해장|감자탕|칼국수|옹심이|죽|비빔|보쌈|족발|쌈밥|식당|밥"),
]
NAME_GROUP = [(g, re.compile(p, re.I)) for g, p in NAME_GROUP]


def group_of(kind, name):
    g = KIND_GROUP.get(kind)
    if g:
        return g
    for g, rx in NAME_GROUP:
        if rx.search(name):
            return g
    return "기타"

# ── EPSG:5174 → WGS84 ─────────────────────────────────────────
# +proj=tmerc +lat_0=38 +lon_0=127.0028902777778 +k=1 +x_0=200000 +y_0=500000 +ellps=bessel
# +towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43
BES_A, BES_F = 6377397.155, 1 / 299.1528128
WGS_A, WGS_F = 6378137.0, 1 / 298.257223563
LAT0, LON0, K0, FE, FN = math.radians(38), math.radians(127.0028902777778), 1.0, 200000.0, 500000.0
TOWGS84 = (-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)


def _meridian(phi, a, e2):
    e4, e6 = e2 * e2, e2 ** 3
    return a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                - (35 * e6 / 3072) * math.sin(6 * phi))


def _tm_inverse(x, y):
    """Snyder 식 역TM. Bessel 위경도(라디안)."""
    a, e2 = BES_A, 2 * BES_F - BES_F ** 2
    ep2 = e2 / (1 - e2)
    m = _meridian(LAT0, a, e2) + (y - FN) / K0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
          + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    s, c, t = math.sin(p1), math.cos(p1), math.tan(p1)
    c1, t1 = ep2 * c * c, t * t
    n1 = a / math.sqrt(1 - e2 * s * s)
    r1 = a * (1 - e2) / (1 - e2 * s * s) ** 1.5
    d = (x - FE) / (n1 * K0)
    lat = p1 - (n1 * t / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / c
    return lat, lon


def tm5174_to_wgs84(x, y):
    lat, lon = _tm_inverse(x, y)
    # Bessel 위경도 → 지심직교(ECEF)
    e2 = 2 * BES_F - BES_F ** 2
    n = BES_A / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    X, Y, Z = n * math.cos(lat) * math.cos(lon), n * math.cos(lat) * math.sin(lon), n * (1 - e2) * math.sin(lat)
    # 7변수 변환(PROJ towgs84 = position vector, 회전은 초, 축척은 ppm)
    tx, ty, tz, rx, ry, rz, sppm = TOWGS84
    rx, ry, rz = (math.radians(v / 3600) for v in (rx, ry, rz))
    k = 1 + sppm * 1e-6
    X2 = tx + k * (X - rz * Y + ry * Z)
    Y2 = ty + k * (rz * X + Y - rx * Z)
    Z2 = tz + k * (-ry * X + rx * Y + Z)
    # WGS84 ECEF → 위경도 (반복)
    e2w = 2 * WGS_F - WGS_F ** 2
    p = math.hypot(X2, Y2)
    lat2 = math.atan2(Z2, p * (1 - e2w))
    for _ in range(6):
        nw = WGS_A / math.sqrt(1 - e2w * math.sin(lat2) ** 2)
        h = p / math.cos(lat2) - nw
        lat2 = math.atan2(Z2, p * (1 - e2w * nw / (nw + h)))
    return math.degrees(lat2), math.degrees(math.atan2(Y2, X2))


def dist_m(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ── 수집 ──────────────────────────────────────────────────────
def fetch(svc, a, b):
    url = f"http://openapi.seoul.go.kr:8088/{urllib.parse.quote(KEY)}/json/{svc}/{a}/{b}/"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.load(r)
            body = d.get(svc)
            if body is None:
                sys.exit(f"{svc} 오류: {json.dumps(d.get('RESULT', d), ensure_ascii=False)[:200]}")
            return body
        except (OSError, json.JSONDecodeError):
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def rows(svc):
    first = fetch(svc, 1, PAGE)
    total = first["list_total_count"]
    yield from first.get("row", [])
    for a in range(PAGE + 1, total + 1, PAGE):
        time.sleep(0.3)
        yield from fetch(svc, a, min(a + PAGE - 1, total)).get("row", [])


def origin():
    streets = json.loads((ROOT / "data" / "streets.json").read_text(encoding="utf-8"))
    b = next(x for x in streets["buildings"] if x["n"] == ORIGIN_NAME)
    return {"n": b["n"], "lat": b["p"][0], "lng": b["p"][1]}


def main():
    if not KEY:
        sys.exit("SEOUL_OPEN_KEY 환경변수가 없다. data.seoul.go.kr 에서 일반 인증키를 받아 넣을 것.")
    o = origin()
    print(f"기준: {o['n']} {o['lat']:.6f},{o['lng']:.6f}  반경 {RADIUS}m", flush=True)
    places, excluded, check, seen = [], Counter(), [], set()
    for svc, license_kind in SERVICES.items():
        n_all = n_open = 0
        for r in rows(svc):
            n_all += 1
            if r.get("TRDSTATENM") != "영업/정상":
                continue
            n_open += 1
            try:
                x, y = float(str(r.get("X", "")).strip()), float(str(r.get("Y", "")).strip())
            except ValueError:
                continue
            lat, lng = tm5174_to_wgs84(x, y)
            dm = dist_m(o["lat"], o["lng"], lat, lng)
            addr = (r.get("RDNWHLADDR") or r.get("SITEWHLADDR") or "").strip()
            if ORIGIN_ADDR in addr:
                check.append(dm)
            if dm > RADIUS:
                continue
            kind = (r.get("UPTAENM") or "").strip() or "기타"
            name = (r.get("BPLCNM") or "").strip()
            if kind in EXCLUDE_KINDS:
                excluded[kind] += 1
                continue
            if EXCLUDE_NAME.search(name):
                excluded["이름(PC방·골프·편의점 등)"] += 1
                continue
            mid = r.get("MGTNO")
            if mid in seen:
                continue
            seen.add(mid)
            places.append({
                "id": mid, "name": name, "license": license_kind, "kind": kind, "group": group_of(kind, name),
                "lat": round(lat, 6), "lng": round(lng, 6), "dist": round(dm), "address": addr,
                "since": (r.get("APVPERMYMD") or "")[:10],
            })
        print(f"  {svc}: 전체 {n_all} · 영업 중 {n_open}", flush=True)

    places.sort(key=lambda p: p["dist"])
    # 좌표 변환 검증: 기준 건물 주소의 가게들이 기준점 가까이(건물 크기 안) 떨어져야 한다
    if check:
        check.sort()
        print(f"\n좌표 검증: '{ORIGIN_ADDR}' 가게 {len(check)}곳, 기준점까지 중앙값 {check[len(check)//2]:.0f}m, 최대 {check[-1]:.0f}m")
        if check[len(check) // 2] > 150:
            sys.exit("좌표 변환이 어긋났다(중앙값 150m 초과). 저장하지 않는다.")

    OUT.write_text(json.dumps({
        "origin": o, "radius": RADIUS,
        "fetched": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="minutes"),
        "source": "서울 열린데이터광장 「일반음식점 인허가 정보」·「휴게음식점 인허가 정보」(금천구·구로구), 공공누리 제1유형",
        "sourceUrl": "https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do",
        "count": len(places), "places": places,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n저장: {OUT.relative_to(ROOT)}  {len(places)}곳")
    print("제외:", ", ".join(f"{k} {v}" for k, v in excluded.most_common()) or "없음")
    for lim in (350, 700, 1000):
        sub = [p for p in places if p["dist"] <= lim]
        groups = Counter(p["group"] for p in sub)
        print(f"≤{lim:4d}m: {len(sub):4d}곳 | " + ", ".join(f"{k} {v}" for k, v in groups.most_common()))
    rest = [p["name"] for p in places if p["group"] == "기타" and p["dist"] <= 700]
    print(f"\n700m 안 '기타'로 남은 {len(rest)}곳 예:", " / ".join(rest[:30]))


if __name__ == "__main__":
    main()

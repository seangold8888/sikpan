# -*- coding: utf-8 -*-
"""메뉴 이름 옆에 붙일 요리 참고 사진 사전.

AI로 그리지 않고 위키미디어 커먼즈의 실제 음식 사진을 쓴다. 외국인이 보고
기대할 모습과 실물이 어긋나면 안 되기 때문이다. 사진은 어디까지나 그 요리가
'일반적으로 어떻게 생겼는지'를 보여주는 참고용이고, 페이지에도 그렇게 적는다.

DISHES 의 각 항목: 메뉴 이름에 이 말이 들어 있으면 이 요리로 본다(match),
커먼즈에서 이 검색어로 사진을 찾는다(search). 긴 match 가 먼저 이긴다.

python scripts/dish_images.py 로 실행하면 커먼즈 API 로 사진을 찾아
data/dish_images.json 에 적는다. 이 파일은 손으로 고칠 수 있고(잘못 찾은
사진을 다른 File: 제목으로 교체), 다시 실행해도 이미 찾은 항목은 건드리지
않는다.
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "dish_images.json"
API = "https://commons.wikimedia.org/w/api.php"
UA = "gasan-lunch/1.0 (dish reference images; contact: github.com/seangold8888)"
THUMB = 320

DISHES = [
    # 닭
    {"key": "fried-chicken",   "match": ["후라이드치킨", "뿌링클", "순살치킨", "치킨스틱", "윙봉", "크리스피치킨"], "search": "Korean fried chicken"},
    {"key": "yangnyeom-chicken", "match": ["양념치킨", "간장치킨", "데리야끼소스닭", "닭강정"], "search": "Yangnyeom chicken"},
    {"key": "jjimdak",         "match": ["찜닭"], "search": "Andong jjimdak"},
    {"key": "dakbokkeumtang",  "match": ["닭볶음탕", "닭도리탕"], "search": "Dak-bokkeum-tang"},
    {"key": "dakgalbi",        "match": ["닭갈비"], "search": "Dak-galbi"},
    {"key": "dakgaejang",      "match": ["닭개장"], "search": "Dak-gaejang"},
    {"key": "samgyetang",      "match": ["삼계탕", "백숙"], "search": "Samgye-tang"},
    # 돼지
    {"key": "jeyuk",           "match": ["제육", "고추장불고기", "두루치기", "돼지불백", "돼지불고기", "매운돼지"], "search": "Jeyuk-bokkeum"},
    {"key": "samgyeopsal",     "match": ["삼겹살", "목살구이", "오겹살"], "search": "Samgyeopsal grilled"},
    {"key": "bossam",          "match": ["보쌈", "수육"], "search": "Bossam pork"},
    {"key": "donkatsu",        "match": ["돈까스", "돈가스", "등심까스"], "search": "Donkatsu Korean pork cutlet"},
    {"key": "tangsuyuk",       "match": ["탕수육"], "search": "Tangsuyuk"},
    {"key": "sundae-bokkeum",  "match": ["순대볶음", "순대철판", "순대깻잎"], "search": "Sundae-bokkeum"},
    {"key": "sundae",          "match": ["순대"], "search": "Sundae Korean sausage"},
    {"key": "spam",            "match": ["스팸", "그릴델리햄", "델리햄"], "search": "Spam slices fried"},
    {"key": "budae-jjigae",    "match": ["부대찌개", "부대전골"], "search": "Budae-jjigae"},
    # 소
    {"key": "bulgogi",         "match": ["불고기", "불백"], "search": "Bulgogi"},
    {"key": "galbijjim",       "match": ["갈비찜"], "search": "Galbi-jjim"},
    {"key": "tteokgalbi",      "match": ["떡갈비"], "search": "Tteok-galbi"},
    {"key": "yukgaejang",      "match": ["육개장"], "search": "Yukgaejang"},
    {"key": "gyudon",          "match": ["소고기덮밥", "규동", "우삼겹덮밥"], "search": "Gyudon"},
    {"key": "meatball",        "match": ["미트볼", "함박", "동그랑땡"], "search": "Meatballs tomato sauce"},
    {"key": "jangjorim",       "match": ["장조림"], "search": "Jangjorim"},
    # 해물
    {"key": "saengseon-gui",   "match": ["고등어", "삼치구이", "임연수", "가자미구이", "생선구이"], "search": "Godeungeo-gui grilled mackerel"},
    {"key": "saengseon-katsu", "match": ["생선까스", "생선가스"], "search": "Fish cutlet fried"},
    {"key": "ojingeo-bokkeum", "match": ["오징어볶음", "오징어채"], "search": "Ojingeo-bokkeum"},
    {"key": "jjukkumi",        "match": ["쭈꾸미", "주꾸미", "낙지볶음"], "search": "Jukkumi-bokkeum spicy octopus"},
    {"key": "shrimp-fried",    "match": ["새우까스", "새우카츠", "새우튀김", "치킨새우"], "search": "Fried shrimp tempura"},
    {"key": "eomuk",           "match": ["어묵", "오뎅"], "search": "Eomuk-bokkeum"},
    {"key": "haemul-jeon",     "match": ["해물전", "완자전", "해물완자"], "search": "Korean jeon pancake"},
    # 찌개·국
    {"key": "kimchi-jjigae",   "match": ["김치찌개", "김치찌게"], "search": "Kimchi-jjigae"},
    {"key": "doenjang-jjigae", "match": ["된장찌개", "된장찌게", "된장지짐"], "search": "Doenjang-jjigae"},
    {"key": "sundubu",         "match": ["순두부"], "search": "Sundubu-jjigae"},
    {"key": "gochujang-jjigae","match": ["고추장찌개"], "search": "Gochujang-jjigae"},
    # 면·밥·분식
    {"key": "bibimbap",        "match": ["비빔밥"], "search": "Bibimbap"},
    {"key": "curry",           "match": ["카레"], "search": "Japanese curry rice"},
    {"key": "pasta-cream",     "match": ["크림파스타", "크림스파게티", "까르보나라"], "search": "Cream pasta mushroom"},
    {"key": "pasta-tomato",    "match": ["토마토파스타", "라구파스타", "토마토칠리스파게티", "미트스파게티"], "search": "Spaghetti tomato sauce"},
    {"key": "eggs-in-hell",    "match": ["에그인헬"], "search": "Shakshouka"},
    {"key": "japchae",         "match": ["잡채"], "search": "Japchae"},
    {"key": "tteokbokki",      "match": ["떡볶이"], "search": "Tteokbokki"},
    {"key": "mapo-tofu",       "match": ["마파두부"], "search": "Mapo doufu"},
    {"key": "takoyaki",        "match": ["타코야끼", "타코야키"], "search": "Takoyaki"},
    {"key": "croquette",       "match": ["고로케", "크로켓"], "search": "Korokke croquette"},
    {"key": "kimchi-bokkeum",  "match": ["김치볶음"], "search": "Kimchi-bokkeum-bap"},
    {"key": "ramyeon",         "match": ["라면"], "search": "Ramyeon Korean instant noodle"},
    {"key": "naengmyeon",      "match": ["냉면", "막국수"], "search": "Mul-naengmyeon"},
]


def api(params):
    q = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    for wait in (0, 15, 40):   # 커먼즈가 요청 속도를 제한하므로 얌전하게 재시도
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    raise RuntimeError("Commons keeps rate-limiting; try again later")


def find(search):
    """커먼즈에서 검색해 가장 그럴듯한 사진 하나를 고른다."""
    data = api({
        "action": "query", "generator": "search",
        "gsrsearch": f"{search} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 5,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": THUMB,
    })
    pages = sorted((data.get("query", {}).get("pages") or {}).values(),
                   key=lambda p: p.get("index", 99))
    for p in pages:
        title = p.get("title", "")
        if not title.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}

        def field(k):
            v = (meta.get(k) or {}).get("value", "")
            import re
            return re.sub(r"<[^>]+>", "", v).strip()

        return {
            "file": title,
            "thumb": ii.get("thumburl"),
            "page": ii.get("descriptionurl"),
            "author": field("Artist")[:80],
            "license": field("LicenseShortName"),
        }
    return None


def main():
    existing = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8")).get("dishes", {})

    dishes = {}
    for d in DISHES:
        prev = existing.get(d["key"])
        if prev and prev.get("thumb"):   # 이미 찾았거나 손으로 고친 것은 그대로 둔다
            dishes[d["key"]] = {**prev, "match": d["match"]}
            continue
        time.sleep(1.5)
        hit = find(d["search"])
        if hit:
            dishes[d["key"]] = {**hit, "match": d["match"]}
            print(f"  {d['key']:<18} {hit['file'][:60]}  [{hit['license']}]")
        else:
            print(f"  {d['key']:<18} NOT FOUND ({d['search']})", file=sys.stderr)
        OUT.write_text(json.dumps({"thumbWidth": THUMB, "dishes": dishes},
                                  ensure_ascii=False, indent=1), encoding="utf-8")

    OUT.write_text(json.dumps({"thumbWidth": THUMB, "dishes": dishes},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(dishes)}/{len(DISHES)} dishes -> {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

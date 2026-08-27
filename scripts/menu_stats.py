# -*- coding: utf-8 -*-
"""메뉴 한 상을 숫자로 바꾼다.

점심을 고르는 기준을 감이 아니라 근거로 만들려는 것이므로, 여기서 나오는 숫자는
전부 메뉴판에 실제로 인쇄된 것에서만 뽑는다. 추정해서 채우지 않는다.
"""

# 메뉴 이름에 나오는 재료를 단백질 종류로 묶는다. 이름만 보고 판단하므로 완벽하지 않다.
# 애매한 것(장조림은 소고기일 수도 메추리알일 수도)은 넣지 않는 쪽을 택했다.
PROTEIN = {
    "닭": ["닭", "치킨", "뿌링", "계육", "닭갈비"],
    "돼지": ["돼지", "제육", "수육", "삼겹", "목살", "두루치기", "탕수육", "돈까스", "돈가스",
            "스팸", "햄", "소세지", "소시지", "순대", "베이컨", "동그랑땡", "보쌈"],
    "소": ["소고기", "쇠고기", "떡갈비", "스테이크", "육개장", "불고기", "미트볼", "우삼겹", "차돌"],
    "해물": ["고등어", "생선", "오징어", "새우", "어묵", "쥐포", "갈치", "동태", "코다리",
                "문어", "낙지", "쭈꾸미", "주꾸미", "임연수", "참치", "맛살", "해물", "멸치",
                "삼치", "가자미", "황태", "북어", "조개", "홍합", "김"],
    "계란": ["계란", "달걀", "에그", "오믈렛", "수란"],
    "두부": ["두부", "유부", "순두부"],
}

# 돼지불고기처럼 앞말이 종류를 뒤집는 경우
OVERRIDE = [("돼지불고기", "돼지"), ("돼지고기", "돼지"), ("닭갈비", "닭"), ("오리", "닭")]


def proteins(items):
    """메뉴 목록에서 단백질 종류를 뽑는다."""
    found = set()
    for it in items:
        ko = it.get("ko", "")
        hit = None
        for word, kind in OVERRIDE:
            if word in ko:
                hit = kind
                break
        if hit:
            found.add(hit)
            continue
        for kind, words in PROTEIN.items():
            if any(w in ko for w in words):
                found.add(kind)
    return sorted(found)


def has_free_extra(items, notes):
    """셀프 라면이나 무료 코너처럼 값을 더 받지 않고 얹어주는 것이 있는지."""
    blob = " ".join(it.get("ko", "") for it in items) + " " + (notes or "")
    return any(w in blob for w in ["셀프", "무료", "플러스코너", "라면", "토스트", "아이스크림"])


def summarize(items, price=None, notes=None):
    """식당 한 곳의 오늘 메뉴를 숫자로."""
    mains = [i for i in items if i.get("main")]
    prot = proteins(items)
    return {
        "count": len(items),
        "mains": len(mains),
        "proteins": prot,
        "proteinCount": len(prot),
        "freeExtra": has_free_extra(items, notes),
        # 가격을 모르는 곳이 많다. 모르면 계산하지 않고 비워 둔다.
        "wonPerItem": round(price / len(items)) if price and items else None,
    }


def rarity(all_menus):
    """오늘 이 동네에서 몇 곳이 같은 메뉴를 내는지 센다.

    같은 날 잡채가 네 곳에서 나오면, 잡채를 먹으러 멀리 갈 이유가 없다는 뜻이다.
    """
    import collections
    import re

    def norm(ko):
        return re.sub(r"[\s/*()·&]+", " ", ko).strip()

    c = collections.Counter()
    for items in all_menus:
        for ko in {norm(i.get("ko", "")) for i in items}:
            if ko:
                c[ko] += 1
    return c

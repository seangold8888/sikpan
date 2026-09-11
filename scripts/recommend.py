# -*- coding: utf-8 -*-
"""오늘 어느 구내식당에 갈지 고르기 위한 점수 재료를 만든다.

여기서는 '점수'를 내지 않고 '축별 원점수'만 0~1로 정규화해 넘긴다.
가중치를 곱해 순위를 내는 일은 화면에서 한다 - 사람마다 중요한 축이 다르고,
남이 정한 가중치로 매긴 순위는 근거를 볼 수 없으면 믿을 이유가 없기 때문이다.

모르는 값은 0으로 깎지 않고 None으로 남긴다. 화면에서 중립(중앙값)으로 처리하고
'정보 없음'이라고 밝힌다. 가격을 모른다는 이유로 그 식당이 나쁜 평가를 받으면 안 된다.
"""

AXES = ["value", "variety", "mains", "protein", "rarity", "near"]


def _norm(vals):
    """값 목록을 0~1로. 모두 같으면 전부 0.5(구분 정보 없음)."""
    known = [v for v in vals if v is not None]
    if not known:
        return [None] * len(vals)
    lo, hi = min(known), max(known)
    if hi == lo:
        return [None if v is None else 0.5 for v in vals]
    return [None if v is None else (v - lo) / (hi - lo) for v in vals]


def _price_score(vals):
    """가격을 0~1로. 보통 가격(아는 값의 중앙값)을 0.5에 두고 1% 싸면 +0.03, 비싸면 -0.03.

    최저·최고로 펴지 않는다. 가격을 아는 곳이 몇 안 되고 대부분 같은 값이라, 500원 차이가
    0점 대 100점이 돼 버린다. 중앙값을 0.5에 두는 까닭은 모르는 곳이 중립(0.5)으로 계산되기
    때문이다 — 보통 가격을 아는 곳도 같은 자리에 있어야 가격을 모르는 곳이 손해를 보지 않는다.
    """
    known = sorted(v for v in vals if v)
    if not known:
        return [None] * len(vals)
    n = len(known)
    med = known[n // 2] if n % 2 else (known[n // 2 - 1] + known[n // 2]) / 2
    return [None if not v else max(0.0, min(1.0, 0.5 + (med - v) / med * 3)) for v in vals]


def build(rows):
    """rows: [{id, stats, price, walkMin, items, boardOffDate}] -> {id: {axis: 0~1}}

    각 축은 클수록 좋게 맞춘다(가까울수록·쌀수록 높은 점수).
    """
    # 오늘 이 동네에서 몇 곳이 같은 메인을 내는지 - 겹칠수록 굳이 갈 이유가 없다.
    import collections
    import re

    def key(ko):
        return re.sub(r"[\s/*()·&]+", "", ko)

    main_count = collections.Counter()
    for r in rows:
        for k in {key(i["ko"]) for i in r["items"] if i.get("main")}:
            main_count[k] += 1

    raw = {"value": [], "variety": [], "mains": [], "protein": [], "rarity": [], "near": []}
    for r in rows:
        st = r.get("stats") or {}
        # 가성비는 가격으로만 본다. 원/품목으로 매기면 반찬 수가 '반찬수' 축과 두 번 들어간다.
        raw["value"].append(r.get("price"))
        raw["variety"].append(st.get("count"))
        raw["mains"].append(st.get("mains"))
        raw["protein"].append(st.get("proteinCount"))
        mains = [i for i in r["items"] if i.get("main")]
        if mains:
            # 메인 하나가 평균 몇 곳에서 겹치는가. 적을수록 오늘 여기서만 먹을 수 있다.
            avg = sum(main_count[key(i["ko"])] for i in mains) / len(mains)
            raw["rarity"].append(-avg)
        else:
            raw["rarity"].append(None)
        wm = r.get("walkMin")
        raw["near"].append(-wm if wm else None)

    normed = {a: _norm(raw[a]) for a in AXES}
    normed["value"] = _price_score(raw["value"])
    out = {}
    for idx, r in enumerate(rows):
        out[r["id"]] = {a: (None if normed[a][idx] is None else round(normed[a][idx], 4)) for a in AXES}
    return out

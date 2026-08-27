# -*- coding: utf-8 -*-
"""메뉴판 사진을 읽어 한국어 원문과 영어 번역을 담은 JSON으로 바꾼다.

Claude 의 이미지 인식을 쓴다. ANTHROPIC_API_KEY 가 없으면 아무것도 하지 않고
조용히 넘어간다 - 그 경우 사이트는 사진과 식당 정보만으로도 정상 동작한다.

결과는 사진의 sha256 을 키로 cache/ocr/ 에 저장한다. 같은 사진을 다시 읽지
않으므로, 하루 중 여러 번 돌려도 새로 올라온 메뉴판만 비용이 든다.
"""
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "ocr"
API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("OCR_MODEL", "claude-haiku-4-5-20251001")

PROMPT = """This is a photo of a Korean office-cafeteria menu board for one day.

Transcribe it as JSON with exactly this shape and nothing else:
{"date_shown":"<date text printed on the board, verbatim, or null>",
 "price":<number or null>,
 "hours":"<operating hours printed, or null>",
 "items":[{"ko":"<menu item exactly as printed in Korean>","en":"<short natural English name>","main":true|false}],
 "notes":"<other printed text: self-serve corner, origin labels, notices; or null>"}

Rules:
- Transcribe the Korean EXACTLY as printed. Do not correct spelling. Use ? for an unreadable character.
- "main" is true only for the main dishes (the protein or entree). Rice, soup, kimchi, side
  vegetables, salad, fruit and drinks are false.
- English: romanization plus a short description, e.g. "Spicy stir-fried pork (Jeyuk-bokkeum)".
- If the board shows several days, transcribe only the column for the date given below.
- If the board shows a different date, transcribe it anyway and say so in "notes".
- If the image is not a menu board at all, return "items":[] and explain in "notes".

Target date: %s
Return only the JSON object."""


def read(sha):
    p = CACHE / f"{sha}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def write(sha, obj):
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{sha}.json").write_text(
        json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def call(img_bytes, target_date, key):
    body = {
        "model": MODEL,
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.b64encode(img_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": PROMPT % target_date},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in resp.get("content", []))
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def prune(days=60):
    """오래된 판독 결과를 지운다. 지난 메뉴판은 다시 쓸 일이 없다."""
    if not CACHE.exists():
        return 0
    import time
    cutoff = time.time() - days * 86400
    gone = 0
    for f in CACHE.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            gone += 1
    return gone


def main():
    key = os.environ.get("ANTHROPIC_API_KEY")
    src = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    target = src.get("sourceDate") or "today"

    todo = [r for r in src["restaurants"] if r.get("sha") and not read(r["sha"])]
    have = sum(1 for r in src["restaurants"] if r.get("sha") and read(r["sha"]))
    print(f"menu photos already transcribed: {have}, new: {len(todo)}")

    if not todo:
        return 0
    if not key:
        print("ANTHROPIC_API_KEY not set - skipping transcription; "
              "the site will show photos without English text")
        return 0

    done = fail = 0
    for r in todo:
        img = ROOT / "cache" / "img" / r["img"]
        try:
            obj = call(img.read_bytes(), target, key)
            obj["_model"] = MODEL
            write(r["sha"], obj)
            done += 1
            print(f"  read {r['ko']}: {len(obj.get('items', []))} items")
        except urllib.error.HTTPError as e:
            fail += 1
            print(f"  ! {r['ko']}: HTTP {e.code} {e.read()[:200]!r}", file=sys.stderr)
        except Exception as e:
            fail += 1
            print(f"  ! {r['ko']}: {e}", file=sys.stderr)

    print(f"transcribed {done}, failed {fail}")
    gone = prune()
    if gone:
        print(f"pruned {gone} old transcriptions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

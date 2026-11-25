"""KDP 출간 에이전트 — 매주 책 1권을 만들어 비서실 텔레그램 봇으로 결재받고, 올릴 파일과 문구를 보냅니다.

흐름 (Jacob은 버튼만 누름):
  1) weekly   일요일 아침: 지난 책을 아직 안 올렸으면 다시 물어보고, 아니면 계획표(plan.json)의 다음 책을 만듦
              → 미리보기 사진 + [✅ 올리기] [🔁 다시 만들기] [❌ 버리기]
  2) choice   버튼 결과 처리
              approve → 속지 PDF·표지 PDF·등록 문구를 텔레그램으로 보내고 [✅ KDP에 올렸음] [⏰ 나중에] 질문
              redo    → 무늬·격자를 새로 섞어 다시 만들고 다시 물어봄
              drop    → 이 책은 건너뜀
              posted  → 출간 기록 (주간 성적표의 로열티 계산에 쓰임)
쓰는 법:
  python kdp/run.py weekly
  python kdp/run.py choice --book taste-of-korea-1 --redo 0 --choice approve
  python kdp/run.py build --book taste-of-korea-1 --out /tmp/x      (텔레그램 없이 파일만)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "hub"))

import books                       # noqa: E402
import secretary as s              # noqa: E402

AGENT = "kdp"
WORKFLOW = "kdp-book.yml"
OUT = Path("/tmp/kdp-out")
STATE = "kdp_books"


def spec_of(book_id: str) -> dict:
    return json.loads((HERE / "wordbanks" / f"{book_id}.json").read_text())


def plan() -> list[str]:
    return json.loads((HERE / "plan.json").read_text())["order"]


def load_state():
    data, sha = s.state_get(STATE, {})
    return data or {}, sha


def save_state(data, sha, msg):
    s.state_put(STATE, data, sha, msg)


def mark(book_id: str, **fields):
    data, sha = load_state()
    rec = data.get(book_id, {})
    rec.update(fields)
    data[book_id] = rec
    save_state(data, sha, f"KDP 기록: {book_id} {', '.join(fields)}")


def build(book_id: str, redo: int, out: Path | None = None) -> tuple[dict, Path]:
    spec = spec_of(book_id)
    seed = int(hashlib.sha1(spec["id"].encode()).hexdigest()[:6], 16) + redo * 7919   # 같은 책·같은 판이면 늘 같은 결과
    out = out or OUT / f"{book_id}-r{redo}"
    info = books.make_book(spec, out, seed=seed)
    return info, out


def ask_approval(book_id: str, redo: int):
    info, out = build(book_id, redo)
    spec = spec_of(book_id)
    lst = json.loads((out / "listing.json").read_text())
    kind = "퍼즐북" if info["kind"] == "wordsearch" else "컬러링북"
    extra = f"퍼즐 {info.get('puzzles')}개 · 단어 {info.get('words')}개" if info["kind"] == "wordsearch" \
        else f"무늬 {info.get('designs')}개 (한 면 인쇄)"
    body = (f"{spec['title']}\n{kind} · {info['pages']}쪽 · {extra}\n"
            f"정가 ${lst['price_usd']} → 1권당 약 ${lst['royalty_estimate_usd']} (추정)")
    if redo:
        body += f"\n🔁 {redo}번째 다시 만든 판"
    key = s.ask(AGENT, f"kdp-{book_id}-r{redo}", "이번 주 책, 올릴까요?", body,
                photo=str(out / "preview.png"), checks=[tuple(c) for c in info["checks"]],
                on_choice={"workflow": WORKFLOW, "inputs": {"book": book_id, "redo": str(redo)}})
    mark(book_id, status="asked", redo=redo, asked=time.strftime("%Y-%m-%d"), fingerprint=info["fingerprint"])
    print("승인 요청 보냄:", key)


def send_doc(path: Path, caption: str):
    _, chat = s._auth()
    if not chat:
        print("(텔레그램 설정 없음) 파일:", path)
        return
    s.tg("sendDocument", {"chat_id": chat, "caption": caption, "disable_notification": "true"},
         file=("document", str(path)), timeout=300)


def send_text(text: str):
    _, chat = s._auth()
    if not chat:
        print(text)
        return
    s.tg("sendMessage", {"chat_id": chat, "text": text[:4000], "disable_notification": "true"})


def deliver(book_id: str, redo: int):
    info, out = build(book_id, redo)
    lst = json.loads((out / "listing.json").read_text())
    s.notify(AGENT, f"📦 '{lst['title']}' 올릴 준비 끝",
             "아래 파일 2개를 길게 눌러 '파일에 저장' 해 두고, 문구는 순서대로 길게 눌러 복사 → KDP 칸에 붙여넣기 하세요.\n"
             "안내서: KDP 화면 순서 = Details → Content → Pricing", level="normal")
    send_doc(out / "interior.pdf", f"① 속지 (Manuscript) · {info['pages']}쪽")
    send_doc(out / "cover.pdf", f"② 표지 (Cover) · 책등 {info['cover']['spine_in']}인치")
    fields = [
        ("제목 Title", lst["title"]), ("부제 Subtitle", lst["subtitle"]), ("시리즈 Series (이름 + 번호)", f"{lst['series']}\n번호(Series number): {lst.get('series_no', 1)}"),
        ("저자 Author (이름 칸에 그대로)", lst["author"]),
        ("설명 Description (KDP 설명 칸은 HTML도 받아요)", lst["description"]),
        ("키워드 7칸 (한 줄씩 한 칸에)", "\n".join(lst["keywords"])),
        ("카테고리 3개 (검색해서 고르기)", "\n".join(lst["categories"])),
        ("인쇄 옵션", lst["trim"]), ("가격 Amazon.com", f"{lst['price_usd']}"),
        ("AI 질문 답", lst["ai_answer"]),
        ("그 밖에", f"Low-content: {lst['low_content']}\n성인 내용: {lst['adult_content']}\nExpanded Distribution: {lst['expanded_distribution']}"),
    ]
    for label, val in fields:
        send_text(f"[{label}]\n{val}")
    s.ask(AGENT, f"kdp-{book_id}-posted", f"'{lst['title']}' KDP에 올리셨나요?",
          "올리고 'Publish' 까지 누르셨으면 ✅ 를 눌러 주세요. 심사는 보통 72시간이에요.",
          buttons=[("✅ KDP에 올렸음", "posted"), ("⏰ 나중에", "later")],
          on_choice={"workflow": WORKFLOW, "inputs": {"book": book_id, "redo": str(redo)}})
    mark(book_id, status="delivered", redo=redo, delivered=time.strftime("%Y-%m-%d"),
         pages=info["pages"], price=lst["price_usd"], royalty=lst["royalty_estimate_usd"])


def handle_choice(book_id: str, redo: int, choice: str):
    if choice == "approve":
        deliver(book_id, redo)
    elif choice == "redo":
        ask_approval(book_id, redo + 1)
    elif choice == "drop":
        mark(book_id, status="dropped")
        s.notify(AGENT, "❌ 이 책은 건너뛸게요", book_id)
    elif choice == "posted":
        mark(book_id, status="posted", posted=time.strftime("%Y-%m-%d"))
        s.notify(AGENT, "✅ 출간 기록했어요", "아마존에 보이기까지 보통 72시간이에요. 3일 뒤 일요일 점검 때 확인 알림을 드릴게요.")
    elif choice == "later":
        mark(book_id, status="delivered_waiting")
        s.notify(AGENT, "⏰ 알겠어요", "다음 일요일에 다시 여쭤볼게요. 파일과 문구는 위 메시지에 그대로 있어요.")


def weekly():
    data, _ = load_state()
    today = time.strftime("%Y-%m-%d")
    # 올렸다고 한 지 3일 넘은 책 → 아마존에서 보이는지 확인 부탁 (한 번만)
    for bid, rec in data.items():
        if rec.get("status") == "posted" and not rec.get("live_checked") and rec.get("posted", today) < today:
            s.notify(AGENT, "🔎 아마존 확인 부탁", f"'{spec_of(bid)['title']}' 이 KDP Bookshelf 에서 'LIVE' 인지 봐 주세요. "
                     "'In review' 면 조금 더 기다리고, 'Action required' 면 메일 내용을 Claude에게 보내 주세요.")
            mark(bid, live_checked=today)
    # 받아 두고 아직 안 올린 책이 있으면 새 책 대신 그 책을 다시 물어봄
    for bid, rec in data.items():
        if rec.get("status") in ("delivered", "delivered_waiting"):
            s.ask(AGENT, f"kdp-{bid}-posted-{today}", f"'{spec_of(bid)['title']}' 아직 안 올리셨나요?",
                  "지난번 보낸 파일·문구로 올리면 돼요. 올렸으면 ✅",
                  buttons=[("✅ KDP에 올렸음", "posted"), ("⏰ 나중에", "later")],
                  on_choice={"workflow": WORKFLOW, "inputs": {"book": bid, "redo": str(rec.get("redo", 0))}})
            return
    todo = [b for b in plan() if data.get(b, {}).get("status") not in ("posted", "dropped", "delivered", "delivered_waiting")]
    asked = [b for b in todo if data.get(b, {}).get("status") == "asked"]
    if asked:
        print("결재 대기 중인 책이 있어 새로 만들지 않음:", asked[0])
        return
    if not todo:
        s.notify(AGENT, "📚 다음 책 재료가 떨어졌어요", "계획표의 책을 모두 만들었어요. Claude에게 '다음 KDP 책 만들어 줘'라고 해 주세요.",
                 level="urgent")
        return
    ask_approval(todo[0], 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["weekly", "choice", "build"])
    ap.add_argument("--book")
    ap.add_argument("--redo", type=int, default=0)
    ap.add_argument("--choice")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        if a.step == "weekly":
            weekly()
        elif a.step == "choice":
            handle_choice(a.book, a.redo, a.choice)
        else:
            info, out = build(a.book, a.redo, Path(a.out) if a.out else None)
            print(json.dumps(info, ensure_ascii=False), out)
    except Exception as e:  # 실패는 비서실로 (소리 나는 알림 + 다시 실행 버튼)
        s.fail(AGENT, f"KDP 책 ({a.step})", f"{type(e).__name__}: {e}", retry=("playlist-agent", WORKFLOW))
        raise


if __name__ == "__main__":
    main()

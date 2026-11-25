# 🗂 비서실 (Secretary) — 모든 에이전트의 보고와 결재를 텔레그램 봇 하나로

AI를 쓰지 않는 코드라 토큰·비용이 들지 않아요. 이 저장소가 공개라 GitHub Actions 시간도 무료예요.

## Jacob이 하는 일
버튼만 누르면 돼요. 글을 칠 일은 없어요.

| 버튼 | 하는 일 |
|---|---|
| 📋 현황 | 모든 에이전트의 마지막 실행 결과 (✅ 정상 · 🔴 실패 · ⏸ 멈춤) |
| ⏳ 승인 대기 | 아직 누르지 않은 승인 요청 목록과 바로 처리 버튼 |
| 📊 성적표 | 주간 성적표를 지금 바로 만들어 보내기 |
| 📚 판매 입력 | 이번 주 KDP 판매 권수를 숫자 버튼으로 기록 (일요일 20:00에 자동으로도 물어봄) |

- 승인 요청에 24시간 답이 없으면 한 번만 다시 물어보고, 누를 때까지 다음 단계는 멈춰 있어요.
- 버튼은 Jacob 계정에서 누를 때만 작동해요.
- 승인 요청을 보내면 15분, 버튼을 누르면 10분 동안 '듣기 모드'가 켜져서 누르자마자 "접수됐어요"가 떠요. 그 밖의 시간엔 5분마다 확인해요.

## 알림 3단계
| 단계 | 쓰는 곳 | 텔레그램 |
|---|---|---|
| `urgent` | 실패, 승인 필요 | 소리 나는 알림 |
| `normal` | 완료 보고 | 무음으로 조용히 도착 |
| `log` | 사소한 기록 | 보내지 않음 (로그만) |

## 공통 부품 (다른 에이전트가 가져다 쓰는 법)
`hub/secretary.py` 파일 하나만 있으면 돼요 (파이썬 기본 기능만 사용).

```python
import secretary as s
s.notify("playlist", "12곡 작곡 완료", "내일 영상으로 만들어요.")             # 무음 보고
s.fail("playlist", "영상 만들기", "ffmpeg 오류", retry=("playlist-agent", "make-video.yml"))
key = s.ask("playlist", "pl-2026-11-25", "새 영상 올릴까요?", "Late Night Seoul · 12곡",
            photo="thumb.png", checks=s.preflight(meta),
            on_choice={"workflow": "upload.yml", "inputs": {"id": "2026-11-25"}})
s.decision(key)   # None(아직) / "approve" / "redo" / "drop"
```

- `on_choice`: 버튼을 누르면 비서실이 그 워크플로를 실행해요. 그 워크플로는 `choice` 입력을 받아야 해요 (`approve`/`redo`/`drop`). 워크플로 안에서 기다리는 것보다 무료 시간을 훨씬 덜 써요.
- 다른 저장소에서 쓸 때: 워크플로에서 `curl -fsSL https://raw.githubusercontent.com/jacobhong082-cmd/playlist-agent/main/hub/secretary.py -o secretary.py`
  승인 대기 목록 등록은 이 저장소에 쓸 수 있는 `HUB_TOKEN`이 있을 때만 돼요 (없어도 버튼은 작동).
- `hub/youtube.py`: 유튜브 업로드. **AI 표시(containsSyntheticMedia)를 항상 켜고**, 설명 끝에 AI 사용 문장을 붙이고, 아동용 아님으로 올려요.
- `s.preflight(meta)`: 업로드 전 검사 (AI 표시 · 영어 제목 · 자막 · 썸네일 · 아동용 아님 · 설명 100자+) → 승인 카드에 ✓/✗로 표시.

## 새 에이전트 추가
`hub/agents.json`에 한 줄 추가하면 📋 현황과 성적표 성공률에 자동으로 들어가요.

## 비밀값 (Settings → Secrets and variables → Actions)
| 이름 | 필수 | 내용 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | 주식 봇과 같은 봇 토큰 (텔레그램 @BotFather → /mybots → API Token) |
| `TELEGRAM_CHAT_ID` | ✅ | Jacob 텔레그램 숫자 ID |
| `STOCK_ACTIONS_TOKEN` | 선택 | stock-agent 실행 열쇠 (cron-job.org에 쓰는 것과 같은 것). 있으면 주식 현황과 '🔁 지금 다시'가 작동 |
| `YOUTUBE_API_KEY`, `YOUTUBE_CHANNEL_ID` | 나중에 | 채널을 만든 뒤. 성적표의 조회수·구독자 |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | 나중에 | 업로드 · 시청 시간 |

## 파일
- `bot.py` 5분마다 버튼·메뉴 처리 (`.github/workflows/secretary.yml`)
- `weekly.py` + `card.html` 주간 성적표 (B2 숲 초록 디자인, `.github/workflows/weekly-report.yml`)
- `state/` 승인 결과, 승인 대기, KDP 판매, 유튜브 숫자 기록 (봇이 자동으로 씀)

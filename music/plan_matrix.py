"""회차 파일에서 새로 만들 곡 목록을 GitHub 매트릭스 JSON으로 출력.
재사용 곡과, 이미 만들어 둔 곡(두 번째 인자 폴더에 <slug>.mp3 가 있으면)은 뺍니다."""
import json, os, sys
ep = json.load(open(sys.argv[1]))
have = sys.argv[2] if len(sys.argv) > 2 else ""
print(json.dumps([s["slug"] for s in ep["songs"] if "reuse" not in s
                  and not (have and os.path.exists(os.path.join(have, s["slug"] + ".mp3")))]))

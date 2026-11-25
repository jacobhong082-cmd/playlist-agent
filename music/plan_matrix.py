"""회차 파일에서 새로 만들 곡 목록(재사용 곡 제외)을 GitHub 매트릭스 JSON으로 출력."""
import json, sys
ep = json.load(open(sys.argv[1]))
print(json.dumps([s["slug"] for s in ep["songs"] if "reuse" not in s]))

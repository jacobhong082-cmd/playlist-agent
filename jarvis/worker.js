// 자비스 — 아이폰 단축어("시리야, 자비스")가 묻는 말에 몇 초 안에 대답하는 무료 Cloudflare Worker.
//
// 단축어가 보내는 것:  GET https://<주소>/ask?k=<암호>&q=<받아쓴 말>
// 돌려주는 것:        시리가 읽어 줄 한국어 대답 (그냥 글자)
//
// 안전 규칙: 조회만 바로 대답해요. 승인·다시 실행은 텔레그램 비서실에 '✅ 네 / ✋ 아니요'
// 확인 버튼만 보내고, Jacob이 눌러야 실행돼요 (버튼 처리는 기존 비서실 봇이 해요).
//
// 비밀값 (GitHub Actions가 설치하면서 넣어 줌):
//   JARVIS_KEY          단축어 암호 (이게 맞아야만 대답)
//   GEMINI_API_KEY      Gemini 무료 열쇠
//   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   확인 버튼 보내기
//   GH_TOKEN            (선택) 비공개 stock-agent 상태 읽기 — Actions 읽기 권한이면 충분

const OWNER = "jacobhong082-cmd";
const HUB = `${OWNER}/playlist-agent`;
const RAW = `https://raw.githubusercontent.com/${HUB}/main/hub`;
const LABEL = { approve: "승인", redo: "다시 만들기", drop: "버리기" };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname !== "/ask") return say("자비스 대기 중");
    const p = url.searchParams;
    let q = p.get("q") || "";
    if (req.method === "POST") {
      try { const b = await req.json(); q = b.q || b.text || q; } catch (e) { /* 글자만 온 경우 */ }
    }
    if (!env.JARVIS_KEY || p.get("k") !== env.JARVIS_KEY) return say("암호가 맞지 않아요.", 403);
    q = q.trim().slice(0, 500);
    if (!q) return say("네, 말씀하세요.");
    try {
      return say(await answer(q, env));
    } catch (e) {
      console.log("error", (e && e.stack) || e);
      return say("지금은 대답을 못 만들었어요. 잠시 뒤에 다시 물어봐 주세요.");
    }
  },
};

function say(text, status = 200) {
  return new Response(text, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
}

const kst = (d) => new Date(new Date(d).getTime() + 9 * 3600e3).toISOString().slice(5, 16).replace("T", " ");

async function gh(path, env, priv) {
  const h = { "user-agent": "jarvis", accept: "application/vnd.github+json" };
  if (priv && env.GH_TOKEN) h.authorization = `Bearer ${env.GH_TOKEN}`;
  const r = await fetch(`https://api.github.com${path}`, { headers: h });
  return r.ok ? r.json() : null;
}

async function quote(sym) {
  try {
    const r = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?range=5d&interval=1d`,
      { headers: { "user-agent": "Mozilla/5.0" } });
    const m = (await r.json()).chart.result[0].meta;
    const prev = m.chartPreviousClose || m.previousClose;
    const ch = prev ? `${((m.regularMarketPrice / prev - 1) * 100).toFixed(1)}%` : "";
    return `${sym} $${m.regularMarketPrice.toFixed(2)} (전일 대비 ${ch}, 한국시간 ${kst(m.regularMarketTime * 1000)} 기준)`;
  } catch (e) {
    return `${sym} 시세 불러오기 실패`;
  }
}

async function context(env) {
  const cfg = await (await fetch(`${RAW}/agents.json`)).json();
  const agents = cfg.agents.filter((a) => !a.paused && !a.manual);
  const failed = [];
  const lines = await Promise.all(agents.map(async (a) => {
    const repo = a.repo.includes("/") ? a.repo : `${OWNER}/${a.repo}`;
    const j = await gh(`/repos/${repo}/actions/workflows/${a.workflow}/runs?per_page=1`, env, !repo.endsWith("playlist-agent"));
    const r = j && j.workflow_runs && j.workflow_runs[0];
    if (!r) return `- ${a.name}: 기록 없음`;
    if (r.conclusion === "failure") failed.push({ name: a.name, repo: a.repo, workflow: a.workflow });
    const st = r.status !== "completed" ? "실행 중" : ({ success: "정상", failure: "실패" }[r.conclusion] || r.conclusion);
    return `- ${a.name}: ${st} (${kst(r.updated_at)})`;
  }));
  const dir = (await gh(`/repos/${HUB}/contents/hub/state/pending?ref=main`, env, false)) || [];
  const pend = (await Promise.all(dir.filter((f) => f.name.endsWith(".json")).map(async (f) => {
    try {
      return await (await fetch(`${RAW}/state/pending/${encodeURIComponent(f.name)}?t=${Date.now()}`)).json();
    } catch (e) {
      return null;
    }
  }))).filter(Boolean);
  const quotes = await Promise.all(["SOXL", "^SOX", "^IXIC"].map(quote));
  const text = `지금 한국시간: ${kst(Date.now())}\n\n[에이전트 상태]\n${lines.join("\n")}\n\n[승인 대기 ${pend.length}건]\n` +
    (pend.map((x) => `- key=${x.key} · ${x.agent} · ${x.title}`).join("\n") || "- 없음") + `\n\n[시세]\n${quotes.join("\n")}`;
  return { text, pend, failed };
}

const PROMPT = `너는 Jacob의 음성 비서 '자비스'야. Jacob은 개발자가 아니고 한국어로 말해. 시리가 네 답을 소리 내어 읽어 줘.
Jacob의 에이전트: 주식(시황 브리핑·급등락 알림·모의매매), AI 플레이리스트 유튜브, 아마존 KDP 주간 책, 비서실(텔레그램 봇).
아래 [지금 상황]만 근거로 답해. 모르는 건 지어내지 말고 모른다고 해. 투자 판단(사라/팔아라)은 하지 말고 사실만.
말로 읽을 답이니 1~3문장, 쉬운 존댓말, 기호·이모지 없이. 퍼센트는 '퍼센트'로, 달러 금액은 '달러'로 써.
action은 하나만:
- none: 대답만
- decide: 승인 대기 하나를 approve/redo/drop — key는 목록의 key 그대로
- retry: 실패한 작업 다시 실행 — name은 목록의 이름 그대로
decide·retry는 바로 실행되지 않고 텔레그램에 확인 버튼이 가. say에서 "텔레그램에 확인 버튼 보냈어요"라고 말해.
업로드·주문·삭제·돈이 드는 일·목록에 없는 일은 none으로 하고 텔레그램 버튼으로 해 달라고 말해.
JSON 하나로만: {"say":"","action":"none|decide|retry","key":"","choice":"","name":""}

[지금 상황]
`;

async function models(env) {
  if (env.GEMINI_MODEL) return [env.GEMINI_MODEL];
  const j = await (await fetch(`https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key=${env.GEMINI_API_KEY}`)).json();
  const skip = ["image", "tts", "live", "audio", "embedding", "exp", "native", "computer", "omni", "robotics"];
  const ok = (j.models || [])
    .filter((m) => (m.supportedGenerationMethods || []).includes("generateContent"))
    .map((m) => m.name.replace("models/", ""))
    .filter((n) => n.includes("flash") && !skip.some((s) => n.includes(s)));
  const ver = (n) => parseFloat((n.match(/gemini-(\d+(?:\.\d+)?)/) || [0, 0])[1]);
  const rank = (a, b) => ver(b) - ver(a) || a.includes("preview") - b.includes("preview") || a.length - b.length;
  // 빠른 대답이 중요해서 Flash-Lite 먼저, 막히면 Flash
  return [...ok.filter((n) => n.includes("lite")).sort(rank).slice(0, 2),
    ...ok.filter((n) => !n.includes("lite")).sort(rank).slice(0, 2)];
}

async function gemini(prompt, env) {
  let last = "모델 없음";
  for (const m of await models(env)) {
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent?key=${env.GEMINI_API_KEY}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: { responseMimeType: "application/json", temperature: 0.3 },
      }),
    });
    if (r.ok) {
      const j = await r.json();
      return JSON.parse(j.candidates[0].content.parts[0].text);
    }
    last = `${m} ${r.status}`;
  }
  throw new Error(`Gemini 실패: ${last}`);
}

async function tg(method, body, env) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  return r.ok;
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function answer(q, env) {
  const ctx = await context(env);
  const out = await gemini(`${PROMPT}${ctx.text}\n\nJacob이 시리에게 한 말: ${q}`, env);
  let text = (out.say || "").trim() || "잘 못 알아들었어요. 다시 말씀해 주세요.";
  let buttons = null;
  let line = "";
  if (out.action === "decide") {
    const it = ctx.pend.find((x) => x.key === out.key);
    if (it && LABEL[out.choice]) {
      line = `<b>${esc(it.title)}</b> → ${LABEL[out.choice]}\n이대로 할까요?`;
      buttons = [[{ text: "✅ 네", callback_data: `a|${it.key}|${out.choice}` }, { text: "✋ 아니요", callback_data: "x" }]];
    } else {
      text = "어느 승인 건인지 확실하지 않아요. 텔레그램 승인 대기 버튼으로 골라 주세요.";
    }
  } else if (out.action === "retry") {
    const f = ctx.failed.find((x) => x.name === out.name);
    if (f) {
      line = `<b>${esc(f.name)}</b> 다시 실행할까요?`;
      buttons = [[{ text: "🔁 네, 다시", callback_data: `r|${f.repo}|${f.workflow}` }, { text: "✋ 아니요", callback_data: "x" }]];
    } else {
      text = "지금 실패한 작업이 없어서 다시 돌릴 게 없어요.";
    }
  }
  if (buttons) {
    const sent = await tg("sendMessage", {
      chat_id: env.TELEGRAM_CHAT_ID, parse_mode: "HTML",
      text: `🎙 <b>자비스</b> · 시리로 받은 말: “${esc(q)}”\n\n${line}`,
      reply_markup: { inline_keyboard: buttons },
    }, env);
    if (!sent) text = "확인 버튼을 텔레그램에 보내지 못했어요. 비서실의 승인 대기 버튼을 써 주세요.";
  }
  return text;
}

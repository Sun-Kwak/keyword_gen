"""
키워드 트렌드 분석기 — 웹 서버
실행: python server.py
브라우저: http://localhost:8000
"""
import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web_searcher import search_keyword_data
from trend_scorer import score_all_keywords
from keyword_generator import generate_new_keywords
from candidate_generator import generate_candidates

app = FastAPI(title="키워드 트렌드 분석기")


class AnalyzeRequest(BaseModel):
    keywords: list[str]


# ── SSE 스트리밍 분석 ────────────────────────────────────────
async def run_analysis_stream(seed_keywords: list[str]) -> AsyncGenerator[str, None]:
    """분석 진행 상황을 SSE(Server-Sent Events)로 실시간 전송"""

    def send(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    # 시드 키워드 → 후보 키워드 생성
    candidates = generate_candidates(seed_keywords)
    yield send("status", {"msg": f"시드: {' / '.join(seed_keywords)} → 후보 {len(candidates)}개 생성"})
    yield send("candidates", {"keywords": candidates})

    kw_data_map = {}
    total = len(candidates)
    t_start = time.time()

    # STEP 1: 검색
    for i, kw in enumerate(candidates, 1):
        yield send("progress", {"step": 1, "current": i, "total": total, "keyword": kw})

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, search_keyword_data, kw)
        kw_data_map[kw] = data

        n = data["result_count"]
        if n >= 12:
            cred = "높음"
        elif n >= 6:
            cred = "보통"
        elif n >= 2:
            cred = "낮음"
        else:
            cred = "매우낮음"

        yield send("search_row", {
            "keyword": kw, "count": n, "credibility": cred,
        })

    elapsed = time.time() - t_start
    total_hits = sum(d["result_count"] for d in kw_data_map.values())
    yield send("status", {
        "msg": f"✅ 검색 완료 — 총 {total_hits}건 / {elapsed:.0f}초 / 평균 {total_hits/total:.1f}건"
    })

    # STEP 2: 점수 분석
    yield send("status", {"msg": "⭐ 점수 분석 중..."})
    loop = asyncio.get_event_loop()
    scored = await loop.run_in_executor(None, score_all_keywords, candidates, kw_data_map)

    for i, kw in enumerate(scored, 1):
        yield send("score_row", {
            "rank": i,
            "keyword": kw["keyword"],
            "trend": kw["trend"],
            "positive": kw["positive"],
            "negative": kw["negative"],
            "originality": kw["originality"],
            "fusion_potential": kw["fusion_potential"],
            "total": kw["total"],
            "hit_count": kw["hit_count"],
        })

    # STEP 3: 신규 키워드 제안
    yield send("status", {"msg": "💡 신규 키워드 조합 생성 중..."})
    suggestions = await loop.run_in_executor(None, generate_new_keywords, scored)

    for s in suggestions:
        yield send("suggest_row", {
            "new_keyword": s["new_keyword"],
            "source_a": s["source_a"],
            "source_b": s["source_b"],
            "rationale": s["rationale"],
            "estimated_score": s["estimated_score"],
        })

    # 완료
    top3 = scored[:3] if scored else []
    yield send("done", {
        "top": [{"keyword": k["keyword"], "total": k["total"]} for k in top3],
        "suggest_count": len(suggestions),
    })


@app.get("/analyze")
async def analyze(keywords: str):
    """GET /analyze?keywords=릴렉싱,스트레칭,요가"""
    kw_list = [k.strip() for k in keywords.replace(" ", ",").split(",") if k.strip()]
    if not kw_list:
        return {"error": "키워드를 입력하세요"}

    return StreamingResponse(
        run_analysis_stream(kw_list),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


# ── HTML 페이지 ──────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>키워드 트렌드 분석기</title>
<style>
  :root {
    --bg: #0f1117;
    --panel: #1a1d2e;
    --border: #2d3057;
    --accent: #4f8ef7;
    --accent2: #7c5bf7;
    --green: #22c55e;
    --yellow: #eab308;
    --red: #ef4444;
    --text: #e2e8f0;
    --muted: #64748b;
    --radius: 10px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }

  /* ── 헤더 ── */
  header {
    background: linear-gradient(135deg, #1a1d2e 0%, #0f1117 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 32px;
    display: flex; align-items: center; gap: 12px;
  }
  header h1 { font-size: 1.3rem; font-weight: 700; color: var(--text); }
  header span { font-size: 1.5rem; }

  /* ── 입력 영역 ── */
  #input-section {
    padding: 24px 32px 0;
    max-width: 1400px;
    margin: 0 auto;
  }
  .input-row { display: flex; gap: 10px; }
  #kw-input {
    flex: 1;
    background: var(--panel);
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-size: 1rem;
    padding: 12px 16px;
    outline: none;
    transition: border-color .2s;
  }
  #kw-input:focus { border-color: var(--accent); }
  #kw-input::placeholder { color: var(--muted); }
  button {
    border: none; border-radius: var(--radius);
    font-size: .95rem; font-weight: 600;
    cursor: pointer; padding: 12px 22px;
    transition: opacity .15s, transform .1s;
  }
  button:active { transform: scale(.97); }
  button:disabled { opacity: .4; cursor: not-allowed; }
  #run-btn { background: var(--accent); color: #fff; }
  #stop-btn { background: var(--red); color: #fff; }

  /* ── 진행 바 ── */
  #progress-section { padding: 16px 32px 0; max-width: 1400px; margin: 0 auto; }
  #progress-wrap { background: var(--panel); border-radius: 6px; height: 8px; overflow: hidden; }
  #progress-bar { height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .3s; border-radius: 6px; }
  #status-text { font-size: .85rem; color: var(--muted); margin-top: 8px; min-height: 1.2em; }

  /* ── 탭 ── */
  #main { padding: 20px 32px 40px; max-width: 1400px; margin: 0 auto; }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 16px; flex-wrap: wrap; }
  .tab-btn {
    background: none; border: none; border-radius: 8px 8px 0 0;
    color: var(--muted); font-size: .9rem; padding: 10px 18px;
    cursor: pointer; transition: color .15s, background .15s;
  }
  .tab-btn:hover { color: var(--text); background: rgba(255,255,255,.04); }
  .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }

  /* ── 테이블 ── */
  .tbl-wrap { overflow-x: auto; border-radius: var(--radius); border: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; font-size: .88rem; }
  thead tr { background: #1e2236; }
  th { padding: 11px 14px; text-align: left; color: var(--muted); font-weight: 600; white-space: nowrap; border-bottom: 1px solid var(--border); }
  td { padding: 10px 14px; border-bottom: 1px solid rgba(45,48,87,.5); white-space: nowrap; }
  tr:last-child td { border-bottom: none; }
  tr:nth-child(even) td { background: rgba(255,255,255,.015); }
  tr:hover td { background: rgba(79,142,247,.06); }

  /* ── 점수 색 ── */
  .score-high { color: var(--green); font-weight: 700; }
  .score-mid  { color: var(--yellow); }
  .score-low  { color: var(--muted); }
  .neg-bad    { color: var(--red); }
  .neg-ok     { color: var(--green); }
  .cred-high  { color: var(--green); font-weight: 600; }
  .cred-mid   { color: var(--yellow); }
  .cred-low   { color: var(--muted); }

  /* ── 점수 바 ── */
  .bar-wrap { display: flex; align-items: center; gap: 8px; }
  .mini-bar { width: 80px; height: 6px; background: #2d3057; border-radius: 3px; overflow: hidden; }
  .mini-bar-fill { height: 100%; border-radius: 3px; }

  /* ── 로그 ── */
  #log-box {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px;
    font-family: 'Menlo', 'Consolas', monospace; font-size: .82rem;
    line-height: 1.7; height: 420px; overflow-y: auto; color: #a8b4d8;
  }
  .log-ok   { color: var(--green); }
  .log-info { color: var(--accent); font-weight: 600; }
  .log-kw   { color: #e2e8f0; }
  .log-dim  { color: var(--muted); }

  /* ── 점수 기준 패널 ── */
  #legend-box { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px 28px; }
  .legend-row { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
  .legend-icon { font-size: 1.4rem; width: 2rem; text-align: center; flex-shrink: 0; }
  .legend-title { font-weight: 700; font-size: .95rem; }
  .legend-weight { color: var(--accent); font-size: .85rem; margin-left: 8px; }
  .legend-desc { color: var(--muted); font-size: .85rem; margin-top: 3px; }
  .legend-divider { border: none; border-top: 1px solid var(--border); margin: 18px 0; }
  .cred-row { display: flex; gap: 24px; flex-wrap: wrap; }
  .cred-item { font-size: .85rem; }

  /* ── 후보 키워드 뱃지 ── */
  #candidates-section {
    display: none;
    padding: 12px 32px 0;
    max-width: 1400px;
    margin: 0 auto;
  }
  #candidates-section .label {
    font-size: .8rem; color: var(--muted); margin-bottom: 8px;
  }
  #candidates-wrap {
    display: flex; flex-wrap: wrap; gap: 8px;
  }
  .cand-badge {
    background: rgba(79,142,247,.12);
    border: 1px solid rgba(79,142,247,.25);
    border-radius: 16px;
    font-size: .8rem; padding: 4px 12px; color: #a8c0ff;
  }

  /* ── 요약 배너 ── */
  #summary-banner {
    display: none;
    background: linear-gradient(135deg, #1a2744, #1a1d2e);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    padding: 20px 24px;
    margin-bottom: 20px;
  }
  #summary-banner h3 { color: var(--accent); margin-bottom: 12px; font-size: 1rem; }
  .top-kw-list { display: flex; gap: 12px; flex-wrap: wrap; }
  .top-kw-badge {
    background: rgba(79,142,247,.15);
    border: 1px solid rgba(79,142,247,.3);
    border-radius: 20px; padding: 6px 14px; font-size: .88rem;
  }
  .medal { margin-right: 4px; }
</style>
</head>
<body>

<div id="login-modal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(15, 17, 23, 0.98); display: flex; align-items: center; justify-content: center; z-index: 9999; backdrop-filter: blur(4px);">
  <div style="background: linear-gradient(135deg, #1a1d2e, #0f1117); border: 1px solid #4f8ef7; border-radius: 16px; padding: 48px; max-width: 360px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.5);">
    <h2 style="color: #e2e8f0; text-align: center; margin-bottom: 8px; font-size: 1.5rem;">🔐 키워드 분석기</h2>
    <p style="color: #64748b; text-align: center; margin-bottom: 28px; font-size: 0.9rem;">접근 비밀번호를 입력하세요</p>
    <input id="pwd-input" type="password" placeholder="비밀번호" 
      style="width: 100%; background: #0f1117; border: 1.5px solid #2d3057; border-radius: 8px; color: #e2e8f0; font-size: 1rem; padding: 12px 16px; outline: none; margin-bottom: 16px; transition: border-color 0.2s;"
      onkeydown="if(event.key==='Enter') checkPassword()">
    <button id="pwd-btn" onclick="checkPassword()" style="width: 100%; background: #4f8ef7; color: white; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; padding: 12px; cursor: pointer; transition: opacity 0.15s;">확인</button>
    <p id="error-msg" style="color: #ef4444; text-align: center; margin-top: 12px; font-size: 0.85rem; display: none;"></p>
  </div>
</div>

<header>
  <span>🔍</span>
  <h1>키워드 트렌드 분석기</h1>
</header>

<section id="input-section">
  <div class="input-row">
    <input id="kw-input" type="text"
      placeholder="분석할 키워드 입력 (쉼표 또는 공백 구분 — 예: 패시브 스트레칭, 소매틱 운동, slow fitness)"
      onkeydown="if(event.key==='Enter') startAnalysis()">
    <button id="run-btn" onclick="startAnalysis()">▶ 분석 시작</button>
    <button id="stop-btn" onclick="stopAnalysis()" disabled>■ 중지</button>
  </div>
</section>

<section id="candidates-section">
  <div class="label">📋 분석 대상 후보 키워드</div>
  <div id="candidates-wrap"></div>
</section>

<section id="progress-section">
  <div id="progress-wrap"><div id="progress-bar"></div></div>
  <div id="status-text">키워드를 입력하고 분석 시작을 누르세요</div>
</section>

<div id="main">
  <div id="summary-banner">
    <h3>🏆 분석 완료</h3>
    <div class="top-kw-list" id="top-kw-list"></div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('log')">📋 진행 로그</button>
    <button class="tab-btn" onclick="switchTab('search')">🔍 검색 현황</button>
    <button class="tab-btn" onclick="switchTab('score')">⭐ 점수 분석</button>
    <button class="tab-btn" onclick="switchTab('suggest')">💡 키워드 제안</button>
    <button class="tab-btn" onclick="switchTab('legend')">📐 점수 기준</button>
  </div>

  <!-- 진행 로그 -->
  <div id="tab-log" class="tab-pane active">
    <div id="log-box"></div>
  </div>

  <!-- 검색 현황 -->
  <div id="tab-search" class="tab-pane">
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>#</th><th>키워드</th><th>수집 건수</th><th>신뢰도</th><th>검색량</th>
        </tr></thead>
        <tbody id="search-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- 점수 분석 -->
  <div id="tab-score" class="tab-pane">
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>#</th><th>키워드</th>
          <th>🔥 트렌드<br><small>×30%</small></th>
          <th>✅ 긍정<br><small>×25%</small></th>
          <th>⚠️ 부정<br><small>×15%↓</small></th>
          <th>💡 독창성<br><small>×20%</small></th>
          <th>🔗 융합<br><small>×10%</small></th>
          <th>⭐ 종합</th>
          <th>검색수</th><th>신뢰도</th>
        </tr></thead>
        <tbody id="score-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- 키워드 제안 -->
  <div id="tab-suggest" class="tab-pane">
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>💡 제안 키워드</th><th>출처 A</th><th>출처 B</th><th>융합 논리</th><th>예상점수</th>
        </tr></thead>
        <tbody id="suggest-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- 점수 기준 -->
  <div id="tab-legend" class="tab-pane">
    <div id="legend-box">
      <div class="legend-row">
        <div class="legend-icon">🔥</div>
        <div>
          <div class="legend-title">트렌드 점수 <span class="legend-weight">가중치 30%</span></div>
          <div class="legend-desc">검색결과 내 트렌드 신호어(인기·핫·바이럴 등) 빈도 + 해당 키워드 검색량</div>
        </div>
      </div>
      <div class="legend-row">
        <div class="legend-icon">✅</div>
        <div>
          <div class="legend-title">긍정 점수 <span class="legend-weight">가중치 25%</span></div>
          <div class="legend-desc">효과·추천·힐링·좋은·benefit·popular 등 긍정 표현 빈도</div>
        </div>
      </div>
      <div class="legend-row">
        <div class="legend-icon">⚠️</div>
        <div>
          <div class="legend-title">부정 점수 <span class="legend-weight">가중치 15% — 낮을수록 유리 (역산)</span></div>
          <div class="legend-desc">부작용·위험·논란·injury·risk 등 부정 표현 빈도. 종합점수에 역방향 반영</div>
        </div>
      </div>
      <div class="legend-row">
        <div class="legend-icon">💡</div>
        <div>
          <div class="legend-title">독창성 점수 <span class="legend-weight">가중치 20%</span></div>
          <div class="legend-desc">패시브·소매틱·마인드풀·딥 등 수식어 포함 여부. 검색량이 적을수록 아직 발견되지 않은 개념으로 가점</div>
        </div>
      </div>
      <div class="legend-row">
        <div class="legend-icon">🔗</div>
        <div>
          <div class="legend-title">융합가능 점수 <span class="legend-weight">가중치 10%</span></div>
          <div class="legend-desc">stretching / relaxation / mind_body / fitness / recovery 등 여러 카테고리에 걸칠수록 융합 잠재력 ↑</div>
        </div>
      </div>
      <hr class="legend-divider">
      <div class="legend-row">
        <div class="legend-icon">⭐</div>
        <div>
          <div class="legend-title">종합 점수 (최대 10점)</div>
          <div class="legend-desc">
            <span class="score-high">7점↑</span> 상위 트렌드 키워드 &nbsp;|&nbsp;
            <span class="score-mid">5–7점</span> 주목할 키워드 &nbsp;|&nbsp;
            <span class="score-low">5점↓</span> 참고용
          </div>
        </div>
      </div>
      <hr class="legend-divider">
      <div>
        <div style="font-weight:700; margin-bottom:10px;">📡 신뢰도 — 검색 결과 수 기반</div>
        <div class="cred-row">
          <div class="cred-item"><span class="cred-high">높음</span> 12건↑</div>
          <div class="cred-item"><span class="cred-mid">보통</span> 6–11건</div>
          <div class="cred-item"><span class="cred-low">낮음</span> 2–5건</div>
          <div class="cred-item" style="color:var(--red)">매우낮음 1건↓</div>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
// ── 비밀번호 검증 ────────────────────────────────────────
function checkPassword() {
  const pwd = document.getElementById('pwd-input').value;
  const errorMsg = document.getElementById('error-msg');
  
  if (pwd === 'lavida') {
    document.getElementById('login-modal').style.display = 'none';
    sessionStorage.setItem('auth', 'true');
  } else {
    errorMsg.textContent = '비밀번호가 틀렸습니다';
    errorMsg.style.display = 'block';
    document.getElementById('pwd-input').value = '';
    document.getElementById('pwd-input').focus();
  }
}

// ── 페이지 로드 시 인증 확인 ────────────────────────────────────────
window.addEventListener('load', () => {
  if (sessionStorage.getItem('auth') === 'true') {
    document.getElementById('login-modal').style.display = 'none';
  }
});

// ── 로그아웃 함수 (선택사항) ────────────────────────────────────────
function logout() {
  sessionStorage.removeItem('auth');
  location.reload();
}

// ── SSE 이벤트 핸들러 ────────────────────────────────────────
let evtSource = null;
let searchIdx = 0, scoreIdx = 0, suggestIdx = 0;

function switchTab(name) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}

function setProgress(pct, status) {
  document.getElementById('progress-bar').style.width = pct + '%';
  if (status) document.getElementById('status-text').textContent = status;
}

function addLog(html) {
  const box = document.getElementById('log-box');
  box.innerHTML += html + '\\n';
  box.scrollTop = box.scrollHeight;
}

function scoreClass(v) {
  return v >= 7 ? 'score-high' : v >= 5 ? 'score-mid' : 'score-low';
}
function credClass(c) {
  return c === '높음' ? 'cred-high' : c === '보통' ? 'cred-mid' : 'cred-low';
}
function miniBar(val, max, color) {
  const pct = Math.min(100, val / max * 100);
  return `<div class="bar-wrap"><div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%;background:${color}"></div></div><span>${val}</span></div>`;
}

function startAnalysis() {
  const raw = document.getElementById('kw-input').value.trim();
  if (!raw) { alert('키워드를 입력하세요'); return; }
  const keywords = raw.replace(/,/g, ' ').split(/\\s+/).filter(Boolean);

  // 초기화
  ['search-tbody','score-tbody','suggest-tbody'].forEach(id => document.getElementById(id).innerHTML = '');
  document.getElementById('log-box').innerHTML = '';
  document.getElementById('summary-banner').style.display = 'none';
  document.getElementById('candidates-section').style.display = 'none';
  document.getElementById('candidates-wrap').innerHTML = '';
  searchIdx = scoreIdx = suggestIdx = 0;
  setProgress(0, '분석 시작...');
  document.getElementById('run-btn').disabled = true;
  document.getElementById('stop-btn').disabled = false;

  if (evtSource) evtSource.close();
  evtSource = new EventSource('/analyze?keywords=' + encodeURIComponent(keywords.join(',')));

  const total = keywords.length;

  evtSource.addEventListener('candidates', e => {
    const d = JSON.parse(e.data);
    const wrap = document.getElementById('candidates-wrap');
    wrap.innerHTML = d.keywords.map(k => `<span class="cand-badge">${k}</span>`).join('');
    document.getElementById('candidates-section').style.display = 'block';
  });

  evtSource.addEventListener('status', e => {
    const d = JSON.parse(e.data);
    addLog(`<span class="log-ok">${d.msg}</span>`);
    document.getElementById('status-text').textContent = d.msg;
  });

  evtSource.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    const pct = Math.round(d.current / total * 50);
    setProgress(pct, `검색 ${d.current}/${total}: ${d.keyword}`);
    addLog(`  <span class="log-dim">[${String(d.current).padStart(2,'0')}/${d.total}]</span> <span class="log-kw">${d.keyword}</span>`);
  });

  evtSource.addEventListener('search_row', e => {
    const d = JSON.parse(e.data);
    searchIdx++;
    const cred = d.credibility;
    const barW = Math.min(100, d.count / 16 * 100);
    const barColor = d.count >= 12 ? '#22c55e' : d.count >= 6 ? '#eab308' : '#64748b';
    document.getElementById('search-tbody').innerHTML +=
      `<tr>
        <td>${searchIdx}</td>
        <td>${d.keyword}</td>
        <td>${d.count}건</td>
        <td class="${credClass(cred)}">${cred}</td>
        <td><div class="bar-wrap"><div class="mini-bar"><div class="mini-bar-fill" style="width:${barW}%;background:${barColor}"></div></div></div></td>
      </tr>`;
  });

  evtSource.addEventListener('score_row', e => {
    const d = JSON.parse(e.data);
    scoreIdx++;
    setProgress(50 + Math.round(scoreIdx / total * 30), `점수 분석 ${scoreIdx}/${total}`);
    const cred = d.hit_count >= 12 ? '높음' : d.hit_count >= 6 ? '보통' : '낮음';
    const negClass = d.negative > 3 ? 'neg-bad' : 'neg-ok';
    document.getElementById('score-tbody').innerHTML +=
      `<tr>
        <td>${d.rank}</td>
        <td>${d.keyword}</td>
        <td>${miniBar(d.trend, 10, '#4f8ef7')}</td>
        <td>${miniBar(d.positive, 10, '#22c55e')}</td>
        <td class="${negClass}">${d.negative}</td>
        <td>${miniBar(d.originality, 10, '#7c5bf7')}</td>
        <td>${d.fusion_potential}</td>
        <td class="${scoreClass(d.total)}">${d.total}</td>
        <td>${d.hit_count}건</td>
        <td class="${credClass(cred)}">${cred}</td>
      </tr>`;
  });

  evtSource.addEventListener('suggest_row', e => {
    const d = JSON.parse(e.data);
    suggestIdx++;
    setProgress(80 + Math.round(suggestIdx / 12 * 15), '신규 키워드 생성 중...');
    document.getElementById('suggest-tbody').innerHTML +=
      `<tr>
        <td style="color:#c084fc;font-weight:600">${d.new_keyword}</td>
        <td>${d.source_a}</td>
        <td>${d.source_b}</td>
        <td style="color:var(--muted);font-size:.82rem">${d.rationale}</td>
        <td class="${scoreClass(d.estimated_score)}">${d.estimated_score}</td>
      </tr>`;
  });

  evtSource.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    setProgress(100, `✅ 분석 완료 — 키워드 제안 ${d.suggest_count}개`);
    addLog(`<span class="log-ok">🎉 분석 완료!</span>`);

    const medals = ['🥇','🥈','🥉'];
    const banner = document.getElementById('top-kw-list');
    banner.innerHTML = d.top.map((k, i) =>
      `<div class="top-kw-badge"><span class="medal">${medals[i]||''}</span>${k.keyword} <strong>${k.total}점</strong></div>`
    ).join('');
    document.getElementById('summary-banner').style.display = 'block';

    document.getElementById('run-btn').disabled = false;
    document.getElementById('stop-btn').disabled = true;
    evtSource.close();
    // 점수 탭으로 이동
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-score').classList.add('active');
    document.querySelectorAll('.tab-btn')[2].classList.add('active');
  });

  evtSource.onerror = () => {
    setProgress(0, '오류 발생 — 다시 시도하세요');
    document.getElementById('run-btn').disabled = false;
    document.getElementById('stop-btn').disabled = true;
    evtSource.close();
  };
}

function stopAnalysis() {
  if (evtSource) { evtSource.close(); evtSource = null; }
  setProgress(0, '⛔ 중단됨');
  addLog('<span style="color:var(--red)">⛔ 분석이 중단되었습니다.</span>');
  document.getElementById('run-btn').disabled = false;
  document.getElementById('stop-btn').disabled = true;
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    print("🚀 서버 시작: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

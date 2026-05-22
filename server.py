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
from naver_datalab import compare_keywords

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


@app.get("/compare")
async def compare(keywords: str):
    """GET /compare?keywords=도수치료,릴렉싱,테라피"""
    import asyncio
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:5]
    if not kw_list:
        return {"error": "키워드를 입력하세요"}
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, compare_keywords, kw_list)
    return {"results": results}


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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
  .mode-tabs {
    max-width: 1400px;
    margin: 14px auto 0;
    padding: 0 32px;
    display: flex;
    gap: 8px;
  }
  .mode-btn {
    border: 1px solid var(--border);
    background: rgba(255,255,255,.02);
    color: #94a3b8;
    border-radius: 999px;
    padding: 8px 14px;
    font-size: .85rem;
    font-weight: 700;
  }
  .mode-btn.active {
    color: #fff;
    background: linear-gradient(120deg, #2b4e89, #5a4cb3);
    border-color: transparent;
  }
  .view-pane { display: none; }
  .view-pane.active { display: block; }

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

  /* ── 검색어 비교 탭 ── */
  .cmp-controls {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    align-items: center;
    flex-wrap: wrap;
    position: sticky;
    top: 0;
    z-index: 50;
    padding: 14px 16px;
    margin-left: -16px;
    margin-right: -16px;
    background: linear-gradient(180deg, rgba(10,13,29,.96), rgba(10,13,29,.88));
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-bottom: 1px solid rgba(45,48,87,.72);
    box-shadow: 0 12px 28px rgba(0,0,0,.18);
  }
  .cmp-controls .cmp-radio-group { margin-left: auto; }
  #compare-page { padding: 20px 32px 40px; max-width: 1400px; margin: 0 auto; }
  #cmp-input {
    flex: 1; min-width: 240px;
    background: var(--panel);
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    color: var(--text); font-size: 1rem; padding: 12px 16px;
    outline: none; transition: border-color .2s;
  }
  #cmp-input:focus { border-color: var(--accent2); }
  #cmp-input::placeholder { color: var(--muted); }
  #cmp-btn { background: var(--accent2); color: #fff; }
  #cmp-status { padding: 8px 0; font-size: .9rem; min-height: 1.4em; }
  .cmp-trend-wrap {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px; margin-bottom: 24px;
  }
  .cmp-trend-wrap h3 { font-size: .95rem; color: var(--muted); margin-bottom: 14px; }
  .cmp-metrics-grid { display: grid; grid-template-columns: 1fr; gap: 18px; }
  @media (min-width: 980px) { .cmp-metrics-grid { grid-template-columns: 1fr 1fr; } }
  .cmp-metric-card {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px;
    min-height: 320px;
  }
  .cmp-metric-card h4 { font-size: .95rem; margin-bottom: 10px; color: var(--muted); }
  .cmp-metric-full { grid-column: 1 / -1; min-height: 360px; }
  .cmp-age-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .cmp-radio-group { display: flex; gap: 10px; flex-wrap: wrap; }
  .cmp-radio {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: #a8b4d8;
    font-size: .82rem;
  }
  .cmp-radio input { accent-color: var(--accent2); }
  .cmp-age-range-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 280px;
  }
  .cmp-age-range-meta {
    display: flex;
    justify-content: space-between;
    font-size: .78rem;
    color: #cbd5e1;
  }
  .cmp-age-range-slider {
    position: relative;
    height: 26px;
    --from: 0%;
    --to: 100%;
  }
  .cmp-age-range-slider::before {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    top: 11px;
    height: 4px;
    border-radius: 999px;
    background: linear-gradient(
      to right,
      rgba(71,85,105,.6) 0%,
      rgba(71,85,105,.6) var(--from),
      rgba(124,91,247,.9) var(--from),
      rgba(124,91,247,.9) var(--to),
      rgba(71,85,105,.6) var(--to),
      rgba(71,85,105,.6) 100%
    );
  }
  .cmp-age-range-slider input[type="range"] {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    height: 26px;
    margin: 0;
    background: transparent;
    -webkit-appearance: none;
    appearance: none;
    pointer-events: none;
  }
  .cmp-age-range-slider input[type="range"]::-webkit-slider-runnable-track {
    height: 4px;
    background: transparent;
  }
  .cmp-age-range-slider input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid #7c5bf7;
    margin-top: -5px;
    pointer-events: auto;
    cursor: pointer;
  }
  .cmp-age-range-slider input[type="range"]::-moz-range-track {
    height: 4px;
    background: transparent;
  }
  .cmp-age-range-slider input[type="range"]::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid #7c5bf7;
    pointer-events: auto;
    cursor: pointer;
  }
  .cmp-age-range-text {
    font-size: .8rem;
    color: #a78bfa;
    font-weight: 700;
  }
  .cmp-opportunity {
    margin-top: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .cmp-opportunity h4 {
    color: var(--muted);
    font-size: .94rem;
    margin-bottom: 10px;
  }
  .cmp-opportunity table { width: 100%; border-collapse: collapse; font-size: .85rem; }
  .cmp-opportunity th, .cmp-opportunity td {
    padding: 9px 10px;
    border-bottom: 1px solid rgba(45,48,87,.55);
    text-align: left;
    white-space: nowrap;
  }
  .cmp-opportunity tr:last-child td { border-bottom: none; }
  .opp-score-high { color: var(--green); font-weight: 700; }
  .opp-score-mid { color: var(--yellow); font-weight: 600; }
  .opp-score-low { color: #94a3b8; }
  .opp-chip {
    display: inline-block;
    font-size: .74rem;
    border-radius: 999px;
    padding: 2px 8px;
    border: 1px solid transparent;
  }
  .opp-chip.high { color: #86efac; border-color: rgba(34,197,94,.45); background: rgba(34,197,94,.12); }
  .opp-chip.mid { color: #fde68a; border-color: rgba(234,179,8,.45); background: rgba(234,179,8,.12); }
  .opp-chip.low { color: #cbd5e1; border-color: rgba(148,163,184,.35); background: rgba(148,163,184,.1); }
  .cmp-growth-card {
    margin-top: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .cmp-growth-card h4 {
    color: var(--muted);
    font-size: .94rem;
    margin-bottom: 10px;
  }
  .cmp-positioning-card {
    margin-top: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .cmp-positioning-card h4 {
    color: var(--muted);
    font-size: .94rem;
    margin-bottom: 10px;
  }
  .cmp-cluster-card {
    margin-top: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .cmp-cluster-card h4 {
    color: var(--muted);
    font-size: .94rem;
    margin-bottom: 10px;
  }
  .cmp-cluster-list {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }
  @media (min-width: 980px) {
    .cmp-cluster-list { grid-template-columns: 1fr 1fr; }
  }
  .cmp-cluster-item {
    border: 1px solid rgba(79,142,247,.28);
    background: rgba(79,142,247,.08);
    border-radius: 10px;
    padding: 12px;
  }
  .cmp-cluster-title {
    font-size: .88rem;
    color: #c7d2fe;
    font-weight: 700;
    margin-bottom: 8px;
  }
  .cmp-cluster-kws {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }
  .cmp-kw-chip {
    display: inline-block;
    font-size: .76rem;
    padding: 2px 8px;
    border-radius: 999px;
    color: #dbeafe;
    background: rgba(30,64,175,.35);
    border: 1px solid rgba(96,165,250,.35);
  }
  .cmp-cluster-strategy {
    font-size: .8rem;
    color: #93c5fd;
    line-height: 1.45;
  }
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

<section class="mode-tabs">
  <button class="mode-btn active" onclick="switchMainView('analysis', this)">키워드트렌드분석</button>
  <button class="mode-btn" onclick="switchMainView('compare', this)">키워드비교</button>
</section>

<div id="view-analysis" class="view-pane active">
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
      <button class="tab-btn active" onclick="switchTab('log', this)">📋 진행 로그</button>
      <button class="tab-btn" onclick="switchTab('search', this)">🔍 검색 현황</button>
      <button class="tab-btn" onclick="switchTab('score', this)">⭐ 점수 분석</button>
      <button class="tab-btn" onclick="switchTab('suggest', this)">💡 키워드 제안</button>
      <button class="tab-btn" onclick="switchTab('legend', this)">📐 점수 기준</button>
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
</div>

<div id="view-compare" class="view-pane">
  <div id="compare-page">
    <div class="cmp-controls">
      <input id="cmp-input" type="text"
        placeholder="키워드 입력 (쉼표 구분, 최대 5개 — 예: 도수치료, 릴렉싱, 테라피)"
        onkeydown="if(event.key==='Enter') startCompare()">
      <button id="cmp-btn" onclick="startCompare()">📊 비교 분석</button>
      <div class="cmp-radio-group" id="cmp-global-gender-group">
        <label class="cmp-radio"><input type="radio" name="cmp-global-gender" value="all" checked onchange="onCompareGenderChange()">전체</label>
        <label class="cmp-radio"><input type="radio" name="cmp-global-gender" value="male" onchange="onCompareGenderChange()">남성</label>
        <label class="cmp-radio"><input type="radio" name="cmp-global-gender" value="female" onchange="onCompareGenderChange()">여성</label>
      </div>
      <div class="cmp-age-range-wrap">
        <div class="cmp-age-range-meta">
          <span>최소: <strong id="cmp-age-min-value">10대</strong></span>
          <span>최대: <strong id="cmp-age-max-value">60대+</strong></span>
        </div>
        <div class="cmp-age-range-slider" id="cmp-age-range-slider">
          <input id="cmp-age-min" type="range" min="0" max="5" step="1" value="0" oninput="onAgeRangeInput('min', this.value)">
          <input id="cmp-age-max" type="range" min="0" max="5" step="1" value="5" oninput="onAgeRangeInput('max', this.value)">
        </div>
        <div class="cmp-age-range-text" id="cmp-age-range-text">10대 ~ 60대+</div>
      </div>
    </div>
    <div id="cmp-status"></div>
    <div id="cmp-trend-section" class="cmp-trend-wrap" style="display:none">
      <h3>📈 월별 검색량 트렌드 (상대 수치 0~100)</h3>
      <canvas id="chart-trend" height="80"></canvas>
    </div>
    <div id="cmp-metrics" class="cmp-metrics-grid" style="display:none">
      <div class="cmp-metric-card">
        <h4>👫 성별 비교 (키워드별)</h4>
        <canvas id="chart-gender-all" height="220"></canvas>
      </div>
      <div class="cmp-metric-card cmp-metric-full">
        <div class="cmp-age-toolbar">
          <h4>👥 연령대 비교 (키워드별)</h4>
          <div style="font-size:.8rem; color:#94a3b8">상단 연령 필터는 무시됨</div>
        </div>
        <canvas id="chart-age-all" height="120"></canvas>
      </div>
    </div>
    <div id="cmp-opportunity" class="cmp-opportunity" style="display:none">
      <h4>🚀 기회 점수 우선순위</h4>
      <div class="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>키워드</th>
              <th>기회 점수</th>
              <th>성장성</th>
              <th>현재 관심도</th>
              <th>타겟 확장성</th>
              <th>추천</th>
            </tr>
          </thead>
          <tbody id="cmp-opportunity-tbody"></tbody>
        </table>
      </div>
    </div>
    <div id="cmp-growth" class="cmp-growth-card" style="display:none">
      <h4>📈 성장률 비교 (1개월 / 3개월 / 6개월)</h4>
      <canvas id="chart-growth-rates" height="90"></canvas>
    </div>
    <div id="cmp-positioning" class="cmp-positioning-card" style="display:none">
      <h4>🧭 포지셔닝 맵 (관심도 vs 경쟁강도 추정)</h4>
      <canvas id="chart-positioning" height="100"></canvas>
    </div>
    <div id="cmp-clusters" class="cmp-cluster-card" style="display:none">
      <h4>🧩 콘텐츠 주제 클러스터</h4>
      <div id="cmp-cluster-list" class="cmp-cluster-list"></div>
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

function switchMainView(mode, btnEl) {
  document.querySelectorAll('.view-pane').forEach(p => p.classList.remove('active'));
  document.getElementById('view-' + mode).classList.add('active');
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  if (btnEl) btnEl.classList.add('active');
}

function switchTab(name, btnEl) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (btnEl) btnEl.classList.add('active');
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

// ── 검색어 비교 ────────────────────────────────────────
let cmpCharts = [];
const CMP_COLORS = ['#4f8ef7','#f7924f','#22c55e','#a855f7','#f43f5e'];
const AGE_LABELS = ['10대', '20대', '30대', '40대', '50대', '60대+'];
let cmpLastResults = [];
let cmpAgeChart = null;
let cmpAgeRangeMin = 0;
let cmpAgeRangeMax = AGE_LABELS.length - 1;

function ageRangeText(minIdx, maxIdx) {
  return `${AGE_LABELS[minIdx]} ~ ${AGE_LABELS[maxIdx]}`;
}

function selectedAgeRange() {
  const minIdx = clamp(cmpAgeRangeMin, 0, AGE_LABELS.length - 1);
  const maxIdx = clamp(cmpAgeRangeMax, minIdx, AGE_LABELS.length - 1);
  return { minIdx, maxIdx };
}

function selectedAgeLabels() {
  const { minIdx, maxIdx } = selectedAgeRange();
  return AGE_LABELS.slice(minIdx, maxIdx + 1);
}

function ageMapForLabels(ageMap, ageLabels) {
  const out = {};
  ageLabels.forEach(label => {
    out[label] = Number(ageMap?.[label] || 0);
  });
  return out;
}

function trendForAge(item, genderKey, ageLabel) {
  const byAge = item.trend_by_age || {};
  const ageGroupMap = byAge[genderKey] || byAge.all || {};
  const trend = ageGroupMap[ageLabel] || [];
  return Array.isArray(trend) ? trend : [];
}

function ageRangeTrendSeries(item, genderKey, ageLabels) {
  const bucket = new Map();
  ageLabels.forEach(ageLabel => {
    trendForAge(item, genderKey, ageLabel).forEach(t => {
      const period = (t.period || '').slice(0, 7);
      if (!period) return;
      const ratio = Number(t.ratio || 0);
      const prev = bucket.get(period) || { sum: 0, count: 0 };
      prev.sum += ratio;
      prev.count += 1;
      bucket.set(period, prev);
    });
  });

  return Array.from(bucket.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period, stat]) => ({ period, ratio: stat.count ? stat.sum / stat.count : 0 }));
}

function syncAgeRangeUI() {
  const { minIdx, maxIdx } = selectedAgeRange();
  const minInput = document.getElementById('cmp-age-min');
  const maxInput = document.getElementById('cmp-age-max');
  if (minInput) minInput.value = String(minIdx);
  if (maxInput) maxInput.value = String(maxIdx);

  const minLabel = document.getElementById('cmp-age-min-value');
  const maxLabel = document.getElementById('cmp-age-max-value');
  const rangeText = document.getElementById('cmp-age-range-text');
  if (minLabel) minLabel.textContent = AGE_LABELS[minIdx];
  if (maxLabel) maxLabel.textContent = AGE_LABELS[maxIdx];
  if (rangeText) rangeText.textContent = ageRangeText(minIdx, maxIdx);

  const sliderWrap = document.getElementById('cmp-age-range-slider');
  if (sliderWrap) {
    const denom = Math.max(1, AGE_LABELS.length - 1);
    sliderWrap.style.setProperty('--from', `${(minIdx / denom) * 100}%`);
    sliderWrap.style.setProperty('--to', `${(maxIdx / denom) * 100}%`);
  }
}

function onAgeRangeInput(bound, value) {
  const idx = clamp(parseInt(value, 10) || 0, 0, AGE_LABELS.length - 1);
  if (bound === 'min') {
    cmpAgeRangeMin = Math.min(idx, cmpAgeRangeMax);
  } else {
    cmpAgeRangeMax = Math.max(idx, cmpAgeRangeMin);
  }
  syncAgeRangeUI();
  if (!cmpLastResults || !cmpLastResults.length) return;
  renderFilteredCompareViews(selectedCompareGender());
}

function startCompare() {
  const raw = document.getElementById('cmp-input').value.trim();
  if (!raw) { alert('키워드를 입력하세요'); return; }
  const keywords = raw.split(/[,，\\s]+/).map(k => k.trim()).filter(Boolean).slice(0, 5);

  const btn = document.getElementById('cmp-btn');
  const status = document.getElementById('cmp-status');
  btn.disabled = true;
  status.style.color = 'var(--accent)';
  status.textContent = '📡 네이버 데이터랩 조회 중... (10~20초 소요)';
  document.getElementById('cmp-trend-section').style.display = 'none';
  document.getElementById('cmp-metrics').style.display = 'none';
  document.getElementById('cmp-opportunity').style.display = 'none';
  document.getElementById('cmp-growth').style.display = 'none';
  document.getElementById('cmp-positioning').style.display = 'none';
  document.getElementById('cmp-clusters').style.display = 'none';
  document.getElementById('cmp-opportunity-tbody').innerHTML = '';
  document.getElementById('cmp-cluster-list').innerHTML = '';
  document.querySelector('input[name="cmp-global-gender"][value="all"]').checked = true;
  cmpAgeRangeMin = 0;
  cmpAgeRangeMax = AGE_LABELS.length - 1;
  syncAgeRangeUI();
  cmpCharts.forEach(c => c.destroy());
  cmpCharts = [];
  if (cmpAgeChart) { cmpAgeChart.destroy(); cmpAgeChart = null; }
  cmpLastResults = [];

  fetch('/compare?keywords=' + encodeURIComponent(keywords.join(',')))
    .then(r => r.json())
    .then(data => {
      btn.disabled = false;
      if (data.error) {
        status.style.color = 'var(--red)';
        status.textContent = '❌ ' + data.error;
        return;
      }
      status.textContent = '';
      renderCompare(data.results);
    })
    .catch(err => {
      btn.disabled = false;
      status.style.color = 'var(--red)';
      status.textContent = '❌ 오류: ' + err.message;
    });
}

function renderCompare(results) {
  if (!results || !results.length) return;
  cmpLastResults = results;

  // ── 트렌드 라인 차트 ──
  const trendSection = document.getElementById('cmp-trend-section');
  trendSection.style.display = 'block';
  document.getElementById('cmp-metrics').style.display = 'grid';
  document.getElementById('cmp-opportunity').style.display = 'block';
  document.getElementById('cmp-growth').style.display = 'block';
  document.getElementById('cmp-positioning').style.display = 'block';
  document.getElementById('cmp-clusters').style.display = 'block';
  renderFilteredCompareViews(selectedCompareGender());
}

function selectedCompareGender() {
  const selected = document.querySelector('input[name="cmp-global-gender"]:checked');
  return selected ? selected.value : 'all';
}

function onCompareGenderChange() {
  if (!cmpLastResults || !cmpLastResults.length) return;
  renderFilteredCompareViews(selectedCompareGender());
}

function trendForGender(item, genderKey) {
  const byGender = item.trend_by_gender || {};
  const trend = byGender[genderKey] || item.trend || [];
  return Array.isArray(trend) ? trend : [];
}

function renderTrendChart(results, genderKey) {
  const ageLabels = selectedAgeLabels();
  const periodSet = new Set();
  results.forEach(r => ageRangeTrendSeries(r, genderKey, ageLabels).forEach(t => periodSet.add((t.period || '').slice(0, 7))));
  const labels = Array.from(periodSet).filter(Boolean).sort();

  cmpCharts.push(new Chart(document.getElementById('chart-trend').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: results.map((r, i) => {
        const map = new Map(ageRangeTrendSeries(r, genderKey, ageLabels).map(t => [(t.period || '').slice(0, 7), Number(t.ratio || 0)]));
        return {
          label: r.keyword,
          data: labels.map(lb => map.has(lb) ? map.get(lb) : null),
          borderColor: CMP_COLORS[i % CMP_COLORS.length],
          backgroundColor: CMP_COLORS[i % CMP_COLORS.length] + '22',
          tension: 0.3,
          fill: false,
          pointRadius: 3,
          spanGaps: true,
        };
      })
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#a8b4d8' } } },
      scales: {
        x: { ticks: { color: '#64748b', maxRotation: 45 }, grid: { color: '#2d3057' } },
        y: { ticks: { color: '#64748b' }, grid: { color: '#2d3057' }, min: 0 }
      }
    }
  }));
}

function renderGenderChart(results) {
  cmpCharts.push(new Chart(
    document.getElementById('chart-gender-all').getContext('2d'), {
    type: 'bar',
    data: {
      labels: results.map(r => r.keyword),
      datasets: [
        {
          label: '남성',
          data: results.map(r => r.gender.male),
          backgroundColor: '#4f8ef799',
          borderColor: '#4f8ef7',
          borderWidth: 1,
        },
        {
          label: '여성',
          data: results.map(r => r.gender.female),
          backgroundColor: '#f472b699',
          borderColor: '#f472b6',
          borderWidth: 1,
        }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#a8b4d8' } } },
      scales: {
        x: { ticks: { color: '#a8b4d8' }, grid: { color: '#2d3057' } },
        y: {
          ticks: { color: '#64748b', callback: v => v + '%' },
          grid: { color: '#2d3057' },
          min: 0,
          max: 100,
        }
      }
    }
  }));
}

function renderFilteredCompareViews(genderKey) {
  cmpCharts.forEach(c => c.destroy());
  cmpCharts = [];
  if (cmpAgeChart) { cmpAgeChart.destroy(); cmpAgeChart = null; }

  renderTrendChart(cmpLastResults, genderKey);
  renderGenderChart(cmpLastResults);
  renderAgeCompareChart(cmpLastResults, genderKey);
  renderOpportunityTable(cmpLastResults, genderKey, selectedAgeLabels());
  renderGrowthRateChart(cmpLastResults, genderKey, selectedAgeLabels());
  renderPositioningMap(cmpLastResults, genderKey, selectedAgeLabels());
  renderContentClusters(cmpLastResults, genderKey, selectedAgeLabels());
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function oppScoreClass(score) {
  if (score >= 70) return 'opp-score-high';
  if (score >= 50) return 'opp-score-mid';
  return 'opp-score-low';
}

function oppTier(score) {
  if (score >= 70) return { label: '지금 공략', cls: 'high' };
  if (score >= 50) return { label: '테스트 권장', cls: 'mid' };
  return { label: '관찰 유지', cls: 'low' };
}

function calcOpportunityMetrics(item, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const trend = ageRangeTrendSeries(item, genderKey, ageLabels);
  const ratios = trend.map(t => Number(t.ratio || 0));

  const last = ratios.length ? ratios[ratios.length - 1] : 0;
  const prev = ratios.slice(Math.max(0, ratios.length - 4), Math.max(0, ratios.length - 1));
  const prevAvg = prev.length ? prev.reduce((a, b) => a + b, 0) / prev.length : 0;

  const growthRaw = prevAvg > 0 ? ((last - prevAvg) / prevAvg) * 100 : (last > 0 ? 100 : 0);
  const growthScore = clamp(((clamp(growthRaw, -100, 200) + 100) / 300) * 100, 0, 100);

  const levelAvg = ratios.length ? ratios.reduce((a, b) => a + b, 0) / ratios.length : 0;
  const levelScore = clamp(levelAvg, 0, 100);

  const g = item.gender || {};
  const d = item.device || {};
  const agesByGender = item.ages_by_gender || {};
  const ages = ageMapForLabels(agesByGender[genderKey] || item.ages || {}, ageLabels);
  const genderBalance = genderKey === 'all' ? (100 - Math.abs((g.male || 0) - (g.female || 0))) : 100;
  const deviceBalance = 100 - Math.abs((d.mobile || 0) - (d.pc || 0));
  const maxAgeShare = Math.max(...Object.values(ages).map(v => Number(v || 0)), 0);
  const ageDiversity = 100 - maxAgeShare;
  const audienceBreadth = clamp(0.4 * genderBalance + 0.3 * deviceBalance + 0.3 * ageDiversity, 0, 100);

  const opportunityScore = clamp(0.45 * growthScore + 0.35 * levelScore + 0.2 * audienceBreadth, 0, 100);

  return {
    growth: Math.round(growthScore),
    level: Math.round(levelScore),
    audience: Math.round(audienceBreadth),
    total: Math.round(opportunityScore),
  };
}

function renderOpportunityTable(results, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const tbody = document.getElementById('cmp-opportunity-tbody');
  const ranked = results.map(r => ({
    keyword: r.keyword,
    ...calcOpportunityMetrics(r, genderKey, ageLabels),
  })).sort((a, b) => b.total - a.total);

  tbody.innerHTML = ranked.map((r, idx) => {
    const tier = oppTier(r.total);
    return `
      <tr>
        <td>${idx + 1}</td>
        <td>${r.keyword}</td>
        <td class="${oppScoreClass(r.total)}">${r.total}</td>
        <td>${r.growth}</td>
        <td>${r.level}</td>
        <td>${r.audience}</td>
        <td><span class="opp-chip ${tier.cls}">${tier.label}</span></td>
      </tr>
    `;
  }).join('');
}

function pctChange(current, past) {
  if (past > 0) return ((current - past) / past) * 100;
  if (current > 0) return 100;
  return 0;
}

function cappedPct(v) {
  return clamp(v, -100, 300);
}

function growthForMonths(ratios, monthsBack) {
  if (!ratios || ratios.length <= monthsBack) return 0;
  const current = Number(ratios[ratios.length - 1] || 0);
  const past = Number(ratios[ratios.length - 1 - monthsBack] || 0);
  return Math.round(cappedPct(pctChange(current, past)));
}

function renderGrowthRateChart(results, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const keywordLabels = results.map(r => r.keyword);
  const growth1 = results.map(r => growthForMonths(ageRangeTrendSeries(r, genderKey, ageLabels).map(t => Number(t.ratio || 0)), 1));
  const growth3 = results.map(r => growthForMonths(ageRangeTrendSeries(r, genderKey, ageLabels).map(t => Number(t.ratio || 0)), 3));
  const growth6 = results.map(r => growthForMonths(ageRangeTrendSeries(r, genderKey, ageLabels).map(t => Number(t.ratio || 0)), 6));

  cmpCharts.push(new Chart(
    document.getElementById('chart-growth-rates').getContext('2d'), {
    type: 'bar',
    data: {
      labels: keywordLabels,
      datasets: [
        {
          label: '1개월',
          data: growth1,
          backgroundColor: '#4f8ef799',
          borderColor: '#4f8ef7',
          borderWidth: 1,
        },
        {
          label: '3개월',
          data: growth3,
          backgroundColor: '#f59e0b99',
          borderColor: '#f59e0b',
          borderWidth: 1,
        },
        {
          label: '6개월',
          data: growth6,
          backgroundColor: '#22c55e99',
          borderColor: '#22c55e',
          borderWidth: 1,
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#a8b4d8' } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}%`
          }
        }
      },
      scales: {
        x: { ticks: { color: '#a8b4d8' }, grid: { color: '#2d3057' } },
        y: {
          ticks: { color: '#64748b', callback: v => v + '%' },
          grid: { color: '#2d3057' },
          min: -100,
          max: 300,
        }
      }
    }
  }));
}

function renderPositioningMap(results, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const datasets = results.map((r, i) => {
    const metrics = calcOpportunityMetrics(r, genderKey, ageLabels);
    const trendRatios = ageRangeTrendSeries(r, genderKey, ageLabels).map(t => Number(t.ratio || 0));
    const interest = trendRatios.length ? trendRatios.reduce((a, b) => a + b, 0) / trendRatios.length : 0;
    const competition = clamp(0.65 * metrics.level + 0.35 * (100 - metrics.audience), 0, 100);
    const radius = 6 + (metrics.total / 100) * 12;

    return {
      label: r.keyword,
      data: [{
        x: Number(interest.toFixed(1)),
        y: Number(competition.toFixed(1)),
        r: Number(radius.toFixed(1)),
      }],
      backgroundColor: CMP_COLORS[i % CMP_COLORS.length] + '88',
      borderColor: CMP_COLORS[i % CMP_COLORS.length],
      borderWidth: 1.5,
    };
  });

  cmpCharts.push(new Chart(
    document.getElementById('chart-positioning').getContext('2d'), {
    type: 'bubble',
    data: { datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#a8b4d8' } },
        tooltip: {
          callbacks: {
            title: items => items?.[0]?.dataset?.label || '',
            label: ctx => {
              const p = ctx.raw || {};
              return `관심도 ${p.x} / 경쟁강도 ${p.y}`;
            }
          }
        }
      },
      scales: {
        x: {
          min: 0,
          max: 100,
          title: { display: true, text: '관심도 (평균 상대검색량)', color: '#94a3b8' },
          ticks: { color: '#64748b' },
          grid: { color: '#2d3057' },
        },
        y: {
          min: 0,
          max: 100,
          title: { display: true, text: '경쟁강도 추정', color: '#94a3b8' },
          ticks: { color: '#64748b' },
          grid: { color: '#2d3057' },
        }
      }
    }
  }));
}

function primaryAgeLabel(item, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const byGender = item.ages_by_gender || {};
  const ages = ageMapForLabels(byGender[genderKey] || item.ages || {}, ageLabels);
  const entries = Object.entries(ages);
  if (!entries.length) return '20대';
  entries.sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
  return entries[0][0] || '20대';
}

function contentTagSet(item, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const trendRatios = ageRangeTrendSeries(item, genderKey, ageLabels).map(t => Number(t.ratio || 0));
  const growth3m = growthForMonths(trendRatios, 3);
  const levelAvg = trendRatios.length ? trendRatios.reduce((a, b) => a + b, 0) / trendRatios.length : 0;

  const gender = item.gender || {};
  const device = item.device || {};
  const male = Number(gender.male || 0);
  const female = Number(gender.female || 0);
  const mobile = Number(device.mobile || 0);
  const pc = Number(device.pc || 0);
  const ageTop = primaryAgeLabel(item, genderKey, ageLabels);

  const momentumTag = growth3m >= 20 ? '급상승형' : growth3m <= -10 ? '하락주의형' : '안정축적형';
  const scaleTag = levelAvg >= 45 ? '대중형' : levelAvg <= 12 ? '니치형' : '중간확장형';

  let personaTag = '균형타겟형';
  if (['10대', '20대'].includes(ageTop)) personaTag = '젊은층형';
  if (['40대', '50대', '60대+'].includes(ageTop)) personaTag = '중장년층형';
  if (female - male >= 15) personaTag = '여성집중형';
  if (male - female >= 15) personaTag = '남성집중형';

  let channelTag = '멀티채널형';
  if (mobile - pc >= 20) channelTag = '숏폼모바일형';
  if (pc - mobile >= 20) channelTag = '검색블로그형';

  return {
    clusterKey: `${momentumTag} · ${personaTag}`,
    momentumTag,
    scaleTag,
    personaTag,
    channelTag,
  };
}

function clusterStrategyText(tag) {
  const base = `${tag.momentumTag} + ${tag.personaTag}`;
  if (tag.channelTag === '숏폼모바일형') {
    return `${base}군: 릴스/숏츠 중심으로 짧은 전후비교, 체험컷, 질문형 훅 콘텐츠를 우선 제작`;
  }
  if (tag.channelTag === '검색블로그형') {
    return `${base}군: 블로그/검색형 가이드로 원인-해결-비교 구조의 롱폼 콘텐츠를 우선 제작`;
  }
  return `${base}군: 숏폼 유입 + 블로그 상세 설명을 함께 운영하는 멀티채널 구성이 효율적`;
}

function renderContentClusters(results, genderKey = 'all', ageLabels = selectedAgeLabels()) {
  const listEl = document.getElementById('cmp-cluster-list');
  const groups = new Map();

  results.forEach(item => {
    const tags = contentTagSet(item, genderKey, ageLabels);
    if (!groups.has(tags.clusterKey)) {
      groups.set(tags.clusterKey, {
        key: tags.clusterKey,
        keywords: [],
        strategy: clusterStrategyText(tags),
      });
    }
    groups.get(tags.clusterKey).keywords.push(item.keyword);
  });

  const clusters = Array.from(groups.values()).sort((a, b) => b.keywords.length - a.keywords.length);
  listEl.innerHTML = clusters.map(cluster => `
    <div class="cmp-cluster-item">
      <div class="cmp-cluster-title">${cluster.key}</div>
      <div class="cmp-cluster-kws">
        ${cluster.keywords.map(k => `<span class="cmp-kw-chip">${k}</span>`).join('')}
      </div>
      <div class="cmp-cluster-strategy">${cluster.strategy}</div>
    </div>
  `).join('');
}

function renderAgeCompareChart(results, genderKey) {
  const ageLabels = AGE_LABELS;
  const ageSourceKey = (genderKey === 'male' || genderKey === 'female') ? genderKey : 'all';

  if (cmpAgeChart) {
    cmpAgeChart.destroy();
    cmpAgeChart = null;
  }

  cmpAgeChart = new Chart(
    document.getElementById('chart-age-all').getContext('2d'), {
    type: 'bar',
    data: {
      labels: ageLabels,
      datasets: results.map((r, i) => ({
        label: r.keyword,
        data: ageLabels.map(a => {
          const byGender = r.ages_by_gender || {};
          const ageMap = byGender[ageSourceKey] || r.ages || {};
          return ageMap[a] || 0;
        }),
        backgroundColor: CMP_COLORS[i % CMP_COLORS.length] + '99',
        borderColor: CMP_COLORS[i % CMP_COLORS.length],
        borderWidth: 1,
      }))
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#a8b4d8' } },
        tooltip: {
          callbacks: {
            title: items => {
              const ageLabel = items?.[0]?.label || '';
              const labelMap = { all: '전체', male: '남성', female: '여성' };
              return `${ageLabel} (${labelMap[ageSourceKey]})`;
            }
          }
        }
      },
      scales: {
        x: { ticks: { color: '#a8b4d8' }, grid: { color: '#2d3057' } },
        y: {
          ticks: { color: '#64748b', callback: v => v + '%' },
          grid: { color: '#2d3057' },
          min: 0,
        }
      }
    }
  });
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    print("🚀 서버 시작: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

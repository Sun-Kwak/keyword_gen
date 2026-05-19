"""
키워드 트렌드 분석기 — TUI 앱
실행: python app.py
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Input, Button, DataTable,
    Log, TabbedContent, TabPane, Static, Label, ProgressBar
)
from textual.containers import Horizontal, Vertical
from textual.worker import get_current_worker
from textual import work, on
from rich.text import Text

from config import SCORE_WEIGHTS


CSS = """
Screen {
    background: $surface;
}

/* ── 상단 입력 바 ── */
#top-bar {
    height: 3;
    padding: 0 1;
    background: $panel;
    border-bottom: tall $primary;
}

#keyword-input {
    width: 1fr;
    margin-right: 1;
}

#run-btn {
    width: 16;
    margin-right: 1;
}

#stop-btn {
    width: 10;
}

/* ── 진행 바 ── */
#progress-row {
    height: 2;
    padding: 0 1;
    background: $panel-darken-1;
}

#progress-bar {
    width: 1fr;
    margin-top: 0;
}

#status-label {
    width: 30;
    text-align: right;
    color: $text-muted;
    padding-top: 0;
}

/* ── 탭 영역 ── */
TabbedContent {
    height: 1fr;
}

TabPane {
    padding: 0;
}

DataTable {
    height: 1fr;
}

Log {
    height: 1fr;
    background: $surface;
}

/* ── 범례 탭 ── */
#legend-text {
    padding: 2 3;
    background: $surface;
    height: 1fr;
}

/* ── 푸터 ── */
Footer {
    height: 1;
}
"""


def _cred_text(hit_count: int) -> Text:
    if hit_count >= 12:
        return Text("높음", style="green bold")
    elif hit_count >= 6:
        return Text("보통", style="yellow")
    elif hit_count >= 2:
        return Text("낮음", style="dim")
    else:
        return Text("매우낮음", style="red")


def _score_text(score: float) -> Text:
    s = f"{score:.2f}"
    if score >= 7:
        return Text(s, style="green bold")
    elif score >= 5:
        return Text(s, style="yellow")
    else:
        return Text(s, style="dim")


class KeywordAnalyzerApp(App):
    TITLE = "키워드 트렌드 분석기"
    CSS = CSS
    BINDINGS = [
        ("ctrl+c", "quit", "종료"),
        ("f1", "switch_tab('log-tab')", "로그"),
        ("f2", "switch_tab('search-tab')", "검색현황"),
        ("f3", "switch_tab('score-tab')", "점수분석"),
        ("f4", "switch_tab('suggest-tab')", "키워드제안"),
        ("f5", "switch_tab('legend-tab')", "점수기준"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="top-bar"):
            yield Input(
                placeholder="분석할 키워드 입력 (예: 패시브 스트레칭, 소매틱 운동, slow fitness)  — Enter 또는 ▶ 버튼",
                id="keyword-input",
            )
            yield Button("▶ 분석 시작", id="run-btn", variant="success")
            yield Button("■ 중지", id="stop-btn", variant="error", disabled=True)
        with Horizontal(id="progress-row"):
            yield ProgressBar(total=100, id="progress-bar", show_eta=False, show_percentage=True)
            yield Label("대기 중", id="status-label")
        with TabbedContent(id="tabs"):
            with TabPane("📋 진행 로그", id="log-tab"):
                yield Log(id="run-log", highlight=True)
            with TabPane("🔍 검색 현황", id="search-tab"):
                yield DataTable(id="search-table", zebra_stripes=True, cursor_type="row")
            with TabPane("⭐ 점수 분석", id="score-tab"):
                yield DataTable(id="score-table", zebra_stripes=True, cursor_type="row")
            with TabPane("💡 키워드 제안", id="suggest-tab"):
                yield DataTable(id="suggest-table", zebra_stripes=True, cursor_type="row")
            with TabPane("📐 점수 기준", id="legend-tab"):
                yield Static(id="legend-text")
        yield Footer()

    def on_mount(self) -> None:
        # 검색 현황 테이블 컬럼
        st = self.query_one("#search-table", DataTable)
        st.add_columns("키워드", "수집건수", "신뢰도", "검색바")

        # 점수 분석 테이블 컬럼
        sc = self.query_one("#score-table", DataTable)
        sc.add_columns(
            "#", "키워드",
            "🔥트렌드\n(×30%)", "✅긍정\n(×25%)",
            "⚠️부정\n(×15%↓)", "💡독창성\n(×20%)",
            "🔗융합\n(×10%)", "⭐종합",
            "검색수", "신뢰도",
        )

        # 키워드 제안 테이블 컬럼
        sg = self.query_one("#suggest-table", DataTable)
        sg.add_columns("💡 제안 키워드", "출처 A", "출처 B", "융합 논리", "예상점수")

        # 범례 초기화
        self._setup_legend()

        # 포커스
        self.query_one("#keyword-input", Input).focus()

    def _setup_legend(self) -> None:
        weights = SCORE_WEIGHTS
        content = (
            "[bold cyan]📐 점수 산정 기준[/bold cyan]\n\n"
            "각 후보 키워드(30개)를 DuckDuckGo로 개별 검색 후 5개 차원에서 0–10점 채점\n\n"
            f"  [bold yellow]🔥 트렌드[/bold yellow]   가중치 [cyan]{int(weights['trend']*100)}%[/cyan]\n"
            "      검색결과 내 트렌드 신호어 빈도 + 해당 키워드 검색량\n\n"
            f"  [bold green]✅ 긍정[/bold green]     가중치 [cyan]{int(weights['positive']*100)}%[/cyan]\n"
            "      효과·추천·힐링·인기 등 긍정 표현 빈도\n\n"
            f"  [bold red]⚠️  부정[/bold red]     가중치 [cyan]{int(weights['negative']*100)}%[/cyan]  (낮을수록 유리, 역산)\n"
            "      부작용·위험·논란·금지 등 부정 표현 빈도\n\n"
            f"  [bold cyan]💡 독창성[/bold cyan]   가중치 [cyan]{int(weights['originality']*100)}%[/cyan]\n"
            "      패시브·소매틱·마인드풀 등 수식어 포함 여부\n"
            "      검색량이 적을수록 아직 발견되지 않은 신규 개념으로 가점\n\n"
            f"  [bold magenta]🔗 융합가능[/bold magenta] 가중치 [cyan]{int(weights['fusion_potential']*100)}%[/cyan]\n"
            "      stretching/relaxation/mind_body 등 여러 카테고리에 걸칠수록 융합 잠재력 ↑\n\n"
            "[dim]──────────────────────────────────────────[/dim]\n\n"
            "  [bold white]⭐ 종합점수[/bold white] = 가중 합산 (최대 10점)\n"
            "    [green]7점↑[/green]  상위 트렌드 키워드\n"
            "    [yellow]5–7점[/yellow] 주목할 키워드\n"
            "    [dim]5점↓[/dim]  참고용\n\n"
            "  [bold white]📡 신뢰도[/bold white] = 검색 결과 수 기반\n"
            "    [green]높음[/green] 12건↑  /  [yellow]보통[/yellow] 6–11건  /  [dim]낮음[/dim] 2–5건  /  [red]매우낮음[/red] 1건↓\n\n"
            "[dim]──────────────────────────────────────────[/dim]\n"
            "  F2 검색현황  F3 점수분석  F4 키워드제안  F5 점수기준\n"
        )
        self.query_one("#legend-text", Static).update(content)

    # ── 엔터키로도 분석 시작 ──────────────────────────────
    @on(Input.Submitted, "#keyword-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._start_analysis()

    @on(Button.Pressed, "#run-btn")
    def on_run_pressed(self) -> None:
        self._start_analysis()

    @on(Button.Pressed, "#stop-btn")
    def on_stop_pressed(self) -> None:
        for worker in self.workers:
            worker.cancel()
        self.query_one("#run-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = True
        self.query_one("#status-label", Label).update("[red]중단됨[/red]")
        self.query_one("#run-log", Log).write_line("[red]⛔ 분석이 중단되었습니다.[/red]")

    def _start_analysis(self) -> None:
        kw_input = self.query_one("#keyword-input", Input).value.strip()
        if not kw_input:
            self.query_one("#run-log", Log).write_line("[red]키워드를 입력해주세요.[/red]")
            self.query_one("#tabs", TabbedContent).active = "log-tab"
            return

        # 쉼표 또는 공백으로 구분 허용
        keywords = [k.strip() for k in kw_input.replace(",", " ").split() if k.strip()]

        # UI 초기화
        self.query_one("#run-log", Log).clear()
        self.query_one("#search-table", DataTable).clear()
        self.query_one("#score-table", DataTable).clear()
        self.query_one("#suggest-table", DataTable).clear()
        self.query_one("#progress-bar", ProgressBar).update(progress=0)
        self.query_one("#run-btn", Button).disabled = True
        self.query_one("#stop-btn", Button).disabled = False
        self.query_one("#status-label", Label).update("검색 중...")
        self.query_one("#tabs", TabbedContent).active = "log-tab"

        self._run_worker(keywords)

    # ── 백그라운드 워커 ───────────────────────────────────
    @work(thread=True)
    def _run_worker(self, keywords: list[str]) -> None:
        from web_searcher import search_keyword_data
        from trend_scorer import score_all_keywords
        from keyword_generator import generate_new_keywords
        from candidate_generator import generate_candidates
        import time

        worker = get_current_worker()

        def log(msg: str) -> None:
            self.call_from_thread(self.query_one("#run-log", Log).write_line, msg)

        def set_progress(pct: int, status: str = "") -> None:
            self.call_from_thread(
                self.query_one("#progress-bar", ProgressBar).update, progress=pct
            )
            if status:
                self.call_from_thread(
                    self.query_one("#status-label", Label).update, status
                )

        # ── 시드 → 후보 키워드 생성 ──────────────────────
        log(f"[bold cyan]━━ 후보 키워드 생성 ━━[/bold cyan]")
        log(f"시드: [cyan]{' / '.join(keywords)}[/cyan]")
        candidates = generate_candidates(keywords)
        log(f"↳ 후보 [yellow]{len(candidates)}[/yellow]개: {', '.join(candidates[:6])}{'...' if len(candidates) > 6 else ''}")
        log("")

        # ── STEP 1: 검색 ─────────────────────────────────
        log(f"[bold cyan]━━ STEP 1  웹 검색 수집 ━━[/bold cyan]")

        kw_data_map: dict = {}
        total = len(candidates)
        t_start = time.time()

        for i, kw in enumerate(candidates, 1):
            if worker.is_cancelled:
                return

            set_progress(int(i / total * 50), f"검색 {i}/{total}")
            log(f"  [{i:2}/{total}] [white]{kw}[/white]")
            kw_data_map[kw] = search_keyword_data(kw)

            n = kw_data_map[kw]["result_count"]
            cred = _cred_text(n)
            bar_filled = int(n / 16 * 10)
            bar = "█" * min(bar_filled, 10) + "░" * max(0, 10 - bar_filled)
            self.call_from_thread(
                self._add_search_row, kw, n, cred, bar
            )

        elapsed = time.time() - t_start
        total_hits = sum(d["result_count"] for d in kw_data_map.values())
        log("")
        log(f"[green]✅ 검색 완료[/green]  총 [bold]{total_hits}[/bold]건  │  소요 {elapsed:.0f}초  │  평균 {total_hits/total:.1f}건/키워드")

        # ── STEP 2: 점수 분석 ────────────────────────────
        log("")
        log("[bold cyan]━━ STEP 2  점수 분석 ━━[/bold cyan]")
        set_progress(60, "점수 분석 중...")

        scored = score_all_keywords(candidates, kw_data_map)

        for i, kw in enumerate(scored, 1):
            if worker.is_cancelled:
                return
            cred = _cred_text(kw["hit_count"])
            self.call_from_thread(self._add_score_row, i, kw, cred)

        log(f"[green]✅ 점수 분석 완료[/green]  {len(scored)}개 키워드")

        # ── STEP 3: 신규 키워드 제안 ────────────────────
        log("")
        log("[bold cyan]━━ STEP 3  신규 키워드 제안 ━━[/bold cyan]")
        set_progress(85, "키워드 조합 생성 중...")

        suggestions = generate_new_keywords(scored)

        for s in suggestions:
            if worker.is_cancelled:
                return
            self.call_from_thread(self._add_suggest_row, s)

        log(f"[green]✅ {len(suggestions)}개 신규 키워드 제안 완료[/green]")

        # ── 완료 ────────────────────────────────────────
        set_progress(100, "완료")
        log("")
        log("[bold green]🎉 분석 완료![/bold green]")
        log("")
        if scored:
            log("[bold white]🏆 상위 키워드[/bold white]")
            medals = ["🥇", "🥈", "🥉", "  4위", "  5위"]
            for medal, kw in zip(medals, scored[:5]):
                cred = "높음" if kw["hit_count"] >= 12 else "보통" if kw["hit_count"] >= 6 else "낮음"
                log(
                    f"  {medal} [yellow]{kw['keyword']}[/yellow]  "
                    f"[bold]{kw['total']}점[/bold]  "
                    f"(트렌드 {kw['trend']} | 긍정 {kw['positive']} | 검색 {kw['hit_count']}건 → {cred})"
                )
        if suggestions:
            log("")
            log("[bold white]💡 추천 신규 키워드[/bold white]")
            for s in suggestions[:3]:
                log(f"  → [magenta]{s['new_keyword']}[/magenta]  ({s['source_a']} × {s['source_b']})")

        self.call_from_thread(self._on_finish)

    # ── UI 업데이트 (메인 스레드) ─────────────────────────
    def _add_search_row(self, kw: str, count: int, cred: Text, bar: str) -> None:
        self.query_one("#search-table", DataTable).add_row(
            kw, f"{count}건", cred, bar
        )

    def _add_score_row(self, rank: int, kw: dict, cred: Text) -> None:
        neg = kw["negative"]
        neg_text = Text(str(neg), style="red" if neg > 3 else "green")
        self.query_one("#score-table", DataTable).add_row(
            str(rank),
            kw["keyword"],
            str(kw["trend"]),
            str(kw["positive"]),
            neg_text,
            str(kw["originality"]),
            str(kw["fusion_potential"]),
            _score_text(kw["total"]),
            str(kw["hit_count"]),
            cred,
        )

    def _add_suggest_row(self, s: dict) -> None:
        self.query_one("#suggest-table", DataTable).add_row(
            Text(s["new_keyword"], style="magenta bold"),
            s["source_a"],
            s["source_b"],
            s["rationale"],
            _score_text(s["estimated_score"]),
        )

    def _on_finish(self) -> None:
        self.query_one("#run-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = True
        # 분석 완료 후 점수 탭으로 자동 이동
        self.query_one("#tabs", TabbedContent).active = "score-tab"

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id


if __name__ == "__main__":
    KeywordAnalyzerApp().run()

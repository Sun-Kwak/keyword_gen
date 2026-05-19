"""
키워드 분석 메인 실행 파일

사용법:
  python run_analysis.py                        # 기본 키워드 (릴렉싱, 스트레칭)
  python run_analysis.py 요가 필라테스          # 직접 키워드 지정
  python run_analysis.py 요가 --top 10          # 상위 N개만 표시
  python run_analysis.py 요가 --detail          # 키워드별 검색 샘플 상세 보기
"""
import argparse
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich import box

from web_searcher import batch_search_keywords
from trend_scorer import score_all_keywords
from keyword_generator import generate_new_keywords
from config import SCORE_WEIGHTS

console = Console(width=120)

# ============================================================
# 분석할 후보 키워드 목록
# ============================================================
CANDIDATE_KEYWORDS = [
    "패시브 스트레칭", "정적 스트레칭", "동적 스트레칭", "PNF 스트레칭",
    "소매틱 스트레칭", "아시스티드 스트레칭", "딥 스트레칭", "마이오파셜 릴리즈",
    "폼 롤러", "인 요가", "리스토러티브 요가", "소매틱 운동",
    "마인드풀 스트레칭", "프로그레시브 머슬 릴렉세이션",
    "슬로우 피트니스", "회복 운동", "수면 스트레칭", "딥 티슈 마사지", "무빙 메디테이션",
    "passive stretching", "somatic stretching", "yin yoga", "restorative yoga",
    "mindful stretching", "recovery workout", "somatic movement",
    "deep stretching", "assisted stretching", "slow fitness", "progressive muscle relaxation",
]


# ─────────────────────────────────────────
# 유틸: 점수 바 시각화
# ─────────────────────────────────────────
def score_bar(value: float, max_val: float = 10.0, width: int = 8) -> str:
    filled = int(round(value / max_val * width))
    bar = "█" * filled + "░" * (width - filled)
    if value >= 7:
        return f"[green]{bar}[/green]"
    elif value >= 4:
        return f"[yellow]{bar}[/yellow]"
    else:
        return f"[dim]{bar}[/dim]"


def credibility_label(hit_count: int) -> str:
    if hit_count >= 12:
        return "[bold green]높음[/bold green]"
    elif hit_count >= 6:
        return "[yellow]보통[/yellow]"
    elif hit_count >= 2:
        return "[dim]낮음[/dim]"
    else:
        return "[red]매우낮음[/red]"


# ─────────────────────────────────────────
# 점수 기준 범례 출력
# ─────────────────────────────────────────
def print_score_legend():
    legend = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    legend.add_column(width=14)
    legend.add_column(width=8, justify="right")
    legend.add_column(width=40)

    rows = [
        ("🔥 트렌드",    f"{int(SCORE_WEIGHTS['trend']*100)}%",       "검색결과 내 트렌드 신호어 빈도 + 검색량"),
        ("✅ 긍정",       f"{int(SCORE_WEIGHTS['positive']*100)}%",    "효과·추천·힐링 등 긍정 표현 빈도"),
        ("⚠️  부정",      f"{int(SCORE_WEIGHTS['negative']*100)}%",   "부작용·위험·논란 등 부정 표현 (낮을수록 좋음, 역산)"),
        ("💡 독창성",    f"{int(SCORE_WEIGHTS['originality']*100)}%",  "패시브·소매틱 등 수식어 + 검색량 적을수록 신선"),
        ("🔗 융합가능",  f"{int(SCORE_WEIGHTS['fusion_potential']*100)}%", "여러 카테고리에 걸칠수록 융합 잠재력 높음"),
    ]
    for name, weight, desc in rows:
        legend.add_row(f"[bold]{name}[/bold]", f"[cyan]가중치 {weight}[/cyan]", f"[dim]{desc}[/dim]")

    console.print(Panel(
        legend,
        title="[bold white]📐 점수 산정 기준[/bold white]",
        border_style="blue",
        padding=(0, 1),
    ))
    console.print(
        "  [dim]신뢰도 = 해당 키워드의 실제 검색 결과 수 기반  │  "
        "높음(12건↑) / 보통(6-11건) / 낮음(2-5건) / 매우낮음(1건↓)[/dim]\n"
    )


# ─────────────────────────────────────────
# 메인 분석
# ─────────────────────────────────────────
def run_analysis(input_keywords: list[str], top_n: int = 25, show_detail: bool = False):
    console.print()
    console.print(Panel.fit(
        f"[bold white]🔍 키워드 트렌드 분석기[/bold white]\n"
        f"[cyan]입력 키워드:[/cyan] {' / '.join(input_keywords)}  "
        f"[dim]│ 후보 키워드 {len(CANDIDATE_KEYWORDS)}개 분석[/dim]",
        border_style="cyan",
    ))

    print_score_legend()

    # ─── STEP 1 검색 ───────────────────────────────
    console.print(Rule("[bold yellow]STEP 1  웹 검색 수집[/bold yellow]", style="yellow"))

    kw_data_map = {}
    start_search = time.time()
    total_count = len(CANDIDATE_KEYWORDS)

    for i, kw in enumerate(CANDIDATE_KEYWORDS, 1):
        # 진행 표시
        bar_w = 30
        filled = int(i / total_count * bar_w)
        prog_bar = f"[green]{'█' * filled}[/green][dim]{'░' * (bar_w - filled)}[/dim]"
        console.print(
            f"  {prog_bar} [cyan]{i:2}/{total_count}[/cyan]  [white]{kw}[/white]" + " " * 20,
            end="\r"
        )
        from web_searcher import search_keyword_data
        kw_data_map[kw] = search_keyword_data(kw)

    elapsed_search = time.time() - start_search
    total_hits = sum(d["result_count"] for d in kw_data_map.values())
    console.print(" " * 80, end="\r")

    # 검색 결과 요약 표
    search_summary = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    search_summary.add_column("키워드", style="white", width=28)
    search_summary.add_column("수집건수", justify="center", width=8)
    search_summary.add_column("신뢰도", justify="center", width=8)
    search_summary.add_column("검색바", width=12)

    # 검색수 기준 정렬해서 표시
    sorted_by_hits = sorted(kw_data_map.items(), key=lambda x: x[1]["result_count"], reverse=True)
    for kw, data in sorted_by_hits:
        n = data["result_count"]
        search_summary.add_row(
            kw,
            f"[bold]{n}[/bold]건",
            credibility_label(n),
            score_bar(min(n, 16), 16, 10),
        )

    console.print(search_summary)
    console.print(
        f"\n  [bold green]✅ 검색 완료[/bold green]  "
        f"총 [bold]{total_hits}[/bold]건 수집  │  "
        f"소요 {elapsed_search:.0f}초  │  "
        f"평균 {total_hits/total_count:.1f}건/키워드\n"
    )

    # ─── STEP 2 점수 분석 ──────────────────────────
    console.print(Rule("[bold yellow]STEP 2  점수 분석[/bold yellow]", style="yellow"))
    scored_keywords = score_all_keywords(CANDIDATE_KEYWORDS, kw_data_map)

    score_table = Table(
        title=None,
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold dim",
    )
    score_table.add_column("#", style="bold cyan", width=3, justify="right")
    score_table.add_column("키워드", style="bold white", width=26)
    score_table.add_column("🔥트렌드\n(×30%)", justify="center", width=11)
    score_table.add_column("✅긍정\n(×25%)", justify="center", width=10)
    score_table.add_column("⚠️부정\n(×15%↓)", justify="center", width=10)
    score_table.add_column("💡독창성\n(×20%)", justify="center", width=11)
    score_table.add_column("🔗융합\n(×10%)", justify="center", width=10)
    score_table.add_column("⭐종합점수", justify="center", style="bold", width=10)
    score_table.add_column("검색\n건수", justify="center", width=5)
    score_table.add_column("신뢰도", justify="center", width=8)
    score_table.add_column("카테고리", width=18)

    for i, kw in enumerate(scored_keywords[:top_n], 1):
        neg_col = f"[red]{kw['negative']}[/red]" if kw["negative"] > 3 else f"[green]{kw['negative']}[/green]"
        t = kw["total"]
        total_str = (
            f"[bold green]{t}[/bold green]" if t >= 7 else
            f"[yellow]{t}[/yellow]" if t >= 5 else
            f"[dim]{t}[/dim]"
        )
        cats = ", ".join(kw["categories"]) if kw["categories"] else "[dim]-[/dim]"
        score_table.add_row(
            str(i),
            kw["keyword"],
            f"{kw['trend']}\n{score_bar(kw['trend'])}",
            f"{kw['positive']}\n{score_bar(kw['positive'])}",
            f"{kw['negative']}\n{score_bar(kw['negative'])}",
            f"{kw['originality']}\n{score_bar(kw['originality'])}",
            f"{kw['fusion_potential']}\n{score_bar(kw['fusion_potential'])}",
            total_str,
            str(kw["hit_count"]),
            credibility_label(kw["hit_count"]),
            cats,
        )

    console.print(score_table)

    # 상세 모드: 키워드별 검색 샘플 출력
    if show_detail:
        console.print(Rule("[dim]상위 키워드 검색 샘플[/dim]", style="dim"))
        for kw in scored_keywords[:5]:
            data = kw_data_map.get(kw["keyword"], {})
            results = data.get("results", [])[:3]
            if results:
                console.print(f"\n[bold cyan]{kw['keyword']}[/bold cyan] (종합 {kw['total']}점, 검색 {kw['hit_count']}건)")
                for r in results:
                    title = r.get("title", "")[:60]
                    body = r.get("body", "")[:80]
                    console.print(f"  [dim]▸ {title}[/dim]")
                    if body:
                        console.print(f"    [dim italic]{body}...[/dim italic]")

    # ─── STEP 3 키워드 생성 ────────────────────────
    console.print()
    console.print(Rule("[bold yellow]STEP 3  신규 키워드 제안[/bold yellow]", style="yellow"))
    new_keywords = generate_new_keywords(scored_keywords)

    sug_table = Table(
        box=box.DOUBLE_EDGE,
        show_lines=True,
        header_style="bold",
    )
    sug_table.add_column("💡 제안 키워드", style="bold magenta", width=24)
    sug_table.add_column("출처 A", width=20)
    sug_table.add_column("출처 B", width=20)
    sug_table.add_column("융합 논리", width=36)
    sug_table.add_column("예상\n점수", justify="center", style="bold green", width=6)

    for s in new_keywords:
        sug_table.add_row(
            s["new_keyword"],
            s["source_a"],
            s["source_b"],
            s["rationale"],
            str(s["estimated_score"]),
        )

    console.print(sug_table)

    # ─── 최종 요약 ─────────────────────────────────
    top5_lines = "\n".join([
        f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else f'{i+1}위'} "
        f"[yellow]{k['keyword']}[/yellow]  "
        f"[bold]{k['total']}점[/bold]  "
        f"[dim](트렌드 {k['trend']} | 긍정 {k['positive']} | 독창성 {k['originality']} | 검색 {k['hit_count']}건 → 신뢰도 {credibility_label(k['hit_count'])})[/dim]"
        for i, k in enumerate(scored_keywords[:5])
    ])
    top3_suggest = "\n".join([
        f"  → [bold magenta]{s['new_keyword']}[/bold magenta]  "
        f"[dim]({s['source_a']} × {s['source_b']})[/dim]"
        for s in new_keywords[:3]
    ])

    console.print(Panel(
        f"[bold]입력:[/bold] {', '.join(input_keywords)}  │  "
        f"분석 {len(scored_keywords)}개  │  수집 {total_hits}건  │  소요 [bold]{time.time() - start_search:.0f}초[/bold]\n\n"
        f"[bold white]🏆 상위 키워드[/bold white]\n{top5_lines}\n\n"
        f"[bold white]💡 추천 신규 키워드[/bold white]\n{top3_suggest}",
        title="[bold green]분석 완료[/bold green]",
        border_style="green",
    ))

    return scored_keywords, new_keywords


# ─────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="키워드 트렌드 분석기 — 입력 키워드 기반 관련 키워드 점수화 및 신규 조합 제안",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""예시:
  python run_analysis.py                      기본값 (릴렉싱 스트레칭)
  python run_analysis.py 요가 필라테스        커스텀 키워드
  python run_analysis.py 요가 --top 10        상위 10개만
  python run_analysis.py 요가 --detail        검색 샘플 상세 출력
        """
    )
    parser.add_argument(
        "keywords",
        nargs="*",
        default=["릴렉싱", "스트레칭"],
        help="분석할 키워드 (기본값: 릴렉싱 스트레칭)",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=25,
        metavar="N",
        help="점수표에 표시할 상위 키워드 수 (기본값: 25)",
    )
    parser.add_argument(
        "--detail", "-d",
        action="store_true",
        help="상위 키워드별 검색 샘플 텍스트 출력",
    )

    args = parser.parse_args()

    start = time.time()
    run_analysis(args.keywords, top_n=args.top, show_detail=args.detail)
    console.print(f"\n[dim]총 소요 시간: {time.time() - start:.1f}초[/dim]\n")


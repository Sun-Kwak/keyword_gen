"""
웹 검색 모듈 - DuckDuckGo를 통한 키워드 리서치
각 후보 키워드를 개별적으로 검색하여 정확한 트렌드/감성 데이터 수집
"""
import time
from typing import List, Dict

from ddgs import DDGS

from config import (
    SEARCH_RESULTS_COUNT,
    SEARCH_QUERY_PASSES,
    SEARCH_RETRY_PER_QUERY,
    SEARCH_SLEEP_SECONDS,
)


def _build_keyword_queries(keyword: str) -> List[str]:
    """키워드별 수집 쿼리 세트 구성"""
    is_ascii = all(ord(c) < 128 for c in keyword)
    if is_ascii and len(keyword) > 3:
        return [
            keyword,
            f"{keyword} trend 2025",
            f"{keyword} benefits",
            f"{keyword} therapy",
        ]
    return [
        keyword,
        f"{keyword} 트렌드",
        f"{keyword} 효과",
        f"{keyword} 테라피",
    ]


def search_keyword_data(keyword: str, max_results: int = SEARCH_RESULTS_COUNT) -> Dict:
    """
    개별 키워드를 검색하여 해당 키워드의 트렌드/감성 데이터 수집

    반환값:
        keyword: 검색한 키워드
        results: 검색 결과 리스트
        result_count: 검색 결과 수 (인기도 프록시)
        combined_text: 결과 통합 텍스트
    """
    queries = _build_keyword_queries(keyword)

    all_results = []
    seen = set()
    query_errors = 0
    total_calls = 0

    ddgs = DDGS()
    for _pass in range(SEARCH_QUERY_PASSES):
        for query in queries:
            success = False
            for _retry in range(SEARCH_RETRY_PER_QUERY):
                total_calls += 1
                try:
                    results = ddgs.text(query, max_results=max_results, region="kr-ko")
                    for r in results:
                        title = (r.get("title", "") or "").strip()
                        body = (r.get("body", "") or "").strip()
                        href = (r.get("href", "") or "").strip()
                        dedupe_key = (href or title).lower()
                        if title and dedupe_key and dedupe_key not in seen:
                            seen.add(dedupe_key)
                            all_results.append({
                                "title": title,
                                "body": body,
                                "href": href,
                                "query": query,
                            })
                    success = True
                    break
                except Exception:
                    query_errors += 1
                    time.sleep(SEARCH_SLEEP_SECONDS)
            if not success:
                continue
            time.sleep(SEARCH_SLEEP_SECONDS)

    combined_text = " ".join([
        r["title"] + " " + r["body"] for r in all_results
    ])

    return {
        "keyword": keyword,
        "results": all_results,
        "result_count": len(all_results),
        "combined_text": combined_text,
        "query_count": len(queries) * SEARCH_QUERY_PASSES,
        "api_calls": total_calls,
        "query_errors": query_errors,
    }


def batch_search_keywords(keywords: List[str], verbose: bool = True) -> Dict[str, Dict]:
    """여러 키워드를 일괄 검색하여 {키워드: 검색데이터} 딕셔너리 반환"""
    keyword_data = {}
    for i, kw in enumerate(keywords):
        if verbose:
            print(f"  [{i+1}/{len(keywords)}] 검색 중: '{kw}'...", end="\r")
        keyword_data[kw] = search_keyword_data(kw)
    if verbose:
        print(" " * 60, end="\r")  # 줄 지우기
    return keyword_data


def search_base_keywords(base_keywords: List[str]) -> List[Dict]:
    """기본 키워드의 전체적인 검색 결과 수집 (초기 컨텍스트용)"""
    all_results = []
    seen = set()
    ddgs = DDGS()

    for kw in base_keywords:
        queries = [
            f"{kw} 최신 트렌드 2025",
            f"{kw} 종류 유형",
            f"new {kw} wellness 2025",
        ]
        for query in queries:
            try:
                results = ddgs.text(query, max_results=SEARCH_RESULTS_COUNT, region="kr-ko")
                for r in results:
                    title = r.get("title", "")
                    if title and title not in seen:
                        seen.add(title)
                        all_results.append({
                            "title": title,
                            "body": r.get("body", ""),
                            "href": r.get("href", ""),
                            "query": query,
                        })
                time.sleep(0.4)
            except Exception:
                pass

    return all_results

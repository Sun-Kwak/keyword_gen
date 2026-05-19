"""
키워드 점수 평가 모듈
각 키워드의 개별 검색 데이터를 기반으로 다차원 점수 평가
"""
import math
from typing import Dict, List
from config import (
    POSITIVE_SIGNALS,
    NEGATIVE_SIGNALS,
    TREND_SIGNALS,
    FUSION_CATEGORIES,
    SCORE_WEIGHTS,
    MIN_RESULTS_FOR_STABLE_SCORE,
)

# 독창성 수식어 (키워드 자체에 포함 여부로 독창성 판단)
ORIGINALITY_MODIFIERS = [
    "패시브", "소매틱", "마인드풀", "딥", "슬로우", "회복", "리스토러티브", "아시스티드",
    "passive", "somatic", "mindful", "deep", "slow", "recovery", "restorative", "assisted",
    "프리미엄", "홀리스틱", "holistic", "통합", "신경", "neuro",
]


def score_keyword_from_data(keyword: str, keyword_data: Dict) -> Dict:
    """
    개별 키워드의 검색 데이터를 바탕으로 다차원 점수 계산

    keyword_data: web_searcher.search_keyword_data()의 반환값
      - result_count: 검색 결과 수 (인기도)
      - combined_text: 검색 결과 통합 텍스트
    """
    text = keyword_data.get("combined_text", "").lower()
    result_count = keyword_data.get("result_count", 0)
    confidence = min(1.0, result_count / float(MIN_RESULTS_FOR_STABLE_SCORE))

    def stabilize(raw_score: float, neutral: float = 5.0) -> float:
        # 표본이 부족할수록 점수를 중립값 쪽으로 보정해 변동폭을 줄인다.
        return neutral + (raw_score - neutral) * confidence

    # --- 트렌드 점수 ---
    # 검색 결과 내 트렌드 시그널 횟수 + 결과 수(인기도)
    trend_hits = sum(1 for s in TREND_SIGNALS if s.lower() in text)
    count_signal = min(5.0, math.log1p(result_count) * 1.8)
    trend_raw = min(10.0, trend_hits * 1.2 + count_signal)
    trend_score = stabilize(trend_raw)

    # --- 긍정 점수 ---
    pos_hits = sum(1 for s in POSITIVE_SIGNALS if s.lower() in text)
    positive_raw = min(10.0, pos_hits * 1.0)
    positive_score = stabilize(positive_raw)

    # --- 부정 점수 (낮을수록 좋음) ---
    neg_hits = sum(1 for s in NEGATIVE_SIGNALS if s.lower() in text)
    negative_raw = min(10.0, neg_hits * 1.5)
    negative_score = stabilize(negative_raw)

    # --- 독창성 점수 ---
    mod_count = sum(1 for m in ORIGINALITY_MODIFIERS if m.lower() in keyword.lower())
    # 결과 수 영향은 로그로 완만화해 검색 변동에 덜 흔들리게 한다.
    novelty = max(0.0, 1.0 - (math.log1p(result_count) / math.log1p(40)))
    originality_raw = min(10.0, mod_count * 3.0 + novelty * 4.0)
    originality_score = stabilize(originality_raw)

    # --- 융합 가능성 점수 ---
    category_matches = []
    for category, terms in FUSION_CATEGORIES.items():
        for term in terms:
            if term.lower() in keyword.lower():
                category_matches.append(category)
                break
    fusion_score = min(10.0, len(set(category_matches)) * 2.5 + 2.5)

    # --- 종합 점수 ---
    total = (
        trend_score * SCORE_WEIGHTS["trend"] +
        positive_score * SCORE_WEIGHTS["positive"] +
        (10 - negative_score) * SCORE_WEIGHTS["negative"] +
        originality_score * SCORE_WEIGHTS["originality"] +
        fusion_score * SCORE_WEIGHTS["fusion_potential"]
    )

    return {
        "keyword": keyword,
        "trend": round(trend_score, 1),
        "positive": round(positive_score, 1),
        "negative": round(negative_score, 1),
        "originality": round(originality_score, 1),
        "fusion_potential": round(fusion_score, 1),
        "total": round(total, 2),
        "hit_count": result_count,
        "data_confidence": round(confidence, 2),
        "categories": list(set(category_matches)),
    }


def score_keyword(keyword: str, search_results: List[Dict]) -> Dict:
    """
    레거시 호환: 통합 검색 결과 리스트에서 키워드 점수 계산
    (run_analysis.py 하위 호환용)
    """
    relevant = [
        r for r in search_results
        if keyword.lower() in (r.get("title", "") + r.get("body", "")).lower()
    ]
    combined_text = " ".join(r.get("title", "") + " " + r.get("body", "") for r in relevant).lower()
    data = {"result_count": len(relevant), "combined_text": combined_text}
    return score_keyword_from_data(keyword, data)


def score_all_keywords(keywords: List[str], keyword_data_map: Dict[str, Dict]) -> List[Dict]:
    """
    모든 키워드 점수화 후 총점 기준 내림차순 정렬

    keyword_data_map: {키워드: web_searcher.search_keyword_data() 결과}
    """
    scores = []
    for kw in keywords:
        data = keyword_data_map.get(kw, {"result_count": 0, "combined_text": ""})
        scores.append(score_keyword_from_data(kw, data))
    return sorted(scores, key=lambda x: x["total"], reverse=True)

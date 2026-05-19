"""
신규 키워드 제안 모듈

기본 전략:
1) 분석 단계에서 계산된 상위 키워드/점수를 기준점으로 사용
2) LLM이 개념 확장형 신규 키워드를 제안
3) LLM 실패 시 간단한 룰 기반 fallback 사용
"""
import json
import os
from typing import Dict, List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _safe_float(value: object, default: float = 5.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _fallback_generate(scored_keywords: List[Dict], limit: int = 12) -> List[Dict]:
    """LLM 실패 시 최소 동작 보장용 fallback"""
    top = scored_keywords[:6]
    if len(top) < 2:
        return []

    suggestions: List[Dict] = []
    seen: set[str] = set()

    for i, a in enumerate(top[:-1]):
        b = top[i + 1]
        a_kw = a.get("keyword", "")
        b_kw = b.get("keyword", "")
        if not a_kw or not b_kw:
            continue

        first = a_kw.split()[0]
        second = b_kw.split()[0]
        candidates = [
            f"{first} {second} 테라피",
            f"{first} 기반 {second}",
        ]

        for new_kw in candidates:
            key = new_kw.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            estimated = round((_safe_float(a.get("total")) + _safe_float(b.get("total"))) / 2, 2)
            suggestions.append({
                "new_keyword": new_kw,
                "source_a": a_kw,
                "source_b": b_kw,
                "rationale": "상위 키워드 조합 기반 fallback 제안",
                "estimated_score": estimated,
                "type": "fallback",
            })
            if len(suggestions) >= limit:
                return suggestions

    return suggestions[:limit]


def _llm_generate(scored_keywords: List[Dict], limit: int = 12) -> List[Dict]:
    client = _get_openai_client()
    if client is None:
        return []

    top = scored_keywords[:12]
    if not top:
        return []

    context = []
    for item in top:
        context.append({
            "keyword": item.get("keyword", ""),
            "trend": item.get("trend", 0),
            "positive": item.get("positive", 0),
            "negative": item.get("negative", 0),
            "originality": item.get("originality", 0),
            "fusion_potential": item.get("fusion_potential", 0),
            "total": item.get("total", 0),
            "categories": item.get("categories", []),
            "hit_count": item.get("hit_count", 0),
        })

    prompt = (
        "다음은 이미 분석된 상위 키워드와 점수 데이터다.\n"
        "이 점수를 기준점(anchor)으로 삼아, 단순 단어 합성이 아닌 '개념 확장형' 신규 키워드를 제안하라.\n\n"
        f"상위 데이터(JSON):\n{json.dumps(context, ensure_ascii=False)}\n\n"
        "요구사항:\n"
        f"- 결과는 최대 {limit}개\n"
        "- 각 항목은 반드시 새로운 키워드(new_keyword)여야 하며 기존 keyword와 완전 동일하면 안 됨\n"
        "- 1~4단어의 짧은 검색어 형태\n"
        "- 상업/거래형 키워드(예약, 가격, 후기, 할인, 구매, 매장, 비교, 앱)는 제외\n"
        "- 가능한 경우 동의어/상위개념/기법/효과/연관분야 관점으로 확장\n"
        "- source_keywords는 근거가 된 기존 키워드 2개를 넣을 것\n"
        "- novelty(0~10), relevance(0~10) 숫자 제공\n"
        "- rationale은 한국어 한 줄\n\n"
        "반드시 아래 JSON 배열만 출력:\n"
        "[{\"new_keyword\":\"...\",\"source_keywords\":[\"...\",\"...\"],\"novelty\":7.2,\"relevance\":8.1,\"rationale\":\"...\"}]"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 키워드 전략가다. 반드시 JSON만 출력한다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=1200,
    )

    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()

    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        return []

    score_map = {str(k.get("keyword", "")).lower(): _safe_float(k.get("total"), 5.0) for k in top}
    existing = {str(k.get("keyword", "")).lower() for k in scored_keywords}

    out: List[Dict] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        new_kw = str(item.get("new_keyword", "")).strip()
        if not new_kw:
            continue
        low = new_kw.lower()
        if low in seen or low in existing:
            continue

        sources = item.get("source_keywords", [])
        if not isinstance(sources, list):
            sources = []
        src_a = str(sources[0]).strip() if len(sources) > 0 else ""
        src_b = str(sources[1]).strip() if len(sources) > 1 else ""

        s1 = score_map.get(src_a.lower(), 5.0)
        s2 = score_map.get(src_b.lower(), 5.0)
        base = (s1 + s2) / 2 if src_a or src_b else 5.0

        novelty = max(0.0, min(10.0, _safe_float(item.get("novelty"), 6.0)))
        relevance = max(0.0, min(10.0, _safe_float(item.get("relevance"), 7.0)))
        estimated = round(min(10.0, base * 0.65 + novelty * 0.2 + relevance * 0.15), 2)

        out.append({
            "new_keyword": new_kw,
            "source_a": src_a or "-",
            "source_b": src_b or "-",
            "rationale": str(item.get("rationale", "점수 기준 확장 제안")).strip()[:140],
            "estimated_score": estimated,
            "type": "llm",
        })
        seen.add(low)
        if len(out) >= limit:
            break

    return out


def generate_new_keywords(scored_keywords: List[Dict], top_n: int = 8) -> List[Dict]:
    """
    분석 점수를 기준점으로 신규 키워드를 제안.

    우선순위:
    1) LLM 제안
    2) 실패 시 fallback
    """
    limit = 12
    try:
        llm_suggestions = _llm_generate(scored_keywords, limit=limit)
        if llm_suggestions:
            llm_suggestions.sort(key=lambda x: x["estimated_score"], reverse=True)
            return llm_suggestions[:limit]
    except Exception as e:
        print(f"[LLM 제안 실패] {e}")

    fallback = _fallback_generate(scored_keywords, limit=limit)
    fallback.sort(key=lambda x: x["estimated_score"], reverse=True)
    return fallback[:limit]

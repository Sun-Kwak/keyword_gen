"""
시드 키워드 → 후보 키워드 자동 생성 모듈

1. DuckDuckGo로 시드 키워드 검색 → 실제 검색 결과 수집
2. OpenAI에게 검색 결과 텍스트를 주고 "사람들이 실제로 검색할 법한 키워드" 추출 요청
3. 어떤 도메인이든 동작 (디카페인, 요가, IT 용어 등)
"""
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()

from ddgs import DDGS
from openai import OpenAI

_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TRANSACTIONAL_TERMS = {
    "예약", "가격", "후기", "할인", "어플", "앱", "샵", "매장", "구매", "판매",
    "이벤트", "쿠폰", "비교", "추천", "체험", "문의", "정보", "커뮤니티", "서비스",
    "booking", "price", "review", "discount", "app", "shop", "buy", "sale", "coupon",
}

DOMAIN_EXPANSION_HINTS = {
    "릴렉싱": [
        "패시브 릴랙싱",
        "릴랙세이션 테라피",
        "소매틱 테라피",
        "홀리스틱 테라피",
        "리스토러티브 테라피",
        "마인드풀 릴랙세이션",
    ],
    "마사지": [
        "바디워크 테라피",
        "근막 이완",
        "신경계 이완",
        "회복 테라피",
    ],
}


def _build_queries(seed: str) -> list[str]:
    is_ko = any("\uAC00" <= c <= "\uD7A3" for c in seed)
    if is_ko:
        return [seed, f"{seed} 종류", f"{seed} 추천", f"{seed} 트렌드"]
    else:
        return [seed, f"{seed} types", f"{seed} trend 2025"]


def _search_texts(seed: str, ddgs: DDGS) -> str:
    """시드 관련 DuckDuckGo 검색 결과 제목+본문 수집"""
    snippets: list[str] = []
    for query in _build_queries(seed):
        try:
            results = ddgs.text(query, max_results=8, region="kr-ko")
            for r in results:
                title = r.get("title", "").strip()
                body = r.get("body", "").strip()
                if title:
                    snippets.append(title)
                if body:
                    snippets.append(body[:200])
            time.sleep(0.3)
        except Exception:
            pass
    return "\n".join(snippets)


def _extract_with_llm(seed_keywords: list[str], texts_by_seed: dict[str, str], max_count: int) -> list[str]:
    """OpenAI에게 검색 결과에서 후보 키워드 추출 요청"""

    # 검색 텍스트를 시드별로 정리
    context_parts = []
    for seed, text in texts_by_seed.items():
        context_parts.append(f"[시드: {seed}]\n{text[:1500]}")
    context = "\n\n".join(context_parts)

    seeds_str = ", ".join(f'"{s}"' for s in seed_keywords)

    prompt = f"""다음은 {seeds_str} 관련 실제 웹 검색 결과입니다.

{context}

목표: 단순 상업 키워드가 아니라 "개념 확장"이 되는 관련 키워드를 추출하세요.
예: 릴렉싱 마사지 -> 테라피, 패시브 릴랙싱, 소매틱 이완, 리스토러티브 케어 같은 방향.

위 검색 결과를 바탕으로, 관련 키워드를 {max_count}개 이내로 추출해주세요.

규칙:
- 각 키워드는 1~3단어로 구성 (너무 길면 안 됨)
- 문장 조각, 동사구, 조사로 끝나는 것은 제외
- 시드 키워드 자체는 포함해도 됨
- 실제 검색어로 쓰일 수 있는 명사 또는 명사구만
- 한국어 또는 영어 키워드 (검색 결과 언어에 맞게)
- 중복 없이
- "예약/가격/후기/할인/샵/어플/비교/구매" 같은 거래형 키워드는 제외
- 개념군을 섞어서 출력: 동의어/상위개념/기법명/효과명/연관 분야

JSON 배열 형식으로만 답변하세요. 예: ["키워드1", "키워드2", ...]"""

    try:
        response = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 SEO 및 키워드 분석 전문가입니다. 요청된 형식으로 정확히 답변합니다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()
        # JSON 배열 파싱
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        keywords = json.loads(raw)
        if isinstance(keywords, list):
            return [str(k).strip() for k in keywords if k and str(k).strip()]
    except Exception as e:
        print(f"[LLM 추출 실패] {e}")

    return list(seed_keywords)  # 실패 시 시드만 반환


def _is_transactional_keyword(keyword: str) -> bool:
    text = keyword.lower().strip()
    if not text:
        return True
    for term in TRANSACTIONAL_TERMS:
        if term in text:
            return True
    return False


def _postprocess_keywords(seed_keywords: list[str], keywords: list[str], max_count: int) -> list[str]:
    """중복/거래형 키워드를 제거하고 시드를 보존"""
    seen: set[str] = set()
    cleaned: list[str] = []

    def add(kw: str) -> None:
        norm = " ".join(kw.strip().split())
        if not norm:
            return
        key = norm.lower()
        if key in seen:
            return
        if len(norm) > 24:
            return
        if _is_transactional_keyword(norm):
            return
        seen.add(key)
        cleaned.append(norm)

    for seed in seed_keywords:
        seed_norm = " ".join(seed.strip().split())
        if seed_norm and seed_norm.lower() not in seen:
            seen.add(seed_norm.lower())
            cleaned.append(seed_norm)

    # 도메인별 개념 확장 힌트를 우선 반영
    lowered_seeds = " ".join(seed_keywords).lower()
    for trigger, hints in DOMAIN_EXPANSION_HINTS.items():
        if trigger in lowered_seeds:
            for hint in hints:
                if len(cleaned) >= max_count:
                    break
                add(hint)

    for kw in keywords:
        if len(cleaned) >= max_count:
            break
        add(kw)

    return cleaned[:max_count]


def generate_candidates(seed_keywords: list[str], max_count: int = 30) -> list[str]:
    """
    시드 키워드를 DuckDuckGo로 검색하고, OpenAI로 후보 키워드 추출.

    1. 각 시드마다 3~4 쿼리로 검색 결과 수집
    2. OpenAI에게 검색 결과 → 깔끔한 키워드 추출 요청
    3. 시드 자체는 항상 포함, 최대 max_count개 반환
    """
    ddgs = DDGS()
    texts_by_seed: dict[str, str] = {}

    print(f"[후보 생성] DuckDuckGo 검색 중... (시드: {seed_keywords})")
    for seed in seed_keywords:
        texts_by_seed[seed] = _search_texts(seed, ddgs)
        print(f"  ✓ '{seed}' 검색 완료")

    print("[후보 생성] OpenAI로 키워드 추출 중...")
    keywords = _extract_with_llm(seed_keywords, texts_by_seed, max_count)
    print(f"  ✓ {len(keywords)}개 추출 완료")

    return _postprocess_keywords(seed_keywords, keywords, max_count)

"""
시드 키워드 → 후보 키워드 자동 생성 모듈

DuckDuckGo로 시드 키워드를 먼저 검색한 후,
실제 검색 결과 텍스트에서 관련 키워드를 추출합니다.
어떤 도메인이든 동작합니다 (디카페인, 요가, IT용어 등).
"""
import re
import time
import warnings
from collections import Counter

warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")
warnings.filterwarnings("ignore", message=".*duckduckgo_search.*renamed.*ddgs.*")
from duckduckgo_search import DDGS


# ── 불용어 (단독으로는 키워드가 될 수 없는 조각) ────────────
STOPWORDS = {
    "의", "를", "을", "이", "가", "은", "는", "에", "에서", "으로", "로",
    "와", "과", "도", "만", "하고", "이란", "이라", "란", "라",
    "하는", "하기", "하면", "해서", "해도", "했다", "한다", "합니다",
    "있는", "있다", "없는", "없다", "이다", "입니다", "이며",
    "또한", "그리고", "그러나", "하지만", "때문에", "위해", "통해",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "for", "in", "on", "at", "to", "of", "and", "or", "but",
    "with", "by", "from", "as", "it", "its", "this", "that",
    "how", "what", "why", "when", "which", "who",
}

# 조사/어미로 끝나는 단어 → 문장 조각 판정 (단음절 조사는 제외 — 오탐 방지)
_KO_JOSA_ENDINGS = re.compile(
    r"(를|을|에서|으로|부터|까지|보다|처럼|만큼|쯤|이나"
    r"|하는|하기|해서|했을|하셨|해보|하면|했다|한다"
    r"|입니다|습니다|겠습니다|았을|었을|이고|이며"
    r"|하고|이어서|인데|인지|하며|하여|되어|되며"
    r"|스럽|스러운|스러워)$"
)

# ── 검색 쿼리 패턴 (시드를 다양하게 검색) ───────────────────
def _build_queries(seed: str) -> list[str]:
    is_ko = any("\uAC00" <= c <= "\uD7A3" for c in seed)
    if is_ko:
        return [
            seed,
            f"{seed} 종류",
            f"{seed} 추천",
            f"{seed} 트렌드",
        ]
    else:
        return [
            seed,
            f"{seed} types",
            f"{seed} trend 2025",
        ]


def _extract_phrases(text: str, seed: str) -> list[str]:
    """
    텍스트에서 시드 단어가 직접 포함된 구문만 추출.
    시드 단어와 무관한 문장 조각은 버립니다.
    """
    phrases = []
    # 단어 경계를 고려한 정확한 시드 매칭 패턴
    seed_pattern = re.escape(seed)

    # ── 한국어: 앞 수식어 + 시드 ────────────────────────────
    # 예: "아이스 디카페인", "저카페인 디카페인"
    for m in re.finditer(
        rf"([가-힣a-zA-Z0-9]{{1,10}}(?:\s[가-힣a-zA-Z0-9]{{1,10}})?)\s+{seed_pattern}",
        text, re.IGNORECASE
    ):
        candidate = f"{m.group(1).strip()} {seed}"
        phrases.append(candidate)

    # ── 한국어: 시드 + 뒤 명사 ──────────────────────────────
    # 예: "디카페인 커피", "디카페인 라떼", "디카페인 원두"
    for m in re.finditer(
        rf"{seed_pattern}\s+([가-힣a-zA-Z0-9]{{1,10}}(?:\s[가-힣a-zA-Z0-9]{{1,10}})?)",
        text, re.IGNORECASE
    ):
        suffix = m.group(1).strip()
        # 불용어 단독이면 스킵
        if suffix.lower() not in STOPWORDS:
            phrases.append(f"{seed} {suffix}")

    # ── 영어: seed + 영단어, 영단어 + seed ─────────────────
    for m in re.finditer(
        rf"([a-zA-Z]{{2,15}})\s+{seed_pattern}|{seed_pattern}\s+([a-zA-Z]{{2,15}})",
        text, re.IGNORECASE
    ):
        prefix, suffix = m.group(1), m.group(2)
        if prefix and prefix.lower() not in STOPWORDS:
            phrases.append(f"{prefix} {seed}")
        if suffix and suffix.lower() not in STOPWORDS:
            phrases.append(f"{seed} {suffix}")

    return phrases


def _is_valid_candidate(phrase: str, seed: str) -> bool:
    """후보로 쓸 수 있는 구문인지 검증"""
    phrase = phrase.strip()
    if len(phrase) < 3 or len(phrase) > 22:
        return False
    words = phrase.split()
    if len(words) > 3:
        return False
    if phrase.lower() == seed.lower():
        return False
    if re.fullmatch(r"[\d\s]+", phrase):
        return False
    # 조사/어미로 끝나는 단어가 포함되면 문장 조각 → 스킵
    for word in words:
        if _KO_JOSA_ENDINGS.search(word):
            return False
    if all(w.lower() in STOPWORDS for w in words):
        return False
    return True


def generate_candidates(seed_keywords: list[str], max_count: int = 30) -> list[str]:
    """
    시드 키워드를 DuckDuckGo로 검색하고 실제 결과에서 후보 키워드 추출.

    1. 각 시드마다 3~4가지 쿼리로 검색
    2. 검색 결과 제목+본문에서 관련 구문 추출
    3. 빈도순 정렬 후 상위 max_count개 반환
    시드 자체는 항상 포함.
    """
    ddgs = DDGS()
    phrase_counter: Counter = Counter()
    seen_queries: set[str] = set()

    for seed in seed_keywords:
        queries = _build_queries(seed)
        for query in queries:
            if query in seen_queries:
                continue
            seen_queries.add(query)
            try:
                results = ddgs.text(query, max_results=10, region="kr-ko")
                for r in results:
                    text = r.get("title", "") + " " + r.get("body", "")
                    for phrase in _extract_phrases(text, seed):
                        phrase = phrase.strip()
                        if _is_valid_candidate(phrase, seed):
                            phrase_counter[phrase] += 1
                time.sleep(0.3)
            except Exception:
                pass

    # 빈도순 정렬
    ranked = [kw for kw, _ in phrase_counter.most_common(max_count * 3)]

    # 최종 후보: 시드 자체 + 상위 빈도 구문 (중복 제거)
    seen: set[str] = set()
    candidates: list[str] = []

    def add(kw: str) -> None:
        kw = kw.strip()
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            candidates.append(kw)

    for seed in seed_keywords:
        add(seed)

    for kw in ranked:
        if len(candidates) >= max_count:
            break
        add(kw)

    return candidates

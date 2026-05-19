"""
키워드 분석 서비스 설정
"""

# 분석 설정
SEARCH_RESULTS_COUNT = 12   # 쿼리당 수집 목표 결과 수
MAX_RELATED_KEYWORDS = 20   # 최대 관련 키워드 수
SEARCH_QUERY_PASSES = 2     # 같은 키워드를 여러 패스로 수집해 표본 확장
SEARCH_RETRY_PER_QUERY = 2  # 쿼리 실패 시 재시도 횟수
SEARCH_SLEEP_SECONDS = 0.25 # DDGS 호출 간 간격
MIN_RESULTS_FOR_STABLE_SCORE = 12  # 이 값 미만이면 점수 신뢰도 보정

# 점수 가중치 (총합 = 1.0)
SCORE_WEIGHTS = {
    "trend": 0.30,          # 트렌드 점수 (최근성/상승세)
    "positive": 0.25,       # 긍정 평가 점수
    "negative": 0.15,       # 부정 평가 점수 (낮을수록 좋음 → 역산)
    "originality": 0.20,    # 독창성/신선도 점수
    "fusion_potential": 0.10  # 다른 키워드와의 융합 가능성
}

# 긍정 신호 단어 (한국어/영어)
POSITIVE_SIGNALS = [
    "효과", "좋은", "추천", "인기", "트렌드", "최신", "주목", "화제",
    "benefit", "effective", "popular", "trending", "growing", "recommended",
    "healing", "recovery", "wellbeing", "wellness", "relaxation", "relief",
    "힐링", "회복", "건강", "이완", "스트레스해소", "다이어트", "유연성",
    "new", "emerging", "rise", "boost", "improve",
    "과학적", "연구", "증명", "검증"
]

# 부정 신호 단어
NEGATIVE_SIGNALS = [
    "부작용", "주의", "위험", "논란", "부상", "통증", "해롭",
    "side effect", "injury", "dangerous", "risk", "harmful", "caution",
    "avoid", "warning", "problem", "negative",
    "단점", "문제", "위험", "금지"
]

# 트렌드 시그널 (최근성 판단)
TREND_SIGNALS = [
    "2024", "2025", "2026", "최신", "새로운", "신개념", "요즘", "최근",
    "new trend", "emerging", "latest", "modern", "contemporary",
    "Z세대", "MZ", "밀레니얼", "SNS", "인스타", "유튜브",
    "viral", "social media"
]

# 카테고리별 융합 가능성 분류
FUSION_CATEGORIES = {
    "stretching": ["스트레칭", "stretch", "flexibility", "유연성", "가동성"],
    "relaxation": ["릴렉싱", "이완", "relax", "release", "힐링", "healing"],
    "mind_body": ["명상", "meditation", "요가", "yoga", "소매틱", "somatic", "마음챙김", "mindful"],
    "fitness": ["운동", "workout", "fitness", "피트니스", "트레이닝", "training"],
    "recovery": ["회복", "recovery", "리커버리", "재생", "regeneration"],
    "therapy": ["테라피", "therapy", "치료", "치유", "healing"],
    "wellness": ["웰니스", "wellness", "웰빙", "wellbeing", "건강"],
}

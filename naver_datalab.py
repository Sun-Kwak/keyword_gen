"""
네이버 데이터랩 검색어 트렌드 비교 모듈

각 키워드에 대해 다음을 조회:
- 전체 트렌드 (최근 12개월, 상대 수치 0~100)
- 성별 비교 (남/여)
- 연령대 비교 (10~60대)
- 디바이스 비교 (모바일/PC)
"""
import os
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
API_URL = "https://openapi.naver.com/v1/datalab/search"

# 연령대 코드 → 레이블
AGE_LABELS = {
    "1": "10대",
    "2": "20대",
    "3": "30대",
    "4": "40대",
    "5": "50대",
    "6": "60대+",
}


def _headers() -> dict:
    return {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json",
    }


def _date_range(months: int = 12) -> tuple[str, str]:
    end = datetime.today()
    start = end - timedelta(days=months * 30)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _query(keyword_groups: list, device: str = "", gender: str = "", ages: list = None) -> dict:
    """네이버 데이터랩 API 단일 호출"""
    start, end = _date_range(12)
    body = {
        "startDate": start,
        "endDate": end,
        "timeUnit": "month",
        "keywordGroups": keyword_groups,
        "device": device,
        "gender": gender,
        "ages": ages or [],
    }
    try:
        resp = httpx.post(API_URL, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Naver API 오류] {e}")
        return {}


def _extract_avg(result: dict, group_name: str) -> float:
    """결과에서 특정 그룹의 평균 수치 추출"""
    if not result or "results" not in result:
        return 0.0
    for r in result.get("results", []):
        if r.get("title") == group_name:
            data = r.get("data", [])
            if data:
                return round(sum(d.get("ratio", 0) for d in data) / len(data), 1)
    return 0.0


def _extract_trend(result: dict, group_name: str) -> list[dict]:
    """월별 트렌드 데이터 추출"""
    if not result or "results" not in result:
        return []
    for r in result.get("results", []):
        if r.get("title") == group_name:
            return [{"period": d.get("period", ""), "ratio": d.get("ratio", 0)} for d in r.get("data", [])]
    return []


def _normalize_age_distribution(kw: str, age_result_map: dict[str, dict]) -> dict[str, float]:
    """키워드별 연령대 분포를 0~100 비율로 정규화"""
    age_vals = {label: _extract_avg(age_result_map[label], kw) for label in AGE_LABELS.values()}
    total = sum(age_vals.values())
    if total > 0:
        return {label: round(v / total * 100, 1) for label, v in age_vals.items()}
    return {label: 0.0 for label in AGE_LABELS.values()}


def _extract_age_trend_series(kw: str, age_result_map: dict[str, dict]) -> dict[str, list[dict]]:
    """키워드별 연령대 시계열 트렌드 추출"""
    return {label: _extract_trend(age_result_map[label], kw) for label in AGE_LABELS.values()}


def compare_keywords(keywords: list[str]) -> list[dict]:
    """
    여러 키워드를 네이버 데이터랩으로 비교 분석.
    최대 5개 키워드 (API 제한).

    반환:
    [
      {
        "keyword": "도수치료",
        "trend": [{"period": "2024-05", "ratio": 65}, ...],   # 월별 트렌드
        "gender": {"male": 35.2, "female": 64.8},             # 성별 비율
        "ages": {"10대": 5.1, "20대": 18.3, ...},             # 연령대 비율
        "device": {"mobile": 72.4, "pc": 27.6},               # 디바이스 비율
      },
      ...
    ]
    """
    keywords = keywords[:5]  # API 최대 5개

    # keyword_groups 형식
    groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords]

    results = []

    # 1) 전체 트렌드
    trend_result = _query(groups)

    # 2) 성별: 남 / 여
    male_result = _query(groups, gender="m")
    female_result = _query(groups, gender="f")

    # 3) 연령대 별 (전체/남/여 각각 호출)
    age_results_all = {}
    age_results_male = {}
    age_results_female = {}
    for age_code, age_label in AGE_LABELS.items():
        age_results_all[age_label] = _query(groups, ages=[age_code])
        age_results_male[age_label] = _query(groups, gender="m", ages=[age_code])
        age_results_female[age_label] = _query(groups, gender="f", ages=[age_code])

    # 4) 디바이스
    mobile_result = _query(groups, device="mo")
    pc_result = _query(groups, device="pc")

    for kw in keywords:
        # 트렌드
        trend = _extract_trend(trend_result, kw)
        trend_male = _extract_trend(male_result, kw)
        trend_female = _extract_trend(female_result, kw)

        # 성별 (상대비율 → 백분율로 정규화)
        male_val = _extract_avg(male_result, kw)
        female_val = _extract_avg(female_result, kw)
        total_gv = male_val + female_val
        if total_gv > 0:
            gender = {
                "male": round(male_val / total_gv * 100, 1),
                "female": round(female_val / total_gv * 100, 1),
            }
        else:
            gender = {"male": 0.0, "female": 0.0}

        # 연령대 정규화 (전체/남성/여성)
        ages_all = _normalize_age_distribution(kw, age_results_all)
        ages_male = _normalize_age_distribution(kw, age_results_male)
        ages_female = _normalize_age_distribution(kw, age_results_female)
        trend_age_all = _extract_age_trend_series(kw, age_results_all)
        trend_age_male = _extract_age_trend_series(kw, age_results_male)
        trend_age_female = _extract_age_trend_series(kw, age_results_female)

        # 디바이스 정규화
        mo_val = _extract_avg(mobile_result, kw)
        pc_val = _extract_avg(pc_result, kw)
        total_dv = mo_val + pc_val
        if total_dv > 0:
            device = {
                "mobile": round(mo_val / total_dv * 100, 1),
                "pc": round(pc_val / total_dv * 100, 1),
            }
        else:
            device = {"mobile": 0.0, "pc": 0.0}

        results.append({
            "keyword": kw,
            "trend": trend,
            "trend_by_gender": {
                "all": trend,
                "male": trend_male,
                "female": trend_female,
            },
            "gender": gender,
            "ages": ages_all,
            "ages_by_gender": {
                "all": ages_all,
                "male": ages_male,
                "female": ages_female,
            },
            "trend_by_age": {
                "all": trend_age_all,
                "male": trend_age_male,
                "female": trend_age_female,
            },
            "device": device,
        })

    return results

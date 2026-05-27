from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .client import G2BClient


KST = ZoneInfo("Asia/Seoul")
DEFAULT_ORGS = [
    "한국인터넷진흥원",
    "한국지능정보사회진흥원",
]


def yyyymmddhhmm(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def yesterday_range_kst(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(tz=KST)
    y = (now - timedelta(days=1)).date()
    start = datetime(y.year, y.month, y.day, 0, 0, tzinfo=KST)
    end = datetime(y.year, y.month, y.day, 23, 59, tzinfo=KST)
    return yyyymmddhhmm(start), yyyymmddhhmm(end)


def normalize_org(s: str) -> str:
    return (s or "").strip()


def main() -> int:
    p = argparse.ArgumentParser(
        description="전일(KST) 나라장터 '일반용역' 발주공고 조회 (KISA/NIA)"
    )
    p.add_argument(
        "--org",
        action="append",
        default=None,
        help="기관명(공고기관/수요기관) 부분일치 검색. 여러 번 지정 가능.",
    )
    p.add_argument(
        "--use-demand-org",
        action="store_true",
        help="기관명을 수요기관(dminsttNm) 기준으로만 조회",
    )
    p.add_argument(
        "--num-of-rows",
        type=int,
        default=100,
        help="페이지당 건수(numOfRows). 너무 크게 하면 응답이 느릴 수 있습니다.",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="JSON pretty-print 출력",
    )
    args = p.parse_args()

    client = G2BClient.from_env()
    inqry_bgn_dt, inqry_end_dt = yesterday_range_kst()

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    orgs = [normalize_org(x) for x in (args.org or DEFAULT_ORGS) if normalize_org(x)]
    search_fields = ("dminstt_nm",) if args.use_demand_org else ("ntce_instt_nm", "dminstt_nm")

    for org in orgs:
        kwargs = {
            "inqry_div": 1,  # 공고게시일시
            "inqry_bgn_dt": inqry_bgn_dt,
            "inqry_end_dt": inqry_end_dt,
            "num_of_rows": args.num_of_rows,
        }

        for search_field in search_fields:
            search_kwargs = {**kwargs, search_field: org}
            for item in client.iter_servc_pps_srch(**search_kwargs):
                # 문서 응답 예시 기준: srvceDivNm (일반용역/기술용역)
                if (item.get("srvceDivNm") or "").strip() != "일반용역":
                    continue

                # 일부 공고는 공고기관/수요기관이 조달청으로 찍히는 케이스가 있어
                # 최종적으로 둘 중 하나에 기관명이 포함되는지 한 번 더 방어적으로 확인.
                ntce_instt_nm = (item.get("ntceInsttNm") or "").strip()
                dminstt_nm = (item.get("dminsttNm") or "").strip()
                if org not in ntce_instt_nm and org not in dminstt_nm:
                    continue

                item_key = (
                    str(item.get("bidNtceNo") or ""),
                    str(item.get("bidNtceOrd") or ""),
                )
                if item_key in seen:
                    continue
                seen.add(item_key)
                results.append(item)

    out = {
        "query": {
            "inqryDiv": 1,
            "inqryBgnDt": inqry_bgn_dt,
            "inqryEndDt": inqry_end_dt,
            "orgs": orgs,
            "searchFields": list(search_fields),
            "filter": {"srvceDivNm": "일반용역"},
        },
        "count": len(results),
        "items": results,
    }

    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

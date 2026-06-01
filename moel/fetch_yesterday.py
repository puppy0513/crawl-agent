from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from lxml import html


KST = ZoneInfo("Asia/Seoul")
BASE_URL = "https://www.moel.go.kr"
NOTICE_LIST_URL = f"{BASE_URL}/news/notice/noticeList.do"
TARGET_DEPARTMENTS = [
    "직업능력정책과",
    "인적자원개발과",
]

ROW_XPATH = '//table[contains(concat(" ", normalize-space(@class), " "), " tstyle_list ")]/tbody/tr'
NUMBER_XPATH = 'normalize-space(.//td[@aria-label="번호"])'
TITLE_XPATH = 'normalize-space(.//td[@aria-label="제목"]//a)'
DETAIL_URL_XPATH = './/td[@aria-label="제목"]//a/@href'
DEPARTMENT_XPATH = 'normalize-space(.//td[@aria-label="담당부서"])'
REGISTERED_DATE_XPATH = 'normalize-space(.//td[@aria-label="등록일"])'


def yesterday_kst(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=KST)
    return (now - timedelta(days=1)).strftime("%Y.%m.%d")


def post_list_page(
    session: requests.Session,
    *,
    department: str,
    page_index: int,
    page_unit: int,
) -> str:
    data = {
        "pageIndex": str(page_index),
        "searchDivCd": "",
        "bbs_id": "9",
        "searchField": "3",  # 담당부서
        "searchText": department,
        "pageUnit": str(page_unit),
    }
    last_error: requests.RequestException | None = None
    for attempt in range(3):
        try:
            response = session.post(NOTICE_LIST_URL, data=data, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            last_error = e
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise last_error


def parse_rows(page_html: str) -> list[dict]:
    document = html.fromstring(page_html)
    rows = []
    for row in document.xpath(ROW_XPATH):
        detail_paths = row.xpath(DETAIL_URL_XPATH)
        detail_url = urljoin(BASE_URL, detail_paths[0]) if detail_paths else ""
        rows.append(
            {
                "number": row.xpath(NUMBER_XPATH),
                "title": row.xpath(TITLE_XPATH),
                "department": row.xpath(DEPARTMENT_XPATH),
                "registeredDate": row.xpath(REGISTERED_DATE_XPATH),
                "detailUrl": detail_url,
            }
        )
    return rows


def iter_department_notices(
    session: requests.Session,
    *,
    department: str,
    target_date: str,
    page_unit: int,
    page_limit: int,
) -> Iterable[dict]:
    for page_index in range(1, page_limit + 1):
        page_html = post_list_page(
            session,
            department=department,
            page_index=page_index,
            page_unit=page_unit,
        )
        rows = parse_rows(page_html)
        if not rows:
            break

        oldest_seen_date = None
        for row in rows:
            registered_date = row["registeredDate"]
            if registered_date:
                oldest_seen_date = registered_date
            if row["department"] == department and registered_date == target_date:
                yield row

        if oldest_seen_date and oldest_seen_date < target_date:
            break


def fetch_yesterday_notices(
    *,
    departments: list[str] | None = None,
    page_unit: int = 50,
    page_limit: int = 10,
    target_date: str | None = None,
) -> list[dict] | None:
    target_date = target_date or yesterday_kst()
    departments = departments or TARGET_DEPARTMENTS

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Referer": NOTICE_LIST_URL,
        }
    )

    results: list[dict] = []
    seen: set[str] = set()
    for department in departments:
        for notice in iter_department_notices(
            session,
            department=department,
            target_date=target_date,
            page_unit=page_unit,
            page_limit=page_limit,
        ):
            key = notice["detailUrl"] or f'{notice["department"]}:{notice["number"]}'
            if key in seen:
                continue
            seen.add(key)
            results.append(notice)

    return results or None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="전일(KST) 고용노동부 공지사항 중 지정 부서 공고 조회"
    )
    parser.add_argument(
        "--department",
        action="append",
        default=None,
        help="담당부서명. 여러 번 지정 가능. 기본값: 직업능력정책과, 인적자원개발과",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        help="조회할 등록일(YYYY.MM.DD). 기본값: 어제(KST)",
    )
    parser.add_argument(
        "--page-unit",
        type=int,
        default=50,
        help="페이지당 조회 건수",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=10,
        help="부서별 최대 조회 페이지 수",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="JSON pretty-print 출력",
    )
    args = parser.parse_args()

    notices = fetch_yesterday_notices(
        departments=args.department,
        page_unit=args.page_unit,
        page_limit=args.page_limit,
        target_date=args.target_date,
    )
    if args.pretty:
        print(json.dumps(notices, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(notices, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

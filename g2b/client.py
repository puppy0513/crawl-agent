from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


DEFAULT_BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"


class G2BApiError(RuntimeError):
    pass


def load_dotenv_if_needed(path: str = ".env") -> None:
    if os.getenv("G2B_SERVICE_KEY"):
        return

    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and not os.environ.get(key):
            os.environ[key] = value


@dataclass(frozen=True)
class G2BClient:
    service_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_s: int = 30

    @classmethod
    def from_env(cls) -> "G2BClient":
        load_dotenv_if_needed()
        service_key = (os.getenv("G2B_SERVICE_KEY") or "").strip()
        if not service_key:
            raise G2BApiError(
                "환경변수 G2B_SERVICE_KEY가 비어 있습니다. "
                "data.go.kr에서 발급받은 서비스키를 설정하세요."
            )
        base_url = (os.getenv("G2B_BASE_URL") or DEFAULT_BASE_URL).strip()
        return cls(service_key=service_key, base_url=base_url)

    def _get_json(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{operation}"
        q = {
            "ServiceKey": self.service_key,
            "type": "json",
            **params,
        }
        try:
            r = requests.get(url, params=q, timeout=self.timeout_s)
        except requests.RequestException as e:
            raise G2BApiError(f"API 요청 실패: {e.__class__.__name__}") from e
        if r.status_code != 200:
            raise G2BApiError(f"HTTP {r.status_code} 응답: {r.text[:500]}")
        try:
            data = r.json()
        except Exception as e:  # noqa: BLE001
            raise G2BApiError(f"JSON 파싱 실패: {e}; body={r.text[:500]}") from e

        header = (data.get("response") or {}).get("header") or {}
        if str(header.get("resultCode")) != "00":
            raise G2BApiError(f"API 오류: {header.get('resultCode')} {header.get('resultMsg')}")
        return data

    def iter_servc_pps_srch(
        self,
        *,
        inqry_div: int,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        ntce_instt_nm: Optional[str] = None,
        dminstt_nm: Optional[str] = None,
        bid_ntce_nm: Optional[str] = None,
        num_of_rows: int = 100,
        page_start: int = 1,
        page_limit: int = 50,
    ) -> Iterable[Dict[str, Any]]:
        """
        나라장터검색조건에 의한 입찰공고용역조회
        - operation: getBidPblancListInfoServcPPSSrch
        - inqryDiv: 1(공고게시일시), 2(개찰일시)
        - inqryBgnDt/inqryEndDt: YYYYMMDDHHMM
        - ntceInsttNm/dminsttNm: 일부 문자열만 넣어도 조회 가능(문서 기준)
        """
        operation = "getBidPblancListInfoServcPPSSrch"

        def items_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
            body = (payload.get("response") or {}).get("body") or {}
            items_container = body.get("items") or {}
            if isinstance(items_container, list):
                items = items_container
            elif isinstance(items_container, dict):
                items = items_container.get("item") or []
            else:
                items = []
            if isinstance(items, dict):
                return [items]
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
            return []

        page_no = page_start
        for _ in range(page_limit):
            params: Dict[str, Any] = {
                "pageNo": page_no,
                "numOfRows": num_of_rows,
                "inqryDiv": str(inqry_div),
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
            }
            if bid_ntce_nm:
                params["bidNtceNm"] = bid_ntce_nm
            if ntce_instt_nm:
                params["ntceInsttNm"] = ntce_instt_nm
            if dminstt_nm:
                params["dminsttNm"] = dminstt_nm

            payload = self._get_json(operation, params)
            items = items_from_payload(payload)
            for it in items:
                yield it

            body = (payload.get("response") or {}).get("body") or {}
            total_count = int(body.get("totalCount") or 0)
            if page_no * num_of_rows >= total_count:
                break
            page_no += 1

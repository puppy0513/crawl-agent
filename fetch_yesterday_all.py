from __future__ import annotations

import argparse
import mimetypes
import json
import os
import smtplib
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from g2b.fetch_yesterday import fetch_yesterday_bids
from moel.fetch_yesterday import fetch_yesterday_notices


KST = ZoneInfo("Asia/Seoul")
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_EMAIL_TO = "bjh@openeg.co.kr"
DOTENV_OVERRIDE_KEYS = {"OPENAI_MODEL"}


def today_kst() -> str:
    return datetime.now(tz=KST).strftime("%Y-%m-%d")


def moel_date(target_date: date) -> str:
    return target_date.strftime("%Y.%m.%d")


def load_env(path: str = ".env") -> None:
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
        if key and (key in DOTENV_OVERRIDE_KEYS or not os.environ.get(key)):
            os.environ[key] = value


def markdown_escape(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", " ").replace("\r", " ").strip()
    return text.replace("|", "\\|") or "-"


def markdown_link(label: object, url: object) -> str:
    label_text = markdown_escape(label)
    url_text = "" if url is None else str(url).strip()
    if not url_text:
        return label_text
    return f"[{label_text}]({url_text})"


def append_table(lines: list[str], headers: list[str], rows: list[list[object]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape(value) for value in row) + " |")
    lines.append("")


def render_g2b_section(lines: list[str], g2b_result: dict) -> None:
    items = g2b_result.get("items") or []
    lines.append("## 나라장터 일반용역")
    lines.append("")
    lines.append(f"- 조회 건수: {len(items)}건")
    lines.append("")
    if not items:
        lines.append("해당 공고가 없습니다.")
        lines.append("")
        return

    for index, item in enumerate(items, start=1):
        lines.append(f"### {index}. {markdown_escape(item.get('bidNtceNm'))}")
        lines.append("")
        append_table(
            lines,
            ["항목", "내용"],
            [
                ["공고번호", item.get("bidNtceNo")],
                ["발주처(수요기관)", item.get("dminsttNm")],
                ["계약 진행 공고", item.get("ntceInsttNm")],
            ],
        )
        append_table(
            lines,
            ["입찰 시작", "입찰 마감", "참가자격 등록마감", "공동수급협정서 접수마감"],
            [
                [
                    item.get("bidBeginDt"),
                    item.get("bidClseDt"),
                    item.get("bidQlfctRgstDt"),
                    item.get("cmmnSpldmdAgrmntClseDt"),
                ]
            ],
        )
        append_table(
            lines,
            ["배정예산액", "추정가격(부가세 제외)", "부가세", "입찰보증금"],
            [
                [
                    item.get("asignBdgtAmt"),
                    item.get("presmptPrce"),
                    item.get("VAT"),
                    item.get("bidPrtcptFee"),
                ]
            ],
        )
        append_table(
            lines,
            ["계약체결방법", "낙찰자결정방법", "평가비율", "예가 방식", "공동수급", "업종제한"],
            [
                [
                    item.get("cntrctCnclsMthdNm"),
                    item.get("sucsfbidMthdNm"),
                    f"{item.get('techAbltEvlRt') or '-'} / {item.get('bidPrceEvlRt') or '-'}",
                    item.get("prearngPrceDcsnMthdNm"),
                    item.get("cmmnSpldmdMethdNm"),
                    item.get("indstrytyLmtYn"),
                ]
            ],
        )


def render_moel_section(lines: list[str], moel_result: dict) -> None:
    items = moel_result.get("items") or []
    lines.append("## 고용노동부 공지사항")
    lines.append("")
    lines.append(f"- 조회 건수: {len(items)}건")
    lines.append("")
    if not items:
        lines.append("해당 공고가 없습니다.")
        lines.append("")
        return

    append_table(
        lines,
        ["번호", "등록일", "담당부서", "제목", "상세"],
        [
            [
                item.get("number"),
                item.get("registeredDate"),
                item.get("department"),
                item.get("title"),
                markdown_link("보기", item.get("detailUrl")),
            ]
            for item in items
        ],
    )


def render_markdown_report(result: dict, *, report_date: str) -> str:
    lines = [
        f"# {report_date} 발주공고 목록",
        "",
        f"- 생성일: {report_date}",
        f"- 나라장터 일반용역: {result['g2b']['count']}건",
        f"- 고용노동부 공지사항: {result['moel']['count']}건",
        "",
    ]
    render_g2b_section(lines, result["g2b"])
    render_moel_section(lines, result["moel"])
    return "\n".join(lines).rstrip() + "\n"


def read_instruction_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_analysis_prompt(result: dict, *, report_date: str) -> str:
    agent_md = read_instruction_file("Agent.md")
    skills_md = read_instruction_file("skills.md")
    notices_json = json.dumps(result, ensure_ascii=False, indent=2)

    return f"""당신은 오픈이지의 발주공고 분석 담당자입니다.

아래 Agent.md와 skills.md를 평가 기준으로 삼아, 크롤링된 발주공고의 제안 관련도와 중요도를 분석하세요.

중요:
- skills.md의 점수 체계, 사업영역, 판단 기준을 사용하세요.
- 현재 요청의 최종 산출물은 사람이 읽을 Markdown 보고서입니다. 따라서 skills.md의 "JSON만 출력" 규칙은 내부 평가 형식 참고용으로만 사용하고, 최종 답변은 Markdown으로만 작성하세요.
- 공고 본문과 첨부파일 텍스트가 없는 항목은 그 한계를 명확히 표시하세요.
- 추정이 필요한 내용은 단정하지 말고 "확인 필요"로 적으세요.
- 교육용역, 보안교육, 개발보안, 시큐어코딩, 보안인식 제고가 명확하지 않은 데이터 구축·데이터 개방·AI 모델 개발·SI 개발 공고는 최종 등급을 C 이하로 평가하세요.
- SI 개발, 개발외주, 시스템 통합, 업무시스템 구축이 핵심이면 최종 등급은 반드시 D로 두세요.
- 데이터 구축, 데이터 개방, 데이터 분석모델 개발, 플랫폼 구축, LMS 구축, 앱·웹 개발, 포털 구축이 핵심이면 최종 점수에서 크게 감점하고 추천 상위 Top 5에 올리지 마세요.
- 공고명에 AI, 데이터, 플랫폼이 있어도 교육 또는 보안 목적이 확인되지 않으면 교육사업으로 추정하지 마세요.
- 목록 데이터만 있고 과업지시서/제안요청서 본문이 없으면 "교육 요소 추가 가능성" 같은 가정을 점수 상승 사유로 쓰지 마세요. 그런 경우는 "확인 필요"로 두고 보수적으로 평가하세요.
- 개발외주나 SI 개발은 오픈이지의 주력 사업이 아니므로 예산이 크더라도 높은 점수를 주지 마세요.
- "지원 용역", "생태계 활성화", "민관협력", "협의체 운영", "운영지원"처럼 포괄적인 일반 용역은 교육운영, 보안교육, 개발보안, 시큐어코딩, 보안인식 제고가 공고명 또는 본문에 명확히 없으면 최종 등급을 C 이하로 두세요.
- 예산 규모, 공공성, 후속 가능성, 교육 가능성 추정만으로 A 또는 S 등급을 주지 마세요.
- 본문/첨부파일이 없는 공고는 공고명에 교육 또는 보안이 직접 드러나지 않는 한 적극 검토 이상으로 올리지 마세요.
- Markdown 코드블록으로 감싸지 말고, 보고서 본문만 출력하세요.

보고서 필수 구성:
1. 제목: "{report_date} 발주공고 분석 보고서"
2. 전체 요약: 총 공고 수, 즉시 검토/적극 검토/조건부/후순위/제외 권장 개수
3. 우선 검토 공고 Top 5: 공고명, 기관, 추천등급, 점수, 핵심 사유, 추가 확인사항
4. 전체 공고 평가표: 공고명, 기관, 분야 매칭, 점수, 등급, 추천, 주요 리스크
5. 공고별 상세 분석: D등급 공고는 제외하고, C등급 이상 공고만 긍정 신호, 부정 신호, 수주 가능성, 수행 리스크, 담당자 확인사항을 작성
6. 공고별 점수 산정 요약: D등급 공고는 제외하고, C등급 이상 공고만 작성
7. 최종 액션 아이템

작성 제한:
- D등급 또는 제외 권장 공고는 "공고별 상세 분석" 섹션에 작성하지 마세요.
- D등급 또는 제외 권장 공고는 "공고별 점수 산정 요약" 섹션에 작성하지 마세요.
- D등급 공고는 "전체 공고 평가표"에는 포함하되, 상세 설명은 주요 리스크 한 줄로 충분합니다.
- 모든 공고가 D등급이면 상세 분석과 점수 산정 요약 섹션에는 "C등급 이상 공고가 없어 생략합니다."라고만 작성하세요.

---

# Agent.md

{agent_md}

---

# skills.md

{skills_md}

---

# 크롤링 결과 JSON

{notices_json}
"""


def extract_response_text(response_data: dict) -> str:
    output_text = response_data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    for item in response_data.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    text = "\n".join(chunks).strip()
    if not text:
        raise RuntimeError("OpenAI 응답에서 텍스트를 찾지 못했습니다.")
    return text


def call_openai_for_markdown(prompt: str, *, model: str) -> str:
    api_key = os.getenv("CHATGPT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 OPENAI_API_KEY 또는 CHATGPT_API_KEY가 필요합니다.")

    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": prompt,
            "max_output_tokens": 12000,
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API 오류 HTTP {response.status_code}: {response.text[:500]}")
    return extract_response_text(response.json()).strip() + "\n"


def env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f".env에 {name} 설정이 필요합니다.")
    return value


def add_attachment(message: EmailMessage, path: Path) -> None:
    content_type, _ = mimetypes.guess_type(path.name)
    if not content_type:
        content_type = "application/octet-stream"
    maintype, subtype = content_type.split("/", 1)
    message.add_attachment(
        path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=path.name,
    )


def send_email_report(
    *,
    to_addrs: list[str],
    subject: str,
    body: str,
    attachments: list[Path],
) -> None:
    host = require_env("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT") or "587")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM") or username
    if not from_addr:
        raise RuntimeError(".env에 SMTP_FROM 또는 SMTP_USERNAME 설정이 필요합니다.")

    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = ", ".join(to_addrs)
    message["Subject"] = subject
    message.set_content(body)

    for attachment in attachments:
        add_attachment(message, attachment)

    use_tls = env_bool("SMTP_USE_TLS", default=True)
    use_ssl = env_bool("SMTP_USE_SSL", default=False)
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def crawl_yesterday_notices(target_date: date | None = None) -> dict:
    moel_notices = fetch_yesterday_notices(
        target_date=moel_date(target_date) if target_date else None
    )
    return {
        "g2b": fetch_yesterday_bids(target_date=target_date),
        "moel": {
            "count": len(moel_notices or []),
            "items": moel_notices,
        },
    }


def total_notice_count(result: dict) -> int:
    return int(result["g2b"]["count"]) + int(result["moel"]["count"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="전일(KST) 나라장터/고용노동부 공고를 한 번에 조회"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="JSON pretty-print 출력",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Markdown 보고서를 저장할 디렉터리. 기본값: 현재 디렉터리",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        help="조회할 공고일(YYYY-MM-DD). 기본값: 어제(KST)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI 모델명. 기본값: OPENAI_MODEL 환경변수 또는 {DEFAULT_OPENAI_MODEL}",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="ChatGPT API 분석 없이 기존 로컬 Markdown 목록만 생성",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help=f"생성된 Markdown 보고서를 이메일로 발송. 기본 수신자: {DEFAULT_EMAIL_TO}",
    )
    parser.add_argument(
        "--email-to",
        action="append",
        default=None,
        help=f"메일 수신자. 여러 번 지정 가능. 기본값: {DEFAULT_EMAIL_TO}",
    )
    args = parser.parse_args()

    load_env()
    target_date = date.fromisoformat(args.target_date) if args.target_date else None
    out = crawl_yesterday_notices(target_date=target_date)

    report_date = target_date.isoformat() if target_date else today_kst()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{report_date}_발주공고목록.json"
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = output_dir / f"{report_date}_발주공고목록.md"
    if args.skip_ai or total_notice_count(out) == 0:
        markdown = render_markdown_report(out, report_date=report_date)
    else:
        model = args.model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        prompt = build_analysis_prompt(out, report_date=report_date)
        markdown = call_openai_for_markdown(prompt, model=model)
    markdown_path.write_text(markdown, encoding="utf-8")

    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"JSON written: {json_path}")
        print(f"Markdown report written: {markdown_path}")

    if args.send_email:
        to_addrs = args.email_to or [DEFAULT_EMAIL_TO]
        send_email_report(
            to_addrs=to_addrs,
            subject=f"{report_date} 발주공고 목록",
            body=(
                f"{report_date} 발주공고 목록을 첨부합니다.\n\n"
                f"- 나라장터 일반용역: {out['g2b']['count']}건\n"
                f"- 고용노동부 공지사항: {out['moel']['count']}건\n"
            ),
            attachments=[markdown_path],
        )
        print(f"Email sent to: {', '.join(to_addrs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

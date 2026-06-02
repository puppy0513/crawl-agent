from __future__ import annotations

import argparse
import html as html_lib
import mimetypes
import json
import os
import re
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
MOEL_REPORT_LABEL = "고용노동부 발주공지(직업능력정책과,인적자원개발과)"


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
    lines.append(f"## {MOEL_REPORT_LABEL}")
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
        f"- {MOEL_REPORT_LABEL}: {result['moel']['count']}건",
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
2. "## 1) 전체 요약": 총 공고 수, 즉시 검토/적극 검토/조건부/후순위/제외 권장 개수와 "### 요약 판단" bullet 3개
3. "## 2) 우선 검토 공고 Top 5": 예시와 같은 Markdown 표 형식으로 최대 5개 작성
4. "## 4) 공고별 상세 분석": D등급 공고는 제외하고, C등급 이상 공고만 작성. 각 공고는 예시처럼 기관/분야 매칭/점수/등급/추천, 긍정 신호, 부정 신호, 수주 가능성, 수행 리스크, 담당자 확인사항, 점수 산정 요약을 작성
5. "## 6) 최종 액션 아이템": 예시처럼 번호 목록으로 작성

작성 제한:
- "전체 공고 평가표" 섹션은 작성하지 마세요.
- "공고별 점수 산정 요약" 섹션은 작성하지 마세요.
- 별도의 "## 3)" 또는 "## 5)" 섹션을 만들지 마세요.
- "## 2) 우선 검토 공고 Top 5" 표에는 전체 공고 중 우선순위 상위 5개를 작성하세요. D등급도 순위 설명을 위해 포함할 수 있습니다.
- D등급 또는 제외 권장 공고는 "## 4) 공고별 상세 분석"에는 작성하지 마세요.
- D등급 공고는 전체 요약에서 "제외 N건"으로만 집계하고 개별 설명하지 마세요.
- 모든 공고가 D등급이면 "## 4) 공고별 상세 분석"에는 "C등급 이상 공고가 없어 생략합니다."라고만 작성하세요.
- 보고서 구조와 표현은 아래 예시 형식을 반드시 따르세요.

형식 예시:

# {report_date} 발주공고 분석 보고서

## 1) 전체 요약

- 총 공고 수: N건
- 즉시 검토: N건
- 적극 검토: N건
- 조건부 검토: N건
- 후순위: N건
- 제외 권장: N건

### 요약 판단

- 핵심 판단 1
- 핵심 판단 2
- 핵심 판단 3

---

## 2) 우선 검토 공고 Top 5

> 기준: 오픈이지 적합도, 수행 가능성, 전략 가치, 리스크를 종합해 선정
> 단, 데이터 구축·개방·AI/SW 개발 중심 공고는 상위 추천에서 강하게 제한

|순위|공고명|기관|추천등급|점수|핵심 사유|추가 확인사항|
|---|---|---|---|---|---|---|
|1|공고명|기관|A|75|핵심 사유|추가 확인사항|

---

## 4) 공고별 상세 분석

### 1) 공고명

- 기관: 기관명
- 분야 매칭: 분야
- 점수: 75
- 등급: A
- 추천: 적극 검토

**긍정 신호**

- 내용

**부정 신호**

- 내용

**수주 가능성**

- 내용

**수행 리스크**

- 내용

**담당자 확인사항**

- 내용

**점수 산정 요약**

- 사업 적합도 24/30: 내용
- 매출 가능성 16/20: 내용
- 수주 가능성 15/20: 내용
- 전략적 가치 10/15: 내용
- 수행 리스크 10/15: 내용

---

## 6) 최종 액션 아이템

1. **액션 제목**
    - 내용

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


def is_allowed_detail_block(block: str) -> bool:
    return not re.search(
        r"(?mi)^-\s*등급:\s*D\b|^-\s*추천:\s*(제외|제외 권장)\b",
        block,
    )


def sanitize_detail_section(section: str) -> str:
    matches = list(re.finditer(r"(?m)^###\s+\d+\)\s+", section))
    if not matches:
        return section

    header = section[: matches[0].start()].rstrip()
    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        blocks.append(section[start:end].strip())

    allowed_blocks: list[str] = []
    for block in blocks:
        if not is_allowed_detail_block(block):
            continue
        next_number = len(allowed_blocks) + 1
        renumbered = re.sub(r"(?m)^###\s+\d+\)", f"### {next_number})", block, count=1)
        allowed_blocks.append(renumbered)

    if not allowed_blocks:
        return f"{header}\n\nC등급 이상 공고가 없어 생략합니다.\n\n---\n"

    return header + "\n\n" + "\n\n".join(allowed_blocks).rstrip() + "\n"


def sanitize_report_markdown(markdown: str) -> str:
    section_matches = list(re.finditer(r"(?m)^##\s+\d+\)\s+", markdown))
    if not section_matches:
        return markdown.strip() + "\n"

    prefix = markdown[: section_matches[0].start()]
    sanitized_sections: list[str] = []

    for index, match in enumerate(section_matches):
        start = match.start()
        end = (
            section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else len(markdown)
        )
        section = markdown[start:end].strip()
        section_number = re.match(r"##\s+(\d+)\)", section)
        if not section_number:
            sanitized_sections.append(section)
            continue

        number = section_number.group(1)
        if number in {"3", "5"}:
            continue
        if number == "4":
            section = sanitize_detail_section(section).strip()
        sanitized_sections.append(section)

    return prefix.rstrip() + "\n\n" + "\n\n".join(sanitized_sections).rstrip() + "\n"


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
    html_body: str | None = None,
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
    if html_body:
        message.add_alternative(html_body, subtype="html")

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


def inline_markdown_to_html(text: str) -> str:
    escaped = html_lib.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def is_markdown_table(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].strip().startswith("|")
        and lines[index].strip().endswith("|")
        and set(lines[index + 1].replace("|", "").replace(":", "").strip()) <= {"-"}
    )


def split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def markdown_table_to_html(lines: list[str]) -> str:
    headers = split_markdown_table_row(lines[0])
    rows = [split_markdown_table_row(line) for line in lines[2:]]
    html = [
        '<table style="border-collapse:collapse;width:100%;margin:12px 0;">',
        "<thead><tr>",
    ]
    for header in headers:
        html.append(
            '<th style="border:1px solid #ddd;padding:8px;background:#f6f8fa;text-align:left;">'
            f"{inline_markdown_to_html(header)}</th>"
        )
    html.append("</tr></thead><tbody>")
    for row in rows:
        html.append("<tr>")
        for cell in row:
            html.append(
                '<td style="border:1px solid #ddd;padding:8px;vertical-align:top;">'
                f"{inline_markdown_to_html(cell)}</td>"
            )
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def markdown_to_email_html(markdown: str) -> str:
    lines = markdown.splitlines()
    html: list[str] = [
        '<html><body style="font-family:Arial, Helvetica, sans-serif;line-height:1.55;color:#222;">'
    ]
    in_list = False
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()

        if is_markdown_table(lines, i):
            if in_list:
                html.append("</ul>")
                in_list = False
            table_lines = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i])
                i += 1
            html.append(markdown_table_to_html(table_lines))
            continue

        if not line:
            if in_list:
                html.append("</ul>")
                in_list = False
            i += 1
            continue

        if line.startswith("#"):
            if in_list:
                html.append("</ul>")
                in_list = False
            level = min(len(line) - len(line.lstrip("#")), 3)
            text = line[level:].strip()
            tag = f"h{level}"
            html.append(f"<{tag}>{inline_markdown_to_html(text)}</{tag}>")
        elif line.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{inline_markdown_to_html(line[2:].strip())}</li>")
        elif re.match(r"^\d+\.\s+", line):
            if not in_list:
                html.append("<ul>")
                in_list = True
            list_text = re.sub(r"^\d+\.\s+", "", line)
            html.append(f"<li>{inline_markdown_to_html(list_text)}</li>")
        elif line.startswith(">"):
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(
                '<blockquote style="border-left:4px solid #ddd;margin:12px 0;padding-left:12px;color:#555;">'
                f"{inline_markdown_to_html(line.lstrip('>').strip())}</blockquote>"
            )
        elif line == "---":
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append("<hr>")
        else:
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<p>{inline_markdown_to_html(line)}</p>")
        i += 1

    if in_list:
        html.append("</ul>")
    html.append("</body></html>")
    return "".join(html)


def build_email_body(
    *,
    report_date: str,
    result: dict,
    markdown: str,
    include_report: bool,
) -> str:
    notice_count = total_notice_count(result)
    intro = (
        f"{report_date} 발주공고가 없습니다.\n\n"
        if notice_count == 0
        else f"{report_date} 발주공고 분석 보고서를 아래에 포함하고, Markdown 파일로도 첨부합니다.\n\n"
    )
    summary = (
        f"- 나라장터 일반용역: {result['g2b']['count']}건\n"
        f"- {MOEL_REPORT_LABEL}: {result['moel']['count']}건\n"
    )
    if not include_report:
        return intro + summary
    return intro + summary + "\n---\n\n" + markdown


def build_email_html_body(
    *,
    report_date: str,
    result: dict,
    markdown: str,
    include_report: bool,
) -> str:
    notice_count = total_notice_count(result)
    intro = (
        f"<p>{html_lib.escape(report_date)} 발주공고가 없습니다.</p>"
        if notice_count == 0
        else (
            f"<p>{html_lib.escape(report_date)} 발주공고 분석 보고서를 아래에 포함하고, "
            "Markdown 파일로도 첨부합니다.</p>"
        )
    )
    summary = (
        "<ul>"
        f"<li>나라장터 일반용역: {int(result['g2b']['count'])}건</li>"
        f"<li>{html_lib.escape(MOEL_REPORT_LABEL)}: {int(result['moel']['count'])}건</li>"
        "</ul>"
    )
    if not include_report:
        return (
            '<html><body style="font-family:Arial, Helvetica, sans-serif;line-height:1.55;color:#222;">'
            f"{intro}{summary}</body></html>"
        )
    return (
        '<html><body style="font-family:Arial, Helvetica, sans-serif;line-height:1.55;color:#222;">'
        f"{intro}{summary}<hr>"
        + markdown_to_email_html(markdown).removeprefix(
            '<html><body style="font-family:Arial, Helvetica, sans-serif;line-height:1.55;color:#222;">'
        ).removesuffix("</body></html>")
        + "</body></html>"
    )


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
    markdown = sanitize_report_markdown(markdown)
    markdown_path.write_text(markdown, encoding="utf-8")

    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"JSON written: {json_path}")
        print(f"Markdown report written: {markdown_path}")

    if args.send_email:
        to_addrs = args.email_to or [DEFAULT_EMAIL_TO]
        notice_count = total_notice_count(out)
        subject = f"{report_date} 발주공고 목록"
        attachments = [markdown_path]
        if notice_count == 0:
            subject += " (발주공고 0건)"
            attachments = []

        send_email_report(
            to_addrs=to_addrs,
            subject=subject,
            body=build_email_body(
                report_date=report_date,
                result=out,
                markdown=markdown,
                include_report=notice_count > 0,
            ),
            html_body=build_email_html_body(
                report_date=report_date,
                result=out,
                markdown=markdown,
                include_report=notice_count > 0,
            ),
            attachments=attachments,
        )
        print(f"Email sent to: {', '.join(to_addrs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

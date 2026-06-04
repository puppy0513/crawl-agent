# 나라장터 입찰공고(OpenAPI) + 고용노동부 발주공고 - 전일 일반용역 조회

이 프로젝트는 조달청 “나라장터 입찰공고정보서비스(BidPublicInfoService)” OpenAPI를 사용해
**전일(어제, KST 기준)** 등록된 **일반용역** 발주공고 중,
기관명이 **한국인터넷진흥원** / **한국지능정보사회진흥원** 인 공고를 조회합니다.

문서 기준 사용 오퍼레이션:
- `getBidPblancListInfoServcPPSSrch` (나라장터검색조건에 의한 입찰공고용역조회)

## 준비물

- **공공데이터포털(data.go.kr) 서비스키(ServiceKey)**  
  (문서에 “ServiceKey 서비스키”로 표기)

## 환경설정

1) 파이썬 가상환경 생성/활성화

```bash
python -m venv .venv
source .venv/bin/activate
```

2) 의존성 설치

```bash
pip install -r requirements.txt
```

3) 환경변수 설정

`.env` 파일을 만들고(또는 쉘 환경변수로 설정) 서비스키를 넣습니다.

```bash
cp .env.example .env
```

`.env` 내용 예시:

```bash
G2B_SERVICE_KEY=발급받은_서비스키
```

## 실행

기본 실행(전일, 공고기관/수요기관 모두 검색):

```bash
python -m g2b.fetch_yesterday --pretty
```

수요기관 기준으로만 검색하고 싶으면:

```bash
python -m g2b.fetch_yesterday --use-demand-org --pretty
```

기관명을 바꿔서 검색하려면:

```bash
python -m g2b.fetch_yesterday --org "한국인터넷진흥원" --org "한국지능정보사회진흥원" --pretty
```

## 결과 필터링 기준

- 조회 범위: 전일 00:00 ~ 23:59 (KST)
- 조회 구분: `inqryDiv=1` (공고게시일시)
- 응답 필드 `srvceDivNm` 이 `"일반용역"` 인 건만 유지
- 기관명은 `ntceInsttNm`(공고기관명) 또는 `dminsttNm`(수요기관명) 에 포함되는지로 방어적으로 재확인

## 출력 필드

각 공고는 아래 필드만 출력합니다.

- `bidNtceNm`: 공고명
- `bidNtceNo`: 공고번호
- `dminsttNm`: 발주처(수요기관)
- `ntceInsttNm`: 계약 진행 공고
- `bidBeginDt`: 입찰 시작 일시
- `bidClseDt`: 입찰 마감 일시
- `bidQlfctRgstDt`: 입찰참가자격 등록마감
- `cmmnSpldmdAgrmntClseDt`: 공동수급협정서 접수마감
- `asignBdgtAmt`: 배정예산액
- `presmptPrce`: 추정가격(부가세제외금액)
- `VAT`: 부가세
- `bidPrtcptFee`: 입찰보증금
- `cntrctCnclsMthdNm`: 계약체결방법
- `sucsfbidMthdNm`: 낙찰자결정방법
- `techAbltEvlRt`: 기술능력 평가비율
- `bidPrceEvlRt`: 입찰가격 평가비율
- `prearngPrceDcsnMthdNm`: 예가 방식
- `cmmnSpldmdMethdNm`: 공동수급 가능여부(컨소여부)
- `indstrytyLmtYn`: 업종제한 여부

## 고용노동부 발주공지(직업능력정책과,인적자원개발과) 조회

고용노동부 발주공지에서 전일(KST) 기준 `직업능력정책과`, `인적자원개발과` 공고만 조회합니다.
조건에 맞는 공고가 없으면 `null`을 출력합니다.

```bash
python -m moel.fetch_yesterday --pretty
```

특정 날짜나 담당부서를 지정할 수도 있습니다.

```bash
python -m moel.fetch_yesterday --target-date 2026.05.12 --department 직업능력정책과 --pretty
```

## 통합 실행 및 AI 분석

나라장터와 고용노동부 공고 조회를 한 번에 실행한 뒤, `Agent.md`와 `skills.md`를 기준으로 ChatGPT API에 분석을 요청하고 결과를 Markdown 파일로 저장합니다.

```bash
python fetch_yesterday_all.py
```

생성 파일:

- `{오늘날짜}_발주공고목록.json`: 크롤링 원본 결과
- `{오늘날짜}_발주공고목록.md`: ChatGPT API가 작성한 제안 관련도/중요도 분석 보고서

사용 환경변수:

- `CHATGPT_API_KEY` 또는 `OPENAI_API_KEY`: OpenAI API 키
- `OPENAI_MODEL`: 사용할 모델명(선택). 기본값은 `gpt-5.4-mini`
- `SMTP_HOST`: SMTP 서버 주소
- `SMTP_PORT`: SMTP 포트. 기본값은 `587`
- `SMTP_USERNAME`: SMTP 로그인 계정
- `SMTP_PASSWORD`: SMTP 로그인 비밀번호 또는 앱 비밀번호
- `SMTP_FROM`: 발신자 이메일. 생략하면 `SMTP_USERNAME` 사용
- `SMTP_USE_TLS`: STARTTLS 사용 여부. 기본값은 `true`
- `SMTP_USE_SSL`: SMTP SSL 사용 여부. 기본값은 `false`

주의: 기본 실행은 `Agent.md`, `skills.md`, 크롤링된 공고 JSON을 OpenAI API로 전송해 분석 보고서를 생성합니다.

API 분석 없이 기존 목록형 Markdown만 만들려면:

```bash
python fetch_yesterday_all.py --skip-ai
```

JSON 출력도 터미널에서 함께 확인하려면:

```bash
python fetch_yesterday_all.py --pretty
```

생성된 Markdown 보고서를 `bjh@openeg.co.kr`로 메일 발송하려면:

```bash
python fetch_yesterday_all.py --send-email
```

수신자를 추가하거나 바꾸려면:

```bash
python fetch_yesterday_all.py --send-email --email-to bjh@openeg.co.kr --email-to someone@example.com
```

## GitHub Actions 자동화

GitHub Actions는 외부 트리거를 받아 크롤링과 메일 발송을 실행합니다.  
이 저장소는 GitHub 내부 `schedule` 대신 `repository_dispatch` 또는 수동 실행을 받도록 설정되어 있습니다.

이 저장소에는 `.github/workflows/daily-bid-report.yml` 워크플로우가 포함되어 있습니다.

- 실행 방식: `cron-job.org` 같은 외부 스케줄러가 GitHub API로 `repository_dispatch` 호출
- 실행 환경: GitHub-hosted Ubuntu runner
- 실행 명령: `python fetch_yesterday_all.py --send-email`
- 메일 본문: 공고가 1건 이상이면 발주공고 분석 보고서 Markdown 내용을 본문에도 포함
- 메일 첨부: 공고가 1건 이상이면 `{오늘날짜}_발주공고목록.md` 첨부, 0건이면 첨부 생략
- 결과 보관: GitHub Actions artifact에 `.md`, `.json` 업로드

공고가 1건 이상이면 ChatGPT API 분석을 호출하고, 공고가 0건이면 API 호출 없이 “해당 공고 없음” 보고서를 발송합니다.

`cron-job.org`에서 GitHub API를 호출하는 예시는 아래와 같습니다.

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR_GITHUB_TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/puppy0513/crawl-agent/dispatches \
  -d '{"event_type":"daily-bid-report"}'
```

`<YOUR_GITHUB_TOKEN>`에는 해당 저장소에 `Contents: write` 권한이 있는 GitHub Personal Access Token 또는 fine-grained token을 넣습니다.

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 `SECRET`이라는 이름으로 `.env`와 같은 형식의 값을 등록합니다.

`SECRET` 안에 들어가야 하는 필수 값:

- `G2B_SERVICE_KEY`
- `CHATGPT_API_KEY` 또는 `OPENAI_API_KEY`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

`SECRET` 안에 들어갈 수 있는 선택 값:

- `OPENAI_MODEL`: 생략 시 `gpt-5.4-mini`
- `SMTP_HOST`: 생략 시 `smtp.gmail.com`
- `SMTP_PORT`: 생략 시 `587`
- `SMTP_FROM`
- `SMTP_USE_TLS`: 생략 시 `true`
- `SMTP_USE_SSL`: 생략 시 `false`

Gmail SMTP 예시:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=bjh.openeg@gmail.com
SMTP_PASSWORD=Google 앱 비밀번호
SMTP_FROM=bjh.openeg@gmail.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

각 값을 개별 GitHub Actions Secret으로 등록해도 동작하지만, 이 워크플로우는 `SECRET` 하나에 위 내용을 모아 넣는 방식을 우선 지원합니다.

수동으로 즉시 실행하려면 GitHub 저장소의 `Actions > Daily Bid Report > Run workflow`를 누르거나, 위 `repository_dispatch`를 직접 호출합니다.

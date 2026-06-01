# skills.md

## 1. 역할

이 문서는 발주공고 분석 LLM이 수집된 공고 데이터를 읽고, 오픈이지 관점에서 중요도를 평가하는 방법을 정의한다.

- `Agent.md`: 오픈이지가 어떤 회사이고 어떤 공고를 선호하는지 정의한다.
- `skills.md`: 공고 데이터를 어떻게 읽고, 점수화하고, 어떤 JSON으로 출력할지 정의한다.

`Agent.md`와 `skills.md`가 충돌하면, 회사 정체성과 사업영역은 `Agent.md`를 우선하고, 점수 산정과 출력 형식은 `skills.md`를 우선한다.

---

## 2. 입력 데이터

LLM은 아래 정규화된 입력 형식을 기준으로 공고를 분석한다.

```json
{
  "notice_title": "공고명",
  "organization": "발주기관 또는 수요기관",
  "contracting_agency": "계약 진행 기관",
  "notice_url": "공고 URL",
  "posted_date": "공고일",
  "bid_start": "입찰 시작 일시",
  "deadline": "입찰 마감 일시",
  "qualification_deadline": "입찰참가자격 등록마감",
  "consortium_deadline": "공동수급협정서 접수마감",
  "budget": "배정예산액",
  "estimated_price": "추정가격",
  "vat": "부가세",
  "bid_bond": "입찰보증금",
  "contract_method": "계약체결방법",
  "award_method": "낙찰자결정방법",
  "evaluation_ratio": "평가비율",
  "price_method": "예가 방식",
  "consortium_allowed": "공동수급 가능여부",
  "industry_restriction": "업종제한 여부",
  "notice_body": "공고 본문",
  "attachments_text": "과업지시서, 제안요청서 등 첨부파일 추출 텍스트"
}
```

입력값 중 일부가 없을 수 있다. 없는 정보는 임의로 추정하지 말고 `"확인 필요"`로 표시한다.

### 2.1 현재 크롤러 출력 필드 매핑

현재 `fetch_yesterday_all.py` 결과를 LLM 입력으로 변환할 때는 아래 매핑을 사용한다.

| LLM 입력 필드 | 나라장터 필드 | 고용노동부 필드 |
|---|---|---|
| `notice_title` | `bidNtceNm` | `title` |
| `organization` | `dminsttNm` | `department` |
| `contracting_agency` | `ntceInsttNm` | `고용노동부` |
| `notice_url` | `bidNtceUrl` 또는 `bidNtceDtlUrl`이 있으면 사용, 없으면 `확인 필요` | `detailUrl` |
| `posted_date` | `확인 필요` | `registeredDate` |
| `bid_start` | `bidBeginDt` | `확인 필요` |
| `deadline` | `bidClseDt` | `확인 필요` |
| `qualification_deadline` | `bidQlfctRgstDt` | `확인 필요` |
| `consortium_deadline` | `cmmnSpldmdAgrmntClseDt` | `확인 필요` |
| `budget` | `asignBdgtAmt` | `확인 필요` |
| `estimated_price` | `presmptPrce` | `확인 필요` |
| `vat` | `VAT` | `확인 필요` |
| `bid_bond` | `bidPrtcptFee` | `확인 필요` |
| `contract_method` | `cntrctCnclsMthdNm` | `확인 필요` |
| `award_method` | `sucsfbidMthdNm` | `확인 필요` |
| `evaluation_ratio` | `techAbltEvlRt / bidPrceEvlRt` | `확인 필요` |
| `price_method` | `prearngPrceDcsnMthdNm` | `확인 필요` |
| `consortium_allowed` | `cmmnSpldmdMethdNm` | `확인 필요` |
| `industry_restriction` | `indstrytyLmtYn` | `확인 필요` |
| `notice_body` | 상세 페이지 수집 전이면 `확인 필요` | 상세 페이지 수집 전이면 `확인 필요` |
| `attachments_text` | 첨부파일 추출 전이면 `확인 필요` | 첨부파일 추출 전이면 `확인 필요` |

중요: 현재 목록 수집만으로는 실제 과업을 완전히 판단하기 어렵다. `notice_body`나 `attachments_text`가 없으면 평가 점수와 사유에 그 불확실성을 반드시 반영한다.

---

## 3. 분석 절차

### Step 1. 실제 과업 파악

공고명만 보고 판단하지 않는다. 공고 본문과 과업지시서/제안요청서가 있으면 반드시 그 내용을 기준으로 판단한다.

다음 질문에 답한다.

- 이 사업은 교육사업인가?
- 콘텐츠 개발사업인가?
- 교육 플랫폼 또는 LMS 구축사업인가?
- 역량평가 또는 직무진단 사업인가?
- 보안진단 또는 보안컨설팅 사업인가?
- 단순 SI, 장비납품, 유지보수, 행사대행 사업인가?
- 교육 관련 과업이 핵심인가, 부수 과업인가?

### Step 2. 오픈이지 사업영역과 매칭

다음 사업영역 중 하나 이상에 매칭한다.

- 교육운영
- KDT·인재양성
- 교육과정 개발
- 교육 콘텐츠 개발
- LMS·교육 플랫폼
- 코딩 실습 플랫폼
- 시큐어코딩 훈련 시스템
- 기술역량 평가
- 보안진단
- 보안컨설팅
- 클라우드 컨설팅
- 기타

### Step 3. 긍정 신호 탐지

다음 조건이 있으면 긍정 신호로 판단한다.

- 클라우드, 보안, AI, 개발 교육이 핵심 과업이다.
- 장기 교육과정 운영이 포함되어 있다.
- 교육과정 설계, 교재 개발, 강사 운영이 포함되어 있다.
- 실습 중심 교육이다.
- 프로젝트 기반 교육, PBL, 멘토링, 해커톤, 발표회가 포함되어 있다.
- 교육생 관리, 출결, 평가, 성과관리가 포함되어 있다.
- LMS, 온라인 교육 플랫폼, 코딩 실습 환경, 웹 IDE가 포함되어 있다.
- 시큐어코딩, SW개발보안, 보안약점 진단이 포함되어 있다.
- KDT, 고용노동부, IITP, KISA, 대학, 지자체 인재양성 사업이다.
- 기존 오픈이지 수행실적과 유사한 구조다.

### Step 4. 부정 신호 탐지

다음 조건이 있으면 부정 신호로 판단한다.

- 교육이 핵심이 아니라 단순 시스템 개발이 핵심이다.
- 장비 납품이나 물품 구매가 중심이다.
- 홈페이지, ERP, 그룹웨어 등 일반 SI 구축사업이다.
- 유지보수, 운영대행, 사무행정이 중심이다.
- 홍보, 행사, 영상, 디자인 중심이다.
- 교육이 포함되어 있어도 단순 행사성 특강에 가깝다.
- 요구 인력이 지나치게 많거나 상주 부담이 크다.
- 특정 대기업 SI 또는 특정 솔루션 벤더에게 유리하다.
- 예산이 낮고 제안 준비 부담이 크다.
- 오픈이지의 핵심 분야인 클라우드, 보안, AI, 개발교육과 관련성이 낮다.

부정 신호가 명확히 없으면 억지로 만들지 말고 `"특이 부정 신호 없음"`이라고 작성한다.

---

## 4. 점수 체계

공고는 100점 만점으로 평가한다.

| 평가항목 | 배점 | 설명 |
|---|---:|---|
| 사업 적합도 | 30 | 오픈이지 핵심 사업과 얼마나 직접적으로 연결되는가 |
| 매출 가능성 | 20 | 교육운영, 콘텐츠, 플랫폼, 평가 등 매출 규모와 반복 가능성이 있는가 |
| 수주 가능성 | 20 | 기존 실적, 인증, 인력, 강사풀로 실제 수주 가능성이 있는가 |
| 전략적 가치 | 15 | 후속사업, 레퍼런스, 시장확장 가치가 있는가 |
| 수행 리스크 | 15 | 수행 부담, 상주, SI성 과업, 인력 리스크가 낮은가 |

수행 리스크 점수는 리스크가 낮을수록 높게 부여한다.

### 4.1 등급 기준

| 등급 | 점수 | 추천 |
|---|---:|---|
| S | 85~100 | 즉시 검토 |
| A | 70~84 | 적극 검토 |
| B | 55~69 | 조건부 검토 |
| C | 40~54 | 후순위 |
| D | 0~39 | 제외 |

### 4.2 세부 점수 기준

사업 적합도:

- 27~30점: 오픈이지 핵심 사업과 매우 직접적이다. 예: 클라우드·보안·AI·개발 장기교육, KDT, 시큐어코딩 교육
- 22~26점: 교육, 콘텐츠, 평가, 플랫폼 중 하나와 명확히 관련 있다.
- 16~21점: 일부 관련은 있으나 핵심 과업은 아니다.
- 8~15점: 키워드는 있으나 실제 사업 적합도는 낮다.
- 0~7점: 오픈이지 사업과 거의 무관하다.

매출 가능성:

- 18~20점: 장기 교육운영, 과정설계, 콘텐츠개발, 평가, 플랫폼 등이 결합되어 매출 규모가 크다.
- 14~17점: 교육운영 또는 콘텐츠개발 중심으로 일정 매출이 기대된다.
- 9~13점: 단기 교육, 특강, 소규모 용역 수준이다.
- 4~8점: 매출 가능성은 있으나 규모가 작거나 일회성이다.
- 0~3점: 오픈이지 기준 매출화 가능성이 낮다.

수주 가능성:

- 18~20점: 기존 수행실적과 매우 유사하며 강점이 명확하다.
- 14~17점: 수행 가능성이 높고 경쟁력도 있다.
- 9~13점: 수행은 가능하나 경쟁이 강하거나 추가 파트너가 필요하다.
- 4~8점: 일부 수행 가능하지만 제약이 많다.
- 0~3점: 수주 가능성이 매우 낮다.

전략적 가치:

- 13~15점: 후속사업, 레퍼런스, 공공시장 확장 가치가 크다.
- 10~12점: 유의미한 레퍼런스가 된다.
- 6~9점: 제한적 전략 가치가 있다.
- 3~5점: 단기 매출 외 전략 가치는 낮다.
- 0~2점: 전략 가치가 거의 없다.

수행 리스크:

- 13~15점: 기존 역량으로 무리 없이 수행 가능하다.
- 10~12점: 일부 조율이 필요하나 수행 가능하다.
- 6~9점: 인력, 일정, 파트너, 과업범위 리스크가 있다.
- 3~5점: 수행 부담이 크다.
- 0~2점: 수행 리스크가 매우 높다.

---

## 5. 공고 유형별 기본 가이드

매우 높은 우선순위:

- KDT 교육 운영
- 디지털 선도기업 아카데미
- SW 인재양성 과정
- 클라우드, 보안, AI, 생성형 AI 교육과정 운영
- 시큐어코딩, SW 개발보안 교육
- 장기 부트캠프
- 실습 중심 개발자 양성과정
- 교육과정 설계 + 교육운영 + 평가가 결합된 사업

높은 우선순위:

- 교육콘텐츠 개발
- 온라인 교육 콘텐츠 제작
- 커리큘럼 또는 교재 개발
- 직무역량 평가
- 코딩테스트
- 보안역량 진단
- LMS, 교육 플랫폼, 시큐어코딩 훈련 플랫폼 구축

중간 우선순위:

- 단기 특강
- 단순 강사 파견
- 일반 IT 교육
- 단순 워크숍
- 행사성 해커톤
- 일반 보안 컨설팅
- 단순 취약점 진단

낮은 우선순위:

- 일반 SI 개발
- 홈페이지, ERP, 그룹웨어 구축
- 장비 납품
- 네트워크 장비 구축
- 단순 유지보수
- 일반 행정 운영
- 행사 대행
- 홍보 용역
- 영상 제작

---

## 6. 출력 형식

LLM은 반드시 아래 JSON 형식으로만 출력한다. JSON 외의 설명 문장, Markdown 표, 코드블록은 출력하지 않는다.

```json
{
  "notice_summary": {
    "title": "",
    "organization": "",
    "contracting_agency": "",
    "url": "",
    "posted_date": "",
    "deadline": "",
    "budget": "",
    "period": ""
  },
  "classification": {
    "final_grade": "",
    "final_score": 0,
    "recommendation": "",
    "matched_business_areas": []
  },
  "score_detail": {
    "business_fit": {
      "score": 0,
      "max_score": 30,
      "reason": ""
    },
    "revenue_potential": {
      "score": 0,
      "max_score": 20,
      "reason": ""
    },
    "win_probability": {
      "score": 0,
      "max_score": 20,
      "reason": ""
    },
    "strategic_value": {
      "score": 0,
      "max_score": 15,
      "reason": ""
    },
    "execution_risk": {
      "score": 0,
      "max_score": 15,
      "reason": ""
    }
  },
  "positive_signals": [],
  "negative_signals": [],
  "key_reasons": {
    "why_relevant": "",
    "why_profitable": "",
    "why_winnable": "",
    "risks": "",
    "additional_checks": ""
  },
  "evidence_quality": {
    "has_notice_body": false,
    "has_attachments_text": false,
    "missing_information": []
  },
  "final_comment": ""
}
```

### 6.1 출력 값 제한

- `classification.final_grade`는 반드시 `S`, `A`, `B`, `C`, `D` 중 하나만 출력한다.
- `classification.recommendation`은 반드시 `즉시 검토`, `적극 검토`, `조건부 검토`, `후순위`, `제외` 중 하나만 출력한다.
- `classification.final_score`는 세부 점수 5개 합계와 반드시 일치해야 한다.
- `classification.matched_business_areas`는 2장의 사업영역 목록 중 하나 이상을 사용한다.
- 정보가 부족하면 빈 문자열이 아니라 `"확인 필요"`라고 작성한다.
- `positive_signals`는 최소 1개 이상 작성한다. 없으면 `"명확한 긍정 신호 확인 필요"`라고 작성한다.
- `negative_signals`는 최소 1개 이상 작성한다. 없으면 `"특이 부정 신호 없음"`이라고 작성한다.
- S등급 또는 A등급인 경우 담당자가 바로 확인해야 할 사항을 `additional_checks`에 작성한다.
- 상세 본문이나 첨부 텍스트가 없으면 `evidence_quality.missing_information`에 반드시 기록하고, `final_comment`에도 판단 한계를 언급한다.

---

## 7. 운영 권장사항

실제 자동화 파이프라인에서는 다음 순서로 처리한다.

1. 나라장터, 고용노동부, 공공기관 사이트에서 공고 수집
2. 공고명, 발주기관, 예산, 마감일, 상세 URL 저장
3. 상세 페이지 본문 수집
4. 첨부파일 PDF, HWP, DOCX, XLSX 텍스트 추출
5. 크롤러 출력 필드를 이 문서의 정규화 입력 형식으로 변환
6. `Agent.md`와 `skills.md`를 함께 LLM에 전달
7. LLM이 JSON 형식으로 공고 평가
8. `final_score`와 `final_grade` 기준으로 저장 및 알림

추천 알림 기준:

- S등급: 즉시 알림
- A등급: 당일 알림
- B등급: 일일 요약 포함
- C등급: 주간 요약 또는 보관
- D등급: 보관 또는 제외

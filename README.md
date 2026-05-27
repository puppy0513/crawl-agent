# 나라장터 입찰공고(OpenAPI) - 전일 일반용역 조회

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

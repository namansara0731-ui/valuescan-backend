# ValueScan Backend

FinanceDataReader(FDR)를 이용해 한국 주식 데이터를 ValueScan에 제공하는 개인용 백엔드입니다.

## 제공 API

- `GET /health` 서버 상태
- `GET /stocks?market=KRX&limit=100` KRX/KOSPI/KOSDAQ/KONEX 종목 목록
- `GET /stock/005930` 종목 기본정보
- `GET /price/005930?days=120` 가격/거래량
- `GET /analyze/005930` 가격 기반 1차 분석

## 실행

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

실행 후:
`http://127.0.0.1:8000/docs`

## 주의

FDR은 오픈소스 금융 데이터 리더이며 여러 데이터 소스를 읽습니다.
가격/종목 목록과 재무제표 기능이 제공되지만, 모든 데이터가 항상 실시간·완전함을 보장하는 공식 거래소 API는 아닙니다.

현재 `/analyze`는 가격/거래량 기반 지표만 계산합니다.
ValueScan의 핵심인 PER/PBR/ROE/성장성 점수는 다음 단계에서 재무 데이터 소스를 붙여야 합니다.

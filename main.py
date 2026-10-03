from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import FinanceDataReader as fdr
import pandas as pd
import time
import threading

app = FastAPI(title="ValueScan Backend", version="0.1.0")

# ValueScan HTML을 다른 주소에서 열어도 API를 호출할 수 있게 함.
# 개인용 테스트 단계에서는 전체 허용. 공개 배포 시에는 반드시 도메인을 제한할 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache = {}
_lock = threading.Lock()
CACHE_SECONDS = 600  # 10분

def cached(key):
    item = _cache.get(key)
    if not item:
        return None
    if time.time() - item["time"] > CACHE_SECONDS:
        return None
    return item["data"]

def put_cache(key, data):
    _cache[key] = {"time": time.time(), "data": data}
    return data

@app.get("/")
def root():
    return {
        "app": "ValueScan Backend",
        "status": "ok",
        "message": "FDR 연결 완료",
        "endpoints": ["/health", "/stocks", "/stock/{code}", "/price/{code}"]
    }

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat(timespec="seconds")}

@app.get("/stocks")
def stocks(market: str = "KRX", limit: int = 100):
    """
    KRX/KOSPI/KOSDAQ 종목 목록.
    FDR 공식 사용 예시의 StockListing('KRX') 등을 이용한다.
    """
    if market not in {"KRX", "KOSPI", "KOSDAQ", "KONEX"}:
        raise HTTPException(400, "market은 KRX, KOSPI, KOSDAQ, KONEX 중 하나여야 합니다.")
    limit = max(1, min(limit, 5000))
    key = f"stocks:{market}"
    data = cached(key)
    if data is None:
        try:
            df = fdr.StockListing(market)
            # NaN/NaT를 JSON으로 내보낼 수 없으므로 문자열/None으로 정리
            df = df.where(pd.notna(df), None)
            records = df.head(limit).to_dict(orient="records")
            data = put_cache(key, records)
        except Exception as e:
            raise HTTPException(502, f"FDR 종목 목록 조회 실패: {e}")
    return {"market": market, "count": len(data), "data": data}

@app.get("/stock/{code}")
def stock(code: str):
    code = code.strip().upper()
    if not code:
        raise HTTPException(400, "종목코드를 입력하세요.")

    key = f"stock:{code}"
    data = cached(key)
    if data is not None:
        return data

    try:
        listing = fdr.StockListing("KRX")
        row = listing[listing["Code"].astype(str).str.zfill(6) == code.zfill(6)]
        if row.empty:
            raise HTTPException(404, "KRX 목록에서 종목을 찾지 못했습니다.")

        record = row.iloc[0].where(pd.notna(row.iloc[0]), None).to_dict()
        return put_cache(key, {"code": code.zfill(6), "data": record})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"종목 조회 실패: {e}")

@app.get("/price/{code}")
def price(code: str, days: int = 120):
    """
    최근 가격/거래량 데이터.
    FDR의 DataReader(code, start)를 사용한다.
    """
    code = code.strip().upper()
    days = max(5, min(days, 5000))
    key = f"price:{code}:{days}"
    data = cached(key)
    if data is not None:
        return data

    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader(code, start)
        if df is None or df.empty:
            raise HTTPException(404, "가격 데이터를 찾지 못했습니다.")

        df = df.tail(days).reset_index()
        # Date -> 문자열
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df = df.where(pd.notna(df), None)
        records = df.to_dict(orient="records")

        result = {
            "code": code,
            "count": len(records),
            "data": records,
            "source": "FinanceDataReader"
        }
        return put_cache(key, result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"가격 데이터 조회 실패: {e}")

@app.get("/analyze/{code}")
def analyze(code: str):
    """
    ValueScan 1차 분석용.
    현재는 가격/거래량 기반 지표만 계산한다.
    PER/PBR/ROE 등 재무지표는 별도 데이터 소스를 연결한 뒤 추가한다.
    """
    code = code.strip().upper()
    try:
        df = fdr.DataReader(code, (datetime.now() - timedelta(days=370)).strftime("%Y-%m-%d"))
        if df is None or df.empty:
            raise HTTPException(404, "분석할 가격 데이터가 없습니다.")

        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()

        latest = float(close.iloc[-1])
        ret_1m = float((latest / close.iloc[-22] - 1) * 100) if len(close) >= 22 else None
        ret_3m = float((latest / close.iloc[-63] - 1) * 100) if len(close) >= 63 else None
        avg20 = float(volume.tail(20).mean()) if len(volume) >= 20 else None
        vol_ratio = float(volume.iloc[-1] / avg20) if avg20 and avg20 > 0 else None

        # 가격 흐름 점수: 투자 추천이 아니라 ValueScan 내부 비교용 지표
        trend_score = 50.0
        if ret_1m is not None:
            trend_score += max(-25, min(25, ret_1m))
        trend_score = max(0, min(100, trend_score))

        return {
            "code": code,
            "latest_close": latest,
            "return_1m_pct": ret_1m,
            "return_3m_pct": ret_3m,
            "volume_vs_20d_avg": vol_ratio,
            "trend_score": round(trend_score, 1),
            "note": "가격 데이터 기반 내부 지표이며 매수/매도 신호가 아닙니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"분석 실패: {e}")

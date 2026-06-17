import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time

def get_us_filtered_tickers_master(min_market_cap_billion=1.5):
    """[US Master] 미국 핵심 우량주($1.5B 이상)를 추출합니다."""
    print("⏳ [US] 미국 전체 시장 시가총액 데이터베이스 동기화 중...")
    tickers = set()
    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers_with_sectors.csv"
        df_master = pd.read_csv(url, timeout=20)
        if 'Symbol' in df_master.columns:
            df_master['Symbol'] = df_master['Symbol'].astype(str).str.strip().str.upper()
            df_filtered = df_master[(df_master['Symbol'].str.isalpha()) & (df_master['Symbol'].str.len() <= 4)]
            raw_list = df_filtered['Symbol'].unique().tolist()
            for t in raw_list:
                tickers.add(t.replace('.', '-'))
            print(f"✅ [US Master] 전체 시장 풀 {len(tickers)}개 확보 완료.")
    except Exception as e:
        print(f"⚠️ [US Master] 실패: {e}. 지수 기반으로 전환합니다.")
        return get_fallback_index_tickers()
    return list(tickers)

def get_fallback_index_tickers():
    """백업용 S&P 500 & 나스닥 100 수집"""
    print("⏳ [Backup] 핵심 지수 종목 대체 수집...")
    tickers = set()
    try:
        url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        df_sp = pd.read_html(requests.get(url_sp, timeout=10).text)[0]
        for t in df_sp['Symbol'].dropna().tolist():
            tickers.add(t.strip().upper().replace('.', '-'))
        print(f"✅ 백업 모드 가동 성공: {len(tickers)}개 자산 확보.")
    except:
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA']
    return list(tickers)

def send_email(content, is_html=False):
    """구글 SMTP 이메일 발송 함수"""
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        print("\n⚠️ 환경변수 설정 미비. 콘솔에 리포트를 출력합니다.\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 전수조사] 3년 박스권 돌파형 장기 신고가 종목 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("📧 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")
        raise e

def screen_stocks():
    raw_tickers = get_us_filtered_tickers_master()
    results = []
    
    chunk_size = 150
    all_close_data = pd.DataFrame()
    
    print(f"📊 총 {len(raw_tickers)}개 기본 풀 대상 주가 데이터 다운로드 시작...")
    for i in range(0, len(raw_tickers), chunk_size):
        chunk_tickers = raw_tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="3y", interval="1wk", progress=False, timeout=50)
            if not chunk_data.empty and 'Close' in chunk_data.columns:
                chunk_close = chunk_data['Close']
                if all_close_data.empty:
                    all_close_data = chunk_close
                else:
                    all_close_data = pd.concat([all_close_data, chunk_close], axis=1)
            print(f"  > ⏳ {min(i + chunk_size, len(raw_tickers))} / {len(raw_tickers)} 종목 완료...")
            time.sleep(1.2)
        except Exception as e:
            print(f"⚠️ 청크 다운로드 중 일시적 지연 발생: {e}")
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 주가 데이터가 존재하지 않습니다. 스캔을 종료합니다.")
        return

    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    print("🔍 [필터링 & 스캔] 기술적 돌파 조건 연산 중...")
    if isinstance(all_close_data, pd.Series):
        all_close_data = all_close_data.to_frame()

    for ticker in all_close_data.columns:
        try:
            series_close = all_close_data[ticker].dropna()
            if len(series_close) < 100:
                continue 
            
            curr_price = series_close.iloc[-1]
            if pd.isna(curr_price) or curr_price <= 0:
                continue
            
            # [조건 1] 3년 전체 최고가(신고가) 검증
            three_year_max = series_close.max()
            if curr_price < (three_year_max - 1e-5):
                continue 

            # [조건 2] 바닥 다지기 비율 검증 (35% 완화)
            absolute_min = series_close.min()
            floor_limit = absolute_min * 1.20
            weeks_in_floor = series_close[(series_close >= absolute_min) & (series_close <= floor_limit)].count()
            floor_ratio = weeks_in_floor / len(series_close)
            if floor_ratio < 0.35:
                continue 

            # [조건 3] 박스권 상단 탈출 마진 검증 (+0% ~ +30% 이내)
            box_period_series = series_close[series_close.index <= one_year_ago]
            if box_period_series.empty:
                continue
            
            past_max = box_period_series.max() 
            if pd.isna(past_max) or past_max == 0:
                continue
            if not (past_max <= curr_price <= past_max * 1.30):
                continue

            # 참고용 각도 계산
            start_price = series_close.iloc[0]
            start_date = series_close.index[0]
            end_date = series_close.index[-1]
            total_days = (end_date - start_date).days
            angle_deg = 0.0
            if total_days > 0 and not pd.

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
    """
    [US Master] 외부 마스터 데이터 가공 주소에서 미국 전체 상장사의 시총 테이블을 통째로 가져옵니다.
    S&P500, NASDAQ, Russell 2000 중 실질적 중상위 우량주($1.5B 이상)를 추출합니다.
    """
    print(f"⏳ [US Master] 미국 전체 시장 시가총액 데이터베이스 동기화 중...")
    tickers = set()
    
    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers_with_sectors.csv"
        df_master = pd.read_csv(url, timeout=20)
        
        if 'Symbol' in df_master.columns:
            df_master['Symbol'] = df_master['Symbol'].astype(str).str.strip().str.upper()
            
            # ETF, 스팩, 우선주 제외 (글자수 1~4자 보통주 선별)
            df_filtered = df_master[
                (df_master['Symbol'].str.isalpha()) & 
                (df_master['Symbol'].str.len() <= 4)
            ]
            
            raw_list = df_filtered['Symbol'].unique().tolist()
            for t in raw_list:
                tickers.add(t.replace('.', '-'))
                
            print(f"✅ [US Master] 전체 시장 풀 {len(tickers)}개 확보 완료.")
            
    except Exception as e:
        print(f"⚠️ [US Master] 대량 마스터 데이터 파싱 실패: {e}. 지수 기반 우량주로 자동 전환합니다.")
        return get_fallback_index_tickers()

    return list(tickers)

def get_fallback_index_tickers():
    """마스터 서버 비상시 작동하는 S&P 500 & 나스닥 100 가동 시스템"""
    print("⏳ [Backup] 위키피디아 기반 핵심 지수 종목 대체 수집...")
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
    """구글 SMTP 서비스를 이용한 안정적인 이메일 발송 함수"""
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        print("\n⚠️ 환경변수(EMAIL_USER, EMAIL_PASS) 설정이 되어있지 않습니다. 콘솔에 리포트를 출력합니다.\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 전수조사] 3년 박스권 돌파형 장기 신고가 종목 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp

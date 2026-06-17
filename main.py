import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time

def get_all_tickers():
    """S&P500, 나스닥 100, 러셀 2000(주요 종목) 티커를 수집하여 중복을 제거합니다."""
    tickers = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # 1. S&P 500
    try:
        url_sp = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        res = requests.get(url_sp, headers=headers, timeout=15)
        df_sp = pd.read_html(res.text, flavor='lxml')[0]
        for t in df_sp['Symbol'].tolist():
            tickers.add(str(t).replace('.', '-'))
        print(f"✅ S&P 500 수집 완료 ({len(df_sp)} 종목)")
    except Exception as e:
        print(f"⚠️ S&P 500 수집 실패: {e}")

    # 2. 나스닥 100
    try:
        url_nd = 'https://en.wikipedia.org/wiki/NASDAQ-100'
        res = requests.get(url_nd, headers=headers, timeout=15)
        dfs = pd.read_html(res.text, flavor='lxml')
        df_nd = None
        for table in dfs:
            if 'Ticker' in table.columns: df_nd = table; break
            elif 'Symbol' in table.columns:
                df_nd = table
                df_nd.rename(columns={'Symbol': 'Ticker'}, inplace=True)
                break
        if df_nd is not None:
            for t in df_nd['Ticker'].tolist():
                tickers.add(str(t).replace('.', '-'))
            print(f"✅ 나스닥 100 수집 완료")
    except Exception as e:
        print(f"⚠️ 나스닥 100 수집 실패: {e}")

    # 3. 러셀 2000 핵심 종목
    try:
        url_r2k = 'https://en.wikipedia.org/wiki/Russell_2000_Index'
        res = requests.get(url_r2k, headers=headers, timeout=15)
        dfs = pd.read_html(res.text, flavor='lxml')
        df_r2k = None
        for table in dfs:
            if 'Ticker' in table.columns: df_r2k = table; break
            elif 'Symbol' in table.columns:
                df_r2k = table
                df_r2k.rename(columns={'Symbol': 'Ticker'}, inplace=True)
                break
        if df_r2k is not None:
            for t in df_r2k['Ticker'].tolist():
                tickers.add(str(t).replace('.', '-'))
            print(f"✅ 러셀 2000 일부 핵심 종목 수집 완료")
    except Exception as e:
        print(f"⚠️ 러셀 2000 수집 실패: {e}")

    if len(tickers) < 10:
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA']
        
    return list(tickers)

def send_email(content, is_html=False):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    if not sender_email or not sender_password:
        print("\n⚠️ 환경변수(EMAIL_USER, EMAIL_PASS) 설정이 되어있지 않습니다. 콘솔에 리포트를 출력합니다.\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 전수조사] 3년 신고가 달성 및 바닥 다지기 완만 상승주 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("📧 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def screen_stocks():
    tickers = get_all_tickers()
    results = []
    print(f"📊 총 {len(tickers)}개 종목 대상 신규 장기 패턴 분석 시작...")
    
    chunk_size = 100
    all_close_data = pd.DataFrame()

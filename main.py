import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        sp500 = pd.read_html(response.text)[0]
        return [t.replace('.', '-') for t in sp500['Symbol'].tolist()]
    except Exception as e:
        print(f"티커 목록 가져오기 실패: {e}")
        return []

def send_email(content, is_html=False):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    if not sender_email or not sender_password:
        print("환경변수 설정이 필요합니다.")
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"🎯 주도주 스캔 결과: {datetime.now().strftime('%Y-%m-%d')}"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("메일 발송 성공!")
    except Exception as e:
        print(f"메일 발송 실패: {e}")

def screen_stocks():
    tickers = get_sp500_tickers()
    if not tickers: return

    results = []
    print(f"데이터 분석 및 뉴스 스캐닝 시작... ({len(tickers)} 종목)")
    
    # 30주선 및 52주 신고가 계산을 위해 2년치 데이터
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    # 뉴스 분석 기준일 (최근 10주)
    ten_weeks_ago = datetime.now() - timedelta(days=70)
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps']

    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 지표 설정
            df['MA30'] = df['Close'].rolling(window=30).mean()
            df['High52'] = df['High'].rolling(window=52).max().shift(1) # 이번 주 제외 과거 52주 최고가

            curr = df.iloc[-1]
            recent_10w = df.iloc[-10:]
            recent_2w = df.iloc[-2:]

            # --- 로직 체크 준비 ---
            is_target = False
            strategy_name = ""
            
            # 조건 1: 최근 10주 내 (30주선 돌파 후 신고가 돌파) & 현재가가 신고가의 90% 위 & PER 30 이하
            #

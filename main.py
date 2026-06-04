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
    msg['Subject'] = f"🎯 주도주 전략 스캔 보고서: {datetime.now().strftime('%Y-%m-%d')}"
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
    print(f"데이터 분석 시작... ({len(tickers)} 종목)")
    
    # 지표 계산을 위해 2년치 주봉 데이터 다운로드
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    ten_weeks_ago = datetime.now() - timedelta(days=70)
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps', 'expansion']

    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 공통 지표 계산
            df['MA30'] = df['Close'].rolling(window=30).mean()
            df['High52'] = df['High'].rolling(window=52).max().shift(1)
            # 박스권 상단(최근 52주 고가)
            box_top = df['High52'].iloc[-1]

            curr_price = df['Close'].iloc[-1]
            recent_2w = df.iloc[-2:]
            recent_4w = df.iloc[-4:]
            recent_10w = df.iloc[-10:]

            is_target = False
            strategy_name = ""

            # Ticker 정보 및 PER 가져오기
            stock = yf.Ticker(ticker)
            try:
                fwd_pe = stock.info.get('forwardPE', 999)
            except:
                fwd_pe = 999

            # --- [전략 1] 30주선 돌파 + 신고가 돌파 후 안착 (PER 30) ---
            if fwd_pe <= 30:
                break_ma30 = any(recent_10w['Close'] > recent_10w['MA30'])
                break_high52 = any(recent_10w['High'] >= recent_10w['High52'])
                # 신고가 돌파 당시의 고점(박스권 상단) 대비 -20% ~ +20%
                if break_ma30 and break_high52:
                    if (box_top * 0.8) <= curr_price <= (box_top * 1.2):
                        is_target = True
                        strategy_name = "1.30주선+신고가 안착"

            # --- [전략 2]

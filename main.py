import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests

# 1. S&P 500 티커 리스트 가져오기
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

# 2. 이메일 발송 함수
def send_email(content, is_html=False):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    if not sender_email or not sender_password:
        print("환경변수 설정이 되어있지 않습니다.")
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📊 미주 스캔: 신고가 눌림목 및 30주선 돌파 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("메일 발송 성공!")
    except Exception as e:
        print(f"메일 발송 실패: {e}")

# 3. 메인 스캐닝 로직
def screen_stocks():
    tickers = get_sp500_tickers()
    if not tickers: return

    results = []
    print(f"데이터 분석 시작... (종목 수: {len(tickers)})")
    # 52주 및 30주 지표 계산을 위해 2년치 주봉 데이터 사용
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    one_month_ago = datetime.now() - timedelta(days=30)

    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 지표 계산
            df['MA30'] = df['Close'].rolling(window=30).mean()
            # 52주 신고가 (과거 52주 최고점)
            df['High52'] = df['High'].rolling(window=52).max().shift(1)

            curr_price = df['Close'].iloc[-1]
            
            # 최근 5주간의 데이터 추출
            recent_5w = df.iloc[-5:]
            
            is_target = False
            strategy_name = ""

            # --- 로직 1: 5주 내 52주 신고가 달성 후 조정 (신고가의 80%~100% 사이) ---
            recent_52wk_high = recent_5w['High'].max()
            past_52wk_high = df['High52'].iloc[-5:].max()
            
            if recent_52wk_high >= past_52wk_high: # 최근 5주 내 신고가 경신 이력 존재
                if recent_52wk_high * 0.8 <= curr_price < recent_52wk_high:
                    is_target = True
                    strategy_name = "1.신고가 눌림목(80%이상)"

            # --- 로직 2: 최근 5주 이내 30주봉 돌파 ---
            # (저번주 종가는 MA30 아래였으나, 이번주 종가가 MA30 위로 돌파 혹은 5주 내 돌파 발생)
            if not is_target:
                was_below = any(df['Close'].iloc[-10:-5] < df['MA30'].iloc[-10:-5]) # 과거에 아래에 있었음
                now_above = any(df['Close'].iloc[-5:] > df['MA30'].iloc[-5:])     # 최근 5주 내 위로 올라옴
                if was_below and now_above:
                    is_target = True
                    strategy_name = "2.최근 5주내 30주선 돌파"

            # --- 로직 3: 5주 내 30주선 돌파 후, 현재 30주선 대비 10% 이상 위 ---
            if not is_target or strategy_name == "2.최근 5주내 30주선 돌파":
                # 5주 내 돌파 이력이 있고 + 현재가가 MA30보다 10% 이상 높은 경우
                if any(df['Close'].iloc[-5:] > df['MA30'].iloc[-5:]) and curr_price >= (df['MA30'].iloc[-1] * 1.1):
                    is_target = True
                    strategy_name = "3.30주선 돌파 후 가속(10%+)"

            if is_target:
                stock = yf.Ticker(ticker)
                info =

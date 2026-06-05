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
        print("환경변수 설정이 되어있지 않습니다. 콘솔에 리포트를 출력합니다.")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"🚀 [박스권 돌파] 핵심 주도주 스캔 보고서 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("메일 발송 성공!")
    except Exception as e:
        print(f"메일 발송 실패: {e}")

def screen_stocks(min_gain=0.05, max_gain=0.30):
    tickers = get_sp500_tickers()
    if not tickers: return

    results = []
    print(f"박스권 돌파 모멘텀 분석 시작... ({len(tickers)} 종목)")
    print(f"설정된 필터 구간: 박스권 상단 대비 +{int(min_gain*100)}% ~ +{int(max_gain*100)}%")
    
    try:
        all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)
    except Exception as e:
        print(f"데이터 다운로드 중 치명적 오류: {e}")
        return

    ten_weeks_ago = datetime.now() - timedelta(days=70)
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps', 'expansion']

    for ticker in tickers:
        try:
            if ticker not in all_data.columns.levels[0]:
                continue
                
            df = all_data[ticker].dropna(subset=['Close']).copy()
            if len(df) < 55: 
                continue

            # 52주 신고가 라인 계산
            df['High52'] = df['High'].rolling(window=52).max().shift(1)
            
            box_top = df['High52'].iloc[-1]
            curr_price = df['Close'].iloc[-1]
            
            if pd.isna(box_top) or box_top == 0:
                continue

            recent_4w = df.iloc[-4:]
            is_target = False

            # 최근 4주 내 돌파 여부 확인
            box_break_recent = any(recent_4w['High'] >= recent_4w['High52'])
            
            if box_break_recent:
                if (box_top * (1 + min_gain)) <= curr_price <= (box_top * (1 + max_gain)):
                    is_target = True

            if is_target:
                stock = yf.Ticker(ticker)
                
                # 변수 기본값 설정
                trail_pe = 999
                fwd_pe = 999
                mkt_cap = 0
                short_name = 'N/A'
                
                try:
                    info = stock.info
                    trail_pe = info.get('trailingPE', 999)  # 💡 현재 PER 추출
                    fwd_pe = info.get('forwardPE', 999)     # 💡 12M 선행 PER 추출
                    mkt_cap = info.get('marketCap', 0)
                    short_name = info.get('shortName', 'N/A')
                except:
                    pass

                # 뉴스 스캔
                has_star = False
                try:
                    news_list = stock.news
                    if news_list:
                        for news in news_list:
                            pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                            if pub_time >= ten_weeks_ago:
                                content = (news.get('title', '') + news.get('summary', '')).lower()
                                if any(k in content for k in keywords):
                                    has_star = True
                                    break
                except: 
                    pass

                display_ticker = f"⭐ {ticker}" if has_star else ticker

                results.append({
                    'Ticker': display_ticker,
                    'Price': round(curr_price, 2),
                    'Box Top': round(box_top, 2),
                    'Gain from Box': f"+{round(((curr_price/box_top)-1)*100, 1)}%",
                    'Current PE': round(trail_pe, 2) if trail_pe != 999 else 'N/A',     # 💡 표에 추가
                    'Forward PE': round(fwd_pe, 2) if fwd_pe != 999 else 'N/A',         # 💡 표에 추가
                    'Market Cap($B)': round(mkt_cap / 1e9, 2),
                    'Name': short_name
                })
                print(f"✅ 발견: {ticker} (박스권 대비 {round(((curr_price/box_top)-1

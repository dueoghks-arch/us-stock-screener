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
        print("환경변수(EMAIL_USER, EMAIL_PASS)가 설정되지 않아 메일을 보내지 않습니다.")
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"🚀 미국 주식 스캔 결과 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email # 본인 수신

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
    
    # 30주선 및 52주 신고가 계산을 위해 2년치 주봉 데이터 다운로드
    print(f"S&P 500 데이터 분석 시작... (종목 수: {len(tickers)})")
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    one_month_ago = datetime.now() - timedelta(days=30)

    for ticker in tickers:
        try:
            # 개별 종목 데이터 추출 및 전처리
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 지표 계산
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA30'] = df['Close'].rolling(window=30).mean()
            # 52주 신고가 (이번 주를 제외한 지난 52주간의 최고가)
            df['High52'] = df['High'].rolling(window=52).max().shift(1)

            curr = df.iloc[-1]   # 이번 주
            prev1 = df.iloc[-2]  # 지난 주
            
            # 최근 10주 내 52주 신고가 돌파 이력이 있는지 확인
            def hit_52wk_high_within(n):
                recent = df.iloc[-n:]
                return any(recent['High'] >= recent['High52'])

            is_target = False
            strategy_name = ""

            # --- 핵심 전략 로직 ---
            # 공통: 30주 이평선 위에 종가가 위치할 것
            if curr['Close'] > curr['MA30']:
                
                # 전략 1: 이번 주 52주 신고가 돌파
                if curr['Close'] > curr['High52']:
                    is_target = True
                    strategy_name = "1.신고가 돌파"

                # 전략 2: 돌파 후 강세 유지 (10주 내 돌파 + MA5 위 + 지난주 종가 이상)
                elif hit_52wk_high_within(10) and curr['Close'] > curr['MA5'] and curr['Close'] >= prev1['Close']:
                    is_target = True
                    strategy_name = "2.돌파 후 강세유지"

                # 전략 3: 돌파 후 눌림목 (10주 내 돌파 + MA5 아래 MA20 위)
                elif hit_52wk_high_within(10) and curr['MA20'] < curr['Close'] < curr['MA5']:
                    is_target = True
                    strategy_name = "3.돌파 후 눌림목"

            # 필터링 통과 시 상세 데이터 확인
            if is_target:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                # 기본적 분석: PER 30 이하
                fwd_pe = info.get('forwardPE', 999)
                if fwd_pe > 30: continue

                # 뉴스 키워드 체크
                has_shortage = False
                for news in stock.news:
                    pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                    if pub_time >= one_month_ago:
                        news_text = (news.get('title', '') + news.get('summary', '')).lower()
                        if any(k in news_text for k in ['shortage', 'supply chain', 'lack of']):
                            has_shortage = True
                            break

                results.append({
                    'Ticker': ticker,
                    'Strategy': strategy_name,
                    'Price': round(curr['Close'], 2),
                    'Forward PE': round(fwd_pe, 2),
                    'Market Cap($B)': round(info.get('marketCap', 0) / 1e9, 2),
                    'Issue': "🌟 SHORTAGE" if has_shortage else "",
                    'Name': info.get('shortName', 'N/A')
                })
                print(f"✅ 발견: {ticker} ({strategy_name})")

        except:
            continue

    # 결과 리포트 생성 및 전송
    if results:
        final_df = pd.DataFrame(results).sort_values(by=['Strategy', 'Market Cap($B)'], ascending=[True, False])
        html_content = f"""
        <h3>🚀 미국 주식 스캔 결과 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p>전략 1: 신고가 돌파 / 전략 2: 강세 유지 / 전략 3: 눌림목 구간</p>
        {final_df.to_html(index=False, border=1, justify='center')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("금일 조건에 부합하는 종목이 없습니다.")
        print("조건 만족 종목 없음.")

if __name__ == "__main__":
    screen_stocks()

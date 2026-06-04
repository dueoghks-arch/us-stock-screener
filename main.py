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
        print("환경변수 설정이 되어있지 않습니다.")
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
    
    # 데이터 확보 (안전하게 2년치)
    try:
        all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)
    except Exception as e:
        print(f"데이터 다운로드 중 치명적 오류: {e}")
        return

    ten_weeks_ago = datetime.now() - timedelta(days=70)
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps', 'expansion']

    for ticker in tickers:
        try:
            # 1. 데이터 검증
            if ticker not in all_data or all_data[ticker].empty:
                continue
            
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 2. 지표 계산
            df['MA30'] = df['Close'].rolling(window=30).mean()
            df['High52'] = df['High'].rolling(window=52).max().shift(1)
            box_top = df['High52'].iloc[-1]

            curr_price = df['Close'].iloc[-1]
            recent_2w = df.iloc[-2:]
            recent_4w = df.iloc[-4:]
            recent_10w = df.iloc[-10:]

            is_target = False
            strategy_name = ""

            # 3. Ticker 정보 로드 (에러 방지용)
            stock = yf.Ticker(ticker)
            fwd_pe = 999
            try:
                info = stock.info
                fwd_pe = info.get('forwardPE', 999)
                mkt_cap = info.get('marketCap', 0)
                short_name = info.get('shortName', 'N/A')
            except:
                fwd_pe = 999
                mkt_cap = 0
                short_name = 'N/A'

            # --- [전략 1] 30주선 돌파 + 신고가 안착 (PER 30) ---
            if fwd_pe <= 30:
                break_ma30 = any(recent_10w['Close'] > recent_10w['MA30'])
                break_high52 = any(recent_10w['High'] >= recent_10w['High52'])
                if break_ma30 and break_high52:
                    if (box_top * 0.8) <= curr_price <= (box_top * 1.2):
                        is_target = True
                        strategy_name = "1.30주선+신고가 안착"

            # --- [전략 2] 최근 2주 신고가 (PER 40) ---
            if not is_target and fwd_pe <= 40:
                if any(recent_2w['High'] >= recent_2w['High52']):
                    is_target = True
                    strategy_name = "2.최근 2주 신고가"

            # --- [전략 3] 박스권 돌파 후 가속 (최근 4주) ---
            if not is_target:
                box_break_recent = any(recent_4w['High'] >= recent_4w['High52'])
                if box_break_recent:
                    if (box_top * 1.2) <= curr_price <= (box_top * 1.5):
                        is_target = True
                        strategy_name = "3.박스권 돌파 가속"

            # 4. 타겟 종목 분석
            if is_target:
                has_star = False
                try:
                    news_list = stock.news
                    if news_list:
                        for news in news_list:
                            pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                            if pub_time >= ten_weeks_ago:
                                content = (news.get('title', '') + news.get('summary', '')).lower()
                                if any(k in content for k in keywords):
                                    has_star = True; break
                except: pass

                display_ticker = f"⭐ {ticker}" if has_star else ticker
                results.append({
                    'Ticker': display_ticker,
                    'Strategy': strategy_name,
                    'Price': round(curr_price, 2),
                    'Forward PE': round(fwd_pe, 2),
                    'Market Cap($B)': round(mkt_cap / 1e9, 2),
                    'Name': short_name
                })
                print(f"✅ 발견: {ticker}")

        except Exception as e:
            print(f"오류 ({ticker}): {e}")
            continue

    # 5. 결과 보고 및 전송
    if results:
        final_df = pd.DataFrame(results).sort_values(by=['Strategy', 'Market Cap($B)'], ascending=[True, False])
        html_content = f"""
        <h3 style="color: #1a237e;">🔥 미국 주식 전략 통합 스캔 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p>⭐ 표시: 공급부족, 실적 호재 등 뉴스 발견(최근 10주)</p>
        {final_df.to_html(index=False, border=1, justify='center').replace('⭐', '<span style="color:blue; font-weight:bold;">⭐</span>')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("부합하는 종목이 없습니다.")

if __name__ == "__main__":
    screen_stocks()

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
    msg['Subject'] = f"📊 미주 핵심 기업 스캔: 차트 돌파 + 호재 뉴스 ({datetime.now().strftime('%Y-%m-%d')})"
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
    print(f"데이터 분석 및 뉴스 스캐닝 시작... (종목 수: {len(tickers)})")
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    # 최근 10주간의 뉴스를 분석하기 위한 기준일 (약 70일)
    ten_weeks_ago = datetime.now() - timedelta(days=70)

    # 분석할 키워드 그룹
    keywords = {
        'SHORTAGE': ['shortage', 'lack of', 'supply chain', 'tight supply', 'backlog'],
        'EXPANSION': ['expansion', 'capacity', 'new factory', 'facility', 'ramping up', 'capex'],
        'GROWTH': ['strong growth', 'robust demand', 'record revenue', 'exceeding expectations', 'guidance raise']
    }

    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            df['MA30'] = df['Close'].rolling(window=30).mean()
            df['High52'] = df['High'].rolling(window=52).max().shift(1)
            curr_price = df['Close'].iloc[-1]
            recent_5w = df.iloc[-5:]
            
            is_target = False
            strategy_name = ""

            # --- [기술적 로직 3종] ---
            recent_52wk_high = recent_5w['High'].max()
            past_52wk_high = df['High52'].iloc[-5:].max()
            
            # 1. 5주 내 신고가 경신 후 눌림
            if recent_52wk_high >= past_52wk_high and (recent_52wk_high * 0.8 <= curr_price < recent_52wk_high):
                is_target = True
                strategy_name = "1.신고가 눌림목"
            # 2. 최근 5주 내 30주선 돌파
            elif any(df['Close'].iloc[-10:-5] < df['MA30'].iloc[-10:-5]) and any(df['Close'].iloc[-5:] > df['MA30'].iloc[-5:]):
                is_target = True
                strategy_name = "2.30주선 돌파"
            # 3. 30주선 돌파 후 10% 이상 가속
            elif any(df['Close'].iloc[-5:] > df['MA30'].iloc[-5:]) and curr_price >= (df['MA30'].iloc[-1] * 1.1):
                is_target = True
                strategy_name = "3.30주선 돌파 가속"

            # 차트 조건 통과 시 뉴스 분석 진행
            if is_target:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                # 기본 필터: PER 30 이하
                fwd_pe = info.get('forwardPE', 999)
                if fwd_pe > 30: continue

                # 뉴스 스캐닝 (최근 10주)
                found_issues = []
                try:
                    for news in stock.news:
                        pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                        if pub_time >= ten_weeks_ago:
                            content = (news.get('title', '') + news.get('summary', '')).lower()
                            for category, k-list in keywords.items():
                                if any(k in content for k in k-list):
                                    if category not in found_issues:
                                        found_issues.append(category)
                except: pass

                issue_tag = ", ".join(found_issues) if found_issues else ""
                display_ticker = f"🔥 {ticker}" if found_issues else ticker

                results.append({
                    'Ticker': display_ticker,
                    'Strategy': strategy_name,
                    'Price': round(curr_price, 2),
                    'Forward PE': round(fwd_pe, 2),
                    'Market Cap($B)': round(info.get('marketCap', 0) / 1e9, 2),
                    'Hot Issue': issue_tag,
                    'Name': info.get('shortName', 'N/A')
                })
                print(f"✅ 발견: {ticker} | 이슈: {issue_tag}")

        except:
            continue

    if results:
        final_df = pd.DataFrame(results).sort_values(by=['Hot Issue', 'Market Cap($B)'], ascending=[False, False])
        html_content = f"""
        <h3 style="color: #2e7d32;">🚀 미국 주식 전략 & 모멘텀 스캔 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p><b>🔥 표시:</b> 최근 10주 내 공급부족, 설비확장, 강한성장 뉴스 존재</p>
        <p style="font-size: 0.9em; color: #555;">전략 1: 신고가 눌림목 | 전략 2: 30주선 돌파 | 전략 3: 30주선 돌파 후 10%+ 상승</p>
        {final_df.to_html(index=False, border=1, justify='center').replace('🔥', '<span style="color:red;">🔥</span>')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("조건에 맞는 기업이 없습니다.")

if __name__ == "__main__":
    screen_stocks()

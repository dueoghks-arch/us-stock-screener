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
        print("환경변수(EMAIL_USER, EMAIL_PASS) 설정이 필요합니다.")
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"🚀 [미주 스캔] 52주 신고가 추세 유지주 ({datetime.now().strftime('%Y-%m-%d')})"
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
    
    # 52주 지표 계산을 위해 안전하게 2년치(2y) 데이터 다운로드
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    # 최근 10주간의 뉴스를 분석하기 위한 기준일
    ten_weeks_ago = datetime.now() - timedelta(days=70)

    # 뉴스 키워드 그룹 정의
    keywords = {
        'SHORTAGE': ['shortage', 'lack of', 'supply chain', 'tight supply', 'backlog'],
        'EXPANSION': ['expansion', 'capacity', 'new factory', 'facility', 'ramping up', 'capex'],
        'GROWTH': ['strong growth', 'robust demand', 'record revenue', 'exceeding expectations', 'guidance raise']
    }

    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 지표 계산: 5주 주봉 이평선 및 과거 52주 신고가(이번 주 제외한 shift(1))
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['High52'] = df['High'].rolling(window=52).max().shift(1)

            curr_price = df['Close'].iloc[-1]
            curr_ma5 = df['MA5'].iloc[-1]
            
            # 1. 최근 10주간 데이터 추출하여 52주 신고가 달성 이력이 있는지 확인
            # (최근 10주간의 주봉 High가 당시의 High52를 한 번이라도 터치하거나 넘겼는지 체크)
            recent_10w = df.iloc[-10:]
            hit_52wk_recently = any(recent_10w['High'] >= recent_10w['High52'])
            
            # 2. 현재 가격이 5주봉 이평선보다 위에 있는지 확인
            above_ma5 = curr_price > curr_ma5

            # 단일 조건 판별
            if hit_52wk_recently and above_ma5:
                stock = yf.Ticker(ticker)
                
                # 기본 필터: PER 30 이하
                fwd_pe = stock.info.get('forwardPE', 999)
                if fwd_pe > 30: continue

                # 뉴스 스캔 (최근 10주)
                found_issues = []
                try:
                    for news in stock.news:
                        pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                        if pub_time >= ten_weeks_ago:
                            content = (news.get('title', '') + news.get('summary', '')).lower()
                            for category, k_list in keywords.items():
                                if any(k in content for k in k_list):
                                    if category not in found_issues:
                                        found_issues.append(category)
                except: pass

                issue_tag = ", ".join(found_issues) if found_issues else ""
                display_ticker = f"🔥 {ticker}" if found_issues else ticker

                results.append({
                    'Ticker': display_ticker,
                    'Price': round(curr_price, 2),
                    '5주선(MA5)': round(curr_ma5, 2),
                    'Forward PE': round(fwd_pe, 2),
                    'Market Cap($B)': round(stock.info.get('marketCap', 0) / 1e9, 2),
                    'Hot Issue': issue_tag,
                    'Name': stock.info.get('shortName', 'N/A')
                })
                print(f"✅ 발견: {ticker} (이슈: {issue_tag if issue_tag else '없음'})")

        except:
            continue

    if results:
        # 핫 이슈(호재 기사)가 있는 종목이 리스트 상단에 오도록 정렬
        final_df = pd.DataFrame(results).sort_values(by=['Hot Issue', 'Market Cap($B)'], ascending=[False, False])
        html_content = f"""
        <h3 style="color: #1565c0;">🚀 미국 주식 단일 전략 스캔 결과 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p><b>필터 조건:</b> 최근 10주 내 52주 신고가 달성 후 현재 가격이 5주봉 이평선(MA5) 위에 안착한 기업 (PER 30 이하)</p>
        <p><b>🔥 표시:</b> 최근 10주 내 공급부족(Shortage), 설비확장(Expansion), 강한성장(Growth) 관련 뉴스 발견</p>
        {final_df.to_html(index=False, border=1, justify='center').replace('🔥', '<span style="color:red;">🔥</span>')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("조건에 부합하는 주도주가 오늘 장에는 없습니다.")

if __name__ == "__main__":
    screen_stocks()

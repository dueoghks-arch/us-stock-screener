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

def screen_stocks():
    tickers = get_sp500_tickers()
    if not tickers: return

    results = []
    print(f"박스권 돌파 모멘텀 분석 시작... ({len(tickers)} 종목)")
    
    # 52주 고가 및 박스권 계산을 위해 2년치 데이터 다운로드
    try:
        all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)
    except Exception as e:
        print(f"데이터 다운로드 중 치명적 오류: {e}")
        return

    ten_weeks_ago = datetime.now() - timedelta(days=70)
    # 공급 부족 및 실적 가이던스 관련 핵심 호재 키워드
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps', 'expansion']

    for ticker in tickers:
        try:
            # 데이터 기본 검증
            if ticker not in all_data or all_data[ticker].empty:
                continue
            
            df = all_data[ticker].dropna()
            if len(df) < 55: continue

            # 52주 신고가 라인 계산 (이번 주 제외 과거 52주 고가의 최댓값 = 박스권 상단)
            df['High52'] = df['High'].rolling(window=52).max().shift(1)
            box_top = df['High52'].iloc[-1]

            curr_price = df['Close'].iloc[-1]
            recent_4w = df.iloc[-4:]

            is_target = False

            # --- [단일 전략] 52주 박스권을 최근 4주 내 돌파 후 가속 (+20% ~ +50%) ---
            # 최근 4주 동안의 주봉 고가 중 한 번이라도 이전 52주 박스권 상단을 뚫었는지 확인
            box_break_recent = any(recent_4w['High'] >= recent_4w['High52'])
            
            if box_break_recent:
                # 현재 가격이 돌파 기준선(box_top)보다 +20% 위, +50% 아래에 위치하는지 검증
                if (box_top * 1.20) <= curr_price <= (box_top * 1.50):
                    is_target = True

            # 조건 만족 시에만 무거운 뉴스 및 기업 정보 가져오기
            if is_target:
                stock = yf.Ticker(ticker)
                
                # 기본 정보 안전하게 추출
                fwd_pe = 999
                mkt_cap = 0
                short_name = 'N/A'
                try:
                    info = stock.info
                    fwd_pe = info.get('forwardPE', 999)
                    mkt_cap = info.get('marketCap', 0)
                    short_name = info.get('shortName', 'N/A')
                except:
                    pass

                # 최근 10주 내 호재 뉴스 스캔 (⭐ 별표 로직)
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
                    'Forward PE': round(fwd_pe, 2) if fwd_pe != 999 else 'N/A',
                    'Market Cap($B)': round(mkt_cap / 1e9, 2),
                    'Name': short_name
                })
                print(f"✅ 발견: {ticker}")

        except Exception as e:
            # 특정 종목 오류 시 멈추지 않고 패스
            continue

    # 결과 리포트 빌드 및 전송
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        html_content = f"""
        <h3 style="color: #0d47a1;">🔥 미주 52주 박스권 돌파 후 가속주 리포트 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p><b>필터 조건:</b> 최근 4주 내 52주 박스권 상단을 돌파하고, 현재 주가가 돌파선 대비 <b>+20% ~ +50%</b> 구간에 위치한 강세 종목</p>
        <p><b>⭐ 표시:</b> 최근 10주 내 공급 부족(Shortage), EPS/가이던스 상회 등 확실한 업황/실적 호재가 포착된 기업</p>
        <br>
        {final_df.to_html(index=False, border=1, justify='center').replace('⭐', '<span style="color:blue; font-weight:bold;">⭐</span>')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("현재 박스권을 돌파하여 가속 구간(+20%~+50%)에 진입한 종목이 없습니다.")

if __name__ == "__main__":
    screen_stocks()

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
    
    # 2년치 데이터 다운로드
    all_data = yf.download(tickers, period="2y", interval="1wk", group_by='ticker', threads=True)

    ten_weeks_ago = datetime.now() - timedelta(days=70)
    # 호재 키워드 리스트
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps']

    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 52: continue

            # 이동평균 및 신고가 계산
            df['MA30'] = df['Close'].rolling(window=30).mean()
            df['High52'] = df['High'].rolling(window=52).max().shift(1)

            curr = df.iloc[-1]
            recent_10w = df.iloc[-10:]
            recent_2w = df.iloc[-2:]

            is_target = False
            strategy_name = ""
            
            # --- Ticker 객체 미리 생성 (정보 확인용) ---
            stock = yf.Ticker(ticker)
            
            # 12개월 선행 PER 확인 (에러 방지용 기본값 999)
            try:
                fwd_pe = stock.info.get('forwardPE', 999)
            except:
                fwd_pe = 999

            # --- 조건 1 판별 ---
            max_high_10w = recent_10w['High'].max()
            cond1_tech = any(recent_10w['Close'] > recent_10w['MA30']) and \
                         any(recent_10w['High'] >= recent_10w['High52']) and \
                         (curr['Close'] >= (max_high_10w * 0.9))
            
            if cond1_tech and fwd_pe <= 30:
                is_target = True
                strategy_name = "1.30주선+신고가(PER30)"
            
            # --- 조건 2 판별 (1번이 아닐 경우) ---
            elif any(recent_2w['High'] >= recent_2w['High52']) and fwd_pe <= 40:
                is_target = True
                strategy_name = "2.최근 2주 신고가(PER40)"

            if is_target:
                # 뉴스 분석
                has_star = False
                try:
                    for news in stock.news:
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
                    'Strategy': strategy_name,
                    'Price': round(curr['Close'], 2),
                    'Forward PE': round(fwd_pe, 2),
                    'Market Cap($B)': round(stock.info.get('marketCap', 0) / 1e9, 2) if stock.info.get('marketCap') else 0,
                    'Name': stock.info.get('shortName', 'N/A')
                })
                print(f"✅ 발견: {ticker}")

        except Exception as e:
            # 개별 종목 에러는 무시하고 다음 종목으로 진행
            continue

    if results:
        final_df = pd.DataFrame(results).sort_values(by=['Strategy', 'Market Cap($B)'], ascending=[True, False])
        html_content = f"""
        <h3 style="color: #d32f2f;">🔥 미국 주식 핵심 주도주 스캔 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p><b>⭐ 표시:</b> 공급 부족, 가이던스 상회 등 핵심 호재 뉴스 발견(최근 10주)</p>
        <div style="border-left: 4px solid #ccc; padding-left: 10px; font-size: 0.9em;">
            <b>전략 1:</b> 10주 내 30주선 돌파 & 신고가 경신, 현재가 고점 대비 -10% 이내 (PER 30 이하)<br>
            <b>전략 2:</b> 최근 2주 내 52주 신고가 돌파 (PER 40 이하)
        </div><br>
        {final_df.to_html(index=False, border=1, justify='center').replace('⭐', '<span style="color:blue; font-weight:bold;">⭐</span>')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("부합하는 종목이 없습니다.")

if __name__ == "__main__":
    screen_stocks()

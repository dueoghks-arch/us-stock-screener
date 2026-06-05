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
    """
    min_gain & max_gain: 박스권 상단 돌파 후 현재 주가의 허용 상승률 구간
    - 기본값 (0.05 ~ 0.30): 돌파 초입 및 안정적 추세 가속 구간 (+5% ~ +30%)
    - 기존값 (0.20 ~ 0.50): 초강세 모멘텀 가속 구간 (+20% ~ +50%)
    """
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

            # 52주 신고가 라인 계산 (이번 주 제외 과거 52주 고가의 최댓값)
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
                # 💡 팁 적용: 파라미터 기반 유연한 구간 검증
                if (box_top * (1 + min_gain)) <= curr_price <= (box_top * (1 + max_gain)):
                    is_target = True

            if is_target:
                stock = yf.Ticker(ticker)
                
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
                    'Forward PE': round(fwd_pe, 2) if fwd_pe != 999 else 'N/A',
                    'Market Cap($B)': round(mkt_cap / 1e9, 2),
                    'Name': short_name
                })
                print(f"✅ 발견: {ticker} (박스권 대비 {round(((curr_price/box_top)-1)*100, 1)}% 상승)")

        except Exception as e:
            continue

    # 결과 리포트 빌드 및 전송
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        html_content = f"""
        <h3 style="color: #0d47a1;">🔥 미주 52주 박스권 돌파 주도주 리포트 ({datetime.now().strftime('%Y-%m-%d')})</h3>
        <p><b>필터 조건:</b> 최근 4주 내 52주 박스권 상단을 돌파하고, 현재 주가가 돌파선 대비 <b>+{int(min_gain*100)}% ~ +{int(max_gain*100)}%</b> 구간에 위치한 강세 종목</p>
        <p><b>⭐ 표시:</b> 최근 10주 내 공급 부족(Shortage), EPS/가이던스 상회 등 확실한 업황/실적 호재가 포착된 기업</p>
        <br>
        {final_df.to_html(index=False, border=1, justify='center').replace('⭐', '<span style="color:blue; font-weight:bold;">⭐</span>')}
        """
        send_email(html_content, is_html=True)
    else:
        send_email(f"현재 박스권을 돌파하여 설정 구간(+{int(min_gain*100)}%~+{int(max_gain*100)}%)에 진입한 종목이 없습니다.")

if __name__ == "__main__":
    # 💡 팁대로 돌파 초입~안정적 가속 구간을 잡고 싶다면 기본값 그대로 실행 (+5% ~ +30%)
    screen_stocks(min_gain=0.05, max_gain=0.30)
    
    # 만약 예전처럼 완전히 날아가는 초강세 모멘텀 종목만 골라내고 싶다면 아래처럼 변경 가능
    # screen_stocks(min_gain=0.20, max_gain=0.50)

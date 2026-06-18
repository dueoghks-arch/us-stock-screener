import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time
import io

# 위키피디아 크롤링 시 봇(Bot) 차단을 막기 위한 브라우저 위장 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def fetch_wiki_tickers(url, index_name):
    """위키피디아에서 지수 편입 종목을 안전하게 추출합니다."""
    tickers = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        dfs = pd.read_html(io.StringIO(res.text), flavor='lxml')
        
        for df in dfs:
            # 테이블의 컬럼명을 대문자로 변환하여 일치 검사
            col_upper = [str(c).upper().strip() for c in df.columns]
            for c in col_upper:
                if 'SYMBOL' in c or 'TICKER' in c:
                    df.columns = col_upper
                    raw_tickers = df[c].dropna().astype(str).tolist()
                    # 주식 심볼 정제 (BRK.B -> BRK-B) 및 이상한 값 제거
                    for t in raw_tickers:
                        clean_t = t.strip().upper().replace('.', '-')
                        if 1 <= len(clean_t) <= 5 and clean_t.isalpha() or '-' in clean_t:
                            tickers.add(clean_t)
                    return tickers
        print(f"⚠️ [{index_name}] 테이블에서 심볼 컬럼을 찾지 못했습니다.")
    except Exception as e:
        print(f"⚠️ [{index_name}] 수집 실패: {e}")
    return tickers

def get_master_universe():
    """S&P 500, 나스닥 100, S&P 400(중형주)를 조합하여 최정예 유니버스를 생성합니다."""
    print("⏳ [Data] 미국 핵심 우량주 유니버스(대형/중형) 동기화 중...")
    
    sp500 = fetch_wiki_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "S&P 500")
    print(f"✅ S&P 500 확보: {len(sp500)}개")
    
    nasdaq100 = fetch_wiki_tickers("https://en.wikipedia.org/wiki/Nasdaq-100", "Nasdaq 100")
    print(f"✅ Nasdaq 100 확보: {len(nasdaq100)}개")
    
    sp400_mid = fetch_wiki_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "S&P 400 MidCap")
    print(f"✅ S&P 400 (중형주/러셀대체) 확보: {len(sp400_mid)}개")
    
    # 중복을 제거한 최종 마스터 풀 생성
    master_pool = list(sp500 | nasdaq100 | sp400_mid)
    
    if len(master_pool) < 100:
        print("⚠️ [Warning] 크롤링 이슈로 백업 대장주 모드를 가동합니다.")
        return ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'BRK-B', 'AVGO', 'JPM']
        
    return master_pool

def send_email(content, is_html=False):
    """결과를 이메일로 발송합니다."""
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        print("\n⚠️ 이메일 환경변수 미비. 콘솔에 출력합니다:\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 스캐너] 주봉 트리플 AND 돌파형 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        print("⏳ [SMTP] 메일 서버 연결 및 발송 중...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls() 
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, sender_email, msg.as_string())
        server.quit()
        print("📧 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def screen_stocks():
    tickers = get_master_universe()
    results = []
    chunk_size = 100 # 야후 서버 차단 방지
    all_close_data = pd.DataFrame()
    
    print(f"\n📊 총 {len(tickers)}개 우량주 대상 주봉 데이터 다운로드 시작...")
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            data = yf.download(chunk, period="5y", interval="1wk", progress=False, timeout=30)
            if not data.empty and 'Close' in data.columns:
                close_data = data['Close']
                # 단일 종목일 경우 Series로 반환되므로 DataFrame으로 형변환
                if isinstance(close_data, pd.Series):
                    close_data = close_data.to_frame(name=chunk[0])
                    
                if all_close_data.empty:
                    all_close_data = close_data
                else:
                    all_close_data = pd.concat([all_close_data, close_data], axis=1)
            
            print(f"  > ⏳ 다운로드 진행률: {min(i + chunk_size, len(tickers))} / {len(tickers)}...")
            time.sleep(2) # 서버 차단 회피용 딜레이
        except Exception as e:
            continue

    if all_close_data.empty:
        print("❌ 주가 데이터를 가져오지 못했습니다.")
        return

    # 시간대(Timezone) 정보 제거
    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    print("\n🔍 [스캔 연산] 이동평균선 돌파 및 52주 신고가 연산 중...")
    
    for ticker in all_close_data.columns:
        try:
            series = all_close_data[ticker].dropna()
            # 200주 이평선을 위해 최소 200개 이상의 주봉 데이터 필요
            if len(series) <= 200:
                continue
                
            curr_price = series.iloc[-1]
            if curr_price < 5:  # 5달러 미만 동전주 안전 차단
                continue

            # 이평선 계산
            ma5 = series.rolling(window=5).mean()
            ma30 = series.rolling(window=30).mean()
            ma200 = series.rolling(window=200).mean()
            
            curr_ma5 = ma5.iloc[-1]
            curr_ma30 = ma30.iloc[-1]
            curr_ma200 = ma200.iloc[-1]
            
            high_52w = series.iloc[-52:].max()

            # [조건 1] 5주 이평선이 30주 혹은 200주를 돌파(Cross)하거나 10% 내 근접
            cross_5_30 = (ma5 > ma30) & (ma5.shift(1) <= ma30.shift(1))
            cross_5_200 = (ma5 > ma200) & (ma5.shift(1) <= ma200.shift(1))
            prox_5_30 = (abs(ma5 - ma30) / series) <= 0.10
            prox_5_200 = (abs(ma5 - ma200) / series) <= 0.10
            
            cond1_30 = cross_5_30 | prox_5_30
            cond1_200 = cross_5_200 | prox_5_200
            cond1 = cond1_30.iloc[-8:].any() or cond1_200.iloc[-8:].any()

            # [조건 2] 최근 26주 내 30주선이 200주선 골든크로스 돌파
            cross_30_200 = (ma30 > ma200) & (ma30.shift(1) <= ma200.shift(1))
            cond2 = cross_30_200.iloc[-26:].any()
            
            # [조건 3] 52주 신고가
            cond3 = (curr_price >= high_52w)

            # 최종 세 가지 AND 연산
            if not (cond1 and cond2 and cond3): 
                continue

            results.append({
                'Ticker': ticker,
                'Price($)': round(curr_price, 2),
                '52W High($)': round(high_52w, 2),
                '5W SMA': round(curr_ma5, 2),
                '30W SMA': round(curr_ma30, 2),
                '200W SMA': round(curr_ma200, 2)
            })
            print(f"🎯 [포착] 조건 만족 종목 발견: {ticker}")

        except Exception:
            continue

    today_str = datetime.now().strftime('%Y-%m-%d')
    if results:
        df_res = pd.DataFrame(results)
        table_html = df_res.to_html(index=False, border=1, justify='center')
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center; font-size: 14px;" border="1"')
        
        html_body = f"""
        <h3 style="color: #0d47a1;">📈 미주 우량주 주봉 트리플 AND 스캔 ({today_str})</h3>
        <p><b>유니버스:</b> S&P 500, 나스닥 100, S&P 400 (우량 대/중형주)</p>
        <div style="background-color: #f5f5f5; padding: 15px; margin-bottom: 20px;">
            <p style="margin: 0;"><b>[로직 (AND)]</b><br>
            1. 최근 8주 내 5주선이 30/200주선 상향돌파 또는 10% 초근접<br>
            2. 최근 6개월 내 30주선이 200주선 상향돌파<br>
            3. 현재가 52주 신고가 달성</p>
        </div>
        {styled_table}
        """
        send_email(html_body, is_html=True)
    else:
        html_body = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 알림 ({today_str})</h3>
        <p>현재 위 3가지 조건을 모두 만족하는 종목이 포착되지 않았습니다.</p>
        """
        send_email(html_body, is_html=True)

if __name__ == "__main__":
    screen_stocks()

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time

def get_all_tickers():
    """S&P500, 나스닥 100, 러셀 2000 주요 종목 티커 수집 및 중복 제거"""
    tickers = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # 1. S&P 500
    try:
        url_sp = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        res = requests.get(url_sp, headers=headers, timeout=15)
        df_sp = pd.read_html(res.text, flavor='lxml')[0]
        for t in df_sp['Symbol'].tolist():
            tickers.add(str(t).replace('.', '-'))
        print(f"✅ S&P 500 수집 완료 ({len(df_sp)} 종목)")
    except Exception as e:
        print(f"⚠️ S&P 500 수집 실패: {e}")

    # 2. 나스닥 100
    try:
        url_nd = 'https://en.wikipedia.org/wiki/NASDAQ-100'
        res = requests.get(url_nd, headers=headers, timeout=15)
        dfs = pd.read_html(res.text, flavor='lxml')
        df_nd = None
        for table in dfs:
            if 'Ticker' in table.columns: df_nd = table; break
            elif 'Symbol' in table.columns:
                df_nd = table
                df_nd.rename(columns={'Symbol': 'Ticker'}, inplace=True)
                break
        if df_nd is not None:
            for t in df_nd['Ticker'].tolist():
                tickers.add(str(t).replace('.', '-'))
            print(f"✅ 나스닥 100 수집 완료")
    except Exception as e:
        print(f"⚠️ 나스닥 100 수집 실패: {e}")

    # 3. 러셀 2000 핵심 종목
    try:
        url_r2k = 'https://en.wikipedia.org/wiki/Russell_2000_Index'
        res = requests.get(url_r2k, headers=headers, timeout=15)
        dfs = pd.read_html(res.text, flavor='lxml')
        df_r2k = None
        for table in dfs:
            if 'Ticker' in table.columns: df_r2k = table; break
            elif 'Symbol' in table.columns:
                df_r2k = table
                df_r2k.rename(columns={'Symbol': 'Ticker'}, inplace=True)
                break
        if df_r2k is not None:
            for t in df_r2k['Ticker'].tolist():
                tickers.add(str(t).replace('.', '-'))
            print(f"✅ 러셀 2000 일부 핵심 종목 수집 완료")
    except Exception as e:
        print(f"⚠️ 러셀 2000 수집 실패: {e}")

    if len(tickers) < 10:
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA']
        
    return list(tickers)

def send_email(content, is_html=False):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    if not sender_email or not sender_password:
        print("\n⚠️ 환경변수(EMAIL_USER, EMAIL_PASS) 설정이 되어있지 않습니다. 콘솔에 리포트를 출력합니다.\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 전수조사] 3년 박스권 돌파형 신고가 및 완만 상승주 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("📧 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def screen_stocks():
    tickers = get_all_tickers()
    results = []
    print(f"📊 총 {len(tickers)}개 종목 대상 신규 장기 패턴 분석 시작...")
    
    chunk_size = 100
    all_close_data = pd.DataFrame()
    
    print("⏳ 데이터 다운로드 중...")
    for i in range(0, len(tickers), chunk_size):
        chunk_tickers = tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="3y", interval="1wk", progress=False, timeout=30)
            if not chunk_data.empty and 'Close' in chunk_data.columns:
                chunk_close = chunk_data['Close']
                if all_close_data.empty:
                    all_close_data = chunk_close
                else:
                    all_close_data = pd.concat([all_close_data, chunk_close], axis=1)
            print(f"  > ⏳ {min(i + chunk_size, len(tickers))} / {len(tickers)} 종목 완료...")
            time.sleep(1.5) 
        except Exception as e:
            print(f"⚠️ 청크 다운로드 중 오류 발생: {e}")
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 데이터가 없습니다.")
        return

    # 💡 깃허브 액션 및 내부 연산 시 타임존 에러 예방
    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    print("🔍 6대 조건 정밀 스캔 진행 중...")
    for ticker in all_close_data.columns:
        try:
            series_close = all_close_data[ticker].dropna()
            if len(series_close) < 100: continue 
            
            curr_price = series_close.iloc[-1]
            if pd.isna(curr_price) or curr_price <= 0: continue
            
            # 💡 [추가 조건] 이번 주 종가가 최근 3년(전체 기간) 최고가인가? (신고가 필터)
            three_year_max = series_close.max()
            # 소수점 오차 감안하여 현재가가 최고가 이상이거나 거의 근접해야 함
            if curr_price < (three_year_max - 1e-5): continue 

            # 💡 조건 3: 최저가와 [최저가 + 20%] 사이 구간이 전체 중 50% 이상 존재해야 함 (하방 경직성)
            absolute_min = series_close.min()
            floor_limit = absolute_min * 1.20
            weeks_in_floor = series_close[(series_close >= absolute_min) & (series_close <= floor_limit)].count()
            floor_ratio = weeks_in_floor / len(series_close)
            
            if floor_ratio < 0.50: continue 

            # 💡 조건 4: 3년 전 ~ 1년 전 DATA의 최고가 대비 현재가가 +0% ~ +30% 이내인가?
            # (바닥 박스권을 돌파하되 오버슈팅 없이 이제 막 대가리를 든 녀석을 잡는 핵심 로직)
            box_period_series = series_close[series_close.index <= one_year_ago]
            if box_period_series.empty: continue
            
            past_max = box_period_series.max() 
            if pd.isna(past_max) or past_max == 0: continue
            
            if not (past_max <= curr_price <= past_max * 1.30): continue

            # 💡 조건 5: 3년 전 가격과 현재가의 기하학적 기울기가 45도 이하여야 함
            start_price = series_close.iloc[0]
            start_date = series_close.index[0]
            end_date = series_close.index[-1]
            
            total_days = (end_date - start_date).days
            if total_days <= 0 or pd.isna(start_price) or start_price == 0: continue
            
            total_gain_ratio = (curr_price - start_price) / start_price
            slope = (total_gain_ratio) / (total_days / 1095.0)
            angle_rad = np.arctan(slope)
            angle_deg = np.degrees(angle_rad)
            
            if angle_deg > 45 or angle_deg < -45: continue 

            # 조건 통과 시 개별 정보 수집
            stock = yf.Ticker(ticker)
            trail_pe, fwd_pe, mkt_cap, short_name = 'N/A', 'N/A', 0, 'N/A'
            try:
                info = stock.info
                trail_pe = round(info.get('trailingPE'), 2) if info.get('trailingPE') else 'N/A'
                fwd_pe = round(info.get('forwardPE'), 2) if info.get('forwardPE') else 'N/A'
                mkt_cap = info.get('marketCap', 0)
                short_name = info.get('shortName', ticker)
            except:
                short_name = ticker

            results.append({
                'Ticker': ticker,
                'Name': short_name,
                'Price($)': round(curr_price, 2),
                '3Y Max($)': round(three_year_max, 2),
                'Floor Ratio': f"{round(floor_ratio * 100, 1)}%",
                'Trend Angle': f"{round(angle_deg, 1)}°",
                'Current PE': trail_pe,
                'Forward PE': fwd_pe,
                'Market Cap($B)': round(mkt_cap / 1e9, 2) if mkt_cap else 0
            })
            print(f"🎯 3년 신고가 박스권 돌파 종포착: {ticker} (바닥밀집: {round(floor_ratio * 100, 1)}%, 기울기: {round(angle_deg, 1)}°)")

        except Exception as e:
            print(f"⚠️ {ticker} 종목 처리 중 오류: {e}")
            continue

    # 리포트 발송
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center', classes='dataframe')
        
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center;" border="1"')
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        html_content = f"""
        <h3 style="color: #1b5e20;">📈 미주 3년 신고가 돌파 초기형 완만 상승주 검색 보고서 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P500, NASDAQ 100, Russell 2000 주요 기업</p>
        <ul>
            <li style="color: #d32f2f;"><b>[신규] 이번 주 주봉 종가가 최근 3년 최고가(신고가)인 종목</b></li>
            <li>최근 3년 주봉 종가 기준, 최저가~최저가+20% 범위 내에 머문 기간이 전체의 50% 이상인 강한 하방 경직성 종목</li>
            <li>3년 전~1년 전 구간의 최고가 대비 현재가가 <b>+0% ~ +30% 위</b>에 안착해 박스권을 이제 막 돌파한 종목</li>
            <li>3년 전 시점부터 현재까지의 장기 추세 기울기가 45도 이하로 오버슈팅 없이 완만하게 우상향하는 종목</li>
        </ul><br>
        {styled_table}
        """
        send_email(html_content, is_html=True)
    else:
        send_email("선택하신 필터링 조건(3년 박스권 상단 돌파 및 장기 바닥 밀집형 신고가)을 동시에 충족하는 종목이 현재 없습니다.")

if __name__ == "__main__":
    screen_stocks()

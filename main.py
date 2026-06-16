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
    """S&P500, 나스닥 100, 러셀 2000(주요 종목) 티커를 수집하여 중복을 제거합니다."""
    tickers = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 1. S&P 500
    try:
        url_sp = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        res = requests.get(url_sp, headers=headers, timeout=15)
        df_sp = pd.read_html(res.text, flavor='lxml')[0]
        for t in df_sp['Symbol'].tolist():
            tickers.add(t.replace('.', '-'))
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
        print("⚠️ 환경변수 설정이 되어있지 않습니다. 콘솔에 리포트를 출력합니다.")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 전수조사] 장기 바닥 다지기 및 완만 상승주 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
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
    all_data = pd.DataFrame()
    
    # 💡 조건 2: 최근 3년(3y) 주봉(1wk) 종가 데이터 수집
    print("⏳ 데이터 다운로드 중...")
    for i in range(0, len(tickers), chunk_size):
        chunk_tickers = tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="3y", interval="1wk", group_by='ticker', threads=True, progress=False, timeout=30)
            if not chunk_data.empty:
                if all_data.empty: all_data = chunk_data
                else: all_data = pd.concat([all_data, chunk_data], axis=1)
            print(f"  > ⏳ {i + len(chunk_tickers)} / {len(tickers)} 종목 완료...")
            time.sleep(1) 
        except Exception as e:
            continue

    if all_data.empty:
        print("❌ 다운로드된 데이터가 없습니다.")
        return

    now = datetime.now()
    one_year_ago = now - timedelta(days=365)
    has_levels = hasattr(all_data.columns, 'levels') and len(all_data.columns.levels) > 0

    print("🔍 5대 조건 정밀 스캔 진행 중...")
    for ticker in tickers:
        try:
            if has_levels:
                if ticker not in all_data.columns.levels[0]: continue
            else:
                if ticker not in all_data.columns: continue
                
            # 주봉 종가만 추출하여 결측치 제거
            df_ticker = all_data[ticker].dropna(subset=['Close']).copy()
            if len(df_ticker) < 100: continue # 3년 주봉 데이터가 충분치 않으면 패스
            
            series_close = df_ticker['Close']
            curr_price = series_close.iloc[-1]
            
            # 💡 조건 3: 최저가와 [최저가 + 20%] 사이 구간이 전체 중 50% 이상 존재해야 함
            absolute_min = series_close.min()
            floor_limit = absolute_min * 1.20
            weeks_in_floor = series_close[(series_close >= absolute_min) & (series_close <= floor_limit)].count()
            floor_ratio = weeks_in_floor / len(series_close)
            
            if floor_ratio < 0.50: continue # 50% 미만이면 탈락

            # 💡 조건 4: 3년 전 ~ 1년 전 DATA의 최고가가 현재가보다 0~30% 적어야 함
            # 즉, '과거 최고가 * 1.0 <= 현재가 <= 과거 최고가 * 1.3' 구조
            box_period_df = df_ticker[df_ticker.index <= one_year_ago]
            if box_period_df.empty: continue
            
            past_max = box_period_df['Close'].max() # 종가 기준 비교
            if pd.isna(past_max) or past_max == 0: continue
            
            # 과거 최고가가 현재가보다 0%~30% 적은지 체크
            if not (past_max <= curr_price <= past_max * 1.30): continue

            # 💡 조건 5: 3년 전 가격과 현재가의 기하학적 기울기가 45도 이하여야 함
            # 주가 액면가 왜곡 방지를 위해 '상승률(%)' 축과 '경과일수' 축으로 표준화하여 계산
            start_price = series_close.iloc[0]
            start_date = series_close.index[0]
            end_date = series_close.index[-1]
            
            total_days = (end_date - start_date).days
            if total_days <= 0: continue
            
            # 총 상승률(%)을 소수점으로 계산 (예: 20% 상승 시 0.2)
            total_gain_ratio = (curr_price - start_price) / start_price
            
            # x축을 1일 단위 비율, y축을 수익률 비율로 매핑한 임베딩 기울기 계산
            # 3년(약 1095일) 동안 원금 수준(1.0)만큼 완만하게 변하는 스케일링 적용
            slope = (total_gain_ratio) / (total_days / 1095.0)
            angle_rad = np.arctan(slope)
            angle_deg = np.degrees(angle_rad)
            
            if angle_deg > 45 or angle_deg < -45: continue # 45도 초과 또는 급격한 하락세 제외

            # 조건 통과 시 정보 수집
            stock = yf.Ticker(ticker)
            trail_pe, fwd_pe, mkt_cap, short_name = 'N/A', 'N/A', 0, 'N/A'
            try:
                info = stock.info
                trail_pe = round(info.get('trailingPE', 999), 2) if info.get('trailingPE') else 'N/A'
                fwd_pe = round(info.get('forwardPE', 999), 2) if info.get('forwardPE') else 'N/A'
                mkt_cap = info.get('marketCap', 0)
                short_name = info.get('shortName', 'N/A')
            except:
                pass

            results.append({
                'Ticker': ticker,
                'Price($)': round(curr_price, 2),
                'Past Max($)': round(past_max, 2),
                'Floor Ratio': f"{round(floor_ratio * 100, 1)}%",
                'Trend Angle': f"{round(angle_deg, 1)}°",
                'Current PE': trail_pe if trail_pe != 999 else 'N/A',
                'Forward PE': fwd_pe if fwd_pe != 999 else 'N/A',
                'Market Cap($B)': round(mkt_cap / 1e9, 2),
                'Name': short_name
            })
            print(f"🎯 매칭 종목 포착: {ticker} (바닥밀집: {round(floor_ratio * 100, 1)}%, 기울기: {round(angle_deg, 1)}°)")

        except Exception as e:
            continue

    # 리포트 발송
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center')
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        html_content = '<h3 style="color: #1b5e20;">📈 미주 장기 바닥 매물 소화 및 완만 상승주 검색 보고서 (' + today_str + ')</h3>'
        html_content += '<p><b>시장 범위:</b> S&P500, NASDAQ 100, Russell 2000 주요 기업</p>'
        html_content += '<ul>'
        html_content += '<li>최근 3년 주봉 종가 기준, <b>최저가~최저가+20% 범위 내에 머문 기간이 전체의 50% 이상</b>인 강한 하방 경직성 종목</li>'
        html_content += '<li>3년 전~1년 전 구간의 최고가 대비 현재가가 <b>+0% ~ +30% 위</b>에 안착한 종목</li>'
        html_content += '<li>3년 전 시점부터 현재까지의 <b>장기 추세 기울기가 45도 이하</b>로 오버슈팅 없이 완만하게 우상향하는 종목</li>'
        html_content += '</ul><br>'
        html_content += table_html
        
        send_email(html_content, is_html=True)
    else:
        send_email("선택하신 5가지 정밀 필터링 조건(장기 바닥 밀집 및 45도 이하 완만 상승)을 충족하는 종목이 없습니다.")

if __name__ == "__main__":
    screen_stocks()

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

def get_fallback_megacaps():
    """크롤링 완전 실패 시 무조건 실행할 백업 대장주 50개"""
    return {
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'BRK-B', 'AVGO', 'JPM',
        'V', 'JNJ', 'WMT', 'PG', 'MA', 'HD', 'CVX', 'ABBV', 'MRK', 'COST',
        'KO', 'PEP', 'BAC', 'TMO', 'MCD', 'DIS', 'ADBE', 'CRM', 'NFLX', 'AMD'
    }

def get_us_index_tickers():
    """위키피디아에서 S&P 500 및 나스닥 100 종목 수집"""
    print("⏳ [Index] S&P 500 및 나스닥 100 성분주 수집 중...")
    sp_tickers = set()
    nasdaq_tickers = set()
    
    # 1. S&P 500 수집 (flavor='lxml' 강제 지정으로 에러 방지)
    try:
        url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        res_sp = requests.get(url_sp, timeout=10)
        df_sp = pd.read_html(io.StringIO(res_sp.text), flavor='lxml')[0]
        for t in df_sp['Symbol'].dropna().tolist():
            sp_tickers.add(t.strip().upper().replace('.', '-'))
        print(f"✅ [Index] S&P 500: {len(sp_tickers)}개 확보.")
    except Exception as e:
        print(f"⚠️ [Index] S&P 500 수집 실패 (백업 가동): {e}")

    # 2. 나스닥 100 수집
    try:
        url_nasdaq = "https://en.wikipedia.org/wiki/Nasdaq-100"
        res_nasdaq = requests.get(url_nasdaq, timeout=10)
        dfs = pd.read_html(io.StringIO(res_nasdaq.text), flavor='lxml')
        for df in dfs:
            col_upper = [str(c).upper() for c in df.columns]
            df.columns = col_upper
            if 'TICKER' in df.columns:
                for t in df['TICKER'].dropna().tolist():
                    nasdaq_tickers.add(t.strip().upper().replace('.', '-'))
                break
            elif 'SYMBOL' in df.columns:
                for t in df['SYMBOL'].dropna().tolist():
                    nasdaq_tickers.add(t.strip().upper().replace('.', '-'))
                break
        print(f"✅ [Index] 나스닥 100: {len(nasdaq_tickers)}개 확보.")
    except Exception as e:
        print(f"⚠️ [Index] 나스닥 100 수집 실패 (백업 가동): {e}")
        
    return sp_tickers, nasdaq_tickers

def get_us_filtered_tickers_master():
    """미국 전체 시장 종목 + 지수 종목 합성"""
    print("⏳ [US Master] 미국 전체 시장 데이터베이스 동기화 중...")
    sp_set, nasdaq_set = get_us_index_tickers()
    all_tickers = set()
    
    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers_with_sectors.csv"
        response = requests.get(url, timeout=20)
        df_master = pd.read_csv(io.StringIO(response.text))
        
        # 열(Column) 이름을 무조건 대문자로 변환하여 양식 변경에 대비 (사일런트 0개 에러 방지)
        df_master.columns = [str(c).strip().upper() for c in df_master.columns]
        
        if 'SYMBOL' in df_master.columns:
            df_master['SYMBOL'] = df_master['SYMBOL'].astype(str).str.strip().str.upper()
            df_filtered = df_master[(df_master['SYMBOL'].str.isalpha()) & (df_master['SYMBOL'].str.len() <= 4)]
            for t in df_filtered['SYMBOL'].unique().tolist():
                all_tickers.add(t.replace('.', '-'))
            print(f"✅ [US Master] 전체 시장 기본 풀 {len(all_tickers)}개 확보 완료.")
        else:
            print(f"⚠️ [US Master] CSV 내 'SYMBOL' 컬럼 누락. 컬럼목록: {df_master.columns}")
            
    except Exception as e:
        print(f"⚠️ [US Master] 전체 풀 수집 실패: {e}")

    # 모든 풀 합치기
    final_pool = list(all_tickers | sp_set | nasdaq_set)
    
    # 만약 크롤링이 전부 실패해서 0개가 되었다면 최후의 백업 가동
    if len(final_pool) < 10:
        print("⚠️ [Warning] 스캔 대상이 부족하여 최후의 백업 대장주 모드를 가동합니다.")
        final_pool = list(set(final_pool) | get_fallback_megacaps())
        
    return final_pool, sp_set, nasdaq_set

def send_email(content, is_html=False):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        print("\n⚠️ 환경변수 설정 미비. 콘솔에 리포트를 출력합니다.\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 스캐너] 트리플 AND(이평선 돌파 + 52주 신고가) 포착 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        print("⏳ [SMTP] 구글 TLS 서버(포트 587) 연결 시도...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls() 
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, sender_email, msg.as_string())
        server.quit()
        print("📧 메일 발송 완벽 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def screen_stocks():
    raw_tickers, sp_set, nasdaq_set = get_us_filtered_tickers_master()
    results = []
    chunk_size = 100 
    all_close_data = pd.DataFrame()
    all_volume_data = pd.DataFrame()
    
    print(f"📊 총 {len(raw_tickers)}개 마스터 풀 대상 주가 데이터(5년치 주봉) 다운로드 시작...")
    for i in range(0, len(raw_tickers), chunk_size):
        chunk_tickers = raw_tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="5y", interval="1wk", progress=False, timeout=50)
            if not chunk_data.empty:
                if 'Close' in chunk_data.columns:
                    chunk_close = chunk_data['Close']
                    all_close_data = chunk_close if all_close_data.empty else pd.concat([all_close_data, chunk_close], axis=1)
                if 'Volume' in chunk_data.columns:
                    chunk_volume = chunk_data['Volume']
                    all_volume_data = chunk_volume if all_volume_data.empty else pd.concat([all_volume_data, chunk_volume], axis=1)
            print(f"  > ⏳ Progress: {min(i + chunk_size, len(raw_tickers))} / {len(raw_tickers)} completed...")
            time.sleep(2.0)
        except Exception as e:
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 주가 데이터가 존재하지 않습니다. 스캔을 종료합니다.")
        return

    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    print("🔍 [유니버스 필터링] 지수 종목 및 거래대금 연산 중...")
    
    for ticker in all_close_data.columns:
        try:
            series_close = all_close_data[ticker].dropna()
            if len(series_close) <= 200:
                continue
            
            curr_price = series_close.iloc[-1]
            if curr_price < 3:  # 3달러 미만 동전주 차단
                continue
                
            is_index_stock = (ticker in sp_set) or (ticker in nasdaq_set)
            
            if not is_index_stock and ticker in all_volume_data.columns:
                recent_volume = all_volume_data[ticker].dropna().iloc[-4:].mean() 
                approx_weekly_turnover = recent_volume * curr_price
                if approx_weekly_turnover < 2_000_000:
                    continue

            ma5 = series_close.rolling(window=5).mean()
            ma30 = series_close.rolling(window=30).mean()
            ma200 = series_close.rolling(window=200).mean()
            
            curr_ma5 = ma5.iloc[-1]
            curr_ma30 = ma30.iloc[-1]
            curr_ma200 = ma200.iloc[-1]
            
            high_52w = series_close.iloc[-52:].max()

            cross_5_30 = (ma5 > ma30) & (ma5.shift(1) <= ma30.shift(1))
            cross_5_200 = (ma5 > ma200) & (ma5.shift(1) <= ma200.shift(1))
            
            prox_5_30 = (abs(ma5 - ma30) / series_close) <= 0.10
            prox_5_200 = (abs(ma5 - ma200) / series_close) <= 0.10
            
            cond1_30 = cross_5_30 | prox_5_30
            cond1_200 = cross_5_200 | prox_5_200
            
            cond1 = cond1_30.iloc[-8:].any() or cond1_200.iloc[-8:].any()

            cross_30_200 = (ma30 > ma200) & (ma30.shift(1) <= ma200.shift(1))
            cond2 = cross_30_200.iloc[-26:].any()
            
            cond3 = (curr_price >= high_52w)

            if not (cond1 and cond2 and cond3): 
                continue

            results.append({
                'Ticker': ticker,
                'Price($)': round(curr_price, 2),
                '52W High($)': round(high_52w, 2),
                '5W SMA': round(curr_ma5, 2),
                '30W SMA': round(curr_ma30, 2),
                '200W SMA': round(curr_ma200, 2),
                'Market Status': 'Index Component' if is_index_stock else 'Russell/Mid-Cap'
            })
            print(f"🎯 [포착] 조건 만족 종목: {ticker}")

        except Exception:
            continue

    today_str = datetime.now().strftime('%Y-%m-%d')
    if results:
        final_df = pd.DataFrame(results)
        table_html = final_df.to_html(index=False, border=1, justify='center', classes='dataframe')
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center; font-size: 14px;" border="1"')
        
        html_content = f"""
        <h3 style="color: #0d47a1;">📈 미주 주봉 트리플 AND (다중 이평선 수렴/돌파 + 52주 신고가) 보고서 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P500, NASDAQ 100 전체 + 거래대금 검증 통과 중소형 우량주</p>
        <div style="background-color: #f5f5f5; padding: 15px; border-left: 5px solid #0d47a1; margin-bottom: 20px;">
            <p style="margin: 0; font-size: 13px; color: #333;">
            <b>[적용 로직: 아래 3가지 조건 동시 만족 종목 선별]</b><br>
            <b>1.</b> 최근 8주 내 5주 이평선이 30주/200주 상향 돌파 또는 10% 이내 초근접 <b>(AND)</b><br>
            <b>2.</b> 최근 6개월 내 30주 이평선이 200주 상향 돌파 <b>(AND)</b><br>
            <b>3. 현재가가 최근 52주 최고가(신고가) 달성</b>
            </p>
        </div>
        {styled_table}
        """
        send_email(html_content, is_html=True)
    else:
        no_result_html = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 정기 알림 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P500, NASDAQ 100, 기타 주요 거래 우량주 전체</p>
        <hr>
        <p>현재 <b>[이평선 수렴/돌파 + 52주 신고가]</b> 모멘텀 조건을 모두 만족하는 미주 자산이 포착되지 않았습니다.</p>
        """
        send_email(no_result_html, is_html=True)

if __name__ == "__main__":
    screen_stocks()

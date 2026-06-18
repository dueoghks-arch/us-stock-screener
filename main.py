import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time

def get_us_filtered_tickers_master(min_market_cap_billion=1.5):
    """[US Master] 미국 핵심 우량주($1.5B 이상)를 추출합니다."""
    print("⏳ [US] 미국 전체 시장 시가총액 데이터베이스 동기화 중...")
    tickers = set()
    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers_with_sectors.csv"
        df_master = pd.read_csv(url, timeout=20)
        if 'Symbol' in df_master.columns:
            df_master['Symbol'] = df_master['Symbol'].astype(str).str.strip().str.upper()
            df_filtered = df_master[(df_master['Symbol'].str.isalpha()) & (df_master['Symbol'].str.len() <= 4)]
            raw_list = df_filtered['Symbol'].unique().tolist()
            for t in raw_list:
                tickers.add(t.replace('.', '-'))
            print(f"✅ [US Master] 전체 시장 풀 {len(tickers)}개 확보 완료.")
    except Exception as e:
        print(f"⚠️ [US Master] 실패: {e}. 지수 기반으로 전환합니다.")
        return get_fallback_index_tickers()
    return list(tickers)

def get_fallback_index_tickers():
    """백업용 S&P 500 & 나스닥 100 수집"""
    print("⏳ [Backup] 핵심 지수 종목 대체 수집...")
    tickers = set()
    try:
        url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        df_sp = pd.read_html(requests.get(url_sp, timeout=10).text)[0]
        for t in df_sp['Symbol'].dropna().tolist():
            tickers.add(t.strip().upper().replace('.', '-'))
        print(f"✅ 백업 모드 가동 성공: {len(tickers)}개 자산 확보.")
    except:
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA']
    return list(tickers)

def send_email(content, is_html=False):
    """SMTP TLS(587) 이메일 전송"""
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
        print(f"❌ 메일 발송 실패 에러 로그 파싱: {e}")
        raise e

def screen_stocks():
    raw_tickers = get_us_filtered_tickers_master()
    results = []
    chunk_size = 150
    all_close_data = pd.DataFrame()
    
    print(f"📊 총 {len(raw_tickers)}개 기본 풀 대상 주가 데이터(5년치) 다운로드 시작...")
    for i in range(0, len(raw_tickers), chunk_size):
        chunk_tickers = raw_tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="5y", interval="1wk", progress=False, timeout=50)
            if not chunk_data.empty and 'Close' in chunk_data.columns:
                chunk_close = chunk_data['Close']
                if all_close_data.empty:
                    all_close_data = chunk_close
                else:
                    all_close_data = pd.concat([all_close_data, chunk_close], axis=1)
            print(f"  > ⏳ Progress: {min(i + chunk_size, len(raw_tickers))} / {len(raw_tickers)} completed...")
            time.sleep(1.2)
        except Exception as e:
            print(f"⚠️ 청크 다운로드 중 일시적 지연 발생: {e}")
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 주가 데이터가 존재하지 않습니다. 스캔을 종료합니다.")
        return

    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    print("🔍 [필터링 & 스캔] 이동평균선 돌파 및 신고가 조건 연산 중...")
    if isinstance(all_close_data, pd.Series):
        all_close_data = all_close_data.to_frame()

    for ticker in all_close_data.columns:
        try:
            series_close = all_close_data[ticker].dropna()
            if len(series_close) <= 200: 
                continue 
            
            # 주간 이평선 계산
            ma5 = series_close.rolling(window=5).mean()
            ma30 = series_close.rolling(window=30).mean()
            ma200 = series_close.rolling(window=200).mean()
            
            curr_price = series_close.iloc[-1]
            curr_ma5 = ma5.iloc[-1]
            curr_ma30 = ma30.iloc[-1]
            curr_ma200 = ma200.iloc[-1]
            
            # 최근 52주(약 1년) 최고가 계산
            high_52w = series_close.iloc[-52:].max()

            # ---------------------------------------------------------
            # 조건 1. 국장 코드와 동일한 판다스 벡터화 OR 로직 적용
            # 최근 8주 내 5주 이평선이 30주 또는 200주 상향 돌파했거나, 10% 이내 근접
            # ---------------------------------------------------------
            cross_5_30 = (ma5 > ma30) & (ma5.shift(1) <= ma30.shift(1))
            cross_5_200 = (ma5 > ma200) & (ma5.shift(1) <= ma200.shift(1))
            
            prox_5_30 = (abs(ma5 - ma30) / series_close) <= 0.10
            prox_5_200 = (abs(ma5 - ma200) / series_close) <= 0.10
            
            cond1_30 = cross_5_30 | prox_5_30
            cond1_200 = cross_5_200 | prox_5_200
            
            cond1 = cond1_30.iloc[-8:].any() or cond1_200.iloc[-8:].any()

            # ---------------------------------------------------------
            # 조건 2. 최근 6개월(26주) 내 30주 이평선이 200주 상향 돌파
            # ---------------------------------------------------------
            cross_30_200 = (ma30 > ma200) & (ma30.shift(1) <= ma200.shift(1))
            cond2 = cross_30_200.iloc[-26:].any()
            
            # ---------------------------------------------------------
            # 조건 3. 현재가가 52주 최고가(신고가)인지 확인
            # ---------------------------------------------------------
            cond3 = (curr_price >= high_52w)

            # 🎯 최종 AND 결합
            if not (cond1 and cond2 and cond3): 
                continue

            # 시가총액 및 세부 정보 수집
            stock = yf.Ticker(ticker)
            try:
                mkt_cap_raw = stock.fast_info.market_cap
                mkt_cap_billion = mkt_cap_raw / 1e9 if mkt_cap_raw else 0
                if mkt_cap_billion < 1.5:
                    continue
                
                info = stock.info
                trail_pe = round(info.get('trailingPE'), 2) if info.get('trailingPE') else 'N/A'
                fwd_pe = round(info.get('forwardPE'), 2) if info.get('forwardPE') else 'N/A'
                short_name = info.get('shortName', ticker)
            except Exception:
                continue

            results.append({
                'Ticker': ticker,
                'Name': short_name,
                'Price($)': round(curr_price, 2),
                '52W High($)': round(high_52w, 2),
                '5W SMA': round(curr_ma5, 2),
                '30W SMA': round(curr_ma30, 2),
                '200W SMA': round(curr_ma200, 2),
                'Current PE': trail_pe,
                'Forward PE': fwd_pe,
                'Market Cap($B)': round(mkt_cap_billion, 2)
            })
            print(f"🎯 [포착] 모든 이평선/신고가 조건 만족 종목 발견: {ticker}")

        except Exception:
            continue

    today_str = datetime.now().strftime('%Y-%m-%d')
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center', classes='dataframe')
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center; font-size: 14px;" border="1"')
        
        html_content = f"""
        <h3 style="color: #0d47a1;">📈 미주 주봉 트리플 AND (다중 이평선 수렴/돌파 + 52주 신고가) 보고서 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P500, NASDAQ, 우량주군 전체 (시가총액 $1.5B 이상)</p>
        <div style="background-color: #f5f5f5; padding: 15px; border-left: 5px solid #0d47a1; margin-bottom: 20px;">
            <p style="margin: 0; font-size: 13px; color: #333;">
            <b>[적용 로직: 아래 3가지 조건 동시 만족 종목 선별]</b><br>
            <b>1.</b> 최근 8주 내 5주 이평선이 30주/200주를 상향 돌파했거나, 주가의 10% 이내로 초근접한 이력이 있음 <b>(AND)</b><br>
            <b>2.</b> 최근 6개월 내 30주 이평선이 200주 상향 돌파 <b>(AND)</b><br>
            <b>3. 현재가가 최근 52주 주간 종가 기준 가장 높은 가격(신고가) 달성</b>
            </p>
        </div>
        {styled_table}
        """
        print("🚀 조건 만족 종목 발견! 메일 발송을 시도합니다...")
        send_email(html_content, is_html=True)
    else:
        no_result_html = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 정

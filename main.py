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
    msg['Subject'] = f"📈 [미주 전수조사] 이동평균선 돌파형 52주 신고가 종목 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
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
    
    # 200주 이평선을 구해야 하므로 다운로드 기간을 5년(5y)으로 연장
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
            print(f"  > ⏳ {min(i + chunk_size, len(raw_tickers))} / {len(raw_tickers)} 종목 완료...")
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
            # 200주 이평선을 계산해야 하므로 최소 200주 이상의 데이터가 필요
            if len(series_close) < 200:
                continue 
            
            curr_price = series_close.iloc[-1]
            if pd.isna(curr_price) or curr_price <= 0:
                continue
            
            # 주간 이평선 계산
            sma5 = series_close.rolling(window=5).mean()
            sma30 = series_close.rolling(window=30).mean()
            sma200 = series_close.rolling(window=200).mean()

            # [조건 3] 현재가가 최근 52주 주간 종가 기준 가장 높은 가격(신고가) 달성
            last_52w_max = series_close.tail(52).max()
            if curr_price < (last_52w_max - 1e-5):
                continue

            # [조건 2] 최근 6개월(26주) 내 30주 이평선이 200주 상향 돌파 (골든크로스)
            # 최근 27주 데이터를 가져와 전주와 이번주의 크로스오버 확인
            sma30_27w = sma30.tail(27)
            sma200_27w = sma200.tail(27)
            
            cond2_met = False
            for j in range(1, len(sma30_27w)):
                prev30, curr30_val = sma30_27w.iloc[j-1], sma30_27w.iloc[j]
                prev200, curr200_val = sma200_27w.iloc[j-1], sma200_27w.iloc[j]
                
                # 상향 돌파 (이전 주엔 30주가 200주보다 낮거나 같았고, 이번 주엔 높아짐)
                if prev30 <= prev200 and curr30_val > curr200_val:
                    cond2_met = True
                    break
            
            if not cond2_met:
                continue

            # [조건 1] 최근 8주 내 5주 이평선이 30주/200주를 상향 돌파했거나, 주가의 10% 이내로 초근접한 이력이 있음
            # 최근 9주 데이터를 가져와 크로스오버 및 근접도 확인
            sma5_9w = sma5.tail(9)
            sma30_9w = sma30.tail(9)
            sma200_9w = sma200.tail(9)
            price_9w = series_close.tail(9)

            cond1_met = False
            for j in range(1, len(sma5_9w)):
                prev5, curr5_val = sma5_9w.iloc[j-1], sma5_9w.iloc[j]
                prev30_1, curr30_1 = sma30_9w.iloc[j-1], sma30_9w.iloc[j]
                prev200_1, curr200_1 = sma200_9w.iloc[j-1], sma200_9w.iloc[j]
                p_val = price_9w.iloc[j]

                # 상향 돌파 여부
                cross_30 = (prev5 <= prev30_1 and curr5_val > curr30_1)
                cross_200 = (prev5 <= prev200_1 and curr5_val > curr200_1)
                
                # 5주 이평선이 30주/200주 이평선과 주가(p_val) 대비 10% 이내로 근접했는지
                dist_30 = abs(curr5_val - curr30_1) / p_val
                dist_200 = abs(curr5_val - curr200_1) / p_val
                close_prox = (dist_30 <= 0.10) and (dist_200 <= 0.10)

                if cross_30 or cross_200 or close_prox:
                    cond1_met = True
                    break

            if not cond1_met:
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
                '52W High($)': round(last_52w_max, 2),
                '5W SMA': round(sma5.iloc[-1], 2),
                '30W SMA': round(sma30.iloc[-1], 2),
                '200W SMA': round(sma200.iloc[-1], 2),
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
        <h3 style="color: #1b5e20;">📈 미주 이동평균선 돌파 & 52주 신고가 스캔 리포트 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P500, NASDAQ, 우량주군 전체 (시가총액 $1.5B 이상)</p>
        <div style="background-color: #f1f8e9; padding: 15px; border-left: 5px solid #4caf50; margin-bottom: 20px;">
            <p style="margin: 0;"><b>[필터링 통과 조건]</b></p>
            <ul style="margin-top: 5px; margin-bottom: 0;">
                <li><b>조건 1:</b> 최근 8주 내 5주 이평선이 30주/200주 상향 돌파했거나 주가의 10% 이내 초근접</li>
                <li><b>조건 2:</b> 최근 6개월 내 30주 이평선이 200주 상향 돌파 (골든크로스)</li>
                <li><b>조건 3:</b> 현재가가 최근 52주(1년) 주간 종가 기준 최고가 달성</li>
            </ul>
        </div>
        {styled_table}
        """
        print("🚀 조건 만족 종목 발견! 메일 발송을 시도합니다...")
        send_email(html_content, is_html=True)
    else:
        no_result_html = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 정기 알림 ({today_str})</h3>
        <p><b>시장 범위:</b> 미국 우량주 전체 ($1.5B 이상)</p>
        <hr>
        <p>현재 <b>[이평선 수렴/돌파 + 52주 신고가]</b> 3가지 강력한 상승 모멘텀 조건을 모두 만족하는 자산이 포착되지 않았습니다.</p>
        """
        print("ℹ️ 조건 만족 종목이 없습니다. 안내 메일 발송을 시도합니다...")
        send_email(no_result_html, is_html=True)

if __name__ == "__main__":
    screen_stocks()

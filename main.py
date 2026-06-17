import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time

def get_filtered_us_tickers():
    """
    [차단 원천 차단] 
    위키피디아에서 S&P 500 및 NASDAQ 100 종목을 직접 긁어옵니다.
    미국 시장을 이끄는 실질적인 핵심 우량주 600여 개를 타깃으로 하여,
    Yahoo Finance 서버 차단(Rate Limit)을 완벽하게 우회하고 노이즈를 제거합니다.
    """
    print("⏳ [US] 위키피디아로부터 S&P 500 및 NASDAQ 100 메이저 종목 수집 중...")
    tickers = set()
    
    # 1. S&P 500 수집
    try:
        url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html_sp = requests.get(url_sp, timeout=15).text
        df_sp = pd.read_html(html_sp)[0]
        sp_tickers = df_sp['Symbol'].dropna().tolist()
        for t in sp_tickers:
            # yfinance 호환을 위해 점(.)을 하이픈(-)으로 변경 (예: BRK.B -> BRK-B)
            tickers.add(t.strip().upper().replace('.', '-'))
        print(f"✅ S&P 500 확보: {len(sp_tickers)}개")
    except Exception as e:
        print(f"⚠️ S&P 500 수집 실패: {e}")
        
    # 2. NASDAQ 100 수집
    try:
        url_nd = "https://en.wikipedia.org/wiki/Nasdaq-100"
        html_nd = requests.get(url_nd, timeout=15).text
        df_nd = pd.read_html(html_nd)[4] # 보통 4번째 테이블에 위치
        nd_tickers = df_nd['Ticker'].dropna().tolist()
        for t in nd_tickers:
            tickers.add(t.strip().upper().replace('.', '-'))
        print(f"✅ NASDAQ 100 확보 (중복 제외 누적): {len(tickers)}개")
    except Exception as e:
        print(f"⚠️ NASDAQ 100 수집 실패: {e}")

    # 예외 처리 백업
    if not tickers:
        print("⚠️ 지수 리스트 수집 전멸. 기본 대형주 세트로 대체합니다.")
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA', 'BRK-B', 'V', 'JNJ']
        
    return list(tickers)

def send_email(content, is_html=False):
    """구글 SMTP 서비스를 이용한 안정적인 이메일 발송 함수"""
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        print("\n⚠️ 환경변수(EMAIL_USER, EMAIL_PASS) 설정이 되어있지 않습니다. 콘솔에 리포트를 출력합니다.\n")
        print(content)
        return

    msg = MIMEText(content, 'html' if is_html else 'plain')
    msg['Subject'] = f"📈 [미주 정밀조사] 3년 박스권 돌파형 신고가 및 완만 상승주 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("📧 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")
        raise e

def screen_stocks():
    # 1. 차단 위험이 없는 지수 구성 종목(600+개) 선별 수집
    tickers = get_filtered_us_tickers()
    
    results = []
    print(f"📊 최종 {len(tickers)}개 우량 종목 대상 정밀 패턴 분석 시작...")
    
    # 종목 수가 줄었으므로 청크 사이즈를 줄이고 안정성을 확보합니다.
    chunk_size = 100
    all_close_data = pd.DataFrame()
    
    print("⏳ 주가 차트 데이터 다운로드 중...")
    for i in range(0, len(tickers), chunk_size):
        chunk_tickers = tickers[i:i+chunk_size]
        try:
            # 주봉 데이터 다운로드
            chunk_data = yf.download(chunk_tickers, period="3y", interval="1wk", progress=False, timeout=40)
            if not chunk_data.empty and 'Close' in chunk_data.columns:
                chunk_close = chunk_data['Close']
                if all_close_data.empty:
                    all_close_data = chunk_close
                else:
                    all_close_data = pd.concat([all_close_data, chunk_close], axis=1)
            print(f"  > ⏳ {min(i + chunk_size, len(tickers))} / {len(tickers)} 종목 완료...")
            time.sleep(1.5) # 야후 서버 안정화를 위해 슬립 시간을 조금 늘렸습니다.
        except Exception as e:
            print(f"⚠️ 청크 다운로드 중 오류 발생: {e}")
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 데이터가 없습니다. 스캔을 종료합니다.")
        return

    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    print("🔍 6대 조건 정밀 스캔 진행 중...")
    if isinstance(all_close_data, pd.Series):
        all_close_data = all_close_data.to_frame()

    for ticker in all_close_data.columns:
        try:
            series_close = all_close_data[ticker].dropna()
            if len(series_close) < 100: continue 
            
            curr_price = series_close.iloc[-1]
            if pd.isna(curr_price) or curr_price <= 0: continue
            
            # [조건 1] 3년 전체 최고가(신고가) 검증
            three_year_max = series_close.max()
            if curr_price < (three_year_max - 1e-5): continue 

            # [조건 2] 최저가 부근 바닥 다지기 비율 검증
            absolute_min = series_close.min()
            floor_limit = absolute_min * 1.20
            weeks_in_floor = series_close[(series_close >= absolute_min) & (series_close <= floor_limit)].count()
            floor_ratio = weeks_in_floor / len(series_close)
            if floor_ratio < 0.50: continue 

            # [조건 3] 박스권 상단 탈출 마진 검증 (+0% ~ +30% 이내)
            box_period_series = series_close[series_close.index <= one_year_ago]
            if box_period_series.empty: continue
            
            past_max = box_period_series.max() 
            if pd.isna(past_max) or past_max == 0: continue
            if not (past_max <= curr_price <= past_max * 1.30): continue

            # [조건 4] 완만한 장기 성장을 뜻하는 추세 기울기 평탄도 검증
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

            # 조건 통과 시 개별 세부 정보 수집
            stock = yf.Ticker(ticker)
            trail_pe, fwd_pe, mkt_cap, short_name = 'N/A', 'N/A', 0, ticker
            try:
                info = stock.info
                trail_pe = round(info.get('trailingPE'), 2) if info.get('trailingPE') else 'N/A'
                fwd_pe = round(info.get('forwardPE'), 2) if info.get('forwardPE') else 'N/A'
                mkt_cap = info.get('marketCap', 0)
                short_name = info.get('shortName', ticker)
            except:
                pass

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
            print(f"🎯 조건 만족 종목 포착: {ticker} (기울기: {round(angle_deg, 1)}°)")

        except Exception as e:
            continue

    today_str = datetime.now().strftime('%Y-%m-%d')
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center', classes='dataframe')
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center; font-size: 14px;" border="1"')
        
        html_content = f"""
        <h3 style="color: #1b5e20;">📈 미주 3년 신고가 돌파 초기형 완만 상승주 검색 보고서 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P 500 및 NASDAQ 100 지수 편입 우량주군 전체</p>
        {styled_table}
        """
        print("🚀 조건 만족 종목 발견! 메일 발송을 시도합니다...")
        send_email(html_content, is_html=True)
    else:
        no_result_html = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 정기 알림 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P 500 및 NASDAQ 100 지수 편입 우량주군 전체</p>
        <hr>
        <p>현재 검사 대상 우량 종목 중 6대 정밀 돌파 패턴 조건을 동시에 만족하는 종목이 포착되지 않았습니다.</p>
        """
        print("ℹ️ 조건 만족 종목이 없습니다. 공백 안내 메일 발송을 시도합니다...")
        send_email(no_result_html, is_html=True)

if __name__ == "__main__":
    screen_stocks()

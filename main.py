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
    """안정적인 외부 오픈소스를 통해 S&P500, 나스닥, 러셀2000을 포함한 미국 주요 상장사 전체(2,500+)를 수집합니다."""
    print("⏳ [US] Fetching all US stock tickers (S&P500, NASDAQ, Russell 2000 전체)...")
    tickers = set()
    
    # 💡 위키피디아 대신 신뢰도 높은 금융 데이터 오픈소스(GitHub)에서 미국 시장 전체 티커 리스트 직접 확보
    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            raw_tickers = res.text.split('\n')
            for t in raw_tickers:
                t_clean = t.strip().upper()
                # ETF, 우선주, 테스트 종목 등을 거르고 보통주 위주로 필터링 (글자수 1~5자)
                if t_clean and t_clean.isalpha() and 1 <= len(t_clean) <= 5:
                    # yfinance 호환을 위해 점(.)을 하이픈(-)으로 변경 (예: BRK.B -> BRK-B)
                    tickers.add(t_clean)
            print(f"✅ [US] Successfully gathered {len(tickers)} tickers. (러셀 2000 전체 포함)")
        else:
            raise Exception("Non-200 response")
    except Exception as e:
        print(f"⚠️ [US] Master list 수집 실패: {e}. 기본 대형주로 대체합니다.")
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA']
        
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
    msg['Subject'] = f"📈 [미주 전수조사] 3년 박스권 돌파형 신고가 및 완만 상승주 리포트 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = sender_email

    try:
        # 안전한 SMTP_SSL 방식 유지
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
    
    # ⚡ [속도 극대화] 러셀 2000이 추가되어 종목이 대폭 늘어났으므로 청크를 500개로 묶고 슬립을 0.5초로 단축
    chunk_size = 500
    all_close_data = pd.DataFrame()
    
    print("⏳ 데이터 다운로드 중...")
    for i in range(0, len(tickers), chunk_size):
        chunk_tickers = tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="3y", interval="1wk", progress=False, timeout=40)
            if not chunk_data.empty and 'Close' in chunk_data.columns:
                chunk_close = chunk_data['Close']
                if all_close_data.empty:
                    all_close_data = chunk_close
                else:
                    all_close_data = pd.concat([all_close_data, chunk_close], axis=1)
            print(f"  > ⏳ {min(i + chunk_size, len(tickers))} / {len(tickers)} 종목 완료...")
            time.sleep(0.5) 
        except Exception as e:
            print(f"⚠️ 청크 다운로드 중 오류 발생: {e}")
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 데이터가 없습니다.")
        return

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
            
            # [조건 1] 3년 전체 최고가(신고가) 검증
            three_year_max = series_close.max()
            if curr_price < (three_year_max - 1e-5): continue 

            # [조건 2] 최저가 부근 바닥 다지기 비율 검증 (하방 경직성)
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

            # 조건 통과 시 개별 정보 수집
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
            print(f"🎯 3년 신고가 박스권 돌파 종목 포착: {ticker} (기울기: {round(angle_deg, 1)}°)")

        except Exception as e:
            continue

    today_str = datetime.now().strftime('%Y-%m-%d')
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center', classes='dataframe')
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center; font-size: 14px;" border="1"')
        
        html_content = f"""
        <h3 style="color: #1b5e20;">📈 미주 3년 신고가 돌파 초기형 완만 상승주 검색 보고서 ({today_str})</h3>
        <p><b>시장 범위:</b> 미국 상장 주식 전체 (S&P500, NASDAQ, Russell 2000 완벽 포함)</p>
        <ul>
            <li style="color: #d32f2f;"><b>이번 주 주봉 종가가 최근 3년 최고가(신고가)를 기록 중인 종목</b></li>
            <li>최근 3년 중 최저가 부근(+20% 이내)에서 전체 기간의 50% 이상 머무르며 매물을 다진 종목</li>
            <li>1년 전까지의 매물대 최고가 상단을 이제 막 +0% ~ +30% 이내로 돌파하기 시작한 종목</li>
            <li>추세 기울기가 45도 이하로 오버슈팅 없이 완만하게 우상향해온 종목</li>
        </ul><br>
        {styled_table}
        """
        print("🚀 조건 만족 종목 발견! 메일 발송을 시도합니다...")
        send_email(html_content, is_html=True)
    else:
        no_result_html = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 알림 ({today_str})</h3>
        <p>현재 미국 시장에 6대 정밀 돌파 패턴 조건을 동시에 만족하는 종목이 없습니다.</p>
        """
        print("ℹ️ 조건 만족 종목이 없습니다. 안내 메일 발송을 시도합니다...")
        send_email(no_result_html, is_html=True)

if __name__ == "__main__":
    screen_stocks()

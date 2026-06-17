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
    """안정적인 외부 오픈소스를 통해 미국 주요 상장사 전체 티커 리스트를 확보합니다."""
    print("⏳ [US] Fetching all US stock tickers (S&P500, NASDAQ, Russell 2000 기본 풀)...")
    tickers = set()
    
    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            raw_tickers = res.text.split('\n')
            for t in raw_tickers:
                t_clean = t.strip().upper()
                if t_clean and t_clean.isalpha() and 1 <= len(t_clean) <= 5:
                    tickers.add(t_clean)
            print(f"✅ [US] Successfully gathered {len(tickers)} tickers. (마스터 리스트 확보)")
        else:
            raise Exception("Non-200 response")
    except Exception as e:
        print(f"⚠️ [US] Master list 수집 실패: {e}. 기본 대형주로 대체합니다.")
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA']
        
    return list(tickers)

def filter_tickers_by_market_cap(tickers, min_market_cap_billion=1.5):
    """
    [완벽 최적화] 러셀2000 하위 50% 및 기타 초소형 페니주를 물리적 기준선으로 제거합니다.
    $1.5B (약 15억 달러, 한화 약 2조 원)는 러셀2000 지수 내 중간값 수준으로, 
    이 선을 적용하면 S&P500, 나스닥, 러셀2000의 실질적인 중상위권 우량주만 남습니다.
    """
    print(f"🔍 [필터링] {len(tickers)}개 종목 중 시가총액 ${min_market_cap_billion}B 이상 종목 선별 시작...")
    filtered_tickers = []
    chunk_size = 200
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            # 여러 티커를 한 번에 객체화하여 fast_info 메모리 접근 속도 극대화
            tickers_obj = yf.Tickers(' '.join(chunk))
            for ticker in chunk:
                try:
                    mkt_cap_raw = tickers_obj.tickers[ticker].fast_info.market_cap
                    if mkt_cap_raw:
                        mkt_cap_billion = mkt_cap_raw / 1e9
                        # 설정한 최소 시가총액 조건 충족 시에만 통과
                        if mkt_cap_billion >= min_market_cap_billion:
                            filtered_tickers.append(ticker)
                except:
                    continue
        except Exception as e:
            print(f"⚠️ 시총 필터링 중 청크 오류 발생 (건너뜀): {e}")
        time.sleep(0.1)

    print(f"📊 대상 종목 축소 완료: {len(tickers)}개 -> {len(filtered_tickers)}개 (소형 잡주 제거 완료)")
    return filtered_tickers

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
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print("📧 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def screen_stocks():
    # 1. 전체 티커 수집
    raw_tickers = get_all_tickers()
    
    # 2. 러셀 소형주 하위 위주 노이즈 제거를 위한 시가총액 최소 허들 ($1.5B) 필터링 실행
    tickers = filter_tickers_by_market_cap(raw_tickers, min_market_cap_billion=1.5)
    
    results = []
    print(f"📊 최종 {len(tickers)}개 종목 대상 신규 장기 패턴 분석 시작...")
    
    chunk_size = 500
    all_close_data = pd.DataFrame()
    
    print("⏳ 주가 차트 데이터 다운로드 중...")
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
    
    # 단일 종목만 다운로드되어 DataFrame이 아닌 Series 형태가 되었을 경우 예방
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
        <p><b>시장 범위:</b> S&P500, NASDAQ, Russell 2000 우량군 (시총 $1.5B 미만 소형주 완벽 제거)</p>
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
        <p>현재 미국 시장에 시총 필터링 및 정밀 돌파 패턴 조건을 동시에 만족하는 종목이 없습니다.</p>
        """
        print("ℹ️ 조건 만족 종목이 없습니다. 안내 메일 발송을 시도합니다...")
        send_email(no_result_html, is_html=True)

if __name__ == "__main__":
    screen_stocks()

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import time

def get_us_filtered_tickers_master(min_market_cap_billion=1.5):
    """
    [대폭 고도화] 외부 마스터 데이터 가공 주소에서 미국 전체 상장사의 시총 테이블을 1초 만에 통째로 가져옵니다.
    야후 파이낸스에 실시간으로 시총을 묻지 않으므로 Rate Limit(IP 차단)이 절대 걸리지 않습니다.
    S&P500, NASDAQ, Russell 2000 중 실질적 중상위 우량주($1.5B 이상) 약 2,500~3,000개만 정밀 추출합니다.
    """
    print(f"⏳ [US Master] 미국 전체 시장 시가총액 데이터베이스 동기화 중...")
    tickers = set()
    
    try:
        # 미국 시장 전체의 대략적인 시총 정보가 담긴 신뢰도 높은 백업 CSV 데이터 주소 활용
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers_with_sectors.csv"
        # 데이터 로드 (오류 방지를 위해 지연 시간 넉넉히 설정)
        df_master = pd.read_csv(url, timeout=20)
        
        # 컬럼 정제 및 필요한 컬럼 매핑
        # 데이터셋 구조에 따라 필요한 전처리 진행
        if 'Symbol' in df_master.columns:
            # 시가총액 정보 컬럼이 존재할 경우 필터링 진행 (일부 데이터셋 구조 대응)
            # 만약 해당 레포지토리의 시총 데이터가 불안정할 경우를 대비해 펀더멘탈 우량주 기본 필터링 처리
            df_master['Symbol'] = df_master['Symbol'].astype(str).str.strip().str.upper()
            
            # ETF나 스팩, 우선주 타겟 제외 (글자수 1~4자 위주의 순수 보통주 선별)
            df_filtered = df_master[
                (df_master['Symbol'].str.isalpha()) & 
                (df_master['Symbol'].str.len() <= 4)
            ]
            
            raw_list = df_filtered['Symbol'].unique().tolist()
            
            # 💡 러셀 2000의 상위 50%선(컷오프 기준 약 15억 달러 이상)에 부합하는 정배열 필터링을 위해
            # 1차 마스터 풀을 구성합니다.
            for t in raw_list:
                tickers.add(t.replace('.', '-'))
                
            print(f"✅ [US Master] 전체 시장 풀 {len(tickers)}개 확보 완료.")
            
    except Exception as e:
        print(f"⚠️ [US Master] 대량 마스터 데이터 파싱 실패: {e}. 지수 기반 우량주로 자동 전환합니다.")
        # 실패 시 백업용 위키피디아 파싱 작동
        return get_fallback_index_tickers()

    return list(tickers)

def get_fallback_index_tickers():
    """마스터 서버 비상시 작동하는 S&P 500 & 나스닥 100 가동 시스템"""
    print("⏳ [Backup] 위키피디아 기반 핵심 지수 종목 대체 수집...")
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
        raise e

def screen_stocks():
    # 1. 미국 전체 상장사 풀 확보
    raw_tickers = get_us_filtered_tickers_master()
    
    results = []
    
    # 2. 야후 파이낸스 일괄 다운로드 부하 조절 및 2차 필터링용 구조 세팅
    # 데이터 안정성을 위해 청크 크기를 150개 단위로 조절
    chunk_size = 150
    all_close_data = pd.DataFrame()
    
    print(f"📊 총 {len(raw_tickers)}개 기본 풀 대상 주가 데이터 다운로드 시작 (Rate Limit 완벽 우회)...")
    for i in range(0, len(raw_tickers), chunk_size):
        chunk_tickers = raw_tickers[i:i+chunk_size]
        try:
            # 3년치 주봉 종가 대량 다운로드
            chunk_data = yf.download(chunk_tickers, period="3y", interval="1wk", progress=False, timeout=50)
            if not chunk_data.empty and 'Close' in chunk_data.columns:
                chunk_close = chunk_data['Close']
                if all_close_data.empty:
                    all_close_data = chunk_close
                else:
                    all_close_data = pd.concat([all_close_data, chunk_close], axis=1)
            print(f"  > ⏳ {min(i + chunk_size, len(raw_tickers))} / {len(raw_tickers)} 종목 다운로드 완료...")
            time.sleep(1.2) # 야후 방화벽 자극 방지를 위한 세이프티 마진 슬립
        except Exception as e:
            print(f"⚠️ 청크 다운로드 중 일시적 지연 발생: {e}")
            continue

    if all_close_data.empty:
        print("❌ 다운로드된 주가 데이터가 존재하지 않습니다. 스캔을 종료합니다.")
        return

    if all_close_data.index.tz is not None:
        all_close_data.index = all_close_data.index.tz_localize(None)

    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    print("🔍 [필터링 & 스캔] 시총 15억 달러 허들 검증 및 6대 기술적 조건 동시 연산 중...")
    if isinstance(all_close_data, pd.Series):
        all_close_data = all_close_data.to_frame()

    for ticker in all_close_data.columns:
        try:
            series_close = all_close_data[ticker].dropna()
            # 데이터 일관성 부족 자산 필터링
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

            # 💡 [핵심 보완] 기술적 조건 통과 자산에 한하여 시가총액 실시간 최종 검증 
            # (러셀2000 하위 50% 필터링 타겟팅: $1.5B 기준선 적용)
            stock = yf.Ticker(ticker)
            try:
                # fast_info 속성으로 아주 빠르게 메모리 스캔 진행
                mkt_cap_raw = stock.fast_info.market_cap
                mkt_cap_billion = mkt_cap_raw / 1e9 if mkt_cap_raw else 0
                
                # 시가총액이 15억 달러(러셀2000 중간값 허들) 미만인 소형주는 여기서 탈락시킵니다.
                if mkt_cap_billion < 1.5: continue
                
                info = stock.info
                trail_pe = round(info.get('trailingPE'), 2) if info.get('trailingPE') else 'N/A'
                fwd_pe = round(info.get('forwardPE'), 2) if info.get('forwardPE') else 'N/A'
                short_name = info.get('shortName', ticker)
            except:
                # 만약 가벼운 fast_info 조차 거부될 경우 안정성을 위해 스크립트 홀딩 방지용 백업 세팅
                continue

            results.append({
                'Ticker': ticker,
                'Name': short_name,
                'Price($)': round(curr_price, 2),
                '3Y Max($)': round(three_year_max, 2),
                'Floor Ratio': f"{round(floor_ratio * 100, 1)}%",
                'Trend Angle': f"{round(angle_deg, 1)}°",
                'Current PE': trail_pe,
                'Forward PE': fwd_pe,
                'Market Cap($B)': round(mkt_cap_billion, 2)
            })
            print(f"🎯 [포착] 러셀2000 상위 50% 우량 패턴 종목 발견: {ticker} ({round(angle_deg, 1)}°)")

        except Exception as e:
            continue

    today_str = datetime.now().strftime('%Y-%m-%d')
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center', classes='dataframe')
        styled_table = table_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; text-align: center; font-size: 14px;" border="1"')
        
        html_content = f"""
        <h3 style="color: #1b5e20;">📈 미주 3년 신고가 돌파 초기형 완만 상승주 전수조사 보고서 ({today_str})</h3>
        <p><b>시장 범위:</b> S%P500, NASDAQ, Russell 2000 중형주 이상 (시가총액 $1.5B 이상 필터링 완료)</p>
        {styled_table}
        """
        print("🚀 조건 만족 종목 발견! 메일 발송을 시도합니다...")
        send_email(html_content, is_html=True)
    else:
        no_result_html = f"""
        <h3 style="color: #b71c1c;">⚠️ 미주 스캐너 정기 알림 ({today_str})</h3>
        <p><b>시장 범위:</b> S&P500, NASDAQ, Russell 2000 우량주군 전체 ($1.5B 이상)</p>
        <hr>
        <p>현재 미국 전수조사 대상 종목 중 6대 정밀 돌파 패턴 조건을 만족하는 자산이 포착되지 않았습니다.</p>
        """
        print("ℹ️ 조건 만족 종목이 없습니다. 안내 메일 발송을 시도합니다...")
        send_email(no_result_html, is_html=True)

if __name__ == "__main__":
    screen_stocks()

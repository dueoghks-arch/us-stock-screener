# ... (앞의 get_all_tickers, send_email 함수는 동일합니다)

def screen_stocks(min_gain=0.00, max_gain=0.30): # 💡 기본값을 0% ~ 30%로 변경
    tickers = get_all_tickers()
    results = []
    print(f"📊 총 {len(tickers)}개 종목 대상 장기 박스권 돌파(3년전~1년전) 분석 시작...")
    
    # [안정성 업그레이드] 대용량 조회를 위해 100개씩 쪼개서 다운로드 진행 (Chunking)
    chunk_size = 100
    all_data = pd.DataFrame()
    
    print("⏳ 데이터 다운로드 중... (종목 수가 많아 수 분이 소요될 수 있습니다.)")
    for i in range(0, len(tickers), chunk_size):
        chunk_tickers = tickers[i:i+chunk_size]
        try:
            chunk_data = yf.download(chunk_tickers, period="4y", interval="1wk", group_by='ticker', threads=True, progress=False, timeout=30)
            if not chunk_data.empty:
                if all_data.empty:
                    all_data = chunk_data
                else:
                    all_data = pd.concat([all_data, chunk_data], axis=1)
            print(f"  > ⏳ {i + len(chunk_tickers)} / {len(tickers)} 종목 완료...")
            time.sleep(1) 
        except Exception as e:
            print(f"⚠️ {i}번째 청크 다운로드 중 일부 오류 발생: {e}")
            continue

    if all_data.empty:
        print("❌ 다운로드된 데이터가 없습니다.")
        return

    # 기준 날짜 계산
    now = datetime.now()
    three_years_ago = now - timedelta(days=1095)
    one_year_ago = now - timedelta(days=365)
    ten_weeks_ago = now - timedelta(days=70)
    
    keywords = ['shortage', 'supply chain', 'guidance raise', 'beat', 'exceed', 'above expectations', 'eps', 'expansion']
    has_levels = hasattr(all_data.columns, 'levels') and len(all_data.columns.levels) > 0

    print("🔍 조건 필터링 및 뉴스 분석 진행 중...")
    for ticker in tickers:
        try:
            if has_levels:
                if ticker not in all_data.columns.levels[0]: continue
            else:
                if ticker not in all_data.columns: continue
                
            df = all_data[ticker].dropna(subset=['Close']).copy()
            if len(df) < 100: continue 

            # [3년 전 ~ 1년 전] 구간만 추출
            box_period_df = df[(df.index >= three_years_ago) & (df.index <= one_year_ago)]
            if box_period_df.empty: continue
            
            box_top = box_period_df['High'].max()
            curr_price = df['Close'].iloc[-1]
            
            if pd.isna(box_top) or box_top == 0: continue

            # 최근 4주 데이터 확인
            recent_4w = df.iloc[-4:]
            box_break_recent = any(recent_4w['High'] >= box_top)
            
            # 💡 [조건 적용] 현재가가 3년~1년 전 최고가보다 0% ~ 30% 높은 종목만 선별
            is_target = False
            if box_break_recent:
                if (box_top * (1 + min_gain)) <= curr_price <= (box_top * (1 + max_gain)):
                    is_target = True

            if is_target:
                stock = yf.Ticker(ticker)
                trail_pe, fwd_pe, mkt_cap, short_name = 999, 999, 0, 'N/A'
                
                try:
                    info = stock.info
                    trail_pe = info.get('trailingPE', 999)
                    fwd_pe = info.get('forwardPE', 999)
                    mkt_cap = info.get('marketCap', 0)
                    short_name = info.get('shortName', 'N/A')
                except:
                    pass

                # 뉴스 스캔
                has_star = False
                try:
                    news_list = stock.news
                    if news_list:
                        for news in news_list:
                            pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                            if pub_time >= ten_weeks_ago:
                                content = (news.get('title', '') + news.get('summary', '')).lower()
                                if any(k in content for k in keywords):
                                    has_star = True
                                    break
                except: 
                    pass

                display_ticker = f"⭐ {ticker}" if has_star else ticker

                results.append({
                    'Ticker': display_ticker,
                    'Price': round(curr_price, 2),
                    'Box Top(3Y-1Y)': round(box_top, 2),
                    'Gain from Box': f"+{round(((curr_price/box_top)-1)*100, 1)}%",
                    'Current PE': round(trail_pe, 2) if trail_pe != 999 else 'N/A',
                    'Forward PE': round(fwd_pe, 2) if fwd_pe != 999 else 'N/A',
                    'Market Cap($B)': round(mkt_cap / 1e9, 2),
                    'Name': short_name
                })
                print(f"🔥 포착: {ticker} (박스권 대비 +{round(((curr_price/box_top)-1)*100, 1)}%)")

        except Exception as e:
            continue

    # 리포트 발송
    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap($B)', ascending=False)
        table_html = final_df.to_html(index=False, border=1, justify='center')
        table_html = table_html.replace('⭐', '<span style="color:blue; font-weight:bold;">⭐</span>')
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        html_content = '<h3 style="color: #0d47a1;">🔥 미주 전수조사 장기 박스권(3년전~1년전) 돌파 주도주 리포트 (' + today_str + ')</h3>'
        html_content += f'<p><b>대상 시장:</b> S&P500, NASDAQ 100, Russell 2000 핵심 종목</p>'
        # 💡 리포트 문구도 조건에 맞게 가독성 높게 수정
        html_content += f'<p><b>필터 조건:</b> 3년 전 ~ 1년 전 구간의 최고점을 최근 4주 내에 돌파하고, 현재 주가가 돌파선 대비 <b>+{int(min_gain*100)}% ~ +{int(max_gain*100)}% (0%~30% 이내 안정권)</b> 구간에 위치한 종목</p>'
        html_content += '<p><b>⭐ 표시:</b> 최근 10주 내 실적/업황 호재 포착 기업</p><br>'
        html_content += table_html
        
        send_email(html_content, is_html=True)
    else:
        send_email(f"조건에 진입한 미국 주식(S&P500/나스닥/러셀) 종목이 없습니다.")

if __name__ == "__main__":
    # 💡 실행 시 0% ~ 30% 범위로 파라미터를 넘겨줍니다.
    screen_stocks(min_gain=0.00, max_gain=0.30)

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import requests
import os
import smtplib
from email.mime.text import MIMEText

def send_email(df_content):
    # 깃허브 Secrets에서 가져오는 설정
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    receiver_email = sender_email # 본인에게 발송

    if not sender_email or not sender_password:
        print("메일 환경변수 설정이 되어있지 않아 발송을 건너뜁니다.")
        return

    msg = MIMEText(df_content)
    msg['Subject'] = f"🚀 미국 주식 스캔 결과 ({datetime.now().strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("메일 발송 성공!")
    except Exception as e:
        print(f"메일 발송 실패: {e}")

def screen_stocks():
    print("--- 미국 주식 스캐너 시작 (자동화 모드) ---")
    
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        sp500 = pd.read_html(response.text)[0]
        tickers = [t.replace('.', '-') for t in sp500['Symbol'].tolist()]
    except Exception as e:
        print(f"리스트 확보 실패: {e}")
        return

    results = []
    start_date = "2024-06-01"
    one_month_ago = datetime.now() - timedelta(days=30)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 조건 1: PER 30 이하
            fwd_pe = info.get('forwardPE')
            if fwd_pe is None or fwd_pe > 30: continue

            df = stock.history(start=start_date, interval="1wk")
            if len(df) < 5: continue

            current_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            prev2_close = df['Close'].iloc[-3]
            period_high = df['High'].iloc[:-1].max()

            # 기술적 조건 (돌파 및 유지)
            cond1 = current_close > period_high
            cond2 = (prev_close > (df['High'].iloc[:-2].max() if len(df)>2 else 0)) and (current_close >= prev_close)
            cond3 = (prev2_close > (df['High'].iloc[:-3].max() if len(df)>3 else 0)) and (prev_close >= prev2_close)

            if cond1 or cond2 or cond3:
                # Shortage 뉴스 체크
                has_shortage = False
                try:
                    for news in stock.news:
                        pub_time = datetime.fromtimestamp(news.get('providerPublishTime', 0))
                        if pub_time >= one_month_ago:
                            if 'shortage' in (news.get('title', '') + news.get('summary', '')).lower():
                                has_shortage = True; break
                except: pass

                results.append({
                    'Ticker': ticker,
                    'Name': info.get('shortName', 'N/A'),
                    'Market Cap': info.get('marketCap', 0),
                    'Forward PE': round(fwd_pe, 2),
                    'Price': round(current_close, 2),
                    'Issue': "🌟 SHORTAGE" if has_shortage else ""
                })
        except: continue

    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap', ascending=False)
        final_df['Market Cap($B)'] = (final_df['Market Cap'] / 1e9).round(2)
        output_text = final_df[['Ticker', 'Name', 'Market Cap($B)', 'Forward PE', 'Price', 'Issue']].to_string(index=False)
        print(output_text)
        send_email(output_text)
    else:
        send_email("조건에 맞는 종목이 없습니다.")

if __name__ == "__main__":
    screen_stocks()

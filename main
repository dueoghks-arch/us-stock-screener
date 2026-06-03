import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import requests
import os
import smtplib
from email.mime.text import MIMEText

def send_email(content):
    sender = os.environ.get('EMAIL_USER')
    password = os.environ.get('EMAIL_PASS')
    receiver = sender  # 본인에게 보냄

    if not sender or not password: return
    
    msg = MIMEText(content)
    msg['Subject'] = f"🚀 Stock Scan: {datetime.now().strftime('%Y-%m-%d')}"
    msg['From'] = sender
    msg['To'] = receiver

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())

def screen_stocks():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    sp500 = pd.read_html(response.text)[0]
    tickers = [t.replace('.', '-') for t in sp500['Symbol'].tolist()]

    results = []
    start_date = "2024-06-01"
    one_month_ago = datetime.now() - timedelta(days=30)

    for ticker in tickers[:100]: # 테스트를 위해 100개만, 성공 확인 후 tickers로 변경 추천
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            fwd_pe = info.get('forwardPE')
            if fwd_pe is None or fwd_pe > 30: continue

            df = stock.history(start=start_date, interval="1wk")
            if len(df) < 5: continue

            current_close = df['Close'].iloc[-1]
            period_high = df['High'].iloc[:-1].max()

            if current_close > period_high: # 가장 깔끔한 조건1만 일단 적용
                results.append({
                    'Ticker': ticker,
                    'Market Cap': info.get('marketCap', 0),
                    'PE': round(fwd_pe, 2),  
                    'Price': round(current_close, 2)
                })
        except: continue

    if results:
        final_df = pd.DataFrame(results).sort_values(by='Market Cap', ascending=False)
        send_email(final_df.to_string(index=False))
        print("메일 발송 완료")

if __name__ == "__main__":
    screen_stocks()

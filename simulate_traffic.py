import boto3
import json
import time
import random
# Create a session using your custom profile, then spawn the S3 client from it
session = boto3.Session(profile_name='momentum-dev')
s3 = session.client('s3')
RAW_BUCKET = "momentum-intel-lakehouse-raw-stage"

tickers = ["ZETA", "ASTS", "PLTR", "SOFI", "HOOD"]
catalysts = ["Earnings beat by 15%", "CEO stepped down", "FDA approval secured", "Guidance lowered"]

print("Initiating simulated market feed...")

for i in range(5):
    # Generate a fake news snippet
    ticker = random.choice(tickers)
    news = f"{ticker} just announced: {random.choice(catalysts)}. Trading volume is surging."
    
    file_name = f"raw_source_files/market_flash_{int(time.time())}_{i}.json"
    payload = json.dumps({"source": "Bloomberg", "raw_text": news})
    
    # Push to S3
    s3.put_object(Bucket=RAW_BUCKET, Key=file_name, Body=payload)
    print(f"Pushed {ticker} update to Lakehouse...")
    
    time.sleep(15) # Stagger the uploads slightly

print("Simulation complete. Refresh your web dashboard in 60 seconds!")
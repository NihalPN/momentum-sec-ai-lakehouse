import json
import boto3
import os
import time
# ⚙️ UPDATED: Importing the native Gemini Extractor engine cleanly
from src.extractors.gemini_extractor import GeminiExtractor

s3_client = boto3.client('s3')

STRUCTURED_BUCKET = os.environ.get(
    "STRUCTURED_STAGE_BUCKET", 
    "momentum-intel-lakehouse-structured-stage"
)

def handler(event, context):
    print(f"[START] Processing S3 Ingestion Event batch containing {len(event['Records'])} record(s).")
    
    # ⚙️ UPDATED: Instantiating the Gemini engine
    extractor = GeminiExtractor()
    processed_count = 0

    for record in event['Records']:
        raw_bucket = record['s3']['bucket']['name']
        file_key = record['s3']['object']['key']
        
        print(f"[PROCESSING] Fetching raw file from S3: s3://{raw_bucket}/{file_key}")
        
        try:
            s3_response = s3_client.get_object(Bucket=raw_bucket, Key=file_key)
            raw_content = json.loads(s3_response['Body'].read().decode('utf-8'))
            
            raw_text = raw_content.get('raw_text', raw_content.get('text', str(raw_content)))
            ticker_fallback = raw_content.get('ticker', 'UNKNOWN')
            
        except Exception as e:
            print(f"[CRITICAL ERROR] Failed to read or parse source S3 file {file_key}: {e}")
            raise e

        # ⚙️ UPDATED: Tracking the Gemini execution pipeline path
        print(f"[LLM INFERENCE] Sending text payload to Gemini Flash engine...")
        try:
            structured_data = extractor.extract_momentum_data(raw_text)
        except Exception as e:
            print(f"[UPSTREAM ERROR] Extraction pipeline failed for file {file_key}: {e}")
            raise e

        if not structured_data or not isinstance(structured_data, dict):
            print(f"[SKIPPED] File {file_key} generated null or non-dictionary data block. Aborting ingestion path.")
            continue

        ingestion_timestamp = int(time.time())
        structured_data['source_file'] = file_key
        structured_data['processed_at'] = ingestion_timestamp
        structured_data['raw_text'] = raw_text
        if structured_data.get('ticker') in ['string', '', None, 'AAPL']:
            structured_data['ticker'] = ticker_fallback

        clean_ticker = ''.join(c for c in structured_data['ticker'] if c.isalnum()).upper()
        destination_key = f"modeled_sentiment/ticker={clean_ticker}/{ingestion_timestamp}_analytics.json"
        
        print(f"[STORE] Writing structured analytical model to: s3://{STRUCTURED_BUCKET}/{destination_key}")
        
        try:
            s3_client.put_object(
                Bucket=STRUCTURED_BUCKET,
                Key=destination_key,
                Body=json.dumps(structured_data),
                ContentType="application/json"
            )
            processed_count += 1
        except Exception as e:
            print(f"[CRITICAL ERROR] S3 write operation failed for destination key {destination_key}: {e}")
            raise e

    print(f"[COMPLETED] Batch extraction runtime finished successfully. Processed rows: {processed_count}/{len(event['Records'])}")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Batch processed successfully",
            "records_written": processed_count
        })
    }
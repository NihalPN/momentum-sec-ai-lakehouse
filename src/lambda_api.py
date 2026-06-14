import json
import boto3
import time
import os

# Initialize BOTH clients
athena = boto3.client('athena')
s3_client = boto3.client('s3') # <-- ADDED THIS

DATABASE = os.environ.get('DATABASE_NAME', 'momentum-intel-lakehouse_db')
OUTPUT_LOCATION = os.environ.get('ATHENA_OUTPUT_LOCATION', 's3://momentum-intel-lakehouse-structured-stage/athena_results/')

def handler(event, context):
    query = """
        SELECT 
            ticker, 
            momentum_sentiment, 
            confidence_score, 
            ai_summary, 
            original_text,
            source_entity,
            source_file
        FROM modeled_sentiment
        WHERE ticker IS NOT NULL
        LIMIT 50;
    """

    try:
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': DATABASE},
            ResultConfiguration={'OutputLocation': OUTPUT_LOCATION}
        )
        query_id = response['QueryExecutionId']

        while True:
            status = athena.get_query_execution(QueryExecutionId=query_id)
            state = status['QueryExecution']['Status']['State']
            if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                break
            time.sleep(0.5)

        if state != 'SUCCEEDED':
            error_msg = status['QueryExecution']['Status'].get('StateChangeReason', 'Unknown Error')
            return {"statusCode": 500, "body": json.dumps({"error": f"Athena Query Failed: {state} - {error_msg}"})}

        results = athena.get_query_results(QueryExecutionId=query_id)
        rows = results['ResultSet']['Rows']

        data = []
        for row in rows[1:]:
            cols = row['Data']
            
            # Extract the raw S3 path
            source_file_path = cols[6].get('VarCharValue', '')
            download_url = None
            
            # Generate a temporary secure download link if the path exists
            if source_file_path.startswith("s3://"):
                try:
                    parts = source_file_path.replace("s3://", "").split("/")
                    bucket_name = parts[0]
                    object_key = "/".join(parts[1:])
                    
                    # FIXED: Use s3_client instead of athena
                    download_url = s3_client.generate_presigned_url( 
                        ClientMethod='get_object',
                        Params={'Bucket': bucket_name, 'Key': object_key},
                        ExpiresIn=3600 # Link dies in 1 hour for security
                    )
                except Exception as e:
                    print(f"Failed to generate URL: {e}")
                    download_url = None

            data.append({
                "ticker": cols[0].get('VarCharValue', 'UNKNOWN'),
                "momentum_sentiment": float(cols[1].get('VarCharValue', 0)),
                "confidence_score": float(cols[2].get('VarCharValue', 0)),
                "ai_summary": cols[3].get('VarCharValue', 'No summary generated.'),
                "original_text": cols[4].get('VarCharValue', 'No original text available.'),
                "source_entity": cols[5].get('VarCharValue', 'Unknown Source'),
                "source_file": source_file_path,
                "download_url": download_url
            })

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"status": "success", "data": data})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
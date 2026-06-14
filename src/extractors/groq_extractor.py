import json
import requests
import time
from src.config import Config

class GroqExtractor:
    def __init__(self):
        self.url = Config.GROQ_URL
        self.headers = {
            "Authorization": f"Bearer {Config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        self.model = "llama-3.3-70b-versatile" 

    def extract_momentum_data(self, raw_text: str) -> dict:
        optimized_text = raw_text[:40000] if len(raw_text) > 40000 else raw_text

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict quantitative financial extraction API. "
                        "You must extract data from the provided text and output ONLY a valid JSON object. "
                        "Do NOT use placeholder words like 'string'. Use actual extracted values. "
                        "Follow this exact schema format:\n\n"
                        "{\n"
                        "  \"ticker\": \"AAPL\",  // MUST be the extracted Company Name or Ticker\n"
                        "  \"momentum_sentiment\": 0.85,  // Float between -1.0 (bearish) and 1.0 (bullish)\n"
                        "  \"confidence_score\": 0.95,  // Float between 0.0 and 1.0 representing your confidence\n"
                        "  \"catalyst_mentioned\": \"Company secured FDA approval\",\n"
                        "  \"source_entity\": \"SEC EDGAR 8-K\",  // Identify the source type\n"
                        "  \"ai_summary\": \"Write a detailed, 3-4 sentence analytical paragraph explaining the financial impact.\"\n"
                        "}"
                    )
                },
                {
                    "role": "user",
                    "content": f"Extract financial metadata from this filing text:\n\n{optimized_text}"
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        max_retries = 4
        base_delay = 4 # Seconds to wait before first retry

        for attempt in range(max_retries):
            try:
                response = requests.post(self.url, json=payload, headers=self.headers, timeout=45)
                
                # 🛡️ THE FIX: Catch Rate Limits and Retry
                if response.status_code == 429:
                    wait_time = base_delay * (2 ** attempt)
                    print(f"[Rate Limit] Groq API saturated. Retrying in {wait_time} seconds (Attempt {attempt + 1})...")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                generated_content = response.json()['choices'][0]['message']['content']
                return json.loads(generated_content)
                
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Network failure on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    # If it fails completely, RAISE the error so Lambda doesn't drop the S3 event
                    raise Exception(f"Groq Extraction failed after {max_retries} attempts.")
                time.sleep(base_delay * (2 ** attempt))
                
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                print(f"[ERROR] Execution failed to parse valid JSON metadata: {e}")
                return {} # Bad data from the LLM, don't retry this
                
        return {}
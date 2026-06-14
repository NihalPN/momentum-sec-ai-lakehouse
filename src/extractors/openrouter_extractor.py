import json
import requests
import time
from ..config import Config

class OpenRouterExtractor:
    def __init__(self):
        # Your new OpenRouter endpoint
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}", 
            "Content-Type": "application/json"
        }
        # The exact free Gemma model you tested
        self.model = "google/gemma-4-31b-it:free"

    def extract_momentum_data(self, raw_text: str) -> dict:
        optimized_text = raw_text[:40000] if len(raw_text) > 40000 else raw_text

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict quantitative financial extraction engine. "
                        "Your job is to read raw regulatory filings, parse corporate catalysts, and evaluate short-term momentum signals.\n"
                        "You must extract data from the provided text and output ONLY a valid JSON object matching the exact schema example below. "
                        "Do NOT output markdown wrappers, comments, conversational text, or data type placeholders like 'string' or '0.0'.\n\n"
                        "EXPECTED SCHEMA FORMAT EXAMPLAR:\n"
                        "{\n"
                        "  \"ticker\": \"CORTEVA\",\n"
                        "  \"momentum_sentiment\": 0.45,\n"
                        "  \"confidence_score\": 0.90,\n"
                        "  \"catalyst_mentioned\": \"Strategic restructuring program and manufacturing asset impairment alignment.\",\n"
                        "  \"source_entity\": \"SEC EDGAR 8-K\",\n"
                        "  \"ai_summary\": \"Corteva announced an operational update detailing structural modifications and asset exit actions. While incurring non-cash charges up to $220M, the alignment targets run-rate savings of $100M by year-end, yielding a net-positive momentum velocity structure for enterprise margins.\"\n"
                        "}"
                    )
                },
                {
                    "role": "user",
                    "content": f"Execute deep data extraction on this file body:\n\n{optimized_text}"
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            # 🧠 Integrating your reasoning flag for deeper financial logic
            "reasoning": {"enabled": True}
        }

        max_retries = 4
        base_delay = 4

        for attempt in range(max_retries):
            try:
                response = requests.post(self.url, json=payload, headers=self.headers, timeout=60)
                
                # OpenRouter might throw 429s on the free tier, backoff is critical here
                if response.status_code == 429:
                    wait_time = base_delay * (2 ** attempt)
                    print(f"[RATE LIMIT] OpenRouter endpoint saturated. Pausing for {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                
                # OpenRouter returns standard content in the message block
                generated_content = response.json()['choices'][0]['message']['content']
                return json.loads(generated_content)
                
            except requests.exceptions.RequestException as e:
                print(f"[RETRY LOG] Network execution barrier on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise Exception(f"Upstream pipeline failed permanently.")
                time.sleep(base_delay * (2 ** attempt))
                
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                print(f"[PARSE ERROR] Gemma inference returned un-parsable data format: {e}")
                return {} 
                
        return {}
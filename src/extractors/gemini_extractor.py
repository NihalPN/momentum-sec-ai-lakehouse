import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from ..config import Config

# 📊 Define the strict output schema using Pydantic to pass directly to the SDK
class MomentumAnalysis(BaseModel):
    ticker: str = Field(description="The stock ticker or corporate entity identifier extracted from the filing (e.g., AAPL, CORTEVA).")
    momentum_sentiment: float = Field(description="Quantitative sentiment score from -1.0 (highly negative/bearish) to +1.0 (highly positive/bullish).")
    confidence_score: float = Field(description="Confidence value from 0.0 to 1.0 indicating structural precision of data extraction.")
    catalyst_mentioned: str = Field(description="Brief string highlighting the primary core business event triggering the filing (e.g., restructuring, earnings guidance adjustment, asset impairment).")
    source_entity: str = Field(description="The source provenance identifier. Always set this strictly to 'SEC EDGAR 8-K'.")
    ai_summary: str = Field(description="A concise executive summary outlining the operational update, financial velocity impacts, and balance-sheet alignment details.")

class GeminiExtractor:
    def __init__(self):
        # 🤖 Initialize the official modern GenAI client
        # The SDK automatically detects the GEMINI_API_KEY environment variable.
        # If your keys are bound to Config, we pass it explicitly to prevent initialization failure.
        api_key = getattr(Config, "GEMINI_API_KEY", None)
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()
            
        # 🏎️ Use the modern 3.1 Flash-Lite engine targeted for high-volume pipelines
        self.model = "gemini-3.1-flash-lite"

    def extract_momentum_data(self, raw_text: str) -> dict:
        """
        Parses raw filing bodies and extracts structured metrics via Gemini 3.1 Flash-Lite.
        """
        # Trim extreme text blocks to guard the token budget space gracefully
        optimized_text = raw_text[:60000] if len(raw_text) > 60000 else raw_text

        system_instruction = (
            "You are a specialized quantitative financial intelligence parser. Your objective is to extract "
            "actionable catalyst metrics and short-term momentum signals from raw regulatory corporate disclosures. "
            "You must populate every single required schema property with accurate factual data derived exclusively from the source text."
        )

        user_content = f"Execute deep qualitative-to-quantitative extraction on this regulatory filing text:\n\n{optimized_text}"

        # ⚙️ Configuration block implementing Pydantic validation and internal chain-of-thought
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            # 🛠️ THE FIX: Evaluate the Pydantic class into a standard dictionary schema
            response_schema=MomentumAnalysis.model_json_schema(),
            temperature=0.0,  
            thinking_config=types.ThinkingConfig(
                thinking_level="high" 
            )
        )

        max_retries = 3
        base_delay = 4

        for attempt in range(max_retries):
            try:
                # Dispatch the call to Google's inference backend
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_content,
                    config=config
                )
                
                if not response.text:
                    print(f"[WARN] Empty string payload generated on attempt {attempt + 1}.")
                    continue
                
                # Parse the validated JSON object safely back to the lakehouse processor
                return json.loads(response.text)

            except Exception as e:
                print(f"[RETRY LOG] Gemini API execution barrier on attempt {attempt + 1}: {e}")
                if "429" in str(e):
                    # Gracefully absorb individual or shared-pool rate throttling limits
                    wait_time = base_delay * (2 ** attempt)
                    print(f"[THROTTLE] Rate limit saturated. Pausing execution pipeline for {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    time.sleep(base_delay)
                
                if attempt == max_retries - 1:
                    print("[CRITICAL ERROR] All retry channels exhausted for current payload segment.")
                    raise e
                    
        return {}
import os

class Config:
    # AWS Lambda reads this natively from your Cloud Configuration.
    # No dotenv library required!
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
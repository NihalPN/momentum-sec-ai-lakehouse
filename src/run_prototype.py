import json
from src.extractors.groq_extractor import GroqExtractor

def run_pipeline():
    # Example raw unstructured post text 
    mock_scraped_feed = (
        "Insane volume spike on $BiotechCorp (BTCX) this morning. Up 24% on massive momentum "
        "after they dropped a press release confirming their Phase 2 clinical trials met all "
        "primary endpoints. Shorts are getting absolutely fried here, easily heading to $15 by Friday."
    )
    
    print("====================================================")
    print("INITIALIZING LOCAL MOMENTUM LAKEHOUSE RUNTIME")
    print("====================================================\n")
    print(f"[Step 1: Raw Ingestion Simulation]\nContent:\n{mock_scraped_feed}\n")
    
    # Initialize our modular extractor
    extractor = GroqExtractor()
    
    print("[Step 2: Processing via Groq LPU Core...]")
    structured_output = extractor.extract_momentum_data(mock_scraped_feed)
    
    print("\n[Step 3: Output Generated for Athena Lakehouse Catalog]")
    print(json.dumps(structured_data := structured_output, indent=4))
    print("\n====================================================")
    print("PROTOTYPE RUN COMPLETE: Execution Successful.")
    print("====================================================")

if __name__ == "__main__":
    run_pipeline()
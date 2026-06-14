import requests
import xml.etree.ElementTree as ET
import boto3
import json
import time
import re
from bs4 import BeautifulSoup

# 1. Configuration
HEADERS = {'User-Agent': 'Muhammed Nihal (momentum.pipeline@example.com)'} 
SEC_ATOM_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-k&count=10&output=atom"

# AWS Setup 
session = boto3.Session(profile_name='momentum-dev')
s3_client = session.client('s3')
RAW_BUCKET_NAME = "momentum-intel-lakehouse-raw-stage" 

def extract_full_sec_document(index_url):
    """
    The Harvester Logic - UPDATED TO BYPASS iXBRL TRAP
    """
    try:
        time.sleep(0.5) 
        res = requests.get(index_url, headers=HEADERS)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')
        
        doc_table = soup.find('table', class_='tableFile')
        if not doc_table:
            return None
            
        doc_url = None
        # Loop through rows to find the primary document (skip header row)
        for row in doc_table.find_all('tr')[1:]: 
            cols = row.find_all('td')
            if len(cols) >= 3:
                a_tag = cols[2].find('a', href=True)
                if a_tag:
                    href = a_tag['href']
                    
                    # 💥 THE FIX: Strip the Interactive XBRL Javascript Viewer
                    if href.startswith('/ix?doc='):
                        href = href.replace('/ix?doc=', '')
                    
                    # Target the actual raw HTML or TXT document
                    if href.endswith('.htm') or href.endswith('.html') or href.endswith('.txt'):
                        doc_url = "https://www.sec.gov" + href
                        break
                        
        if not doc_url:
            return None
            
        time.sleep(12)
        doc_res = requests.get(doc_url, headers=HEADERS)
        doc_res.raise_for_status()
        
        doc_soup = BeautifulSoup(doc_res.content, 'html.parser')
        clean_text = doc_soup.get_text(separator=' ', strip=True)
        
        if len(clean_text) < 100:
            return None
            
        return clean_text
    except Exception as e:
        print(f"   [Scrape Error] Failed to harvest full document: {e}")
        return None

def fetch_historical_sec_filings():
    print("[SEC Harvester] Polling EDGAR for the 10 most recent 8-K filings...")
    try:
        response = requests.get(SEC_ATOM_URL, headers=HEADERS)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        filings = []
        entries = root.findall('atom:entry', ns)
        
        for entry in entries:
            title = entry.find('atom:title', ns).text
            link = entry.find('atom:link', ns).attrib['href']
            updated = entry.find('atom:updated', ns).text
            
            # Bulletproof Company Name Extraction using Regex
            company_name = "UNKNOWN"
            match = re.search(r'-\s*(.*?)\s*\(', title)
            if match:
                company_name = match.group(1).strip()
            else:
                company_name = title[:30] 
            
            print(f" > Harvesting full 50-page text for: {company_name}...")
            
            # Fire the Harvester Web Scraper
            full_text = extract_full_sec_document(link)
            
            # Fallback to the short summary if the scraper fails
            if not full_text or len(full_text) < 100:
                print(f"   [Warning] Extraction too short. Falling back to summary.")
                summary_element = entry.find('atom:summary', ns)
                full_text = summary_element.text if summary_element is not None else "Material event filed."
                
            filings.append({
                "ticker": company_name, 
                "source": "SEC EDGAR 8-K",
                "title": title,
                "url": link,
                "published": updated,
                "raw_text": full_text 
            })
            
        return filings
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch SEC data: {e}")
        return []

def push_to_lakehouse(filings):
    for filing in filings:
        safe_name = filing['ticker'].replace(" ", "_").replace(",", "").replace(".", "").replace("/", "")
        timestamp = int(time.time() * 1000)
        filename = f"{safe_name}_SEC_{timestamp}.json"
        
        print(f"[S3 Upload] Dropping {filename} into raw bucket...")
        
        s3_client.put_object(
            Bucket=RAW_BUCKET_NAME,
            Key=f"raw_source_files/{filename}",
            Body=json.dumps(filing),
            ContentType="application/json"
        )
        # 🏎️ THE FIX: Sped up from 12 seconds to 4.5 seconds for the 15 RPM limit
        time.sleep(6)

if __name__ == "__main__":
    print("=========================================")
    print("  DEEP-HARVEST SEC INGESTION INITIALIZED")
    print("=========================================\n")
    
    historical_data = fetch_historical_sec_filings()
    
    if historical_data:
        print(f"\n[INFO] Successfully harvested {len(historical_data)} massive filings.")
        push_to_lakehouse(historical_data)
        print("\n[SUCCESS] Data injected into Lakehouse. Groq LPU is now analyzing the full texts!")
    else:
        print("\n[INFO] Feed pull failed.")
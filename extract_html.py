import os
import re

log_path = r'C:\Users\Happy\.gemini\antigravity\brain\d2d280cf-bbea-4ec0-bc3e-be612902088a\.system_generated\logs\overview.txt'
out_path = r'c:\Users\Happy\Downloads\fact-claim-verifier-v10\fact-claim-verifier\frontend\public\standalone.html'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Find the last USER_REQUEST that contains the HTML
matches = re.finditer(r'<USER_REQUEST>\s*run this(.*?)</USER_REQUEST>', text, re.DOTALL)
last_match = list(matches)[-1].group(1).strip()

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(last_match)

print(f"Saved {len(last_match)} bytes to {out_path}")

import re

text = """
Models & Quota
Account: tanya73e39gagne03@gmail.com

GEMINI MODELS
Models within this group: Gemini Flash, Gemini Pro

Weekly Limit
  [||||||||||||||...................................] 7.78%
  8% remaining . Refreshes in 105h 20m

Five Hour Limit
  [||||||||||||||||||||||||||||||||||||||...........] 50.97%
  51% remaining . Refreshes in 1h 24m

CLAUDE AND GPT MODELS
Models within this group: Claude Opus, Claude Sonnet, GPT-OSS

Weekly Limit
  [|||||||||||||||||||||||||||||||||||||||||||||||||] 100.00%
  Quota available
"""

def parse_quota(text):
    data = {"account": "", "groups": []}
    acc_match = re.search(r"Account:\s*([^\n]+)", text)
    if acc_match:
        data["account"] = acc_match.group(1).strip()
        
    blocks = text.split("\n\n")
    current_group = None
    
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        lines = [line.strip() for line in block.split('\n')]
        
        if "MODELS" in lines[0]:
            current_group = {"name": lines[0], "models": "", "limits": []}
            if len(lines) > 1 and "within this group:" in lines[1]:
                current_group["models"] = lines[1].split("group:")[1].strip()
            data["groups"].append(current_group)
        elif "Limit" in lines[0] and current_group is not None:
            limit_name = lines[0]
            pct_str = "100"
            if len(lines) > 1 and "]" in lines[1]:
                pct_str = lines[1].split("]")[-1].replace("%", "").strip()
            
            info = ""
            if len(lines) > 2:
                info = lines[2]
                
            try:
                pct = float(pct_str)
            except:
                pct = 100.0
                
            current_group["limits"].append({
                "name": limit_name,
                "percent": pct,
                "info": info
            })
            
    return data

import json
print(json.dumps(parse_quota(text), indent=2))

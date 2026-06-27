import subprocess
import re

def parse_agy_quota():
    try:
        proc = subprocess.run(["agy", "models"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        output = proc.stdout
    except Exception:
        return {"success": False, "error": "Failed to run agy models"}
        
    if proc.returncode != 0:
        return {"success": False, "error": "Not authenticated or agy models failed"}
        
    quota = {"account": "", "groups": []}
    
    # Extract account
    acc_match = re.search(r'Account:\s*([^\n]+)', output)
    if acc_match:
        quota["account"] = acc_match.group(1).strip()
        
    # Split into groups (split by double newline, or look for ALL CAPS lines followed by Models within this group)
    lines = output.split('\n')
    current_group = None
    current_limit = None
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for group title (e.g. GEMINI MODELS) followed by "Models within this group"
        if re.match(r'^[A-Z0-9\s]+$', line.strip()) and len(line.strip()) > 0 and i + 1 < len(lines) and "Models within this group:" in lines[i+1]:
            if current_group:
                if current_limit:
                    current_group["limits"].append(current_limit)
                    current_limit = None
                quota["groups"].append(current_group)
            
            group_name = line.strip()
            models_str = lines[i+1].split("Models within this group:")[1].strip()
            current_group = {"name": group_name, "models": models_str, "limits": []}
            i += 2
            continue
            
        # Look for Limit title (e.g. Weekly Limit)
        if current_group and re.match(r'^[A-Za-z\s]+Limit$', line.strip()):
            if current_limit:
                current_group["limits"].append(current_limit)
            
            limit_name = line.strip()
            # Next line should be the progress bar [============] 100.00%
            if i + 1 < len(lines) and "[" in lines[i+1] and "%" in lines[i+1]:
                pct_match = re.search(r'([0-9\.]+)%', lines[i+1])
                pct = float(pct_match.group(1)) if pct_match else 0.0
                used = 100.0 - pct
                
                # Next line might be description (e.g. Quota available)
                desc = lines[i+2].strip() if i + 2 < len(lines) else ""
                
                color = "#22c55e" # Green
                if used > 90:
                    color = "#ef4444" # Red
                elif used > 75:
                    color = "#f59e0b" # Orange
                    
                current_limit = {
                    "name": limit_name,
                    "used": used,
                    "color": color,
                    "description": desc
                }
                i += 3
                continue
        
        i += 1
        
    if current_group:
        if current_limit:
            current_group["limits"].append(current_limit)
        quota["groups"].append(current_group)
        
    return {"success": True, "quota": quota}

if __name__ == "__main__":
    import json
    print(json.dumps(parse_agy_quota(), indent=2))

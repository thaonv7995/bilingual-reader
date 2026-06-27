import re

def get_auth_quota_impl(app, is_agy_authenticated, get_agy_binary):
    @app.get("/api/auth/quota")
    def get_auth_quota():
        import subprocess
        logged_in = is_agy_authenticated(force=False)
        if not logged_in:
            return {"success": False, "error": "Not authenticated"}
            
        agy_bin = get_agy_binary()
        try:
            proc = subprocess.run(
                [agy_bin, "models"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15
            )
            if proc.returncode != 0:
                return {"success": False, "error": f"CLI error: {proc.stderr or proc.stdout}"}
                
            # Clean ansi escapes
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            text = ansi_escape.sub('', proc.stdout)
            
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
                
                if "MODELS" in lines[0].upper() or "MODELS" in lines[0]:
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
                    
            return {"success": True, "quota": data}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Request to CLI timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

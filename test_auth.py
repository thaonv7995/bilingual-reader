import sys, time
sys.path.insert(0, 'application/backend')
from books_cli.server import is_agy_authenticated, get_token_path, get_agy_binary, _auth_cache
import subprocess

now = time.time()
print("token_file exists:", get_token_path().is_file())

agy_bin = get_agy_binary()
print("agy_bin:", agy_bin)
try:
    proc = subprocess.run(
        [agy_bin, "models"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5
    )
    print("Return code:", proc.returncode)
    print("Stdout length:", len(proc.stdout))
    print("Stdout content snippet:", repr(proc.stdout[:100]))
    is_auth = (proc.returncode == 0) and any(m in proc.stdout for m in ["Gemini", "Claude", "GPT"])
    print("is_auth:", is_auth)
except Exception as e:
    print("Exception:", e)
    is_auth = False

print("Final is_auth:", is_auth)

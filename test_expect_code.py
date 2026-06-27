import subprocess
import time

proc = subprocess.Popen(["expect", "login_agy.exp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

for line in iter(proc.stdout.readline, ''):
    if "authorization code" in line:
        break

proc.stdin.write("fake_code_123\n")
proc.stdin.flush()

for line in iter(proc.stdout.readline, ''):
    pass

proc.wait()
print("RETURN CODE:", proc.returncode)

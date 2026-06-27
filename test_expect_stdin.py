import subprocess
import time

proc = subprocess.Popen(["expect", "login_agy.exp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

out = ""
for line in iter(proc.stdout.readline, ''):
    print("GOT:", repr(line))
    if "authorization code" in line:
        break

print("SENDING CODE...")
proc.stdin.write("fake_code_123\n")
proc.stdin.flush()

for line in iter(proc.stdout.readline, ''):
    print("POST GOT:", repr(line))


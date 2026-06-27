import subprocess, time

proc = subprocess.Popen(
    ["/Users/thaonv/.local/bin/agy", "-p", '""'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

proc.stdin.write("1\n")
proc.stdin.flush()

import fcntl, os
fd = proc.stdout.fileno()
fl = fcntl.fcntl(fd, fcntl.F_GETFL)
fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

url = None
start_t = time.time()
while time.time() - start_t < 10:
    try:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        print("Read:", repr(line))
        if "http" in line or "accounts.google.com" in line:
            parts = line.split()
            for p in parts:
                if p.startswith("http"):
                    url = p
                    break
            if url:
                break
    except TypeError:
        time.sleep(0.1)
    except IOError:
        time.sleep(0.1)

print("FOUND URL:", url)
proc.kill()

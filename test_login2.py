import subprocess, time, os, fcntl

proc = subprocess.Popen(
    ["/Users/thaonv/.local/bin/agy"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

proc.stdin.write("1\n")
proc.stdin.flush()
time.sleep(2)

fd1 = proc.stdout.fileno()
fl1 = fcntl.fcntl(fd1, fcntl.F_GETFL)
fcntl.fcntl(fd1, fcntl.F_SETFL, fl1 | os.O_NONBLOCK)

fd2 = proc.stderr.fileno()
fl2 = fcntl.fcntl(fd2, fcntl.F_GETFL)
fcntl.fcntl(fd2, fcntl.F_SETFL, fl2 | os.O_NONBLOCK)

out = ""
err = ""
try:
    out = proc.stdout.read()
except:
    pass
try:
    err = proc.stderr.read()
except:
    pass

print("STDOUT:", repr(out))
print("STDERR:", repr(err))
proc.kill()

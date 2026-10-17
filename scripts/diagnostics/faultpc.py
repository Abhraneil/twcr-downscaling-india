"""Show the machine instructions where wrf.exe crashed, with data addresses named.
   python faultpc.py WRF_EXE RSL_FILE...   (needs binutils: nm, objdump)"""
import bisect, re, subprocess, sys
exe, rsls = sys.argv[1], sys.argv[2:]
nm = subprocess.run(["nm", "-n", "--defined-only", exe], capture_output=True, text=True).stdout.split("\n")
text, data = [], []
for l in nm:
    p = l.split()
    if len(p) == 3:
        (text if p[1] in "tTwW" else data if p[1] in "bBdDrRgGsS" else []).append((int(p[0], 16), p[2]))
tk, dk = [a for a, _ in text], [a for a, _ in data]
def owner(tab, keys, a):
    i = bisect.bisect_right(keys, a) - 1
    return (tab[i][1], a - tab[i][0]) if i >= 0 else ("?", 0)
pcs = {}
for f in rsls:
    s = open(f, errors="replace").read()
    i = s.find("Program received signal")
    # the first backtrace frame inside wrf.exe's own code is the instruction that faulted
    # (frames before it are the gfortran runtime and the C library's signal handler)
    frames = [int(h, 16) for h in re.findall(r"#\d+\s+(0x[0-9a-f]+)", s[i:i + 3000])] if i >= 0 else []
    own = [a for a in frames if tk[0] <= a <= tk[-1] + 0x100000]
    if own:
        pcs.setdefault(own[0], []).append(f)
    else:
        print(f, ": no backtrace")
for pc, fs in pcs.items():
    fn, off = owner(text, tk, pc)
    print(f"== fault at {pc:#x} = {fn}+{off:#x}   ({', '.join(fs)})")
    start = pc - off
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn", f"--start-address={start:#x}",
                          f"--stop-address={pc + 24:#x}", exe], capture_output=True, text=True).stdout
    lines = [l for l in out.split("\n") if re.match(r"\s+[0-9a-f]+:", l)]
    for l in lines[-60:]:
        names = []
        for h in re.findall(r"0x([0-9a-f]{6,})", l.split(":", 1)[1]):
            a = int(h, 16)
            if dk and dk[0] <= a <= dk[-1] + 0x10000000:
                n, o = owner(data, dk, a)
                names.append(f"{n}+{o:#x}")
        mark = "  <== fault" if int(l.split(":")[0], 16) == pc else ""
        print(l.rstrip() + (f"    # {', '.join(names)}" if names else "") + mark)

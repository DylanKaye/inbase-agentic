import time
from sys import argv
from fca import fca
import pandas as pd
from analyze_run import analyze_run

with open(f"testing/{argv[1]}-{argv[2]}.txt", "w") as f:
    f.write("running")

base = argv[1].upper()
seat = argv[2].upper()

if seat in ['CA','FO','FA'] and base in ['DAL','BUR','LAS','SNA','OPF','SCF','OAK']: 
    if base == 'DAL':
        ttr = 1500
    elif base in ['BUR','LAS']:
        ttr = 1000
    else:
        ttr = 500

    fca(base, seat, '2025-03-01', '2025-03-31', ttr)
    analyze_run(base, seat)
else:
    with open(f"testing/{base}-{seat}-opt.txt", "w") as f:
        f.write('not actually running yet')

with open(f"testing/{base}-{seat}.txt", "w") as f:
    f.write("finished")
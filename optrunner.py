import time
from sys import argv
from fca import fca
import pandas as pd

with open(f"testing/{argv[1]}-{argv[2]}.txt", "w") as f:
    f.write("running")

base = argv[1].upper()
seat = argv[2].upper()

if base == 'SNA' and seat == 'CA':

    fca(base, seat, '2025-03-01', '2025-03-31', 300)

    df = pd.read_csv(f'xpv{base}.csv')

    with open(f"testing/{base}-{seat}-opt.txt", "w") as f:
        f.write(df.iloc[0,:10].to_string())
else:
    with open(f"testing/{base}-{seat}-opt.txt", "w") as f:
        f.write('not actually running yet')

with open(f"testing/{base}-{seat}.txt", "w") as f:
    f.write("finished")

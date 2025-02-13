import time
from sys import argv
from fca import fca
import pandas as pd

with open(f"testing/{argv[1]}-{argv[2]}.txt", "w") as f:
    f.write("running")

time.sleep(20)

# print(argv[1], argv[2])

# if argv[1] == 'sna' and argv[2] == 'ca':

#     fca(argv[1], argv[2], '2025-03-01', '2025-03-31', 300)

#     df = pd.read_csv(f'xpv{argv[1]}.csv')

#     with open(f"testing/{argv[1]}-{argv[2]}-opt.txt", "w") as f:
#         f.write(df.iloc[0,:10].to_string())
# else:
#     with open(f"testing/{argv[1]}-{argv[2]}-opt.txt", "w") as f:
#         f.write('not actually running yet')
    
with open(f"testing/{argv[1]}-{argv[2]}-opt.txt", "w") as f:
    f.write('person 1: days 1,2,3; person 2: days 1,3,4')


with open(f"testing/{argv[1]}-{argv[2]}.txt", "w") as f:
    f.write("finished")

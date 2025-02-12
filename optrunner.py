import time
from sys import argv

with open(f"testing/{argv[1]}-{argv[2]}.txt", "w") as f:
    f.write("running")

time.sleep(20)

with open(f"testing/{argv[1]}-{argv[2]}-opt.txt", "w") as f:
    f.write("person 1: days 1,2,3; person 2: days 1,3,4")

with open(f"testing/{argv[1]}-{argv[2]}.txt", "w") as f:
    f.write("finished")

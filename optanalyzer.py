import time
from sys import argv

with open(f"{argv[1]}-{argv[2]}-opt.txt", "r") as f:
    data = f.read()
    print(data)
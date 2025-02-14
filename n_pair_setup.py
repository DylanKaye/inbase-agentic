import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json

#resfa = {'BUR':[2,1,1,2,2,1,2], 'DAL':[2,1,1,2,2,1,2], 'LAS':[2,1,1,2,2,1,2],'SCF':[1,1,1,1,1,1,1],'OAK':[0,0,0,0,0,0,1]}
resfa = {'BUR':[1,1,1,1,1,1,1], 'DAL':[1,1,1,1,1,1,1], 'LAS':[1,1,1,1,1,1,1]}
#resfa = {'BUR':[1,1,1,1,2,1,2], 'DAL':[], 'LAS':[1,1,1,1,1,1,1], 'SNA':[], 'OPF':[]}
seat = 'first_officer'

selpairs = pd.read_csv(f'pairing_file_mar.csv')

bdt = pd.read_csv('tdy_opt_dat_fin_FO.csv')
bdt[bdt['non tdy days worked']!=0].to_csv('tdy_opt_dat_fin_FO.csv',index=False)

selpairs = selpairs[~selpairs['idx'].isin([67386, 67387, 67388, 67389, 67390, 67391])].reset_index(drop=True)

spg = selpairs.groupby('base_start')['mult'].sum()
print([spg['BUR'], spg['DAL'], 0, spg['LAS'], 0, spg['OAK'], spg['SCF'], spg['SNA']])

def ret_row(day, base, idx):
    tme = time.mktime(datetime.fromisoformat(day).timetuple()) + 13*3600
    tme2 = time.mktime(datetime.fromisoformat(day).timetuple()) + 17*3600
    return [idx, idx, base, 1, day, day, tme, tme2, 0, 10000, 8, 1, False]

dtes_dt = [i for i in pd.date_range('2025-03-01','2025-03-31')]
dtes = [i.strftime('%Y-%m-%d') for i in dtes_dt]
res_list = []
rid = 0
for base, ddict in resfa.items():
    for ind, day in enumerate(dtes):
        if base == 'LAS' and day > '2025-03-10':
            continue
        if base == 'BUR' and day > '2025-03-12':
            continue
        if base == 'DAL' and day  == '2025-03-29':
            continue
        for n in range(ddict[dtes_dt[ind].dayofweek]):
            res_list.append(ret_row(day, base, f'R{rid}'))
            rid += 1

for r in res_list:
    selpairs.loc[len(selpairs.index)] = r

seat = 'FO'
    
selpairs.to_csv(f'selpair_setup_{seat}_dec.csv',index=False)

spg = selpairs.groupby('base_start')['mult'].sum()
print(spg)
print([spg['BUR'], spg['DAL'], 0, spg['LAS'], spg['OAK'], spg['OPF'], spg['SCF'], spg['SNA']])

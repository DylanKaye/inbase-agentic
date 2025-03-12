import cvxpy as cp
import numpy as np
import time
import pickle
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
from utils import get_date_range, capture_solver_output

# Define preferred times for each base
BASE_TIME_PREFERENCES = {
    'DAL': [6, 11, 17],
    'BUR': [6, 12, 15],
    'LAS': [6, 10, 14],
    'OAK': [7, 9, 11],
    'OPF': [9, 10, 11], 
    'SCF': [6, 10, 16],
    'SNA': [7, 9, 11]
}

# Default values if base not found in the dictionary
DEFAULT_TIME_PREFERENCES = [7, 11, 15]

def fca(base, seat, d1, d2, seconds):
    print(f"FCA optimization started for {base} {seat} from {d1} to {d2} with {seconds} seconds time limit", flush=True)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    
    start_time = time.time()
    
    try:
        dalpair = pd.read_csv(f'selpair_setup_{seat}.csv')
        print(f"Loaded selpair_setup_{seat}.csv with {len(dalpair)} rows", flush=True)
        
        if base == 'OPF':
            add = ['BCT']
        else:
            add = []
            
        inbasedat = pd.read_csv(f'{seat}_crew_records.csv')
        print(f"Loaded {seat}_crew_records.csv with {len(inbasedat)} rows", flush=True)
        
        inbasedat.index = inbasedat['name']
        inbasedat = inbasedat[(inbasedat['base']==base)|(inbasedat['to_base']==base)]
        print(f"Filtered to {len(inbasedat)} crew members for base {base}", flush=True)

        tot_days = []
        is_tdy = []
        for row in inbasedat[['non_tdy_days_worked','five_day_tdy','six_day_tdy','base']].values:
            if row[1] and row[3] != base:
                tot_days.append(5)
                is_tdy.append(True)
            elif row[2] and row[3] != base:
                tot_days.append(6)
                is_tdy.append(True)
            else:
                tot_days.append(row[0])
                is_tdy.append(False)
        inbasedat['tot_days'] = tot_days
        inbasedat['is_tdy'] = is_tdy

        prefs = pd.read_csv(f'bid_dat_test.csv')
        print(f"Loaded bid_dat_test.csv with {len(prefs)} rows", flush=True)
        prefs = prefs[(prefs['user_name'].isin(inbasedat.index))].sort_values(by='user_seniority', ascending=False)
        prefs['crew_pbs_idx'] = list(range(len(prefs)))
        prefs.index = prefs['crew_pbs_idx']

        days_worked = inbasedat.loc[prefs['user_name'].values]['tot_days'].values
        istdy = inbasedat.loc[prefs['user_name'].values]['is_tdy'].values
        
        dalpair = dalpair[dalpair['base_start'].isin([base]+add)]
        
        pdays = dalpair['mult'].astype(int).values
        
        print('sum',dalpair['mult'].sum(), days_worked.sum())

        dtes_dt = [i for i in pd.date_range(d1, d2)]
        dtes = [i.strftime('%Y-%m-%d') for i in dtes_dt]
        dalpair['dalidx'] = list(range(len(dalpair)))
        
        print(dalpair['d1'].value_counts())
        print(dalpair)

        dtemap = {}
        for ind, d in enumerate(dtes):
            tmp = dalpair[(dalpair['d1']==d)|(dalpair['d2']==d)]
            try:
                tmp2 = dalpair[(dalpair['d1']==dtes[ind-1])&(dalpair['d2']==dtes[ind+1])&(dalpair['mult']==3)]['dalidx'].values.tolist()
            except:
                tmp2 = []
            try:
                tmp3 = dalpair[(dalpair['d1']==dtes[ind-1])&(dalpair['d2']==dtes[ind+2])&(dalpair['mult']==4)]['dalidx'].values.tolist()
            except:
                tmp3 = []
            try:
                tmp4 = dalpair[(dalpair['d1']==dtes[ind-2])&(dalpair['d2']==dtes[ind+1])&(dalpair['mult']==4)]['dalidx'].values.tolist()
            except:
                tmp4 = []
            dtemap[d] = tmp['dalidx'].values.tolist() + tmp2 + tmp3 + tmp4
        sidx = len(dalpair)

        r_idxs = dalpair[dalpair['idx'].isin([i for i in dalpair['idx'] if 'R' in i])]['dalidx']
        c_idxs = dalpair[dalpair['charter']==True]['dalidx']

        dofflst = []
        for row in prefs['preferred_days_off'].values:
            tmpl = []
            for d in eval(row):
                tmpl.append(d[:10])
            dofflst.append(tmpl)

        prefs['dofflst'] = dofflst

        dofflst = prefs['dofflst'].values

        pref_off = []
        for row in dofflst:
            tmplst = []
            for d in row:
                if d not in dtes:
                    continue
                tmplst.extend(dtemap[d])
            pref_off.append(tmplst)

        dates = sorted(dalpair['d1'].unique())
        datemap = dict(zip(dates, list(range(len(dates)))))
        dalpair['d1_int'] = dalpair['d1'].map(datemap)
        dalpair['d2_int'] = dalpair['d2'].map(datemap).fillna(-1)
        proc_dat = []
        for pair in dalpair[['pstart','pend','d1_int','d2_int','dalidx','idx']].values:
            if pair[4] in r_idxs.values:
                continue
            if pair[3] >= 0:
                last_day = pair[3]
            else:
                last_day = pair[2]
            first_day = pair[2]
            start_time = pair[0]
            end_time = pair[1]
            if 'M' in pair[-1]: 
                print(first_day, 1/0)
                dtme = datetime(year=2024, month=5, day=int(first_day+1), hour=7, minute=0)
                dtme += timedelta(hours=5)
                start_time = time.mktime(pd.to_datetime(dtme.strftime("%Y-%m-%dT%H:%M:%S")).to_pydatetime().timetuple())
                dtme = datetime(year=2024, month=5, day=min(int(last_day+1),30), hour=23, minute=0)
                dtme += timedelta(hours=5)
                end_time = time.mktime(pd.to_datetime(dtme.strftime("%Y-%m-%dT%H:%M:%S")).to_pydatetime().timetuple())
            # if pair[4] in r_idxs.values:
            #     dtme = datetime(year=2024, month=4, day=int(first_day+1), hour=2, minute=0)
            #     dtme += timedelta(hours=5)
            #     start_time = time.mktime(pd.to_datetime(dtme.strftime("%Y-%m-%dT%H:%M:%S")).to_pydatetime().timetuple())
            #     dtme = datetime(year=2024, month=4, day=int(last_day+1), hour=18, minute=0)
            #     dtme += timedelta(hours=5)
            #     end_time = time.mktime(pd.to_datetime(dtme.strftime("%Y-%m-%dT%H:%M:%S")).to_pydatetime().timetuple())
            proc_dat.append([start_time, end_time, first_day, last_day])
        procdf = pd.DataFrame(proc_dat)
        disallow = {}
        for ind, row in enumerate(procdf.values):
            x = procdf[procdf[2]==row[3] + 1]
            x = x[x[0] - row[1] < 12*3600]
            disallow[ind] = x.index.tolist()
        disa2 = {}
        for k,v in disallow.items():
            if len(v) == 0:
                continue
            if str(v) not in disa2:
                disa2[str(v)] = []
            disa2[str(v)].append(k)
        constr_rest = []
        rest_constraints = []
        for k,v in disa2.items():
            constr_rest.append(eval(k) + v)

        # Add constraints for pairings with long duty times (over 11 hours)
        long_duty_pairings = dalpair[dalpair['dtime'] >= 11*3600]['dalidx'].values
        print(f"Found {len(long_duty_pairings)} pairings with duty time > 11 hours", flush=True)

        # For each long duty pairing, find other long duty pairings within 1 day
        for idx in long_duty_pairings:
            # Get the date of this pairing
            pairing_date = dalpair.loc[dalpair['dalidx'] == idx, 'd1'].values[0]
            pairing_date_dt = pd.to_datetime(pairing_date)
            
            # Find other long duty pairings within 1 day (before or after)
            nearby_pairings = []
            for other_idx in long_duty_pairings:
                if other_idx == idx:
                    continue
                    
                other_date = dalpair.loc[dalpair['dalidx'] == other_idx, 'd1'].values[0]
                other_date_dt = pd.to_datetime(other_date)
                
                # Check if within 1 day
                if abs((other_date_dt - pairing_date_dt).days) <= 1:
                    nearby_pairings.append(other_idx)
            
            # If there are nearby long duty pairings, add constraint
            if nearby_pairings:
                constr_rest.append([idx] + nearby_pairings)

        print(f"Added {len(constr_rest) - len(rest_constraints)} constraints for long duty pairings", flush=True)

        # Add constraints for pairings with many legs (5 or more)
        many_legs_pairings = dalpair[dalpair['mlegs'] >= 5]['dalidx'].values
        print(f"Found {len(many_legs_pairings)} pairings with 5 or more legs", flush=True)

        # For each many-legs pairing, find other many-legs pairings within 1 day
        for idx in many_legs_pairings:
            # Get the date of this pairing
            pairing_date = dalpair.loc[dalpair['dalidx'] == idx, 'd1'].values[0]
            pairing_date_dt = pd.to_datetime(pairing_date)
            
            # Find other many-legs pairings within 1 day (before or after)
            nearby_pairings = []
            for other_idx in many_legs_pairings:
                if other_idx == idx:
                    continue
                    
                other_date = dalpair.loc[dalpair['dalidx'] == other_idx, 'd1'].values[0]
                other_date_dt = pd.to_datetime(other_date)
                
                # Check if within 1 day
                if abs((other_date_dt - pairing_date_dt).days) <= 1:
                    nearby_pairings.append(other_idx)
            
            # If there are nearby many-legs pairings, add constraint
            if nearby_pairings:
                constr_rest.append([idx] + nearby_pairings)

        print(f"Added constraints for pairings with 5 or more legs", flush=True)

        # Also add constraints for combinations of long duty and many legs
        for idx in long_duty_pairings:
            pairing_date = dalpair.loc[dalpair['dalidx'] == idx, 'd1'].values[0]
            pairing_date_dt = pd.to_datetime(pairing_date)
            
            # Find many-legs pairings within 1 day
            nearby_pairings = []
            for other_idx in many_legs_pairings:
                if other_idx == idx:  # Skip if same pairing (could be both long duty and many legs)
                    continue
                    
                other_date = dalpair.loc[dalpair['dalidx'] == other_idx, 'd1'].values[0]
                other_date_dt = pd.to_datetime(other_date)
                
                # Check if within 1 day
                if abs((other_date_dt - pairing_date_dt).days) <= 1:
                    nearby_pairings.append(other_idx)
            
            # If there are nearby many-legs pairings, add constraint
            if nearby_pairings:
                constr_rest.append([idx] + nearby_pairings)

        print(f"Total fatigue-related constraints added: {len(constr_rest) - len(rest_constraints)}", flush=True)

        n_p = len(dalpair)

        multi = dalpair[dalpair['nlayovers']>=1]['dalidx']
        single = np.array([i for i in range(n_p) if i not in multi])
        
        pover = []
        for i in prefs['overnight_preference'].values:
            if i == "No Overnights":
                val = 1
            elif i == "Many":
                val = 3
            elif i == "Some":
                val = 2
            else:
                val = 4
            pover.append(val)

        prefs['pref_over'] = pover
        pref_over = prefs['pref_over']

        pover = []
        for i in prefs['time_period_preference'].values:
            if i == "AM":
                val = 1
            elif i == "PM":
                val = 3
            elif 'Midday':
                val = 2
            else:
                val = 4
            pover.append(val)
        prefs['ptime'] = pover
        pref_time = prefs['ptime']

        res_pref = []
        for i in prefs['reserve_preference'].values:
            if i == "Yes":
                val = 1
            elif i == "No":
                val = 0
            else:
                val = 2
            res_pref.append(val)

        prefs['res_pref'] = res_pref
        pref_reserves = prefs['res_pref']

        gap = days_worked.sum() - dalpair['mult'].sum()
        # lpr = len(pref_reserves[pref_reserves==1])
        # egp = int(gap/lpr + .99)
        # print(gap, lpr, gap/lpr, egp)

        vaca_pto = []
        for row in prefs[['work_restriction_days','vacation_days','training_days']].values:
            tmpl = []
            x1 = eval(row[0])
            x2 = eval(row[1])
            x3 = eval(row[2])
            for x in x1:
                tmpl.append(x[:10])
            for x in x2:
                tmpl.append(x[:10])
            for x in x3:
                tmpl.append(x[:10])
            vaca_pto.append(tmpl)
        prefs['vacation_tr'] = vaca_pto
        vacations = prefs['vacation_tr'].to_dict()

        n_c = len(prefs)
        n_d = len(dtes)

        x = dalpair[dalpair['base_start']==base]['d1'].value_counts()
        y = dalpair[(dalpair['base_start']==base)&(dalpair['mult']==2)]['d2'].value_counts() 
        z = (x + (y + x*0).fillna(0)).to_dict()
        
        # Analyze vacation days totals
        vacation_counts = {}
        for crew_idx, dates in vacations.items():
            for date in dates:
                if date not in vacation_counts:
                    vacation_counts[date] = 0
                vacation_counts[date] += 1
        
        # Print analysis comparing work days to available crew
        print("\nDaily Work Assignment Analysis:", flush=True)
        print("Date\t\tWork Days\tCrew on Vac\tAvailable Crew\tDifference", flush=True)
        print("-" * 80, flush=True)
        all_dates = sorted(set(list(z.keys()) + list(vacation_counts.keys())))
        for date in all_dates:
            work_days = z.get(date, 0)
            crew_on_vac = vacation_counts.get(date, 0)
            available_crew = n_c - crew_on_vac
            difference = available_crew - work_days
            print(f"{date}\t{work_days}\t\t{crew_on_vac}\t\t{available_crew}\t\t{difference}", flush=True)
        
        # Print totals
        total_work = sum(z.values())
        total_vac_days = sum(vacation_counts.values())
        print("\nSummary:", flush=True)
        print(f"Total crew members (n_c): {n_c}", flush=True)
        print(f"Total work days to assign: {total_work}", flush=True)
        print(f"Total vacation days: {total_vac_days}", flush=True)
        print(f"Average daily crew availability: {n_c - (total_vac_days/len(all_dates)):.1f}", flush=True)
        
        print(dalpair[['d1','d2','idx']], flush=True)
        #exit(0)

        # pto = []
        # for row in prefs['pto_days'].values:
        #     tmpl = []
        #     for x in eval(row):
        #         tmpl.append(x[:10])
        #     pto.append(tmpl)
        # prefs['pto'] = pto
        # pto = prefs['pto'].to_dict()


        # if seat == 'captain':
        #     if base == 'DAL':
        #         squal_duties = dalpair[dalpair['gunq']==True]['dalidx'].values
        #         squal_caps = np.argwhere(['G' in [j for j in eval(i)] for i in prefs['user_special_roles']])
        #     if base == 'BUR' or base == 'SNA':
        #         squal_duties = dalpair[dalpair['rnoq']==True]['dalidx'].values
        #         squal_caps = np.argwhere(['R' in [j for j in eval(i)] for i in prefs['user_special_roles']])

        rowl = []
        for row1, row2 in zip(dalpair['dtime'].values, dalpair['mlegs'].values):
            rowl.append(int(row1) >= 9*3600 or row2 >= 5)
        rowl = np.array(rowl)

        max_days = days_worked
        min_days = days_worked
        # if base != 'SNA':
        #     min_days = days_worked
        # else:
        #     #min_days = days_worked - (pref_reserves==1).astype(int).values*egp
        #     egp_sub = np.zeros(len(pref_reserves))
        #     egp_sub[0] = 3
        #     egp_sub[1] = 5
        #     egp_sub[2] = 3
        #     min_days = days_worked - egp_sub
        maxres = 10
        print(min_days)
        print('min',dalpair['mult'].sum(), max_days.sum(), min_days.sum())
        print(pref_reserves)
        # exit(0)
        xp = cp.Variable((n_c,n_p), boolean=True)
        po = cp.Variable(n_c, integer=True)
        pover = cp.Variable(n_c, integer=True)
        ptime = cp.Variable(n_c, integer=True)
        if len(r_idxs) > 0:
            pres = cp.Variable(n_c, integer=True)
        if len(c_idxs) > 0:
            pcha = cp.Variable(n_c, integer=True)
        # ppto = cp.Variable(n_c, integer=True)
        chnk = cp.Variable(n_c, integer=True)
        cdos = cp.Variable(n_c, integer=True)
        #debu = cp.Variable(n_c, integer=True)
        constraints = []

        # if base == 'OPF':
        #     opfarr = dalpair[dalpair['base_start']=='OPF']['dalidx'].values
        #     boca_cid = 3
        #     constraints += [cp.sum(xp[boca_cid,opfarr]) == 3]

        #all pairings covered once
        for p in range(n_p):
            constraints += [cp.sum(xp[:,p]) == 1]

        #doesn't go above max_days
        for c in range(n_c):
            constraints += [cp.sum(cp.multiply(xp[c], pdays)) <= max_days[c]]

        #doesn't go below min_days
        for c in range(n_c):
            constraints += [cp.sum(cp.multiply(xp[c], pdays)) >= min_days[c]]

        #no more than 1 duty per day
        for d in dtes:
            arr = np.array(dtemap[d])
            if len(arr) > 0:
                constraints += [cp.sum(xp[:, arr], axis=1) <= 1]

        # Pre-compute numpy arrays for each date once
        dtemap_np = {d: np.array(dtemap[d]) for d in dtes}

        # For each crew member
        for c in range(n_c):
            # Calculate day sums once - this creates a vector of work assignments per day
            day_sums = []
            for d in dtes:
                arr = dtemap_np[d]
                if len(arr) > 0:
                    day_sums.append(cp.sum(xp[c, arr]))
                else:
                    day_sums.append(0)
            
            # Convert lists to CVXPY expressions we can operate on
            day_sums = cp.vstack(day_sums)
            
            # Calculate work pattern metrics more efficiently
            # 1. Chunks: count transitions from work to non-work
            chunks = cp.sum(cp.pos(day_sums[:-1] - day_sums[1:])) 
            
            # 2. CDOs: count consecutive pairs of non-work days
            # Instead of using maximum, use a simpler formulation
            non_work_pairs = (1 - day_sums[:-1]) + (1 - day_sums[1:])
            cdo = cp.sum(cp.minimum(non_work_pairs, 2)) / 2  # Divide by 2 since we're counting pairs
            
            # Add constraints
            if is_tdy[c]:
                constraints += [chunks <= 1]
            constraints += [chnk[c] >= chunks]
            constraints += [cdos[c] <= cdo]
        

        #chunks and cdo calculation
        # for c in range(n_c):
        #     chunks = 0
        #     cdo = 0
        #     mon = []
        #     for ind in range(len(dtes)):
        #         arr1 = np.array(dtemap[dtes[ind]])
        #         if len(arr1) == 0:
        #             p1 = 0
        #         else:
        #             p1 = cp.sum(xp[c,arr1])
        #         if ind == len(dtes) - 1:
        #             p2 = 0
        #         else:
        #             arr2 = np.array(dtemap[dtes[ind+1]])
        #             if len(arr2) == 0:
        #                 p2 = 0
        #             else:
        #                 p2 = cp.sum(xp[c,arr2])
        #         m12 = cp.maximum(p1, p2)
        #         chunks += m12 - p2
        #         cdo += -1*(m12-1)
        #     if is_tdy[c]:
        #         constraints += [chunks <= 1]
        #     constraints += [chnk[c] >= chunks]
        #     constraints += [cdos[c] <= cdo]
        # for c in range(n_c):
        #     chunks = 0
        #     cdo = 0
        #     mon = []
        #     for ind in range(len(dtes)):
        #         arr1 = np.array(dtemap[dtes[ind]])
        #         if len(arr1) == 0:
        #             p1 = 0
        #         else:
        #             p1 = cp.sum(xp[c,arr1])
        #         if ind == len(dtes) - 1:
        #             p2 = 0
        #         else:
        #             arr2 = np.array(dtemap[dtes[ind+1]])
        #             if len(arr2) == 0:
        #                 p2 = 0
        #             else:
        #                 p2 = cp.sum(xp[c,arr2])
        #         m12 = cp.maximum(p1, p2)
        #         chunks += m12 - p2
        #         cdo += -1*(m12-1)
        #     if c > 10:
        #         num = 5
        #         num2 = 12
        #     elif c > 5:
        #         num = 6
        #         num2 = 11
        #     else:
        #         num = 10
        #         num2 = 10
        #     constraints += [chunks <= num]
        #     constraints += [cdo >= num2]
        # Pre-compute day sums for each crew member
        for c in range(n_c):
            # Calculate day sums once
            day_sums = []
            for d in dtes:
                arr = dtemap_np[d]
                if len(arr) > 0:
                    day_sums.append(cp.sum(xp[c, arr]))
                else:
                    day_sums.append(0)
            day_sums = cp.vstack(day_sums)
            
            # Add the three specific window constraints:
            
            # 1. Max 7 days of work in any 8 day period
            for i in range(len(dtes) - 8):
                constraints += [cp.sum(day_sums[i:i+8]) <= 7]
            
            # 2. Max 10 days of work in any 14 day period
            for i in range(len(dtes) - 14):
                constraints += [cp.sum(day_sums[i:i+14]) <= 10]
            
            # 3. Max 8 days of work in any 10 day period
            for i in range(len(dtes) - 10):
                constraints += [cp.sum(day_sums[i:i+10]) <= 8]

        # for c in range(n_c):
        #     maxlen = 7
        #     #minlen = 2
        #     #mon = []
        #     for ind in range(len(dtes)-maxlen):
        #         p = 0
        #         for ind2 in range(ind,ind+maxlen+1):
        #             arr = np.array(dtemap[dtes[ind2]])
        #             if len(arr) == 0:
        #                 pass
        #             else:
        #                 p += cp.sum(xp[c,arr])
        #         constraints += [p <= maxlen]

        # for c in range(n_c):
        #     maxlen = 10
        #     #minlen = 2
        #     #mon = []
        #     for ind in range(len(dtes)-maxlen-4):
        #         p = 0
        #         for ind2 in range(ind,ind+maxlen+4):
        #             arr = np.array(dtemap[dtes[ind2]])
        #             if len(arr) == 0:
        #                 pass
        #             else:
        #                 p += cp.sum(xp[c,arr])
        #         constraints += [p <= maxlen]

        # for c in range(n_c):
        #     maxlen = 8
        #     #minlen = 2
        #     #mon = []
        #     for ind in range(len(dtes)-maxlen-2):
        #         p = 0
        #         for ind2 in range(ind,ind+maxlen+2):
        #             arr = np.array(dtemap[dtes[ind2]])
        #             if len(arr) == 0:
        #                 pass
        #             else:
        #                 p += cp.sum(xp[c,arr])
        #         constraints += [p <= maxlen]

        #must be at least 2 consecutive days off
        # for c in range(n_c):
        #     for ind in range(len(dtes)-3):
        #         arr1 = np.array(dtemap[dtes[ind]])
        #         arr2 = np.array(dtemap[dtes[ind+1]])
        #         arr3 = np.array(dtemap[dtes[ind+2]])
        #         p1 = cp.sum(xp[c,arr1])
        #         p2 = cp.sum(xp[c,arr2])
        #         p3 = cp.sum(xp[c,arr3])
        #         constraints += [1-p1 + p2 + 1-p3 >= 0]        
        #         # p3 = cp.sum(xp[c,arr2])
        #         # p1 = cp.maximum(cp.sum(xp[c,arr1]), p3)
        #         # p2 = cp.maximum(p3, cp.sum(xp[c,arr3]))
        #         # constraints += [p1 + p2 - p3 <= 1]

        #days off + pto
        # for c in range(n_c):
        #     arr = np.array(pref_off[c])
        #     arr2 = np.array(pto_req[c])
        #     doffval = cp.sum(xp[c,arr]) + pto_mult * cp.sum(xp[c,arr2])
        #     constraints += [po[c] == doffval]

        #days off
        for c in range(n_c):
            if len(pref_off[c]) == 0:
                constraints += [po[c] == max_days[c]]
            else:
                arr = np.array(pref_off[c])
                constraints += [po[c] == max_days[c] - cp.sum(xp[c,arr])]

        #pto req
        # for c, v in pto.items():
        #     if len(v) == 0:
        #         constraints += [ppto[c] == max_days[c]]
        #         continue
        #     idx_lst = []
        #     for v2 in v:
        #         if v2 not in dtes:
        #             continue
        #         idx_lst.extend(dtemap[v2])
        #     pto_count = np.array(idx_lst)
        #     if len(pto_count) == 0:
        #         constraints += [ppto[c] == max_days[c]]
        #         continue
        #     constraints += [ppto[c] == max_days[c] - cp.sum(xp[c, pto_count])]

        #overnight
        for c in range(n_c):
            pref = pref_over[c]
            if pref == 1:
                idxs = single
                constraints += [pover[c] == cp.sum(xp[c,idxs])]
            elif pref == 3:
                idxs = multi
                constraints += [pover[c] == cp.sum(xp[c,idxs])]
            elif pref == 2:
                # For "Some" preference: 
                # - Get points for multi (overnight) pairings up to 3
                # - Get points for single pairings after that
                
                # Create auxiliary variables for the capped multi count
                multi_count = cp.sum(xp[c,multi])
                single_count = cp.sum(xp[c,single])
                
                # Use binary variables to implement min(multi_count, 3)
                has_multi = cp.Variable(4, boolean=True)  # has_multi[i] = 1 if multi_count >= i
                
                # Enforce ordering: has_multi[i] >= has_multi[i+1]
                for i in range(3):
                    constraints += [has_multi[i] >= has_multi[i+1]]
                
                # Connect has_multi to multi_count
                constraints += [multi_count >= has_multi[0]]
                for i in range(1, 4):
                    constraints += [multi_count >= i*has_multi[i]]
                    constraints += [multi_count <= i + 3*(1-has_multi[i])]
                
                # Calculate capped multi (0 to 3)
                multi_capped = has_multi[0] + has_multi[1] + has_multi[2]
                
                # Calculate excess multi beyond 3
                multi_excess = multi_count - multi_capped
                
                # Calculate effective single count (single count minus excess multi)
                # We need to ensure this is non-negative
                effective_single = cp.Variable(1)
                constraints += [effective_single <= single_count]
                constraints += [effective_single <= max_days[c] - multi_excess]  # Upper bound using max days
                constraints += [effective_single >= 0]
                
                # Set pover to be the sum of capped multi and effective single
                constraints += [pover[c] == multi_capped + effective_single]
            else:
                constraints += [pover[c] == 0]
                continue
        
        # houidxs = dalpair[(dalpair['mult']==2)&(dalpair['dtime']==9600)]['dalidx']
        # fav = 16
        # constraints += [cp.sum(xp[fav,houidxs]) == 3]
        # constraints += [cp.sum(xp[-1,houidxs])+cp.sum(xp[-2,houidxs])+cp.sum(xp[-4,houidxs]) == 6]

        # Replace the personalized time penalty system with a bonus-only approach
        # Use base-specific time preferences
        base_times = BASE_TIME_PREFERENCES.get(base, DEFAULT_TIME_PREFERENCES)
        early_time = base_times[0]  # Early hour
        middle_time = base_times[1]  # Middle hour
        late_time = base_times[2]   # Late hour
        
        print(f"Using time preferences for {base}: Early={early_time}, Middle={middle_time}, Late={late_time}", flush=True)
        
        # First calculate maximum possible distance for normalization
        max_time_distance = 10  # Maximum hours distance in a day
        
        # Create a bonus-only time preference system with integer values
        time_bonuses = {}
        for c in range(n_c):
            pref = pref_time[c]
            if pref not in [1, 2, 3]:  # No time preference
                time_bonuses[c] = np.zeros(n_p, dtype=int)
                continue
                
            # Choose reference time based on preference
            if pref == 1:  # Early
                ref_time = early_time
            elif pref == 2:  # Middle
                ref_time = middle_time
            else:  # Late
                ref_time = late_time
            
            # Calculate raw distances
            distances = np.abs(dalpair['shour'].values - ref_time)
            
            # Convert distances to integer bonuses (closer = higher bonus)
            # Normalize to 0-10 range where 10 is perfect match and 0 is furthest possible
            # Round to nearest integer to ensure all values are integers
            bonuses = np.round(10 * (1 - distances / max_time_distance)).astype(int)
            
            # Apply modifications for reserves and overnights ONLY if crew prefers them
            if len(r_idxs) > 0 and pref_reserves[c] == 1:  # Prefers reserves
                # Boost reserve bonuses
                for idx in r_idxs:
                    bonuses[idx] = 4  # Maximum bonus for preferred reserves
            
            # Create a copy of the boolean mask to avoid modifying original data
            is_overnight = dalpair['mult'].values > 1
            
            if pref_over[c] == 3:  # Prefers many overnights
                # Boost overnight bonuses - ensure result is integer
                temp_bonuses = bonuses.copy()
                temp_bonuses[is_overnight] = int(temp_bonuses[is_overnight] * 1.5)
                bonuses = np.minimum(temp_bonuses, 10)  # Cap at 10
            elif pref_over[c] == 2:  # Prefers some overnights
                # Slight boost for overnight bonuses - ensure result is integer
                temp_bonuses = bonuses.copy()
                temp_bonuses[is_overnight] = int(temp_bonuses[is_overnight] * 1.2)
                bonuses = np.minimum(temp_bonuses, 10)  # Cap at 10
            elif pref_over[c] == 1:  # No overnights
                # Reduce overnight bonuses - ensure result is integer
                temp_bonuses = bonuses.copy()
                temp_bonuses[is_overnight] = int(temp_bonuses[is_overnight] * 0.8)
                bonuses = temp_bonuses
            
            time_bonuses[c] = bonuses
            
        print(f"Created bonus-only integer time preference system", flush=True)
        
        # Replace the existing timeofday constraint with the bonus system
        for c in range(n_c):
            # Use the bonus values directly (higher is better for maximization)
            if pref_time[c] in [1, 2, 3]:  # Has time preference
                constraints += [ptime[c] == cp.sum(cp.multiply(time_bonuses[c], xp[c]))]
            else:
                constraints += [ptime[c] == 0]

        #reserves
        if len(r_idxs) > 0:
            for c in range(n_c):
                pref = pref_reserves[c]
                idxs = np.array(r_idxs)
                # if c <= 1:
                #     constraints += [pres[c] == -maxres]
                #     constraints += [cp.sum(xp[c,idxs]) <= 0]
                #     continue
                if pref == 0:
                    constraints += [pres[c] == -cp.sum(xp[c,idxs])]
                elif pref == 1:
                    constraints += [pres[c] == cp.sum(xp[c,idxs])]
                else:
                    constraints += [pres[c] == -maxres]
                    constraints += [cp.sum(xp[c,idxs]) <= 7]
                    continue
                constraints += [pres[c] <= maxres]
                constraints += [pres[c] >= -maxres]
                constraints += [cp.sum(xp[c,idxs]) <= int(max_days[c]/1.5)] 
                #constraints += [cp.sum(xp[c,idxs]) <= maxres] 

        #charters
        if len(c_idxs) > 0:
            for c in range(n_c):
                pref = c >= n_c - 5
                idxs = np.array(c_idxs)
                if pref == 1:
                    constraints += [pcha[c] == cp.sum(xp[c,idxs])]
                else:
                    constraints += [pcha[c] == 0]

        #rest time
        rest_constraints = []
        for idxs in constr_rest:
            idxs_arr = np.array(idxs)
            constraints += [cp.sum(xp[:, idxs_arr], axis=1) <= 1]

        #vacation block
        vacation_constraints = []
        for k, v in vacations.items():
            if not v:
                continue
            indices = [idx for date in v if date in dtemap for idx in dtemap[date]]
            if indices:
                vacation_constraints.append((k, np.array(indices)))

        for k, indices in vacation_constraints:
            constraints += [cp.sum(xp[k, indices]) == 0]

        #exit(0)
        #special qual
        # if seat == 'captain':
        #     if base in []:
        #         for c in range(n_c):
        #             if c not in squal_caps:
        #                 constraints += [cp.sum(xp[c, squal_duties]) == 0]

        #duty time
        for c in range(n_c):
            overage = cp.sum(cp.multiply(rowl, xp[c]))
            if base == 'OAK':
                constraints += [overage <= 8]
                continue
            elif base == 'SCF' or base == 'SNA':
                constraints += [overage <= 8]
                continue
            constraints += [overage <= 5] 

        sen = (prefs.index + 1) / len(prefs)
        if len(r_idxs) > 0:
            #res_val = cp.sum(cp.multiply(cp.minimum(pres, np.ones(n_c)*5),sen))
            res_val = cp.sum(cp.multiply(pres,sen))
        else:
            res_val = 0
        if len(c_idxs) > 0:
            char_val = cp.sum(pcha)
        else:
            char_val = 0
        objective = cp.Maximize(.3*cp.sum(cdos) - .3*cp.sum(chnk) + 3*cp.sum(cp.multiply(po,sen)) + 1.2*cp.sum(cp.multiply(pover,sen)) + .2*cp.sum(cp.multiply(ptime,sen)) + 1.5*res_val + char_val)
        #objective = cp.Maximize(3*cp.sum(cp.multiply(po,sen)) + 1.2*cp.sum(cp.multiply(pover,sen)) + .3*cp.sum(cp.multiply(ptime,sen)) + 4*cp.sum(ppto) + 1.5*res_val + char_val)
        #objective = cp.Maximize(1.5*cp.sum(cp.multiply(po,sen)) + 1.2*cp.sum(cp.multiply(pover,sen)) + cp.sum(cp.multiply(ptime,sen)) + 3*cp.sum(ppto) + 1.1*res_val + char_val)
        #objective = cp.Maximize(cp.sum(po) + cp.sum(pover) + cp.sum(ptime) + cp.sum(ppto) + cp.sum(cp.minimum(pres, np.ones(n_c)*3)))# - cp.max(over) + cp.min(over))# + cp.sum(ppto))
        #objective = cp.Minimize(0)

        prob = cp.Problem(objective, constraints)
        #.solve(verbose=True)
        print(f"Starting optimization solver at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print(f"Problem has {len(constraints)} constraints", flush=True)
        print(f"Using CBC solver with {seconds} seconds time limit", flush=True)
        
        solve_start_time = time.time()
        
        # Ensure all output is flushed before solver starts
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Use the capture_solver_output function to capture CBC solver output
        def run_solver():
            return prob.solve(solver='CBC', 
                             numberThreads=24, 
                             verbose=True, 
                             maximumSeconds=seconds,
                             allowableGap=0.01)  # Accept solutions within 1% of optimal
        
        # Run the solver with output capture
        capture_solver_output(run_solver, output_file=sys.stdout)
        
        solve_end_time = time.time()
        solve_elapsed = solve_end_time - solve_start_time
        
        print(f"Solver completed in {solve_elapsed:.2f} seconds with status: {prob.status}", flush=True)
        #prob.solve(solver=cp.SCIPY, scipy_options={"method": "highs"}, verbose=True)
        # prob.solve(solver='CBC', numberThreads=2, verbose=True, maximumSeconds=60)
        # prob.solve(solver=cp.SCIPY, scipy_options={'verbose': True})

        print(f"Saving results to files", flush=True)
        xpv = xp.value
        xpv_df = pd.DataFrame(xpv)
        xpv_df.to_csv(f'xpv{base}.csv',index=False)
        with open(f"{base}.txt", "w") as text_file:
            print(f"Status: {prob.status}", file=text_file)
            text_file.flush()
        satd = {}
        satd['po'] = po.value
        # satd['cdos'] = cdos.value
        # satd['chnk'] = chnk.value
        satd['pover'] = pover.value
        satd['ptime'] = ptime.value
        # satd['ppto'] = ppto.value
        if len(r_idxs) > 0:
            satd['res'] = pres.value
        if len(c_idxs) > 0:
            satd['char'] = pcha.value
        with open(f'satd_{base}{seat}.pkl','wb') as fp:
            pickle.dump(satd, fp)
            fp.flush()
        print(f"Results saved successfully", flush=True)
        # print(np.sum(po.value), np.sum(pover.value), np.sum(ptime.value), np.sum(ppto.value))
        # print(chnk.value)
        # print(cdos.value)
        
        # captsarr = np.array(capts.value)
        #
        # print(X_sol.shape)
        # np.save('xsol.npy', X_sol)
        # print(X_sol)
        # print(captsarr)

        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"FCA optimization completed in {elapsed_time:.2f} seconds", flush=True)
        return satd
    except Exception as e:
        print(f"Error in fca: {e}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None

# for base in ['BUR','DAL','HOU','LAS','MCO','OAK','OPF','SCF','SNA']:
# for base in ['DAL']:
#     seat = 'flight_attendant'
#     print(base,seat)
#     fca(base, seat)

# Replace hardcoded dates like:
# period_start = "2025-03-01"
# period_end = "2025-03-31"

# With:
#period_start, period_end = get_date_range()
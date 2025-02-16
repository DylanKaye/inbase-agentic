import cvxpy as cp
import numpy as np
import time
import pickle
import pandas as pd
from datetime import datetime, timedelta

def fca(base, seat, d1, d2, seconds):
    dalpair = pd.read_csv(f'selpair_setup_{seat}_dec.csv')
    if base == 'OPF':
        add = ['BCT']
    else:
        add = []
        
    inbasedat = pd.read_csv(f'tdy_opt_dat_fin_{seat}.csv')
    inbasedat.index = inbasedat['name']
    inbasedat = inbasedat[(inbasedat['base']==base)|(inbasedat['to_base']==base)]

    tot_days = []
    is_tdy = []
    for row in inbasedat[['non tdy days worked','5day tdy','6day tdy','base']].values:
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

    prefs = pd.read_csv(f'bid_dat_test_{seat}.csv')
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
    for k,v in disa2.items():
        constr_rest.append(eval(k) + v)

    n_p = len(dalpair)

    multi = dalpair[dalpair['nlayovers']>=1]['dalidx']
    single = np.array([i for i in range(n_p) if i not in multi])
    
    pover = []
    for i in prefs['overnight_preference'].values:
        if i == "Not Preferred":
            val = 1
        elif i == "Many":
            val = 3
        else:
            val = 2
        pover.append(val)

    prefs['pref_over'] = pover
    pref_over = prefs['pref_over']

    pover = []
    for i in prefs['time_period_preference'].values:
        if i == "AM":
            val = 1
        elif i == "PM":
            val = 3
        elif i == 'Midday':
            val = 2
        else:
            val = 4
        pover.append(val)
    prefs['ptime'] = pover
    pref_time = prefs['ptime']

    res_pref = []
    for i in prefs['reserve_preference'].values:
        if i == "Preferred":
            val = 1
        elif i == "Not Preferred":
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
    print("\nDaily Work Assignment Analysis:")
    print("Date\t\tWork Days\tCrew on Vac\tAvailable Crew\tDifference")
    print("-" * 80)
    all_dates = sorted(set(list(z.keys()) + list(vacation_counts.keys())))
    for date in all_dates:
        work_days = z.get(date, 0)
        crew_on_vac = vacation_counts.get(date, 0)
        available_crew = n_c - crew_on_vac
        difference = available_crew - work_days
        print(f"{date}\t{work_days}\t\t{crew_on_vac}\t\t{available_crew}\t\t{difference}")
    
    # Print totals
    total_work = sum(z.values())
    total_vac_days = sum(vacation_counts.values())
    print("\nSummary:")
    print(f"Total crew members (n_c): {n_c}")
    print(f"Total work days to assign: {total_work}")
    print(f"Total vacation days: {total_vac_days}")
    print(f"Average daily crew availability: {n_c - (total_vac_days/len(all_dates)):.1f}")
    
    print(dalpair[['d1','d2','idx']])
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

    early = [5,6,7,8]
    middle = [9,10,11,12]
    late = [13,14,15,16,17,18,19]

    early_idx = dalpair[(dalpair['shour'].isin(early))&(dalpair['mult']==1)]['dalidx']
    middle_idx = dalpair[(dalpair['shour'].isin(middle))&(dalpair['mult']==1)]['dalidx']
    late_idx = dalpair[(dalpair['shour'].isin(late))&(dalpair['mult']==1)]['dalidx']

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
        elif pref == 3:
            idxs = multi
        else:
            constraints += [pover[c] == 0]
            continue
        constraints += [pover[c] == cp.sum(xp[c,idxs])]
    
    # houidxs = dalpair[(dalpair['mult']==2)&(dalpair['dtime']==9600)]['dalidx']
    # fav = 16
    # constraints += [cp.sum(xp[fav,houidxs]) == 3]
    # constraints += [cp.sum(xp[-1,houidxs])+cp.sum(xp[-2,houidxs])+cp.sum(xp[-4,houidxs]) == 6]

    #timeofday
    for c in range(n_c):
        pref = pref_time[c]
        if pref == 1:
            idxs = early_idx
            constraints += [ptime[c] == 2*cp.sum(xp[c,idxs]) + cp.sum(xp[c,middle_idx])]
        elif pref == 2:
            idxs = middle_idx
            constraints += [ptime[c] == 2*cp.sum(xp[c,idxs])]
        elif pref == 3:
            idxs = late_idx
            constraints += [ptime[c] == 2*cp.sum(xp[c,idxs]) + cp.sum(xp[c,middle_idx])]
        else:
            constraints += [ptime[c] == 0]
            continue
            
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
    print(constr_rest)
    print(dalpair[dalpair['idx'].isin(['60699','60712'])])
    print([i for i in constr_rest if 62 in i])
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
        constraints += [overage <= 6] 

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
    #objective = cp.Maximize(3*cp.sum(cp.multiply(po,sen)) + 1.2*cp.sum(cp.multiply(pover,sen)) + .2*cp.sum(cp.multiply(ptime,sen)) + 4*cp.sum(ppto) + 1.5*res_val + char_val)
    #objective = cp.Maximize(3*cp.sum(cp.multiply(po,sen)) + 1.2*cp.sum(cp.multiply(pover,sen)) + .3*cp.sum(cp.multiply(ptime,sen)) + 4*cp.sum(ppto) + 1.5*res_val + char_val)
    #objective = cp.Maximize(1.5*cp.sum(cp.multiply(po,sen)) + 1.2*cp.sum(cp.multiply(pover,sen)) + cp.sum(cp.multiply(ptime,sen)) + 3*cp.sum(ppto) + 1.1*res_val + char_val)


    #objective = cp.Maximize(cp.sum(po) + cp.sum(pover) + cp.sum(ptime) + cp.sum(ppto) + cp.sum(cp.minimum(pres, np.ones(n_c)*3)) - cp.max(over))
    #objective = cp.Maximize(cp.sum(po) + cp.sum(pover) + cp.sum(ptime) + cp.sum(ppto) + cp.sum(cp.minimum(pres, np.ones(n_c)*3)))# - cp.max(over) + cp.min(over))# + cp.sum(ppto))
    #objective = cp.Minimize(0)

    prob = cp.Problem(objective, constraints)
    #.solve(verbose=True)
    prob.solve(solver='CBC', 
              numberThreads=24, 
              verbose=True, 
              maximumSeconds=seconds,
              allowableGap=0.01)  # Accept solutions within 1% of optimal
    #prob.solve(solver=cp.SCIPY, scipy_options={"method": "highs"}, verbose=True)
    # prob.solve(solver='CBC', numberThreads=2, verbose=True, maximumSeconds=60)
    # prob.solve(solver=cp.SCIPY, scipy_options={'verbose': True})

    xpv = xp.value
    xpv_df = pd.DataFrame(xpv)
    xpv_df.to_csv(f'xpv{base}.csv',index=False)
    with open(f"{base}.txt", "w") as text_file:
        print(f"Stauts: {prob.status}", file=text_file)
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
    # print(np.sum(po.value), np.sum(pover.value), np.sum(ptime.value), np.sum(ppto.value))
    # print(chnk.value)
    # print(cdos.value)
    
    # captsarr = np.array(capts.value)
    #
    # print(X_sol.shape)
    # np.save('xsol.npy', X_sol)
    # print(X_sol)
    # print(captsarr)

# for base in ['BUR','DAL','HOU','LAS','MCO','OAK','OPF','SCF','SNA']:
# for base in ['DAL']:
#     seat = 'flight_attendant'
#     print(base,seat)
#     fca(base, seat)
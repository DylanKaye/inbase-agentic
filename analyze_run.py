import sys
import pandas as pd
import numpy as np
import json
import requests
from datetime import datetime

def analyze_run(base: str, seat: str):
    # Keep seat as the original input (CA/FO/FA)
    seat = seat.upper()

    od = pd.read_csv(f'{seat}_crew_records.csv')

    with open('crew_id_map.json','r') as fp:
        crew_id_map = json.load(fp)
        
    with open('crew_id_map_e.json','r') as fp:
        crew_id_map_e = json.load(fp)
    crew_id_map_e = {k.lower():v for k,v in crew_id_map_e.items()}

    # Create output file
    output_file = f'testing/{base}-{seat}-opt.txt'
    output_file_line = f'testing/{base}-{seat}-line.txt'
    with open(output_file, 'w') as f:
        f.write(f'Analysis Run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'Base: {base}, Seat: {seat}\n\n')
    
    with open(output_file_line, 'w') as f:
        f.write(f'Analysis Run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'Base: {base}, Seat: {seat}\n\n')

    def log(message):
        """Helper function to both print and write to file"""
        print(message)
        with open(output_file, 'a') as f:
            f.write(str(message) + '\n')
    
    def log_line(message):
        """Helper function to both print and write to file"""
        print(message)
        with open(output_file_line, 'a') as f:
            f.write(str(message) + '\n')

    # Add crew ID mappings
    crew_id_map_e['lexie.leone@jsx.com'] = 75207
    crew_id_map_e['emily.fowler@jsx.com'] = 43480
    crew_id_map_e['skylar.manning@jsx.com'] = 39138
    crew_id_map_e['carly.ghafouri@jsx.com'] = 79914
    crew_id_map_e['ricardo.gutierrez@jsx.com'] = 99113
    crew_id_map_e['michael.boucher@jsx.com'] = 47727
    crew_id_map_e['robert.ferraro@jsx.com'] = 52586
    crew_id_map_e['chad.tucker@jsx.com'] = 15684
    crew_id_map_e['kelly.coble@jsx.com'] = 35816
    crew_id_map_e ['zachary.greenemeier@jsx.com'] = 42658
    crew_id_map_e ['matthew.bernier@jsx.com'] = 48229
    crew_id_map_e ['emily.gause@jsx.com'] = 22065
    crew_id_map_e ['shane.okeeffe@jsx.com'] = 41731
    crew_id_map_e ['joanna.pappy@jsx.com'] = 36838
    crew_id_map_e ['hannah.ilan@jsx.com'] = 36839
    crew_id_map_e ['marisa.malone@jsx.com'] = 36840
    crew_id_map_e ['steven.means@jsx.com'] = 36837
    crew_id_map_e ['deanna.english@jsx.com'] = 80048
    crew_id_map_e ['steven.means@jsx.com'] = 36837
    crew_id_map_e ['jennifer.sagong@jsx.com'] = 25569

    with open('crew_id_map_e2.json','r') as fp:
        crew_id_map_e = json.load(fp)

    crew_id_map_e ['asalogue@jsx.com'] = 10183
    crew_id_map_e ['eric.ladner@jsx.com'] = 10304
    crew_id_map_e ['shane.viera@jsx.com'] = 10302
    crew_id_map_e ['michelle.barnett@jsx.com'] = 10303

    # with open('pair_map_sept_4.json','r') as fp:
    #     pair_map = json.load(fp)

    # with open('pidmap_sept_1.json','r') as fp:
    #     pidmap = json.load(fp)
        
    # pidmap['dhdDAL01'] = 53396

    # for i in pair_map.values():
    #     if i not in pidmap.keys():
    #         print(i)
        
    trassd = {}
    mar = pd.read_csv(f'selpair_setup.csv')
    xpv = pd.read_csv(f'xpv{base}.csv')
    prefs = pd.read_csv(f'bid_dat_test.csv')
    # Map seat abbreviation to its full crew role name
    seat_full_mapping = {"CA": "captain", "FO": "first_officer", "FA": "flight_attendant"}
    seat_full = seat_full_mapping.get(seat, seat)
    prefs = prefs[((prefs['user_base']==base)&(prefs['user_role']==seat_full)&(prefs['user_name'].isin(od['name'].values)))].sort_values(by='user_seniority', ascending=False)
    
    # Check if we found any crew members
    if len(prefs) == 0:
        log(f"No crew members found for base={base} and seat={seat}")
        log("Filtered criteria:")
        log(f"- Base: {base}")
        log(f"- Seat: {seat}")
        log(f"- Names in od file: {od['name'].values.tolist()}")
        log("\nPlease verify:")
        log("1. The base code is correct")
        log("2. The seat code is correct")
        log("3. There are crew members in bid_dat_test.csv for this base/seat")
        log("4. The crew members are also present in {seat}_crew_records.csv")
        return
    
    names = prefs['user_name'].values
    log(f"Names: {names}")
    emails = prefs['user_email'].values
    if base == 'OPF':
        base2 = ['OPF','BCT']
    else:
        base2 = [base]
    mar_base = mar[mar['base_start'].isin(base2)]
    for ind, row in enumerate(xpv.values):
        for ind2, row2 in enumerate(row):
            if row2 == 0:
                continue
            if emails[ind] not in trassd:
                trassd[emails[ind]] = []
            pair = mar_base.iloc[ind2]['idx']
            trassd[emails[ind]].append(pair)
    with open(f'{base}_trassd_{seat}.json','w') as fp:
        json.dump(trassd, fp)
    
    sum_npsd = 0
    sum_dbd = 0
    for k,v in enumerate(trassd.values()):
        log(f"\nAnalyzing {names[k]}")
        log_line(f"\nFor {names[k]}")
        days = mar[mar['idx'].isin(v)][['d1','d2','idx','mult']].sort_values(by='d1').values
        dbd = od[od['name']==names[k]]['non tdy days worked'].values[0]
        npsd = np.sum(days[:,-1])
        log(f"Days worked - NPSD: {npsd}, DBD: {dbd}")
        sum_npsd += npsd
        sum_dbd += dbd
        log(f"Overnight preference: {prefs['overnight_preference'].iloc[k]}")
        log(f"Reserve preference: {prefs['reserve_preference'].iloc[k]}")
        log(f"Special roles: {prefs['user_special_roles'].iloc[k]}")
        log(f"Days: {sorted(np.unique(days[:,0].tolist() + days[:,1].tolist()))}")

        for row in days:
            log_line(f'{row[0]}, {row[1]}, {row[2]}, {row[3]}')

    log(f"\nSummary:")
    log(f"Total NPSD: {sum_npsd}")
    log(f"Total DBD: {sum_dbd}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python analyze_run.py <base> <seat>")
        print("Example: python analyze_run.py DAL CA")
        sys.exit(1)
    
    base = sys.argv[1].upper()
    seat = sys.argv[2].upper()
    analyze_run(base, seat)
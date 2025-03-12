import sys
import pandas as pd
import numpy as np
import json
import requests
import time
from datetime import datetime
from utils import get_date_range

def analyze_run(base: str, seat: str):
    print(f"Starting analysis for {base} {seat} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    start_time = time.time()
    
    # Keep seat as the original input (CA/FO/FA)
    seat = seat.upper()

    # Create output file
    output_file = f'testing/{base}-{seat}-opt.txt'
    output_file_line = f'testing/{base}-{seat}-line.txt'
    
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

    try:
        print(f"Loading crew records from {seat}_crew_records.csv")
        od = pd.read_csv(f'{seat}_crew_records.csv')
        print(f"Loaded {len(od)} crew records")
        
        with open(output_file, 'w') as f:
            f.write(f'Analysis Run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Base: {base}, Seat: {seat}\n\n')
        
        with open(output_file_line, 'w') as f:
            f.write(f'Analysis Run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Base: {base}, Seat: {seat}\n\n')
        
        print(f"Loading selpair_setup_{seat}.csv and xpv{base}.csv")
        trassd = {}
        mar = pd.read_csv(f'selpair_setup_{seat}.csv')
        xpv = pd.read_csv(f'xpv{base}.csv')
        prefs = pd.read_csv(f'bid_dat_test.csv')
        print(f"Loaded all required data files")
        
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
        
        print(f"Found {len(prefs)} crew members for analysis")
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
            dbd = od[od['name']==names[k]]['non_tdy_days_worked'].values[0]
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

    except Exception as e:
        print(f"Error occurred during analysis: {e}")
        import traceback
        traceback.print_exc()
    finally:
        end_time = time.time()
        print(f"Analysis completed in {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python analyze_run.py <base> <seat>")
        sys.exit(1)
    analyze_run(sys.argv[1], sys.argv[2])
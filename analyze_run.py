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
        print(message, flush=True)
        with open(output_file, 'a') as f:
            f.write(str(message) + '\n')
            f.flush()
    
    def log_line(message):
        """Helper function to both print and write to file"""
        print(message, flush=True)
        with open(output_file, 'a') as f:
            f.write(str(message) + '\n')
            f.flush()

    try:
        print(f"Loading crew records from {seat}_crew_records.csv", flush=True)
        od = pd.read_csv(f'{seat}_crew_records.csv')
        print(f"Loaded {len(od)} crew records", flush=True)
        
        with open(output_file, 'w') as f:
            f.write(f'Analysis Run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Base: {base}, Seat: {seat}\n\n')
            f.flush()
        
        with open(output_file_line, 'w') as f:
            f.write(f'Analysis Run: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Base: {base}, Seat: {seat}\n\n')
            f.flush()
        
        print(f"Loading selpair_setup_{seat}.csv and xpv{base}.csv", flush=True)
        trassd = {}
        mar = pd.read_csv(f'selpair_setup_{seat}.csv')
        xpv = pd.read_csv(f'xpv{base}.csv')
        prefs = pd.read_csv(f'bid_dat_test.csv')
        print(f"Loaded all required data files", flush=True)
        
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
        
        print(f"Found {len(prefs)} crew members for analysis", flush=True)
        names = prefs['user_name'].values
        log(f"Names: {names}")
        emails = prefs['user_email'].values
        if base == 'OPF':
            base2 = ['OPF','BCT']
        else:
            base2 = [base]
        mar_base = mar[mar['base_start'].isin(base2)]
        
        # Create a mapping from positions in xpv to actual indices in mar_base
        # This assumes xpv columns correspond to the same order as mar before filtering
        xpv_to_mar_mapping = {}
        mar_filtered_indices = mar_base.index.tolist()
        
        # If mar was originally in the same order as columns in xpv
        # we need to track which positions in the original mar correspond to positions in mar_base
        original_positions = mar.index[mar['base_start'].isin(base2)].tolist()
        for i, pos in enumerate(original_positions):
            xpv_to_mar_mapping[pos] = i
        
        for ind, row in enumerate(xpv.values):
            for ind2, row2 in enumerate(row):
                if row2 == 0:
                    continue
                if emails[ind] not in trassd:
                    trassd[emails[ind]] = []
                
                # Only access valid indices using the mapping
                if ind2 in xpv_to_mar_mapping:
                    mar_base_idx = xpv_to_mar_mapping[ind2]
                    pair = mar_base.iloc[mar_base_idx]['idx']
                    trassd[emails[ind]].append(pair)
        with open(f'{base}_trassd_{seat}.json','w') as fp:
            json.dump(trassd, fp)
            fp.flush()
        
        sum_npsd = 0
        sum_dbd = 0
        # Convert to list and reverse the order for enumeration
        trassd_values = list(trassd.values())
        trassd_keys = list(trassd.keys())
        
        # Enumerate in reverse order (from last to first)
        for k in range(len(trassd_values)-1, -1, -1):
            v = trassd_values[k]
            log(f"\nAnalyzing {names[k]}")
            log_line(f"\nFor {names[k]}")
            days = mar[mar['idx'].isin(v)][['d1','d2','idx','mult','shour']].sort_values(by='d1').values
            dbd = od[od['name']==names[k]]['non_tdy_days_worked'].values[0]
            npsd = np.sum(days[:,-2])
            log(f"Days worked - Duties Assigned: {npsd}, Duties to Assign: {dbd}")
            sum_npsd += npsd
            sum_dbd += dbd
            log(f"Overnight preference: {prefs['overnight_preference'].iloc[k]}")
            log(f"Reserve preference: {prefs['reserve_preference'].iloc[k]}")
            log(f"Time Period Preference: {prefs['time_period_preference'].iloc[k]}")
            # log(f"Days: {sorted(np.unique(days[:,0].tolist() + days[:,1].tolist()))}")
            
            # Get preferred days off for this crew member
            preferred_days_off = prefs['preferred_days_off'].iloc[k]
            # Convert to list if it's a string (assuming comma-separated format)
            if isinstance(preferred_days_off, str):
                preferred_days_off = [int(day.strip()) for day in preferred_days_off.split(',') if day.strip().isdigit()]
            elif pd.isna(preferred_days_off):
                preferred_days_off = []
            else:
                preferred_days_off = list(preferred_days_off)
                
            log(f"Preferred days off: {preferred_days_off}")

            for row in days:
                log_line(f'{row[0]}, {row[1]}, {row[2]}, {row[3]}, {row[4]}')
                # Check if either d1 or d2 is in preferred days off
                if preferred_days_off and (row[0] in preferred_days_off or row[1] in preferred_days_off):
                    conflicting_days = []
                    if row[0] in preferred_days_off:
                        conflicting_days.append(row[0])
                    if row[1] in preferred_days_off:
                        conflicting_days.append(row[1])
                    log_line(f'  ⚠️ CONFLICT: Day(s) {conflicting_days} overlap with preferred days off')

        log(f"\nSummary:")
        log(f"Duties Assigned: {sum_npsd}")
        log(f"Duties to Assign: {sum_dbd}")

    except Exception as e:
        print(f"Error occurred during analysis: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        end_time = time.time()
        print(f"Analysis completed in {end_time - start_time:.2f} seconds", flush=True)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python analyze_run.py <base> <seat>")
        sys.exit(1)
    analyze_run(sys.argv[1], sys.argv[2])
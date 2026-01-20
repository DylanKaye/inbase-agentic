"""
MIP Diagnostic Tool for FCA Optimization

This module provides comprehensive diagnosis of why a MIP optimization might fail.
It includes:
- Data validation (supply/demand balance)
- Feasibility-only testing
- Fatigue rule checking (7-in-a-row, 8-in-10, 10-in-14)
- Individual crew availability analysis
"""

import warnings
warnings.filterwarnings('ignore')  # Suppress pandas warnings

import pandas as pd
import numpy as np
import cvxpy as cp
import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# Import config from fca.py so limits stay in sync
from fca import get_long_duty_limit, LONG_DUTY_LIMITS


class DiagnosticResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


@dataclass
class DiagnosticReport:
    """Container for diagnostic results"""
    check_name: str
    result: DiagnosticResult
    message: str
    details: Optional[Dict] = None


def diagnose_optimization(base: str, seat: str, d1: str, d2: str, verbose: bool = True) -> List[DiagnosticReport]:
    """
    Main diagnostic function that runs all checks and returns a report.
    
    Args:
        base: Base code (e.g., 'DAL', 'BUR')
        seat: Seat type (e.g., 'FO', 'CA', 'FA')
        d1: Start date (YYYY-MM-DD)
        d2: End date (YYYY-MM-DD)
        verbose: Whether to print progress
    
    Returns:
        List of DiagnosticReport objects
    """
    reports = []
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"MIP DIAGNOSTIC REPORT")
        print(f"Base: {base}, Seat: {seat}")
        print(f"Date Range: {d1} to {d2}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
    
    # Phase 1: Data Loading & Validation
    if verbose:
        print("PHASE 1: DATA LOADING & VALIDATION")
        print("-" * 40)
    
    try:
        data = load_and_validate_data(base, seat, d1, d2, verbose)
        if data is None:
            reports.append(DiagnosticReport(
                check_name="Data Loading",
                result=DiagnosticResult.FAIL,
                message="Failed to load required data files"
            ))
            return reports
        
        reports.append(DiagnosticReport(
            check_name="Data Loading",
            result=DiagnosticResult.PASS,
            message="All required data files loaded successfully"
        ))
        
        # Print quick summary of numbers
        if verbose:
            print_data_summary(data)
        
        # Supply/Demand Balance Check
        supply_demand_report = check_supply_demand_balance(data, verbose)
        reports.append(supply_demand_report)
        
        # Daily Coverage Check
        daily_report = check_daily_coverage(data, verbose)
        reports.append(daily_report)
        
        # Vacation Conflict Check (aggregate)
        vacation_report = check_vacation_conflicts(data, verbose)
        reports.append(vacation_report)
        
        # Individual Crew Feasibility Check (vacation vs required work per person)
        individual_report = check_individual_crew_feasibility(data, verbose)
        reports.append(individual_report)
        
        # Pairing Coverage Check - are there pairings that NO crew can take?
        pairing_coverage_report = check_pairing_vacation_coverage(data, verbose)
        reports.append(pairing_coverage_report)
        
        # TDY Contiguity Check (TDY crew must work in one block)
        tdy_report = check_tdy_contiguity(data, verbose)
        reports.append(tdy_report)
        
        # Long Duty Limits Check
        long_duty_report = check_long_duty_limits(data, verbose)
        reports.append(long_duty_report)
        
    except Exception as e:
        reports.append(DiagnosticReport(
            check_name="Data Validation",
            result=DiagnosticResult.FAIL,
            message=f"Error during data validation: {str(e)}"
        ))
        return reports
    
    # Phase 2: Constraint Analysis
    if verbose:
        print("\nPHASE 2: CONSTRAINT ANALYSIS")
        print("-" * 40)
    
    try:
        constraint_reports = analyze_constraints(data, verbose)
        reports.extend(constraint_reports)
    except Exception as e:
        reports.append(DiagnosticReport(
            check_name="Constraint Analysis",
            result=DiagnosticResult.FAIL,
            message=f"Error during constraint analysis: {str(e)}"
        ))
    
    # Phase 3: Feasibility Testing
    if verbose:
        print("\nPHASE 3: FEASIBILITY TESTING")
        print("-" * 40)
    
    try:
        feasibility_reports = test_feasibility_incremental(data, verbose)
        reports.extend(feasibility_reports)
    except Exception as e:
        reports.append(DiagnosticReport(
            check_name="Feasibility Testing",
            result=DiagnosticResult.FAIL,
            message=f"Error during feasibility testing: {str(e)}"
        ))
    
    # Summary
    if verbose:
        print_summary(reports)
    
    return reports


def load_and_validate_data(base: str, seat: str, d1: str, d2: str, verbose: bool) -> Optional[Dict]:
    """Load all required data files and return as a dictionary"""
    data = {}
    
    # Load pairing data
    pairing_file = f'selpair_setup_{seat}.csv'
    if not os.path.exists(pairing_file):
        if verbose:
            print(f"  ✗ Missing file: {pairing_file}")
        return None
    
    data['pairings'] = pd.read_csv(pairing_file)
    if verbose:
        print(f"  ✓ Loaded {pairing_file}: {len(data['pairings'])} pairings")
    
    # Load crew records
    crew_file = f'{seat}_crew_records.csv'
    if not os.path.exists(crew_file):
        if verbose:
            print(f"  ✗ Missing file: {crew_file}")
        return None
    
    data['crew'] = pd.read_csv(crew_file)
    if verbose:
        print(f"  ✓ Loaded {crew_file}: {len(data['crew'])} crew members")
    
    # Filter crew for base (use .copy() to avoid SettingWithCopyWarning)
    data['crew'].index = data['crew']['name']
    data['crew_filtered'] = data['crew'][(data['crew']['base'] == base) | (data['crew']['to_base'] == base)].copy()
    if verbose:
        print(f"  ✓ Filtered to {len(data['crew_filtered'])} crew for base {base}")
    
    # Load preferences
    pref_file = 'bid_dat_test.csv'
    if not os.path.exists(pref_file):
        if verbose:
            print(f"  ✗ Missing file: {pref_file}")
        return None
    
    data['prefs'] = pd.read_csv(pref_file)
    data['prefs'] = data['prefs'][data['prefs']['user_name'].isin(data['crew_filtered'].index)].copy()
    if verbose:
        print(f"  ✓ Loaded {pref_file}: {len(data['prefs'])} crew preferences")
    
    # Process days worked
    tot_days = []
    is_tdy = []
    for row in data['crew_filtered'][['non_tdy_days_worked', 'five_day_tdy', 'six_day_tdy', 'base']].values:
        if row[1] and row[3] != base:
            tot_days.append(5)
            is_tdy.append(True)
        elif row[2] and row[3] != base:
            tot_days.append(6)
            is_tdy.append(True)
        else:
            tot_days.append(row[0])
            is_tdy.append(False)
    data['crew_filtered']['tot_days'] = tot_days
    data['crew_filtered']['is_tdy'] = is_tdy
    
    # Filter pairings for base (use .copy() to avoid SettingWithCopyWarning)
    add = ['BCT'] if base == 'OPF' else []
    data['pairings_filtered'] = data['pairings'][data['pairings']['base_start'].isin([base] + add)].copy()
    if verbose:
        print(f"  ✓ Filtered to {len(data['pairings_filtered'])} pairings for base {base}")
    
    # Store metadata
    data['base'] = base
    data['seat'] = seat
    data['d1'] = d1
    data['d2'] = d2
    data['dates'] = [d.strftime('%Y-%m-%d') for d in pd.date_range(d1, d2)]
    
    # Calculate days worked from preferences order
    data['prefs'] = data['prefs'].sort_values(by='user_seniority', ascending=False)
    data['days_worked'] = data['crew_filtered'].loc[data['prefs']['user_name'].values]['tot_days'].values
    
    return data


def print_data_summary(data: Dict):
    """Print a quick summary of the key numbers for easy debugging"""
    
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    days_worked = data['days_worked']
    dates = data['dates']
    base = data['base']
    
    print(f"\n  📊 Quick Data Summary for {base}:")
    print(f"  " + "-" * 50)
    
    # Crew and pairings
    print(f"    Crew members: {len(prefs)}")
    print(f"    Total pairings: {len(pairings)}")
    print(f"    Crew-days to assign: {int(sum(days_worked))}")
    print(f"    Pairing-days available: {int(pairings['mult'].sum())}")
    gap = int(sum(days_worked) - pairings['mult'].sum())
    print(f"    Gap: {gap} {'✓' if gap >= 0 else '⚠️ NEGATIVE'}")
    
    # Pairing breakdown
    if 'mult' in pairings.columns:
        print(f"\n    Pairings by duration:")
        for mult in sorted(pairings['mult'].unique()):
            count = len(pairings[pairings['mult'] == mult])
            days = pairings[pairings['mult'] == mult]['mult'].sum()
            print(f"      {int(mult)}-day: {count} trips ({int(days)} days)")
    
    # Overnight preferences
    if 'overnight_preference' in prefs.columns:
        print(f"\n    Crew overnight preferences:")
        for pref in ['No Overnights', 'Some', 'Many']:
            count = len(prefs[prefs['overnight_preference'] == pref])
            if count > 0:
                print(f"      {pref}: {count}")
    
    # TDY crew
    if 'is_tdy' in data['crew_filtered'].columns:
        tdy_count = data['crew_filtered']['is_tdy'].sum()
        if tdy_count > 0:
            print(f"\n    TDY crew: {int(tdy_count)}")
    
    # Long duty pairings
    if 'dtime' in pairings.columns or 'mlegs' in pairings.columns:
        if 'dtime' in pairings.columns and 'mlegs' in pairings.columns:
            long_duty = ((pairings['dtime'] >= 9 * 3600) | (pairings['mlegs'] >= 5)).sum()
        elif 'dtime' in pairings.columns:
            long_duty = (pairings['dtime'] >= 9 * 3600).sum()
        else:
            long_duty = (pairings['mlegs'] >= 5).sum()
        limit = get_long_duty_limit(base)
        capacity = len(prefs) * limit
        print(f"\n    Long duty trips: {long_duty} (capacity: {capacity})")
    
    print(f"  " + "-" * 50)


def check_supply_demand_balance(data: Dict, verbose: bool) -> DiagnosticReport:
    """Check if total crew-days equals total pairing-days"""
    
    total_crew_days = data['days_worked'].sum()
    total_pairing_days = data['pairings_filtered']['mult'].sum()
    
    gap = total_crew_days - total_pairing_days
    
    details = {
        'total_crew_days': int(total_crew_days),
        'total_pairing_days': int(total_pairing_days),
        'gap': int(gap),
        'num_crew': len(data['prefs']),
        'num_pairings': len(data['pairings_filtered'])
    }
    
    if verbose:
        print(f"\n  Supply/Demand Balance:")
        print(f"    Total crew-days available: {total_crew_days}")
        print(f"    Total pairing-days needed: {total_pairing_days}")
        print(f"    Gap: {gap} {'(surplus)' if gap > 0 else '(deficit)' if gap < 0 else '(balanced)'}")
    
    if gap < 0:
        return DiagnosticReport(
            check_name="Supply/Demand Balance",
            result=DiagnosticResult.FAIL,
            message=f"INFEASIBLE: Need {abs(gap)} more crew-days than available. "
                    f"({total_pairing_days} needed vs {total_crew_days} available)",
            details=details
        )
    elif gap == 0:
        return DiagnosticReport(
            check_name="Supply/Demand Balance",
            result=DiagnosticResult.WARNING,
            message=f"Exactly balanced - no slack for constraints. "
                    f"May be tight but feasible.",
            details=details
        )
    else:
        return DiagnosticReport(
            check_name="Supply/Demand Balance",
            result=DiagnosticResult.PASS,
            message=f"Surplus of {gap} crew-days. Good for constraint flexibility.",
            details=details
        )


def check_daily_coverage(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if each day has enough crew to cover work.
    
    This builds a date-to-pairing map similar to fca.py's dtemap to properly
    count multi-day pairings that span across days.
    """
    
    pairings = data['pairings_filtered'].copy()
    prefs = data['prefs']
    dates = data['dates']
    n_c = len(prefs)
    
    # Build date mapping similar to fca.py
    # A pairing "touches" a day if:
    # - d1 == day OR d2 == day (for 1-2 day pairings)
    # - day is between d1 and d2 (for multi-day pairings)
    pairings['dalidx'] = list(range(len(pairings)))
    
    dtemap = {}
    for ind, d in enumerate(dates):
        # Pairings that start or end on this day
        tmp = pairings[(pairings['d1'] == d) | (pairings['d2'] == d)]
        touching = tmp['dalidx'].values.tolist()
        
        # Also check for 3-day pairings where this day is in the middle
        try:
            if ind > 0 and ind < len(dates) - 1:
                tmp2 = pairings[(pairings['d1'] == dates[ind-1]) & 
                               (pairings['d2'] == dates[ind+1]) & 
                               (pairings['mult'] == 3)]['dalidx'].values.tolist()
                touching.extend(tmp2)
        except:
            pass
        
        # 4-day pairings
        try:
            if ind > 0 and ind < len(dates) - 2:
                tmp3 = pairings[(pairings['d1'] == dates[ind-1]) & 
                               (pairings['d2'] == dates[ind+2]) & 
                               (pairings['mult'] == 4)]['dalidx'].values.tolist()
                touching.extend(tmp3)
        except:
            pass
        try:
            if ind > 1 and ind < len(dates) - 1:
                tmp4 = pairings[(pairings['d1'] == dates[ind-2]) & 
                               (pairings['d2'] == dates[ind+1]) & 
                               (pairings['mult'] == 4)]['dalidx'].values.tolist()
                touching.extend(tmp4)
        except:
            pass
            
        dtemap[d] = list(set(touching))  # Remove duplicates
    
    # Count work per day (number of unique pairings touching that day)
    daily_work = {d: len(dtemap[d]) for d in dates}
    
    # Count vacation per day
    vacation_counts = {}
    for row in prefs[['work_restriction_days', 'vacation_days', 'training_days']].values:
        for col in [row[0], row[1], row[2]]:
            try:
                for date in eval(col):
                    d = date[:10]
                    if d in dates:
                        if d not in vacation_counts:
                            vacation_counts[d] = 0
                        vacation_counts[d] += 1
            except:
                pass
    
    # Check each day
    problem_days = []
    for d in dates:
        work = daily_work.get(d, 0)
        vac = vacation_counts.get(d, 0)
        available = n_c - vac
        
        if available < work:
            problem_days.append({
                'date': d,
                'work_needed': work,
                'crew_available': available,
                'deficit': work - available
            })
    
    if verbose:
        print(f"\n  Daily Coverage Check:")
        print(f"    Total crew: {n_c}")
        print(f"    Days checked: {len(dates)}")
        if problem_days:
            print(f"    ⚠ Problem days found: {len(problem_days)}")
            for pd_item in problem_days[:3]:  # Show first 3
                print(f"      {pd_item['date']}: need {pd_item['work_needed']}, "
                      f"have {pd_item['crew_available']} (deficit: {pd_item['deficit']})")
        else:
            print(f"    ✓ All days have sufficient crew coverage")
    
    if problem_days:
        return DiagnosticReport(
            check_name="Daily Coverage",
            result=DiagnosticResult.FAIL,
            message=f"{len(problem_days)} day(s) have more trips than available crew. "
                    f"Worst: {problem_days[0]['date']} needs {problem_days[0]['work_needed']} "
                    f"crew but only {problem_days[0]['crew_available']} available.",
            details={'problem_days': problem_days}
        )
    else:
        return DiagnosticReport(
            check_name="Daily Coverage",
            result=DiagnosticResult.PASS,
            message="All days have sufficient crew to cover work"
        )


def check_vacation_conflicts(data: Dict, verbose: bool) -> DiagnosticReport:
    """Check for any obvious vacation blocking issues - aggregate level"""
    
    prefs = data['prefs']
    total_vacation_days = 0
    crew_with_vacation = 0
    
    for row in prefs[['work_restriction_days', 'vacation_days', 'training_days']].values:
        days = 0
        for col in [row[0], row[1], row[2]]:
            try:
                days += len(eval(col))
            except:
                pass
        if days > 0:
            crew_with_vacation += 1
            total_vacation_days += days
    
    details = {
        'crew_with_vacation': crew_with_vacation,
        'total_vacation_days': total_vacation_days,
        'avg_per_crew': total_vacation_days / len(prefs) if len(prefs) > 0 else 0
    }
    
    if verbose:
        print(f"\n  Vacation Analysis (Aggregate):")
        print(f"    Crew with vacation/restrictions: {crew_with_vacation}")
        print(f"    Total vacation days: {total_vacation_days}")
        print(f"    Average per crew: {details['avg_per_crew']:.1f}")
    
    return DiagnosticReport(
        check_name="Vacation Analysis",
        result=DiagnosticResult.PASS,
        message=f"{crew_with_vacation} crew have vacation blocking {total_vacation_days} total days",
        details=details
    )


def check_individual_crew_feasibility(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if each crew member has enough available days to work their required days.
    
    This catches cases where a crew member needs to work 15 days in a 30-day period,
    but has 20 vacation/restricted days, making it impossible.
    """
    
    prefs = data['prefs']
    dates = data['dates']
    days_worked = data['days_worked']
    n_dates = len(dates)
    
    # Convert dates to set for fast lookup
    dates_set = set(dates)
    
    impossible_crew = []
    tight_crew = []
    
    for idx, (crew_idx, row) in enumerate(prefs[['user_name', 'work_restriction_days', 'vacation_days', 'training_days']].iterrows()):
        crew_name = row['user_name']
        required_days = days_worked[idx]
        
        # Count restricted days within the date range
        restricted_dates = set()
        for col in [row['work_restriction_days'], row['vacation_days'], row['training_days']]:
            try:
                for date in eval(col):
                    d = date[:10]  # Extract YYYY-MM-DD
                    if d in dates_set:
                        restricted_dates.add(d)
            except:
                pass
        
        restricted_count = len(restricted_dates)
        available_days = n_dates - restricted_count
        slack = available_days - required_days
        
        crew_info = {
            'name': crew_name,
            'required_days': int(required_days),
            'restricted_days': restricted_count,
            'available_days': available_days,
            'slack': slack,
            'period_days': n_dates
        }
        
        if slack < 0:
            # Impossible: not enough days to work
            impossible_crew.append(crew_info)
        elif slack <= 2:
            # Very tight: only 0-2 days of flexibility
            tight_crew.append(crew_info)
    
    if verbose:
        print(f"\n  Individual Crew Feasibility (Vacation vs Required Work):")
        print(f"    Period length: {n_dates} days")
        print(f"    Crew checked: {len(prefs)}")
        
        if impossible_crew:
            print(f"\n    ⚠️ IMPOSSIBLE ({len(impossible_crew)} crew cannot meet requirements):")
            for c in impossible_crew[:5]:  # Show first 5
                print(f"      • {c['name']}: needs {c['required_days']} days, "
                      f"but only {c['available_days']} available "
                      f"({c['restricted_days']} restricted)")
            if len(impossible_crew) > 5:
                print(f"      ... and {len(impossible_crew) - 5} more")
        
        if tight_crew:
            print(f"\n    ⚠️ TIGHT ({len(tight_crew)} crew have ≤2 days slack):")
            for c in tight_crew[:3]:  # Show first 3
                print(f"      • {c['name']}: needs {c['required_days']} days, "
                      f"has {c['available_days']} available (slack: {c['slack']})")
            if len(tight_crew) > 3:
                print(f"      ... and {len(tight_crew) - 3} more")
        
        if not impossible_crew and not tight_crew:
            print(f"    ✓ All crew have sufficient available days")
    
    if impossible_crew:
        return DiagnosticReport(
            check_name="Individual Crew Feasibility",
            result=DiagnosticResult.FAIL,
            message=f"INFEASIBLE: {len(impossible_crew)} crew member(s) have more restricted days "
                    f"than can fit their required work. First: {impossible_crew[0]['name']} "
                    f"needs {impossible_crew[0]['required_days']} days but only has "
                    f"{impossible_crew[0]['available_days']} available.",
            details={'impossible_crew': impossible_crew, 'tight_crew': tight_crew}
        )
    elif tight_crew:
        return DiagnosticReport(
            check_name="Individual Crew Feasibility",
            result=DiagnosticResult.WARNING,
            message=f"{len(tight_crew)} crew member(s) have very little scheduling flexibility "
                    f"(≤2 days slack). This may make the problem hard to solve.",
            details={'impossible_crew': impossible_crew, 'tight_crew': tight_crew}
        )
    else:
        return DiagnosticReport(
            check_name="Individual Crew Feasibility",
            result=DiagnosticResult.PASS,
            message="All crew have sufficient available days for their required work",
            details={'impossible_crew': [], 'tight_crew': []}
        )


def check_pairing_vacation_coverage(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if there are any pairings that NO crew member can be assigned to
    because everyone is blocked by vacation on at least one day the pairing touches.
    
    This is the key check for vacation-related infeasibility!
    """
    
    pairings = data['pairings_filtered'].copy()
    prefs = data['prefs']
    dates = data['dates']
    dates_set = set(dates)
    
    # Build vacation sets for each crew member
    crew_vacation = {}
    for idx, row in prefs[['user_name', 'work_restriction_days', 'vacation_days', 'training_days']].iterrows():
        crew_name = row['user_name']
        blocked_dates = set()
        for col in [row['work_restriction_days'], row['vacation_days'], row['training_days']]:
            try:
                for date in eval(col):
                    d = date[:10]
                    if d in dates_set:
                        blocked_dates.add(d)
            except:
                pass
        crew_vacation[crew_name] = blocked_dates
    
    # Build a mapping of which dates each pairing touches
    pairings['dalidx'] = list(range(len(pairings)))
    
    # For each pairing, find all dates it touches
    pairing_dates = {}
    for idx, row in pairings.iterrows():
        pairing_id = row['dalidx']
        d1 = row['d1']
        d2 = row['d2'] if pd.notna(row['d2']) else d1
        mult = row['mult'] if 'mult' in row else 1
        
        # Get all dates this pairing spans
        touched_dates = set()
        if d1 in dates_set:
            touched_dates.add(d1)
        if d2 in dates_set and d2 != d1:
            touched_dates.add(d2)
        
        # For multi-day pairings, include middle days
        if mult >= 3 and d1 in dates_set and d2 in dates_set:
            try:
                d1_idx = dates.index(d1)
                d2_idx = dates.index(d2)
                for i in range(d1_idx, d2_idx + 1):
                    if i < len(dates):
                        touched_dates.add(dates[i])
            except ValueError:
                pass
        
        pairing_dates[pairing_id] = touched_dates
    
    # Check each pairing: how many crew members can be assigned?
    uncovered_pairings = []
    low_coverage_pairings = []
    
    crew_names = list(crew_vacation.keys())
    n_crew = len(crew_names)
    
    for pairing_id, touched in pairing_dates.items():
        if not touched:
            continue
            
        # Count how many crew can take this pairing (not blocked on any touched date)
        eligible_count = 0
        for crew_name in crew_names:
            blocked = crew_vacation[crew_name]
            # Crew is eligible if none of their blocked dates overlap with pairing dates
            if not touched.intersection(blocked):
                eligible_count += 1
        
        pairing_info = pairings[pairings['dalidx'] == pairing_id].iloc[0]
        
        if eligible_count == 0:
            uncovered_pairings.append({
                'idx': pairing_info.get('idx', f'Pairing {pairing_id}'),
                'd1': pairing_info['d1'],
                'd2': pairing_info.get('d2', ''),
                'mult': pairing_info.get('mult', 1),
                'touched_dates': list(touched),
                'eligible_crew': 0
            })
        elif eligible_count <= 2:
            low_coverage_pairings.append({
                'idx': pairing_info.get('idx', f'Pairing {pairing_id}'),
                'd1': pairing_info['d1'],
                'eligible_crew': eligible_count
            })
    
    if verbose:
        print(f"\n  Pairing Vacation Coverage Check:")
        print(f"    Total pairings: {len(pairings)}")
        print(f"    Crew members: {n_crew}")
        
        if uncovered_pairings:
            print(f"\n    ⚠️ UNCOVERED PAIRINGS ({len(uncovered_pairings)} pairings NO crew can take):")
            for p in uncovered_pairings[:5]:
                dates_str = ', '.join(p['touched_dates'][:3])
                if len(p['touched_dates']) > 3:
                    dates_str += f"... ({len(p['touched_dates'])} days)"
                print(f"      • {p['idx']} ({p['d1']} to {p['d2']}, {p['mult']} days)")
                print(f"        Touches dates: {dates_str}")
                print(f"        All {n_crew} crew are blocked on at least one of these dates!")
            if len(uncovered_pairings) > 5:
                print(f"      ... and {len(uncovered_pairings) - 5} more uncovered pairings")
        elif low_coverage_pairings:
            print(f"    ⚠️ {len(low_coverage_pairings)} pairings have only 1-2 eligible crew")
        else:
            print(f"    ✓ All pairings have at least one eligible crew member")
    
    if uncovered_pairings:
        return DiagnosticReport(
            check_name="Pairing Vacation Coverage",
            result=DiagnosticResult.FAIL,
            message=f"{len(uncovered_pairings)} pairing(s) cannot be assigned because ALL crew members "
                    f"are blocked by vacation on at least one day. "
                    f"First: {uncovered_pairings[0]['idx']} ({uncovered_pairings[0]['d1']}) - "
                    f"no crew available.",
            details={'uncovered_pairings': uncovered_pairings, 'low_coverage': low_coverage_pairings}
        )
    elif low_coverage_pairings:
        return DiagnosticReport(
            check_name="Pairing Vacation Coverage",
            result=DiagnosticResult.WARNING,
            message=f"{len(low_coverage_pairings)} pairing(s) have only 1-2 eligible crew members. "
                    f"This makes scheduling very tight.",
            details={'low_coverage': low_coverage_pairings}
        )
    else:
        return DiagnosticReport(
            check_name="Pairing Vacation Coverage",
            result=DiagnosticResult.PASS,
            message="All pairings have at least one eligible crew member (not blocked by vacation)"
        )


def check_tdy_contiguity(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if TDY crew can work their required days in one contiguous block.
    
    TDY crew have a constraint that they can only work in one "chunk" - 
    their work days must be consecutive (no vacation splitting their work).
    """
    
    prefs = data['prefs']
    dates = data['dates']
    days_worked = data['days_worked']
    crew_filtered = data['crew_filtered']
    n_dates = len(dates)
    dates_set = set(dates)
    
    # Get TDY status for each crew member
    tdy_status = crew_filtered.loc[prefs['user_name'].values]['is_tdy'].values
    
    impossible_tdy = []
    
    if verbose:
        print(f"\n  TDY Contiguity Check:")
        tdy_count = sum(tdy_status)
        print(f"    TDY crew members: {tdy_count}")
    
    for idx, (crew_idx, row) in enumerate(prefs[['user_name', 'work_restriction_days', 'vacation_days', 'training_days']].iterrows()):
        if not tdy_status[idx]:
            continue  # Skip non-TDY crew
            
        crew_name = row['user_name']
        required_days = int(days_worked[idx])
        
        # Get restricted dates for this crew member
        restricted_dates = set()
        for col in [row['work_restriction_days'], row['vacation_days'], row['training_days']]:
            try:
                for date in eval(col):
                    d = date[:10]
                    if d in dates_set:
                        restricted_dates.add(d)
            except:
                pass
        
        # Build availability array (1 = can work, 0 = restricted)
        availability = []
        for d in dates:
            availability.append(0 if d in restricted_dates else 1)
        
        # Find the longest contiguous block of available days
        max_contiguous = 0
        current_contiguous = 0
        for avail in availability:
            if avail == 1:
                current_contiguous += 1
                max_contiguous = max(max_contiguous, current_contiguous)
            else:
                current_contiguous = 0
        
        # TDY crew need to fit all their work days in one contiguous block
        if max_contiguous < required_days:
            impossible_tdy.append({
                'name': crew_name,
                'required_days': required_days,
                'max_contiguous': max_contiguous,
                'restricted_count': len(restricted_dates)
            })
    
    if verbose:
        if impossible_tdy:
            print(f"    ⚠️ TDY crew who CANNOT work in one block ({len(impossible_tdy)}):")
            for t in impossible_tdy[:3]:
                print(f"      • {t['name']}: needs {t['required_days']} consecutive days, "
                      f"but longest available block is {t['max_contiguous']} days")
            if len(impossible_tdy) > 3:
                print(f"      ... and {len(impossible_tdy) - 3} more")
        else:
            print(f"    ✓ All TDY crew can work in one contiguous block")
    
    if impossible_tdy:
        return DiagnosticReport(
            check_name="TDY Contiguity",
            result=DiagnosticResult.FAIL,
            message=f"{len(impossible_tdy)} TDY crew member(s) have vacation that splits the period, "
                    f"making it impossible to work their required days in one block. "
                    f"First: {impossible_tdy[0]['name']} needs {impossible_tdy[0]['required_days']} "
                    f"consecutive days but can only get {impossible_tdy[0]['max_contiguous']}.",
            details={'impossible_tdy': impossible_tdy}
        )
    else:
        return DiagnosticReport(
            check_name="TDY Contiguity",
            result=DiagnosticResult.PASS,
            message="All TDY crew can work in one contiguous block"
        )


def check_long_duty_limits(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if long-duty pairings can be distributed within limits.
    
    Uses LONG_DUTY_LIMITS from fca.py so the diagnostic stays in sync
    with the actual optimization constraints.
    
    A "long duty" pairing has duty time >= 9 hours OR 5+ legs
    """
    
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    base = data['base']
    n_c = len(prefs)
    
    # Get limit from fca.py config (stays in sync with actual constraint)
    limit_per_crew = get_long_duty_limit(base)
    
    # Count long duty pairings
    long_duty_count = 0
    if 'dtime' in pairings.columns and 'mlegs' in pairings.columns:
        long_duty_mask = (pairings['dtime'] >= 9 * 3600) | (pairings['mlegs'] >= 5)
        long_duty_count = long_duty_mask.sum()
    elif 'dtime' in pairings.columns:
        long_duty_count = (pairings['dtime'] >= 9 * 3600).sum()
    elif 'mlegs' in pairings.columns:
        long_duty_count = (pairings['mlegs'] >= 5).sum()
    
    # Total capacity for long duty trips
    total_capacity = n_c * limit_per_crew
    deficit = long_duty_count - total_capacity
    
    if verbose:
        print(f"\n  Long Duty Trip Limits (from fca.py config):")
        print(f"    Long duty trips (9+ hrs or 5+ legs): {long_duty_count}")
        print(f"    Limit per crew member: {limit_per_crew}")
        print(f"    Total capacity ({n_c} crew × {limit_per_crew}): {total_capacity}")
    
    if deficit > 0:
        if verbose:
            print(f"    ⚠️ OVER CAPACITY by {deficit} trips!")
        return DiagnosticReport(
            check_name="Long Duty Limits",
            result=DiagnosticResult.FAIL,
            message=f"There are {long_duty_count} long-duty trips but crew can only handle "
                    f"{total_capacity} total ({n_c} crew × {limit_per_crew} each). "
                    f"Over capacity by {deficit} trips. "
                    f"To fix: increase LONG_DUTY_LIMITS['{base}'] in fca.py",
            details={'long_duty_count': long_duty_count, 'capacity': total_capacity, 'deficit': deficit}
        )
    elif total_capacity - long_duty_count < n_c:
        if verbose:
            print(f"    ⚠️ Tight - only {total_capacity - long_duty_count} slots of slack")
        return DiagnosticReport(
            check_name="Long Duty Limits",
            result=DiagnosticResult.WARNING,
            message=f"Long duty trips ({long_duty_count}) are close to capacity ({total_capacity}). "
                    f"May be hard to distribute evenly.",
            details={'long_duty_count': long_duty_count, 'capacity': total_capacity}
        )
    else:
        if verbose:
            print(f"    ✓ Within limits")
        return DiagnosticReport(
            check_name="Long Duty Limits",
            result=DiagnosticResult.PASS,
            message=f"Long duty trips ({long_duty_count}) are within capacity ({total_capacity})"
        )


def analyze_constraints(data: Dict, verbose: bool) -> List[DiagnosticReport]:
    """Check for fatigue rule violations and overnight assignment issues"""
    
    reports = []
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    dates = data['dates']
    days_worked = data['days_worked']
    
    if verbose:
        print(f"\n  Checking Scheduling Rules:")
    
    # Check for 3+ day pairings vs crew who want overnights
    long_pairings = pairings[pairings['mult'] >= 3] if 'mult' in pairings.columns else pd.DataFrame()
    many_overnight_crew = len(prefs[prefs['overnight_preference'] == 'Many']) if 'overnight_preference' in prefs.columns else 0
    
    if verbose:
        print(f"    3+ day trips: {len(long_pairings)}")
        print(f"    Crew who want many overnights: {many_overnight_crew}")
    
    if len(long_pairings) > 0 and many_overnight_crew == 0:
        reports.append(DiagnosticReport(
            check_name="3+ Day Trip Assignment",
            result=DiagnosticResult.FAIL,
            message=f"There are {len(long_pairings)} trips that are 3+ days, but no crew members "
                    f"selected 'Many Overnights' preference. These trips cannot be assigned.",
            details={'long_pairings': len(long_pairings), 'many_overnight_crew': many_overnight_crew}
        ))
    elif len(long_pairings) > many_overnight_crew * 5:
        reports.append(DiagnosticReport(
            check_name="3+ Day Trip Assignment",
            result=DiagnosticResult.WARNING,
            message=f"There are {len(long_pairings)} trips that are 3+ days, but only "
                    f"{many_overnight_crew} crew want many overnights. This may be tight.",
            details={'long_pairings': len(long_pairings), 'many_overnight_crew': many_overnight_crew}
        ))
    else:
        if verbose:
            print(f"    ✓ 3+ day trips can be assigned")
        reports.append(DiagnosticReport(
            check_name="3+ Day Trip Assignment",
            result=DiagnosticResult.PASS,
            message=f"3+ day trips can be assigned to willing crew"
        ))
    
    # Check overnight distribution (single vs multi-day pairings)
    overnight_report = check_overnight_distribution(data, verbose)
    reports.append(overnight_report)
    
    # Check fatigue rules
    fatigue_report = check_fatigue_rules(data, verbose)
    reports.append(fatigue_report)
    
    # Check reserve distribution
    reserve_report = check_reserve_distribution(data, verbose)
    if reserve_report:
        reports.append(reserve_report)
    
    return reports


def check_reserve_distribution(data: Dict, verbose: bool) -> Optional[DiagnosticReport]:
    """
    Check if reserve pairings can be distributed within limits.
    
    In fca.py, each crew member can only have up to max_days/1.5 reserve pairings.
    """
    
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    days_worked = data['days_worked']
    
    # Find reserve pairings (identified by 'R' in the idx column)
    if 'idx' not in pairings.columns:
        return None
    
    reserve_pairings = pairings[pairings['idx'].str.contains('R', na=False)]
    n_reserves = len(reserve_pairings)
    
    if n_reserves == 0:
        return None  # No reserves to check
    
    # Calculate total reserve capacity
    # Each crew can have at most max_days/1.5 reserves
    total_reserve_capacity = 0
    for days in days_worked:
        total_reserve_capacity += int(days / 1.5)
    
    if verbose:
        print(f"\n  Reserve Distribution Check:")
        print(f"    Reserve pairings: {n_reserves}")
        print(f"    Total reserve capacity: {total_reserve_capacity}")
    
    if n_reserves > total_reserve_capacity:
        deficit = n_reserves - total_reserve_capacity
        if verbose:
            print(f"    ⚠️ Too many reserves! Over capacity by {deficit}")
        return DiagnosticReport(
            check_name="Reserve Distribution",
            result=DiagnosticResult.FAIL,
            message=f"There are {n_reserves} reserve pairings but crew can only handle "
                    f"{total_reserve_capacity} total. Over capacity by {deficit}.",
            details={'n_reserves': n_reserves, 'capacity': total_reserve_capacity}
        )
    else:
        if verbose:
            print(f"    ✓ Reserves within capacity")
        return DiagnosticReport(
            check_name="Reserve Distribution",
            result=DiagnosticResult.PASS,
            message=f"Reserve pairings ({n_reserves}) are within capacity ({total_reserve_capacity})"
        )


def check_overnight_distribution(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if the mix of single-day vs multi-day pairings matches crew preferences.
    
    In fca.py, crew who want "No Overnights" can only be assigned single-day pairings,
    and crew who want "Many Overnights" get multi-day pairings.
    
    This checks if there are enough single-day pairings for crew who don't want overnights.
    """
    
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    days_worked = data['days_worked']
    
    if 'mult' not in pairings.columns or 'overnight_preference' not in prefs.columns:
        return DiagnosticReport(
            check_name="Overnight Distribution",
            result=DiagnosticResult.PASS,
            message="Cannot check overnight distribution (missing data columns)"
        )
    
    # Count pairings by type
    single_day_pairings = pairings[pairings['mult'] == 1]
    multi_day_pairings = pairings[pairings['mult'] >= 2]
    
    single_day_count = len(single_day_pairings)
    multi_day_count = len(multi_day_pairings)
    
    # Count days by type
    single_day_total = single_day_pairings['mult'].sum() if len(single_day_pairings) > 0 else 0
    multi_day_total = multi_day_pairings['mult'].sum() if len(multi_day_pairings) > 0 else 0
    
    # Count crew by preference
    no_overnight_crew = prefs[prefs['overnight_preference'] == 'No Overnights']
    many_overnight_crew = prefs[prefs['overnight_preference'] == 'Many']
    some_overnight_crew = prefs[prefs['overnight_preference'] == 'Some']
    
    n_no_overnight = len(no_overnight_crew)
    n_many_overnight = len(many_overnight_crew)
    n_some_overnight = len(some_overnight_crew)
    
    # Calculate days needed by "No Overnights" crew
    no_overnight_indices = no_overnight_crew.index.tolist()
    no_overnight_days_needed = 0
    for idx, row in prefs.iterrows():
        if row['overnight_preference'] == 'No Overnights':
            crew_idx = prefs.index.get_loc(idx)
            no_overnight_days_needed += days_worked[crew_idx]
    
    if verbose:
        print(f"\n  Overnight Distribution Check:")
        print(f"    Single-day trips: {single_day_count} ({single_day_total} days)")
        print(f"    Multi-day trips: {multi_day_count} ({multi_day_total} days)")
        print(f"    Crew wanting 'No Overnights': {n_no_overnight} (need {no_overnight_days_needed} days)")
        print(f"    Crew wanting 'Many Overnights': {n_many_overnight}")
        print(f"    Crew wanting 'Some Overnights': {n_some_overnight}")
    
    # Check if there are enough single-day pairings for "No Overnights" crew
    if single_day_total < no_overnight_days_needed:
        deficit = no_overnight_days_needed - single_day_total
        if verbose:
            print(f"    ⚠️ Not enough single-day trips! Deficit: {deficit} days")
        return DiagnosticReport(
            check_name="Overnight Distribution",
            result=DiagnosticResult.FAIL,
            message=f"Crew who want 'No Overnights' need {no_overnight_days_needed} days of single-day trips, "
                    f"but there are only {single_day_total} days available. "
                    f"Short by {deficit} days.",
            details={
                'single_day_total': int(single_day_total),
                'no_overnight_days_needed': int(no_overnight_days_needed),
                'deficit': int(deficit)
            }
        )
    
    # Check if multi-day pairings can be absorbed
    # Crew who want "Many" or "Some" overnights can take multi-day pairings
    crew_for_multi = n_many_overnight + n_some_overnight
    if multi_day_count > 0 and crew_for_multi == 0:
        if verbose:
            print(f"    ⚠️ Multi-day trips exist but no crew want overnights!")
        return DiagnosticReport(
            check_name="Overnight Distribution",
            result=DiagnosticResult.FAIL,
            message=f"There are {multi_day_count} multi-day (overnight) trips, but no crew members "
                    f"want overnights. These trips cannot be assigned.",
            details={'multi_day_count': multi_day_count, 'crew_for_multi': crew_for_multi}
        )
    
    if verbose:
        print(f"    ✓ Overnight distribution looks feasible")
    
    return DiagnosticReport(
        check_name="Overnight Distribution",
        result=DiagnosticResult.PASS,
        message=f"Single-day trips ({single_day_total} days) can cover 'No Overnights' crew ({no_overnight_days_needed} days needed)"
    )


def check_fatigue_rules(data: Dict, verbose: bool) -> DiagnosticReport:
    """
    Check if fatigue rules (7-in-a-row, 8-in-10, 10-in-14) can be satisfied.
    
    These rules are:
    - No more than 7 consecutive work days
    - No more than 8 work days in any 10-day window
    - No more than 10 work days in any 14-day window
    """
    
    prefs = data['prefs']
    dates = data['dates']
    days_worked = data['days_worked']
    n_dates = len(dates)
    dates_set = set(dates)
    
    violations = []
    warnings_list = []
    
    if verbose:
        print(f"\n  Fatigue Rules Check:")
        print(f"    Rules: Max 7 consecutive | Max 8 in 10 days | Max 10 in 14 days")
    
    for idx, (crew_idx, row) in enumerate(prefs[['user_name', 'work_restriction_days', 'vacation_days', 'training_days']].iterrows()):
        crew_name = row['user_name']
        required_days = days_worked[idx]
        
        # Get restricted dates for this crew member
        restricted_dates = set()
        for col in [row['work_restriction_days'], row['vacation_days'], row['training_days']]:
            try:
                for date in eval(col):
                    d = date[:10]
                    if d in dates_set:
                        restricted_dates.add(d)
            except:
                pass
        
        # Build availability array (1 = can work, 0 = restricted)
        availability = []
        for d in dates:
            availability.append(0 if d in restricted_dates else 1)
        
        available_days = sum(availability)
        
        # Skip if already impossible (caught by other check)
        if available_days < required_days:
            continue
        
        # Check: Can they work their required days without violating fatigue rules?
        # We'll check the "worst case" - what if their restricted days create
        # forced work patterns that violate rules?
        
        crew_issues = []
        
        # Check for forced 8+ consecutive work days
        # If there's a gap of restricted days that forces work on both sides
        consecutive_available = 0
        max_consecutive = 0
        for i, avail in enumerate(availability):
            if avail == 1:
                consecutive_available += 1
                max_consecutive = max(max_consecutive, consecutive_available)
            else:
                consecutive_available = 0
        
        # Check each 10-day window
        for i in range(n_dates - 9):
            window_available = sum(availability[i:i+10])
            # If more than 8 days available in window, we might exceed 8-in-10
            # But the real issue is if we MUST work > 8 days in a 10-day window
            # This happens if required_days is high relative to available spread
        
        # Check each 14-day window  
        for i in range(n_dates - 13):
            window_available = sum(availability[i:i+14])
        
        # Simplified check: If required days > 10 and available days cluster together,
        # the 10-in-14 rule might be violated
        
        # More practical check: Look for "dense" required work periods
        # If crew needs many days and has vacation clusters, check windows around vacation
        
        # Find vacation clusters and check surrounding windows
        if required_days >= 10:
            # Check if any 14-day window has all available days < required work
            min_window_14 = n_dates
            for i in range(n_dates - 13):
                window_available = sum(availability[i:i+14])
                min_window_14 = min(min_window_14, window_available)
            
            # If smallest 14-day window has <10 available but crew needs many days,
            # they might not be able to spread work out
            if min_window_14 < 10 and required_days > available_days - 4:
                crew_issues.append(f"tight 14-day windows (min {min_window_14} available)")
        
        if required_days >= 8:
            # Check 10-day windows
            min_window_10 = n_dates
            for i in range(n_dates - 9):
                window_available = sum(availability[i:i+10])
                min_window_10 = min(min_window_10, window_available)
            
            if min_window_10 < 8 and required_days > available_days - 3:
                crew_issues.append(f"tight 10-day windows (min {min_window_10} available)")
        
        # Check for stretches where vacation forces dense work
        # Look for vacation gaps that create "islands" of work
        work_islands = []
        current_island = 0
        for avail in availability:
            if avail == 1:
                current_island += 1
            else:
                if current_island > 0:
                    work_islands.append(current_island)
                current_island = 0
        if current_island > 0:
            work_islands.append(current_island)
        
        # If the largest island is smaller than required days, work must span multiple islands
        # which is fine. But if an island is exactly 8-10 days and they need most of those days,
        # it could force 8 consecutive
        for island in work_islands:
            if 8 <= island <= 10:
                # This island could force 7+ consecutive if heavily loaded
                if required_days >= available_days - 2:
                    crew_issues.append(f"may be forced into 7+ consecutive work days")
                    break
        
        if crew_issues:
            warnings_list.append({
                'name': crew_name,
                'required': int(required_days),
                'available': available_days,
                'issues': crew_issues
            })
    
    if verbose:
        if warnings_list:
            print(f"\n    ⚠️ Potential fatigue rule issues ({len(warnings_list)} crew):")
            for w in warnings_list[:3]:
                print(f"      • {w['name']}: {', '.join(w['issues'])}")
            if len(warnings_list) > 3:
                print(f"      ... and {len(warnings_list) - 3} more")
        else:
            print(f"    ✓ Fatigue rules appear satisfiable")
    
    if warnings_list:
        return DiagnosticReport(
            check_name="Fatigue Rules (7 consecutive, 8-in-10, 10-in-14)",
            result=DiagnosticResult.WARNING,
            message=f"{len(warnings_list)} crew member(s) have vacation patterns that may make "
                    f"fatigue rules hard to satisfy. Check: {warnings_list[0]['name']} - "
                    f"{', '.join(warnings_list[0]['issues'])}",
            details={'warnings': warnings_list}
        )
    else:
        return DiagnosticReport(
            check_name="Fatigue Rules (7 consecutive, 8-in-10, 10-in-14)",
            result=DiagnosticResult.PASS,
            message="Fatigue rules appear satisfiable for all crew"
        )


def test_feasibility_incremental(data: Dict, verbose: bool) -> List[DiagnosticReport]:
    """
    Test feasibility by incrementally adding constraint groups.
    This helps identify which constraint group causes infeasibility.
    """
    reports = []
    
    pairings = data['pairings_filtered'].copy()
    prefs = data['prefs'].copy()
    dates = data['dates']
    
    n_c = len(prefs)
    n_p = len(pairings)
    
    if n_c == 0 or n_p == 0:
        reports.append(DiagnosticReport(
            check_name="Feasibility Test",
            result=DiagnosticResult.FAIL,
            message="Cannot test feasibility: no crew or no pairings"
        ))
        return reports
    
    pairings['dalidx'] = list(range(len(pairings)))
    pdays = pairings['mult'].astype(int).values
    
    # Build date mapping
    dtemap = {}
    for ind, d in enumerate(dates):
        tmp = pairings[(pairings['d1'] == d) | (pairings['d2'] == d)]
        dtemap[d] = tmp['dalidx'].values.tolist()
    
    # Get days worked
    days_worked = data['days_worked']
    
    # Define constraint groups to test
    constraint_groups = [
        ("Coverage (all pairings assigned once)", "coverage"),
        ("Max days per crew", "max_days"),
        ("Min days per crew", "min_days"),
        ("One duty per day", "one_per_day"),
        ("Work window limits (7-in-8, etc.)", "windows"),
    ]
    
    if verbose:
        print(f"\n  Incremental Feasibility Testing:")
        print(f"  Testing constraint groups one by one...\n")
    
    # Create base problem
    xp = cp.Variable((n_c, n_p), boolean=True)
    
    active_constraints = []
    last_feasible = None
    
    for group_name, group_id in constraint_groups:
        constraints = active_constraints.copy()
        
        # Add constraints for this group
        if group_id == "coverage":
            for p in range(n_p):
                constraints.append(cp.sum(xp[:, p]) == 1)
        
        elif group_id == "max_days":
            for c in range(n_c):
                constraints.append(cp.sum(cp.multiply(xp[c], pdays)) <= days_worked[c])
        
        elif group_id == "min_days":
            for c in range(n_c):
                constraints.append(cp.sum(cp.multiply(xp[c], pdays)) >= days_worked[c])
        
        elif group_id == "one_per_day":
            for d in dates:
                arr = np.array(dtemap.get(d, []))
                if len(arr) > 0:
                    constraints.append(cp.sum(xp[:, arr], axis=1) <= 1)
        
        elif group_id == "windows":
            dtemap_np = {d: np.array(dtemap.get(d, [])) for d in dates}
            for c in range(n_c):
                day_sums = []
                for d in dates:
                    arr = dtemap_np[d]
                    if len(arr) > 0:
                        day_sums.append(cp.sum(xp[c, arr]))
                    else:
                        day_sums.append(0)
                day_sums = cp.vstack(day_sums)
                
                # 7 in 8 constraint
                for i in range(len(dates) - 8):
                    constraints.append(cp.sum(day_sums[i:i+8]) <= 7)
        
        # Test feasibility with current constraint set
        prob = cp.Problem(cp.Minimize(0), constraints)
        
        try:
            prob.solve(solver='CBC', maximumSeconds=30, verbose=False)
            status = prob.status
        except Exception as e:
            status = f"error: {str(e)}"
        
        is_feasible = status in ['optimal', 'optimal_inaccurate']
        
        if verbose:
            symbol = "✓" if is_feasible else "✗"
            print(f"    {symbol} {group_name}: {status}")
        
        if is_feasible:
            last_feasible = group_id
            active_constraints = constraints  # Keep these constraints for next iteration
        else:
            # Found the problematic constraint group
            reports.append(DiagnosticReport(
                check_name=f"Feasibility: {group_name}",
                result=DiagnosticResult.FAIL,
                message=f"Problem becomes INFEASIBLE when adding '{group_name}' constraints. "
                        f"Previous feasible state: {last_feasible or 'none'}",
                details={'failed_group': group_id, 'last_feasible': last_feasible, 'status': status}
            ))
            return reports
    
    # All constraint groups passed
    reports.append(DiagnosticReport(
        check_name="Feasibility Test",
        result=DiagnosticResult.PASS,
        message="Problem is feasible with core constraints. "
                "If full optimization fails, check advanced constraints (overnight limits, etc.)"
    ))
    
    return reports


def print_summary(reports: List[DiagnosticReport]):
    """Print a summary of all diagnostic reports"""
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")
    
    failures = [r for r in reports if r.result == DiagnosticResult.FAIL]
    warnings = [r for r in reports if r.result == DiagnosticResult.WARNING]
    passes = [r for r in reports if r.result == DiagnosticResult.PASS]
    
    if failures:
        print("🔴 PROBLEMS FOUND - Optimization will NOT work until fixed:")
        print()
        for r in failures:
            print(f"   • {r.message}")
        print()
    
    if warnings:
        print("🟡 POTENTIAL ISSUES - May cause problems:")
        print()
        for r in warnings:
            print(f"   • {r.message}")
        print()
    
    if not failures and not warnings:
        print("🟢 ALL CHECKS PASSED")
        print()
    
    print(f"{'='*60}")
    if failures:
        print("NEXT STEP: Fix the problems above before running optimization.")
    elif warnings:
        print("NEXT STEP: Optimization may work but could be slow or fail.")
        print("           Consider adjusting vacation/work assignments if it fails.")
    else:
        print("NEXT STEP: Run the optimization - it should work!")
        print("           If it still fails, try increasing the time limit.")
    print(f"{'='*60}\n")


def diagnose_from_args():
    """Run diagnosis from command line arguments"""
    if len(sys.argv) < 3:
        print("Usage: python fca_diagnose.py <BASE> <SEAT> [START_DATE] [END_DATE]")
        print("Example: python fca_diagnose.py DAL FO 2025-01-01 2025-01-31")
        sys.exit(1)
    
    base = sys.argv[1].upper()
    seat = sys.argv[2].upper()
    
    # Get dates from utils or use defaults
    try:
        from utils import get_date_range
        default_d1, default_d2 = get_date_range()
    except:
        default_d1, default_d2 = "2025-01-01", "2025-01-31"
    
    d1 = sys.argv[3] if len(sys.argv) > 3 else default_d1
    d2 = sys.argv[4] if len(sys.argv) > 4 else default_d2
    
    reports = diagnose_optimization(base, seat, d1, d2, verbose=True)
    
    # Return exit code based on failures
    failures = [r for r in reports if r.result == DiagnosticResult.FAIL]
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    diagnose_from_args()


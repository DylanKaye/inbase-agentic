"""
MIP Diagnostic Tool for FCA Optimization

This module provides comprehensive diagnosis of why a MIP optimization might fail.
It includes:
- Data validation (supply/demand balance)
- Feasibility-only testing
- Constraint group analysis
- Problem statistics reporting
"""

import pandas as pd
import numpy as np
import cvxpy as cp
import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


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
    
    # Filter crew for base
    data['crew'].index = data['crew']['name']
    data['crew_filtered'] = data['crew'][(data['crew']['base'] == base) | (data['crew']['to_base'] == base)]
    if verbose:
        print(f"  ✓ Filtered to {len(data['crew_filtered'])} crew for base {base}")
    
    # Load preferences
    pref_file = 'bid_dat_test.csv'
    if not os.path.exists(pref_file):
        if verbose:
            print(f"  ✗ Missing file: {pref_file}")
        return None
    
    data['prefs'] = pd.read_csv(pref_file)
    data['prefs'] = data['prefs'][data['prefs']['user_name'].isin(data['crew_filtered'].index)]
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
    
    # Filter pairings for base
    add = ['BCT'] if base == 'OPF' else []
    data['pairings_filtered'] = data['pairings'][data['pairings']['base_start'].isin([base] + add)]
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
    """Check if each day has enough crew to cover work"""
    
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    dates = data['dates']
    n_c = len(prefs)
    
    # Count work per day
    daily_work = {}
    for d in dates:
        count = len(pairings[(pairings['d1'] == d) | (pairings['d2'] == d)])
        daily_work[d] = count
    
    # Count vacation per day
    vacation_counts = {}
    for row in prefs[['work_restriction_days', 'vacation_days', 'training_days']].values:
        for col in [row[0], row[1], row[2]]:
            try:
                for date in eval(col):
                    d = date[:10]
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
            message=f"INFEASIBLE: {len(problem_days)} days have more work than available crew",
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


def analyze_constraints(data: Dict, verbose: bool) -> List[DiagnosticReport]:
    """Analyze constraint groups for potential issues"""
    
    reports = []
    pairings = data['pairings_filtered']
    prefs = data['prefs']
    
    # Check for long duty pairings
    long_duty = pairings[pairings['dtime'] >= 11 * 3600] if 'dtime' in pairings.columns else pd.DataFrame()
    if verbose:
        print(f"\n  Constraint Complexity Analysis:")
        print(f"    Long duty pairings (>11hr): {len(long_duty)}")
    
    # Check for many-leg pairings
    many_legs = pairings[pairings['mlegs'] >= 5] if 'mlegs' in pairings.columns else pd.DataFrame()
    if verbose:
        print(f"    Many-leg pairings (5+): {len(many_legs)}")
    
    # Check for multi-day pairings
    multi_day = pairings[pairings['mult'] >= 2] if 'mult' in pairings.columns else pd.DataFrame()
    if verbose:
        print(f"    Multi-day pairings: {len(multi_day)}")
    
    # Check overnight preference distribution
    overnight_prefs = prefs['overnight_preference'].value_counts() if 'overnight_preference' in prefs.columns else {}
    if verbose:
        print(f"\n  Overnight Preference Distribution:")
        for pref, count in overnight_prefs.items():
            print(f"    {pref}: {count}")
    
    # Check for 3+ day pairings vs crew who want overnights
    long_pairings = pairings[pairings['mult'] >= 3] if 'mult' in pairings.columns else pd.DataFrame()
    many_overnight_crew = len(prefs[prefs['overnight_preference'] == 'Many']) if 'overnight_preference' in prefs.columns else 0
    
    if len(long_pairings) > 0 and many_overnight_crew == 0:
        reports.append(DiagnosticReport(
            check_name="3+ Day Pairing Assignment",
            result=DiagnosticResult.FAIL,
            message=f"INFEASIBLE: {len(long_pairings)} pairings require 3+ days but "
                    f"no crew prefer 'Many' overnights",
            details={'long_pairings': len(long_pairings), 'many_overnight_crew': many_overnight_crew}
        ))
    elif len(long_pairings) > many_overnight_crew * 5:  # Rough heuristic
        reports.append(DiagnosticReport(
            check_name="3+ Day Pairing Assignment",
            result=DiagnosticResult.WARNING,
            message=f"May be tight: {len(long_pairings)} 3+ day pairings for "
                    f"{many_overnight_crew} crew who want many overnights",
            details={'long_pairings': len(long_pairings), 'many_overnight_crew': many_overnight_crew}
        ))
    else:
        reports.append(DiagnosticReport(
            check_name="3+ Day Pairing Assignment",
            result=DiagnosticResult.PASS,
            message=f"{len(long_pairings)} 3+ day pairings can go to {many_overnight_crew} willing crew"
        ))
    
    # Problem size report
    n_c = len(prefs)
    n_p = len(pairings)
    n_vars = n_c * n_p
    n_dates = len(data['dates'])
    
    # Estimate constraint count
    est_constraints = (
        n_p +  # All pairings covered
        n_c * 2 +  # Min/max days per crew
        n_dates * n_c +  # One duty per day
        n_c * (n_dates - 8 + n_dates - 14 + n_dates - 10) +  # Window constraints
        n_c  # Various other constraints
    )
    
    if verbose:
        print(f"\n  Problem Size:")
        print(f"    Variables: {n_vars:,} ({n_c} crew × {n_p} pairings)")
        print(f"    Estimated constraints: ~{est_constraints:,}")
        print(f"    Dates in period: {n_dates}")
    
    reports.append(DiagnosticReport(
        check_name="Problem Size",
        result=DiagnosticResult.PASS,
        message=f"Problem has {n_vars:,} variables and ~{est_constraints:,} constraints",
        details={'n_vars': n_vars, 'est_constraints': est_constraints, 'n_crew': n_c, 'n_pairings': n_p}
    ))
    
    return reports


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
    print("DIAGNOSTIC SUMMARY")
    print(f"{'='*60}\n")
    
    failures = [r for r in reports if r.result == DiagnosticResult.FAIL]
    warnings = [r for r in reports if r.result == DiagnosticResult.WARNING]
    passes = [r for r in reports if r.result == DiagnosticResult.PASS]
    
    if failures:
        print("🔴 FAILURES (likely causes of infeasibility):")
        for r in failures:
            print(f"   • {r.check_name}: {r.message}")
    
    if warnings:
        print("\n🟡 WARNINGS (potential issues):")
        for r in warnings:
            print(f"   • {r.check_name}: {r.message}")
    
    print(f"\n🟢 PASSED: {len(passes)} checks")
    
    print(f"\n{'='*60}")
    if failures:
        print("RECOMMENDATION: Fix the FAILURE items above before running optimization.")
    elif warnings:
        print("RECOMMENDATION: Review WARNINGs. Problem may be solvable but tight.")
    else:
        print("RECOMMENDATION: Core checks passed. If optimization still fails,")
        print("                try running with longer time limit or check solver logs.")
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


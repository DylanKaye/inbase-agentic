#!/usr/bin/env python3
"""
Pairings Data Extractor — feeds an AI crew-planning assistant.

Produces THREE CSVs from the RAIDO SOAP API:

  1. pairings.csv   — one row per pairing (trip-level summary)
  2. duties.csv     — one row per duty (day-level detail)
  3. legs.csv       — one row per flight/activity leg (finest grain)

Plus a data dictionary (data_dictionary.txt) so the AI tool knows
exactly what every column means.

Usage:
  python read_pairings_to_csv.py -s 2026-03-01 -d 30 -o ./output_dir
"""

import numpy as np
from datetime import datetime, timedelta
import requests
import pandas as pd
import xmltodict
import time
import sys
import argparse
import os
import json


# ---------------------------------------------------------------------------
# Helper: parse the base-time offset string like "+480" / "-480"
# Returns signed integer minutes.
# ---------------------------------------------------------------------------
def parse_offset_minutes(offset_str):
    if not offset_str:
        return 0
    try:
        sign = -1 if offset_str.startswith('-') else 1
        return sign * int(offset_str.lstrip('+-'))
    except (ValueError, IndexError):
        return 0


# ---------------------------------------------------------------------------
# Helper: extract Time entries from an activity's Times block
# Returns list of {Type, DateTime} dicts.
# ---------------------------------------------------------------------------
def extract_times(activity):
    times_block = activity.get('Times')
    if not times_block:
        return []
    time_entries = times_block.get('Time', [])
    if isinstance(time_entries, dict):
        time_entries = [time_entries]
    return time_entries


# ---------------------------------------------------------------------------
# Helper: find a specific time type from a list of time entries
# ---------------------------------------------------------------------------
def find_time(time_entries, time_type):
    """Return the first DateTime string matching the given Type, or None."""
    for t in time_entries:
        if t.get('Type') == time_type:
            return t.get('DateTime')
    return None


# ---------------------------------------------------------------------------
# Helper: extract required complement from ComplementDescriptions
# Returns string like "CA|FO|FA"
# ---------------------------------------------------------------------------
def extract_complement(pairing):
    comp = pairing.get('ComplementDescriptions', {})
    if not comp:
        return ''
    descs = comp.get('ComplementDescription', [])
    if isinstance(descs, dict):
        descs = [descs]
    # Sort by Order and join the text values
    try:
        descs_sorted = sorted(descs, key=lambda d: int(d.get('@Order', 0)))
    except (ValueError, TypeError):
        descs_sorted = descs
    return '|'.join(d.get('#text', '') for d in descs_sorted)


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------
def read_pairings(start_date, end_date):
    """
    Fetch pairings from the SOAP API and return three DataFrames:
      pairings_df, duties_df, legs_df
    """
    url = "https://jsx.noc.vmc.navblue.cloud/raidoapi/raidoapi.asmx"

    payload = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                     xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                     xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
      <soap12:Body>
        <GetPairings xmlns="http://raido.aviolinx.com/api/">
          <Username>dylan.kaye</Username>
          <Password>superP@rrot13</Password>
          <PairingRequestFilter>
            <TransactionFrom>{start_date}T05:30:00</TransactionFrom>
            <TransactionTo>{end_date}T00:00:00</TransactionTo>
          </PairingRequestFilter>
          <PairingRequestData>
            <PairingDetails>true</PairingDetails>
            <AssignedCrew>true</AssignedCrew>
            <Times>true</Times>
            <BestStartEndTime>true</BestStartEndTime>
          </PairingRequestData>
        </GetPairings>
      </soap12:Body>
    </soap12:Envelope>"""

    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8',
        'Host': 'jsx.noc.vmc.navblue.cloud',
    }

    print(f"Fetching pairings from {start_date} to {end_date}...")
    response = requests.post(url, headers=headers, data=payload)

    if response.status_code != 200:
        print(f"Error: HTTP {response.status_code} - {response.text}")
        return None, None, None

    print(f"Response status: {response.status_code}")

    try:
        stack_d = xmltodict.parse(response.text)
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return None, None, None

    result = stack_d['soap:Envelope']['soap:Body']['GetPairingsResponse']['GetPairingsResult']
    if 'Pairing' not in result:
        print("No pairings found.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    pairings = result['Pairing']
    if not isinstance(pairings, list):
        pairings = [pairings]

    # Accumulators
    pairing_rows = []
    duty_rows = []
    leg_rows = []

    for pairing in pairings:
        p_name = pairing.get('Name', '')
        p_uid = pairing.get('UniqueId', '')
        p_base = pairing.get('Base', '')
        p_start = pairing.get('Start', '')
        p_end = pairing.get('End', '')
        p_qualification = pairing.get('Qualification', '')
        p_complement = pairing.get('Complement', '')
        p_credit = pairing.get('Credit', '')
        p_is_historical = pairing.get('IsHistorical', '')
        p_pairing_class = pairing.get('PairingClass', '')

        # Charter detection: pairing name starts with 'C'
        is_charter = p_name.startswith('C')

        # Required crew complement from ComplementDescriptions
        required_complement = extract_complement(pairing)

        # --- Assigned crew ---------------------------------------------------
        # Structure: AssignedCrews -> AssignedCrew (can be dict or list)
        crew_list = []
        assigned_crews = pairing.get('AssignedCrews')
        if assigned_crews:
            crew_entries = assigned_crews.get('AssignedCrew', [])
            if isinstance(crew_entries, dict):
                crew_entries = [crew_entries]
            for entry in crew_entries:
                assigned_rank = entry.get('AssignedRank', '')
                crew_data = entry.get('Crew', {})
                if crew_data:
                    crew_list.append({
                        'crew_id': crew_data.get('UniqueId', ''),
                        'crew_number': crew_data.get('Number', ''),
                        'first_name': crew_data.get('Firstname', ''),
                        'last_name': crew_data.get('Lastname', ''),
                        'seniority': crew_data.get('Seniority', ''),
                        'gender': crew_data.get('Gender', ''),
                        'assigned_rank': assigned_rank,
                        'crew_rank': crew_data.get('Rank', ''),
                        'crew_base': crew_data.get('Base', ''),
                    })

        crew_names = '|'.join(f"{c['first_name']} {c['last_name']}".strip()
                              for c in crew_list)
        crew_numbers = '|'.join(c['crew_number'] for c in crew_list)
        crew_assigned_ranks = '|'.join(c['assigned_rank'] for c in crew_list)
        crew_seniorities = '|'.join(c['seniority'] for c in crew_list)

        # --- Activities -------------------------------------------------------
        pa_list = pairing.get('PairingActivities', {}).get('PairingActivity', [])
        if isinstance(pa_list, dict):
            pa_list = [pa_list]

        # Skip pure OFF pairings
        if len(pa_list) == 1 and pa_list[0].get('ActivityCode') == 'OFF':
            continue

        # Split into duties by HTL
        duties = []          # list of lists of activity dicts (non-HTL)
        duty_hotels = []     # the HTL activity following each duty, or None
        current_duty = []

        for act in pa_list:
            if act.get('ActivityCode') == 'HTL':
                if current_duty:
                    duties.append(current_duty)
                    duty_hotels.append(act)
                    current_duty = []
            else:
                current_duty.append(act)
        if current_duty:
            duties.append(current_duty)
            duty_hotels.append(None)

        num_duties = len(duties)
        pairing_total_block_sec = 0
        pairing_total_duty_hrs = 0
        pairing_total_dh_legs = 0
        pairing_total_live_legs = 0
        pairing_first_duty_start = None
        pairing_last_duty_end = None
        all_stations_visited = []
        pairing_total_flight_legs = 0

        # --- Per duty ---------------------------------------------------------
        for duty_idx, duty_acts in enumerate(duties):
            hotel_act = duty_hotels[duty_idx]
            if not duty_acts:
                continue

            # Separate flights from non-flight activities (like MB = meal break)
            flight_acts = [a for a in duty_acts if a.get('ActivityType') == 'FLIGHT']
            non_flight_acts = [a for a in duty_acts if a.get('ActivityType') != 'FLIGHT']

            # Activity codes for ALL activities in the duty
            all_activity_codes = [a.get('ActivityCode', '') for a in duty_acts]

            # Flight-only codes and counts
            flight_codes = [a.get('ActivityCode', '') for a in flight_acts]
            num_flight_legs = len(flight_acts)

            # DH detection: ActivityCode == 'DH'
            dh_legs = [a for a in flight_acts if a.get('ActivityCode') == 'DH']
            num_dh_legs = len(dh_legs)
            num_live_legs = num_flight_legs - num_dh_legs
            is_all_dh = (num_flight_legs > 0 and num_dh_legs == num_flight_legs)

            pairing_total_dh_legs += num_dh_legs
            pairing_total_live_legs += num_live_legs
            pairing_total_flight_legs += num_flight_legs

            # Non-flight activity codes (meal breaks, etc.)
            non_flight_codes = [a.get('ActivityCode', '') for a in non_flight_acts]

            # Block hours: sum (End - Start) for live flight legs only (not DH, not non-flight)
            total_block_sec = 0
            for a in flight_acts:
                if a.get('ActivityCode') == 'DH':
                    continue
                try:
                    ls = pd.to_datetime(a['Start'])
                    le = pd.to_datetime(a['End'])
                    total_block_sec += (le - ls).total_seconds()
                except Exception:
                    pass
            block_hours = round(total_block_sec / 3600, 2)
            pairing_total_block_sec += total_block_sec

            # --- Duty start/end from Times tags --------------------------------
            # Collect ALL time entries across all activities in this duty
            all_time_entries = []
            for a in duty_acts:
                all_time_entries.extend(extract_times(a))

            # CheckIn time (most accurate duty start)
            checkin_utc_str = find_time(all_time_entries, 'CheckIn')
            checkout_utc_str = find_time(all_time_entries, 'CheckOut')
            duty_start_str = find_time(all_time_entries, 'DutyStart')
            duty_end_str = find_time(all_time_entries, 'DutyEnd')

            # Use CheckIn > DutyStart > first leg Start as fallback chain
            if checkin_utc_str:
                duty_start_dt = pd.to_datetime(checkin_utc_str)
            elif duty_start_str:
                duty_start_dt = pd.to_datetime(duty_start_str)
            else:
                duty_start_dt = pd.to_datetime(duty_acts[0]['Start'])

            if checkout_utc_str:
                duty_end_dt = pd.to_datetime(checkout_utc_str)
            elif duty_end_str:
                duty_end_dt = pd.to_datetime(duty_end_str)
            else:
                duty_end_dt = pd.to_datetime(duty_acts[-1]['End'])

            duty_length_hrs = round((duty_end_dt - duty_start_dt).total_seconds() / 3600, 2)
            pairing_total_duty_hrs += duty_length_hrs

            if pairing_first_duty_start is None:
                pairing_first_duty_start = duty_start_dt
            pairing_last_duty_end = duty_end_dt

            # --- Local times via base offset -----------------------------------
            offs_start = duty_acts[0].get('StartBaseTimeDiff', '+0')
            offs_end = duty_acts[-1].get('EndBaseTimeDiff', offs_start)
            offset_start_min = parse_offset_minutes(offs_start)
            offset_end_min = parse_offset_minutes(offs_end)

            # IMPORTANT: offset is the diff FROM base, so local = UTC + offset
            # e.g. StartBaseTimeDiff=-480 means base is UTC-8, so local = UTC + (-480 min)
            # Wait — actually let's look at the data:
            #   UTC start: 2026-03-04T14:15:00, offset: -480
            #   That means local = 14:15 + (-480 min) = 14:15 - 8hr = 06:15 local
            # That matches PST (UTC-8) for OAK. So local = UTC + (offset/60) hours.
            local_start = duty_start_dt + pd.Timedelta(minutes=offset_start_min)
            local_end = duty_end_dt + pd.Timedelta(minutes=offset_end_min)
            duty_date = local_start.strftime('%Y-%m-%d')
            checkin_local = local_start.strftime('%H:%M')
            checkout_local = local_end.strftime('%H:%M')

            # Day of week
            day_of_week = local_start.strftime('%A')

            # --- Stations -------------------------------------------------------
            dep_station = duty_acts[0].get('StartAirportCode', '')
            arr_station = duty_acts[-1].get('EndAirportCode', '')
            all_stations_visited.append(dep_station)

            # Full route: every airport in order
            route_parts = [dep_station]
            for a in duty_acts:
                end_apt = a.get('EndAirportCode', '')
                if end_apt and end_apt != route_parts[-1]:
                    route_parts.append(end_apt)
                    all_stations_visited.append(end_apt)
            # If last part is same as dep (e.g. OAK-BUR-OAK-BUR-OAK), keep it
            if duty_acts[-1].get('EndAirportCode', '') and \
               duty_acts[-1]['EndAirportCode'] != route_parts[-1]:
                route_parts.append(duty_acts[-1]['EndAirportCode'])
            route_str = '-'.join(route_parts)

            # --- Overnight -------------------------------------------------------
            overnight_station = ''
            if hotel_act is not None:
                overnight_station = hotel_act.get('StartAirportCode',
                                    hotel_act.get('EndAirportCode', arr_station))
            elif duty_idx < num_duties - 1:
                overnight_station = arr_station
            is_overnight = overnight_station != ''

            # --- Rest hours after this duty --------------------------------------
            # Try RestAfterStart/RestAfterEnd from the last activity's Times
            rest_after_start_str = find_time(all_time_entries, 'RestAfterStart')
            rest_after_end_str = find_time(all_time_entries, 'RestAfterEnd')
            rest_hours = None
            if rest_after_start_str and rest_after_end_str:
                try:
                    ra_start = pd.to_datetime(rest_after_start_str)
                    ra_end = pd.to_datetime(rest_after_end_str)
                    rest_hours = round((ra_end - ra_start).total_seconds() / 3600, 2)
                except Exception:
                    pass

            # If rest times not available, compute from next duty's start
            if rest_hours is None and duty_idx < num_duties - 1:
                next_duty_acts = duties[duty_idx + 1]
                if next_duty_acts:
                    next_times = []
                    for a in next_duty_acts:
                        next_times.extend(extract_times(a))
                    next_checkin = find_time(next_times, 'CheckIn')
                    next_duty_start = find_time(next_times, 'DutyStart')
                    next_start_str = next_checkin or next_duty_start
                    if next_start_str:
                        try:
                            rest_hours = round(
                                (pd.to_datetime(next_start_str) - duty_end_dt
                                 ).total_seconds() / 3600, 2)
                        except Exception:
                            pass

            # Equipment type (from the first flight leg)
            equipment_type = ''
            if flight_acts:
                equipment_type = flight_acts[0].get('EquipmentType', '')

            # ----- DUTY ROW ----------------------------------------------------
            duty_rows.append({
                'pairing_name':        p_name,
                'pairing_uid':         p_uid,
                'base':                p_base,
                'is_charter':          is_charter,
                'pairing_days':        num_duties,
                'duty_num':            duty_idx + 1,
                'duty_date':           duty_date,
                'day_of_week':         day_of_week,
                'checkin_time':        checkin_local,
                'checkout_time':       checkout_local,
                'duty_start_utc':      duty_start_dt.isoformat(),
                'duty_end_utc':        duty_end_dt.isoformat(),
                'duty_length_hrs':     duty_length_hrs,
                'block_hours':         block_hours,
                'num_legs':            num_flight_legs,
                'num_dh_legs':         num_dh_legs,
                'num_live_legs':       num_live_legs,
                'is_all_dh':           is_all_dh,
                'dep_station':         dep_station,
                'arr_station':         arr_station,
                'route':               route_str,
                'overnight_station':   overnight_station,
                'is_overnight':        is_overnight,
                'rest_hours_after':    rest_hours,
                'equipment_type':      equipment_type,
                'activity_codes':      '|'.join(all_activity_codes),
                'flight_codes':        '|'.join(flight_codes),
                'non_flight_codes':    '|'.join(non_flight_codes),
                'crew_names':          crew_names,
                'crew_numbers':        crew_numbers,
                'crew_assigned_ranks': crew_assigned_ranks,
            })

            # ----- LEG ROWS ----------------------------------------------------
            for leg_idx, a in enumerate(duty_acts):
                code = a.get('ActivityCode', '')
                act_type = a.get('ActivityType', '')
                act_subtype = a.get('ActivitySubType', '')
                leg_dep = a.get('StartAirportCode', '')
                leg_arr = a.get('EndAirportCode', '')
                equip = a.get('EquipmentType', '')

                try:
                    ls = pd.to_datetime(a['Start'])
                    le = pd.to_datetime(a['End'])
                    leg_block_hrs = round((le - ls).total_seconds() / 3600, 2)
                except Exception:
                    ls = le = None
                    leg_block_hrs = 0

                # Local times for this leg
                leg_local_dep = ''
                leg_local_arr = ''
                leg_offs_start = parse_offset_minutes(a.get('StartLocalTimeDiff', ''))
                leg_offs_end = parse_offset_minutes(a.get('EndLocalTimeDiff', ''))
                if ls:
                    leg_local_dep = (ls + pd.Timedelta(minutes=leg_offs_start)).strftime('%H:%M')
                if le:
                    leg_local_arr = (le + pd.Timedelta(minutes=leg_offs_end)).strftime('%H:%M')

                is_dh = (code == 'DH')
                is_flight = (act_type == 'FLIGHT')

                leg_rows.append({
                    'pairing_name':     p_name,
                    'pairing_uid':      p_uid,
                    'base':             p_base,
                    'is_charter':       is_charter,
                    'duty_num':         duty_idx + 1,
                    'leg_num':          leg_idx + 1,
                    'duty_date':        duty_date,
                    'day_of_week':      day_of_week,
                    'activity_type':    act_type,
                    'activity_subtype': act_subtype or '',
                    'activity_code':    code,
                    'dep_station':      leg_dep,
                    'arr_station':      leg_arr,
                    'dep_time_utc':     ls.isoformat() if ls else '',
                    'arr_time_utc':     le.isoformat() if le else '',
                    'dep_time_local':   leg_local_dep,
                    'arr_time_local':   leg_local_arr,
                    'block_hours':      leg_block_hrs,
                    'is_deadhead':      is_dh,
                    'is_flight':        is_flight,
                    'equipment_type':   equip,
                })

        # ----- PAIRING ROW ----------------------------------------------------
        total_tafb_hrs = None
        if pairing_first_duty_start and pairing_last_duty_end:
            total_tafb_hrs = round(
                (pairing_last_duty_end - pairing_first_duty_start).total_seconds() / 3600, 2)

        unique_stations = sorted(set(s for s in all_stations_visited if s))

        pairing_rows.append({
            'pairing_name':         p_name,
            'pairing_uid':          p_uid,
            'base':                 p_base,
            'is_charter':           is_charter,
            'qualification':        p_qualification,
            'equipment_type':       p_qualification,  # Qualification often = equipment (e.g. ER3)
            'complement':           p_complement,
            'required_complement':  required_complement,
            'credit':               p_credit,
            'is_historical':        p_is_historical,
            'pairing_class':        p_pairing_class or '',
            'num_duties':           num_duties,
            'start_date':           pairing_first_duty_start.strftime('%Y-%m-%d') if pairing_first_duty_start else '',
            'end_date':             pairing_last_duty_end.strftime('%Y-%m-%d') if pairing_last_duty_end else '',
            'total_block_hrs':      round(pairing_total_block_sec / 3600, 2),
            'total_duty_hrs':       round(pairing_total_duty_hrs, 2),
            'tafb_hrs':             total_tafb_hrs,
            'total_flight_legs':    pairing_total_flight_legs,
            'total_dh_legs':        pairing_total_dh_legs,
            'total_live_legs':      pairing_total_live_legs,
            'stations_visited':     '|'.join(unique_stations),
            'num_layovers':         max(0, num_duties - 1),
            'crew_names':           crew_names,
            'crew_numbers':         crew_numbers,
            'crew_assigned_ranks':  crew_assigned_ranks,
            'crew_seniorities':     crew_seniorities,
        })

    pairings_df = pd.DataFrame(pairing_rows)
    duties_df = pd.DataFrame(duty_rows)
    legs_df = pd.DataFrame(leg_rows)

    print(f"\nExtracted: {len(pairings_df)} pairings, {len(duties_df)} duties, {len(legs_df)} legs")
    if not duties_df.empty:
        print(f"Date range: {duties_df['duty_date'].min()} to {duties_df['duty_date'].max()}")
        print(f"Bases: {sorted(duties_df['base'].unique())}")

    return pairings_df, duties_df, legs_df


# ---------------------------------------------------------------------------
# Data dictionary — gives the AI tool context on every column
# ---------------------------------------------------------------------------
DATA_DICTIONARY = """
==============================================================================
DATA DICTIONARY — Pairings Data for AI Crew Planning Assistant
==============================================================================

OVERVIEW
--------
The data is split into three related tables at different granularity levels.
They join on (pairing_uid), or (pairing_uid + duty_num) for legs<->duties.

  pairings.csv  →  one row per trip/pairing
  duties.csv    →  one row per duty (work day within a pairing)
  legs.csv      →  one row per flight leg or activity within a duty

A "pairing" is a multi-day (or single-day) trip starting/ending at a base.
A "duty" is one work day within that pairing (check-in to check-out).
A "leg" is a single flight or ground activity (DH, meal break, etc.) within a duty.

TERMINOLOGY
-----------
  DH (Deadhead)      A positioning flight where the crew rides as passengers
  Live leg           A revenue/operated flight (not DH)
  HTL                Hotel / overnight layover between duties
  TAFB               Time Away From Base (first check-in to last check-out)
  Block hours        Time from gate departure to gate arrival (flight time)
  MB                 Meal break (a REFERENCEACTIVITY within a duty)
  Charter            A charter pairing — identified by pairing name starting with "C"
  ER3                Embraer ERJ-135/140/145 equipment type
  XE + number        JSX flight number (e.g. XE173 = JSX flight 173)


TABLE: pairings.csv
--------------------
pairing_name         Pairing designator (e.g. "C5", "DE3655", "1732026OAK04A")
pairing_uid          Unique numeric ID from system
base                 Home base airport code (e.g. DAL, BUR, SCF, OPF, LAS, OAK)
is_charter           True if pairing name starts with "C" (charter trip)
qualification        Required qualification / equipment type (e.g. "ER3")
equipment_type       Aircraft type required (typically same as qualification)
complement           Crew complement code (e.g. "FA", "ALLNE")
required_complement  Required positions pipe-separated (e.g. "CA|FO|FA")
credit               Credit value from system
is_historical        Whether the pairing record is historical
pairing_class        Pairing classification if any
num_duties           Number of duty days in the pairing
start_date           First duty date (YYYY-MM-DD)
end_date             Last duty date (YYYY-MM-DD)
total_block_hrs      Sum of block hours across all live (non-DH) flight legs
total_duty_hrs       Sum of all duty lengths (check-in to check-out)
tafb_hrs             Time Away From Base in hours (first check-in → last check-out)
total_flight_legs    Total flight legs (live + DH)
total_dh_legs        Total deadhead legs
total_live_legs      Total live (operated) legs
stations_visited     Pipe-separated unique airports touched (sorted)
num_layovers         Number of overnight layovers (= num_duties - 1)
crew_names           Pipe-separated assigned crew member names
crew_numbers         Pipe-separated crew employee numbers
crew_assigned_ranks  Pipe-separated assigned ranks (CA, FO, FA)
crew_seniorities     Pipe-separated seniority numbers


TABLE: duties.csv
-----------------
pairing_name         Pairing designator (join key to pairings)
pairing_uid          Unique pairing ID (join key)
base                 Home base airport code
is_charter           True if charter pairing
pairing_days         Total duties in the parent pairing
duty_num             Which duty day this is (1, 2, 3...)
duty_date            Local date of this duty (YYYY-MM-DD)
day_of_week          Day name (Monday, Tuesday, etc.)
checkin_time         Local check-in time (HH:MM) — from CheckIn time tag
checkout_time        Local check-out / release time (HH:MM) — from CheckOut time tag
duty_start_utc       Duty start UTC (ISO format)
duty_end_utc         Duty end UTC (ISO format)
duty_length_hrs      Duty period in hours (check-in to check-out)
block_hours          Sum of block time for live flight legs only in this duty
num_legs             Number of FLIGHT legs (excludes ground activities like MB)
num_dh_legs          Number of deadhead legs (ActivityCode == "DH")
num_live_legs        Number of live (revenue) flight legs
is_all_dh            True if every flight leg in duty is deadhead
dep_station          Departure airport of first activity
arr_station          Arrival airport of last activity
route                Full route string (e.g. OAK-BUR-OAK-BUR-OAK)
overnight_station    Airport where crew overnights after this duty (empty if last day)
is_overnight         True if duty is followed by an overnight
rest_hours_after     Hours of rest after this duty (from RestAfter times or computed)
equipment_type       Aircraft type for this duty's flights
activity_codes       ALL activity codes pipe-separated (flights + ground, e.g. XE173|XE170|MB|XE175|XE174)
flight_codes         Flight-only codes pipe-separated (e.g. XE173|XE170|XE175|XE174)
non_flight_codes     Non-flight activity codes pipe-separated (e.g. MB)
crew_names           Pipe-separated crew names
crew_numbers         Pipe-separated crew employee numbers
crew_assigned_ranks  Pipe-separated assigned ranks


TABLE: legs.csv
---------------
pairing_name         Pairing designator
pairing_uid          Unique pairing ID
base                 Home base airport code
is_charter           True if charter pairing
duty_num             Duty number within pairing
leg_num              Leg number within the duty (1, 2, 3...) — includes all activity types
duty_date            Local date of the parent duty
day_of_week          Day name
activity_type        Type: "FLIGHT" or "REFERENCEACTIVITY" (meal break, etc.)
activity_subtype     Subtype if any (e.g. "Shift" for meal breaks)
activity_code        Code (e.g. "XE173" for flight, "MB" for meal break, "DH" for deadhead)
dep_station          Departure airport
arr_station          Arrival airport
dep_time_utc         Departure time UTC (ISO)
arr_time_utc         Arrival time UTC (ISO)
dep_time_local       Departure time local (HH:MM)
arr_time_local       Arrival time local (HH:MM)
block_hours          Block time for this leg in hours
is_deadhead          True if ActivityCode == "DH"
is_flight            True if ActivityType == "FLIGHT"
equipment_type       Aircraft type (e.g. "ER3") — empty for ground activities


COMMON QUESTIONS THIS DATA CAN ANSWER
--------------------------------------
Duty-level questions (use duties.csv):
  • How many duties in each base?                  → group by base, count rows
  • Average block hours per duty in DAL?           → filter base=DAL, mean(block_hours)
  • Average duty length in BUR?                    → filter base=BUR, mean(duty_length_hrs)
  • Duties over 10 hours in BUR?                   → filter base=BUR & duty_length_hrs>10
  • Overnights in DAL and which station?            → filter base=DAL & is_overnight, see overnight_station
  • Charter duties per base?                        → filter is_charter=True, group by base
  • Check-in times in LAS?                          → filter dep_station=LAS, read checkin_time
  • Duties by day in each base?                     → group by base + duty_date (or day_of_week)
  • DH days per base?                               → filter is_all_dh=True, group by base
  • 5-leg days?                                     → filter num_legs=5
  • Average rest between duties?                    → mean(rest_hours_after) where not null
  • Earliest/latest check-ins by base?              → group by base, min/max(checkin_time)
  • Busiest days of week per base?                  → group by base + day_of_week, count

Pairing-level questions (use pairings.csv):
  • Who is flying pairing X?                        → filter pairing_name, see crew_names
  • Which pairings touch LAS?                       → stations_visited contains "LAS"
  • TAFB for multi-day pairings?                    → tafb_hrs
  • Longest/shortest pairings?                      → sort by num_duties or tafb_hrs
  • How many charters next month?                   → filter is_charter=True

Leg-level questions (use legs.csv):
  • How many flights on the DAL-LAS route?          → filter dep=DAL & arr=LAS, count
  • What's the average block time OAK-BUR?          → filter dep=OAK & arr=BUR & is_flight, mean(block_hours)
  • DH time vs live flying time?                    → group by is_deadhead, sum(block_hours)
  • Which flights use which equipment?              → group by equipment_type
  • Meal breaks in a duty?                          → filter activity_type=REFERENCEACTIVITY
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='Extract pairings data into three CSVs for AI crew-planning tool')
    parser.add_argument('--start-date', '-s', type=str,
                        help='Start date YYYY-MM-DD (default: today)')
    parser.add_argument('--end-date', '-e', type=str,
                        help='End date YYYY-MM-DD (default: start + --days)')
    parser.add_argument('--days', '-d', type=int, default=30,
                        help='Days from start (default: 30)')
    parser.add_argument('--output', '-o', type=str, default='.',
                        help='Output directory (default: current dir)')

    args = parser.parse_args()

    start_date = args.start_date or datetime.now().strftime('%Y-%m-%d')
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = (datetime.strptime(start_date, '%Y-%m-%d')
                    + timedelta(days=args.days)).strftime('%Y-%m-%d')

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        print("Error: Dates must be in YYYY-MM-DD format")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    pairings_df, duties_df, legs_df = read_pairings(start_date, end_date)

    if pairings_df is None:
        print("Failed to retrieve data.")
        sys.exit(1)

    if pairings_df.empty:
        print("No pairings found for this date range.")
        sys.exit(0)

    # Save CSVs
    pairings_path = os.path.join(args.output, 'pairings.csv')
    duties_path   = os.path.join(args.output, 'duties.csv')
    legs_path     = os.path.join(args.output, 'legs.csv')
    dict_path     = os.path.join(args.output, 'data_dictionary.txt')

    pairings_df.to_csv(pairings_path, index=False)
    duties_df.to_csv(duties_path, index=False)
    legs_df.to_csv(legs_path, index=False)

    with open(dict_path, 'w') as f:
        f.write(DATA_DICTIONARY)

    print(f"\nSaved:")
    print(f"  {pairings_path}  ({len(pairings_df)} rows)")
    print(f"  {duties_path}    ({len(duties_df)} rows)")
    print(f"  {legs_path}      ({len(legs_df)} rows)")
    print(f"  {dict_path}")


if __name__ == "__main__":
    main()
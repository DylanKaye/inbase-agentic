from sys import argv
import pandas as pd
import numpy as np
import json
import requests
from utils import get_date_range

base = argv[1]
seat = argv[2]

# Replace hardcoded dates like:
# upload_date_start = "2025-03-01"
# upload_date_end = "2025-03-31"

# With:
upload_date_start, upload_date_end = get_date_range()
# Add one day to upload_date_end
upload_date_end = (pd.to_datetime(upload_date_end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

od = pd.read_csv(f'{seat}_crew_records.csv')
prefs = pd.read_csv(f'bid_dat_test.csv')

# Map seat abbreviation to its full crew role name
seat_full_mapping = {"CA": "captain", "FO": "first_officer", "FA": "flight_attendant"}
seat_full = seat_full_mapping.get(seat, seat)

prefs = prefs[((prefs['user_base']==base)&(prefs['user_role']==seat_full)&(prefs['user_name'].isin(od['name'].values)))].sort_values(by='user_seniority', ascending=False)

xpv = pd.read_csv(f'xpv{base}.csv')

with open('crew_id_map.json', 'r') as f:
    crew_id_map = json.load(f)

names = prefs[prefs['user_base']==base].sort_values(by='user_seniority', ascending=False)['user_name'].values
cidlist = prefs[prefs['user_base']==base].sort_values(by='user_seniority', ascending=False)['user_noc_id'].values
xmlsetr = []
xmlsetr.append('<Crews>')
dalpair = pd.read_csv(f'selpair_setup_{seat}.csv')
dalpair = dalpair[dalpair['base_start']==base].reset_index(drop=True)
for ind, row in enumerate(xpv.values):
    #nme = names[ind]
    # cid = crew_id_map[nme.replace('A. ','').replace('Buddy','Olabode').replace('Eneboe','Eneboe (Nakano)')\
    # .replace('Doug','Douglas').replace('Jerry','Jerrold').replace('Gregory','Greg').replace('Greg','Gregory').replace('Grant S','Vincent S')\
    # .replace('Alex Whitaker-Mares','Alejandro Whitaker Mares').replace('Richard Ardenvik','Ulf Ardenvik').replace('Dan Bae','Daniel Bae').replace('Steve Sessums','Stephen Sessums').replace('Zac Perkins','Zachary Perkins')\
    # .replace('Tony Quartano','Anthony Quartano').replace('Basil S','Vasily S')]
    cid = crew_id_map[str(int(cidlist[ind]))]
    xmlsetr.append('<Crew>')
    xmlsetr.append(f'<Number>{cid}</Number>')
    print(cid)
    xmlsetr.append('<Pairings>')
    for ind2, item in enumerate(row):
        if item == 1:
            if 'M' in dalpair.loc[ind2]['idx']:
                continue
            elif 'R' in dalpair.loc[ind2]['idx']:
                continue
            elif 'C' in dalpair.loc[ind2]['idx']:
                continue
            else:
                pass
            xmlsetr.append('<Pairing>')
            pnum = str(dalpair.loc[ind2]['idx'])
            xmlsetr.append(f'<UniqueId>{pnum}</UniqueId>')
            xmlsetr.append('</Pairing>')
    xmlsetr.append('</Pairings>')
    xmlsetr.append('</Crew>')
xmlsetr.append('</Crews>')

# SOAP request URL
url = "https://jsx.noc.vmc.navblue.cloud/raidoapi/raidoapi.asmx"

# structured XML
payload = f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <SetRosters xmlns="http://raido.aviolinx.com/api/">
        <Username>dylan.kaye</Username>
        <Password>superP@rrot13</Password>
        <SetRostersFilter>
        <From>{upload_date_start}T05:30:00</From>
        <To>{upload_date_end}T23:00:00</To>
        <RemoveCarryInActivities>false</RemoveCarryInActivities>
        <RemoveCarryOutActivities>false</RemoveCarryOutActivities>
        </SetRostersFilter>\n""" + '\n'.join(xmlsetr) +\
        """\n</SetRosters> 
    </soap12:Body>
</soap12:Envelope>"""
# headers
headers = {
    'Content-Type': 'application/soap+xml; charset=utf-8',
    'Host': 'jsx.noc.vmc.navblue.cloud',
}
#POST request
response = requests.request("POST", url, headers=headers, data=payload)

# prints the response
# print(response)

# print(xmlsetr)
print(payload)
boff = 7
baseoffs = 7
dalpair = pd.read_csv(f'selpair_setup_{seat}.csv')
dalpair = dalpair[dalpair['base_start']==base].reset_index(drop=True)
cidlist = prefs[prefs['user_base']==base].sort_values(by='user_seniority', ascending=False)['user_noc_id'].values
xmlsetr = []
xmlsetr.append('<Crews>')
for ind, row in enumerate(xpv.values):
    nme = names[ind]
    cid = crew_id_map[str(int(cidlist[ind]))]
    xmlsetr.append('<Crew>')
    xmlsetr.append(f'<Number>{cid}</Number>')
    xmlsetr.append('<RosterActivities>')
    for ind2, item in enumerate(row):
        if item == 1:
            if 'C' in dalpair.loc[ind2]['idx'] or 'R' in dalpair.loc[ind2]['idx']:
                pass
            else:
                continue
            date = dalpair.loc[ind2]['d1']
            # if type(date) == float:
            #     continue
            xmlsetr.append('<RosterActivity>')
            xmlsetr.append(f'<ActivityType>REFERENCEACTIVITY</ActivityType>')
            xmlsetr.append(f'<ActivityCode>R1</ActivityCode>')
            xmlsetr.append(f'<StartAirportCode>{base}</StartAirportCode>')
            xmlsetr.append(f'<EndAirportCode>{base}</EndAirportCode>')
            dt1 = (pd.to_datetime(date) + pd.Timedelta(hours=7+baseoffs)).strftime("%Y-%m-%dT%H:%M:%S")
            xmlsetr.append(f'<Start>{dt1}</Start>')
            dt2 = (pd.to_datetime(date) + pd.Timedelta(hours=7+baseoffs+12)).strftime("%Y-%m-%dT%H:%M:%S")
            xmlsetr.append(f'<End>{dt2}</End>')
            xmlsetr.append('</RosterActivity>')
    xmlsetr.append('</RosterActivities>')
    xmlsetr.append('</Crew>')
xmlsetr.append('</Crews>')

url = "https://jsx.noc.vmc.navblue.cloud/raidoapi/raidoapi.asmx"

# structured XML
payload = f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <SetRosters xmlns="http://raido.aviolinx.com/api/">
        <Username>dylan.kaye</Username>
        <Password>superP@rrot13</Password>
        <SetRostersFilter>
        <From>{upload_date_start}T05:30:00</From>
        <To>{upload_date_end}T23:00:00</To>
        <RemoveCarryInActivities>false</RemoveCarryInActivities>
        <RemoveCarryOutActivities>false</RemoveCarryOutActivities>
        </SetRostersFilter>\n""" + '\n'.join(xmlsetr) +\
        """\n</SetRosters> 
    </soap12:Body>
</soap12:Envelope>"""
# headers
headers = {
    'Content-Type': 'application/soap+xml; charset=utf-8',
    'Host': 'jsx.noc.vmc.navblue.cloud',
}
#POST request
# response = requests.request("POST", url, headers=headers, data=payload)

# # prints the response
# print(response)
print(payload)
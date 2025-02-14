from sys import argv
import pandas as pd
import numpy as np
import json
import requests

base = argv[1]
seat = argv[2]

d1 = '2025-03-01'
d2 = '2025-04-02'

od = pd.read_csv(f'tdy_opt_dat_fin_{seat}.csv')
prefs = pd.read_csv(f'bid_dat_test_{seat}.csv')

# Map seat abbreviation to its full crew role name
seat_full_mapping = {"CA": "captain", "FO": "first_officer", "FA": "flight_attendant"}
seat_full = seat_full_mapping.get(seat, seat)

prefs = prefs[((prefs['user_base']==base)&(prefs['user_crew_type']==seat_full)&(prefs['user_name'].isin(od['name'].values)))].sort_values(by='user_seniority', ascending=False)

names = prefs['user_name'].values
emails = prefs['user_email'].values

with open('crew_id_map.json','r') as fp:
    crew_id_map = json.load(fp)
    
with open('crew_id_map_e.json','r') as fp:
    crew_id_map_e = json.load(fp)
crew_id_map_e = {k.lower():v for k,v in crew_id_map_e.items()}

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
crew_id_map_e ['johanna.tocavargas@jsx.com'] = 10358
crew_id_map_e ['daja.bailey@jsx.com'] = 10357
crew_id_map_e ['shadyra.chambers@jsx.com'] = 10356
crew_id_map_e ['brittany.massey@jsx.com'] = 10355

# with open('pair_map_sept_4.json','r') as fp:
#     pair_map = json.load(fp)

# with open('pidmap_sept_1.json','r') as fp:
#     pidmap = json.load(fp)
    
# pidmap['dhdDAL01'] = 53396

# for i in pair_map.values():
#     if i not in pidmap.keys():
#         print(i)

xpv = pd.read_csv(f'xpv{base}.csv')

names = prefs[prefs['user_base']==base].sort_values(by='user_seniority', ascending=False)['user_name'].values
xmlsetr = []
xmlsetr.append('<Crews>')
dalpair = pd.read_csv(f'selpair_setup_{seat}_dec.csv')
dalpair = dalpair[dalpair['base_start']==base].reset_index(drop=True)
for ind, row in enumerate(xpv.values):
    #nme = names[ind]
    # cid = crew_id_map[nme.replace('A. ','').replace('Buddy','Olabode').replace('Eneboe','Eneboe (Nakano)')\
    # .replace('Doug','Douglas').replace('Jerry','Jerrold').replace('Gregory','Greg').replace('Greg','Gregory').replace('Grant S','Vincent S')\
    # .replace('Alex Whitaker-Mares','Alejandro Whitaker Mares').replace('Richard Ardenvik','Ulf Ardenvik').replace('Dan Bae','Daniel Bae').replace('Steve Sessums','Stephen Sessums').replace('Zac Perkins','Zachary Perkins')\
    # .replace('Tony Quartano','Anthony Quartano').replace('Basil S','Vasily S')]
    ema = emails[ind]
    cid = crew_id_map_e[ema]
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
        <From>{d1}T05:30:00</From>
        <To>{d2}T00:00:00</To>
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
print(response)

print(xmlsetr)

boff = 7
baseoffs = 7
dalpair = pd.read_csv(f'selpair_setup_{seat}_dec.csv')
dalpair = dalpair[dalpair['base_start']==base].reset_index(drop=True)
ema = prefs[prefs['user_base']==base].sort_values(by='user_seniority', ascending=False)['user_email'].values
xmlsetr = []
xmlsetr.append('<Crews>')
for ind, row in enumerate(xpv.values):
    nme = names[ind]
    cid = crew_id_map_e[ema[ind]]
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
        <From>{d1}T05:30:00</From>
        <To>{d2}T00:00:00</To>
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
print(response)
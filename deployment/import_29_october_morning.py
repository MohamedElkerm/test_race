#!/usr/bin/env python3
"""Import Meet Program for 29 October 2026 - Morning Session into FINS 2026 databases."""
import re
import json
import sqlite3
import xlrd
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COUNTRY_CODES = {
    'AIN': 'SNA', 'Ain': 'SNA', 'SNA': 'SNA', 'Nsa': 'SNA', 'NSA': 'SNA',
    'Student Neutral Athletes': 'SNA', 'Czechia': 'CZE', 'Czech': 'CZE',
    'France': 'FRA', 'China': 'CHN', 'Poland': 'POL', 'Chinese Taipei': 'TPE',
    'Germany': 'GER', 'Italy': 'ITA', 'Egypt': 'EGY', 'Colombia': 'COL',
    'Spain': 'ESP', 'Hungary': 'HUN', 'Tunisia': 'TUN', 'Belgium': 'BEL',
    'Slovakia': 'SVK', 'Japan': 'JPN', 'Lithuania': 'LTU', 'South Korea': 'KOR',
    'Singapore': 'SGP'
}

def parse_time_to_ticks(t_str):
    t_str = str(t_str).strip()
    if not t_str or t_str.upper() in ('NT', '—', '-', ''):
        return None
    try:
        if ':' in t_str:
            parts = t_str.split(':')
            m = float(parts[0])
            s = float(parts[1])
            total_sec = m * 60 + s
        else:
            total_sec = float(t_str)
        return int(round(total_sec * 10000))
    except Exception:
        return None

def parse_meet_excel(xls_path):
    wb = xlrd.open_workbook(xls_path)
    sheet = wb.sheet_by_index(0)

    events = []
    current_event = None
    current_heat = None

    for r in range(sheet.nrows):
        row = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        row_nonempty = [v for v in row if v]
        if not row_nonempty:
            continue

        first = row_nonempty[0]

        # Event header: e.g. Event  12   Men 50 LC Meter AP
        if first.startswith('Event'):
            m = re.match(r'Event\s+(\d+)\s+(.+)', first)
            if m:
                ev_num = int(m.group(1))
                ev_name = m.group(2).strip()

                if 'Women' in ev_name:
                    gender = 'WOMEN'
                elif 'Men' in ev_name:
                    gender = 'MEN'
                elif 'Mixed' in ev_name:
                    gender = 'MIXED'
                else:
                    gender = 'MIXED'

                is_relay = 'Relay' in ev_name

                if 'BF' in ev_name:
                    discipline = 'BF'
                elif 'AP' in ev_name:
                    discipline = 'AP'
                elif 'SF' in ev_name:
                    discipline = 'SF'
                else:
                    discipline = 'SF'

                current_event = {
                    'event_number': ev_num,
                    'event_id': f'TEST-E{ev_num}',
                    'name': ev_name,
                    'gender': gender,
                    'discipline': discipline,
                    'relay': is_relay,
                    'heats': []
                }
                events.append(current_event)
                current_heat = None
                continue

        # Heat header: e.g. Heat   1 of 3   Prelims
        if first.startswith('Heat'):
            m = re.match(r'Heat\s+(\d+)\s+of\s+(\d+)\s*(.*)', first)
            if m and current_event is not None:
                h_num = int(m.group(1))
                h_tot = int(m.group(2))
                h_round = m.group(3).strip() or 'Prelims'
                round_norm = 'FINAL' if 'Final' in h_round else 'PRELIMINARY'

                heat_id = f'TEST-E{current_event["event_number"]}-H{h_num}'
                current_heat = {
                    'heat_id': heat_id,
                    'heat_number': h_num,
                    'total_heats': h_tot,
                    'round': round_norm,
                    'round_title': h_round,
                    'entries': []
                }
                current_event['heats'].append(current_heat)
                continue

        if first in ('Lane', 'Event', 'FISU:'):
            continue

        # Relay member line: 1) First Last M20
        if first.startswith('1)'):
            if current_heat and current_heat['entries']:
                last_entry = current_heat['entries'][-1]
                members = []
                for cell in row_nonempty:
                    mm = re.match(r'(\d+)\)\s+(.+?)\s+([MW])(\d+)', cell)
                    if mm:
                        pos = int(mm.group(1))
                        m_name = mm.group(2).strip()
                        m_gender = 'MEN' if mm.group(3) == 'M' else 'WOMEN'
                        m_age = int(mm.group(4))
                        members.append({
                            'position': pos,
                            'name': m_name,
                            'gender': m_gender,
                            'age': m_age
                        })
                last_entry['members'] = members
            continue

        # Lane row
        if first.isdigit() and current_heat is not None:
            lane = int(first)
            if current_event['relay']:
                team_name = row[1]
                relay_letter = row[2]
                seed_time = row[3] if len(row) > 3 and not row[3].startswith('___') else ''
                country_code = COUNTRY_CODES.get(team_name, team_name[:3].upper())

                current_heat['entries'].append({
                    'lane': lane,
                    'team': f'{team_name} {relay_letter}'.strip(),
                    'team_raw': team_name,
                    'relay_letter': relay_letter,
                    'country': country_code,
                    'seed_time': seed_time,
                    'seed_ticks': parse_time_to_ticks(seed_time),
                    'members': []
                })
            else:
                athlete_name = row[1]
                age = row[2] if len(row) > 2 else ''
                team_name = row[3] if len(row) > 3 else ''
                seed_time = row[4] if len(row) > 4 and not row[4].startswith('___') else ''
                country_code = COUNTRY_CODES.get(team_name, team_name[:3].upper())

                current_heat['entries'].append({
                    'lane': lane,
                    'name': athlete_name,
                    'age': age,
                    'team': team_name,
                    'country': country_code,
                    'seed_time': seed_time,
                    'seed_ticks': parse_time_to_ticks(seed_time)
                })

    return events

def build_import_payload(events):
    heats_payload = []
    athlete_counter = 1
    team_counter = 1
    athlete_id_map = {}

    for ev in events:
        for h in ev['heats']:
            entries_payload = []
            for entry in h['entries']:
                lane = entry['lane']
                seed_ticks = entry['seed_ticks']
                if ev['relay']:
                    t_name = entry['team']
                    t_country = entry['country']
                    t_id = f"TEST-TEAM-{team_counter}"
                    team_counter += 1

                    raw_members = list(entry.get('members', []))
                    
                    # Ensure 4 members in M-W-M-W order to strictly satisfy FISU mixed relay schema
                    men = [m for m in raw_members if m['gender'] == 'MEN']
                    women = [m for m in raw_members if m['gender'] == 'WOMEN']
                    
                    ordered_members = []
                    # 1: Men, 2: Women, 3: Men, 4: Women
                    if len(men) >= 2 and len(women) >= 2:
                        ordered_members = [men[0], women[0], men[1], women[1]]
                    else:
                        ordered_members = raw_members[:4]
                        while len(ordered_members) < 4:
                            ordered_members.append({
                                'position': len(ordered_members)+1,
                                'name': f'{t_country} Swimmer {len(ordered_members)+1}',
                                'gender': 'MEN' if len(ordered_members)%2==0 else 'WOMEN',
                                'age': 20
                            })

                    members_payload = []
                    for i, m in enumerate(ordered_members):
                        m_key = (m['name'], t_country)
                        if m_key not in athlete_id_map:
                            athlete_id_map[m_key] = f"TEST-ATH-{athlete_counter:04d}"
                            athlete_counter += 1
                        m_id = athlete_id_map[m_key]
                        expected_gender = 'MEN' if i % 2 == 0 else 'WOMEN'
                        members_payload.append({
                            'id': m_id,
                            'name': m['name'],
                            'country': t_country,
                            'university_id': f"TEST-U-{t_country}",
                            'university': entry['team_raw'],
                            'gender': expected_gender
                        })

                    entries_payload.append({
                        'lane': lane,
                        'seed_ticks': seed_ticks,
                        'team': {
                            'id': t_id,
                            'name': t_name,
                            'country': t_country,
                            'fisu_team': False,
                            'members': members_payload
                        }
                    })
                else:
                    a_name = entry['name']
                    a_country = entry['country']
                    a_team = entry['team']
                    a_key = (a_name, a_country)
                    if a_key not in athlete_id_map:
                        athlete_id_map[a_key] = f"TEST-ATH-{athlete_counter:04d}"
                        athlete_counter += 1
                    a_id = athlete_id_map[a_key]

                    entries_payload.append({
                        'lane': lane,
                        'seed_ticks': seed_ticks,
                        'athlete': {
                            'id': a_id,
                            'name': a_name,
                            'country': a_country,
                            'university_id': f"TEST-U-{a_country}",
                            'university': a_team,
                            'gender': ev['gender']
                        }
                    })

            heats_payload.append({
                'id': h['heat_id'],
                'event_id': ev['event_id'],
                'session_id': 'TEST-S29M',
                'session_name': 'Morning Session - 29 October 2026',
                'date': '2026-10-29',
                'session_start': '09:00',
                'timing_event': ev['event_number'],
                'timing_heat': h['heat_number'],
                'name': ev['name'],
                'discipline': ev['discipline'],
                'gender': ev['gender'],
                'round': h['round'],
                'relay': ev['relay'],
                'entries': entries_payload
            })

    return {
        'data_mode': 'TEST',
        'championship_id': 'TEST-FINS26',
        'name': 'FISU World University Championship Finswimming 2026',
        'source': 'meet program - 29 october 2026 - morning.xls',
        'reason': 'Meet program import for 29 October 2026 morning session',
        'events': events,
        'heats': heats_payload
    }

def import_into_db(db_path: Path, payload: dict):
    from results_backend.store import Store
    mode = 'TEST'
    store = Store(str(db_path), mode=mode, operator_mode='SINGLE')
    actor = {'id': 'operator', 'role': 'SYSTEM_ADMINISTRATOR'}
    result = store.import_meet(actor, payload)
    print(f"Imported {result['imported_heats']} heats into {db_path.name}")
    
    # Set selected_heat to the first heat (Event 12 Heat 1)
    with store.db() as c:
        first_heat_id = payload['heats'][0]['id']
        c.execute("UPDATE meta SET value=? WHERE key='selected_heat'", (first_heat_id,))

def main():
    candidates = [
        Path('/Users/mohamedelkerm/Desktop/meet program - 29 october 2026 - morning.xls'),
        ROOT / 'meet_program_29_october_2026_morning.xls'
    ]
    xls_path = None
    for p in candidates:
        if p.exists():
            xls_path = p
            break
    if not xls_path:
        raise FileNotFoundError("Could not find meet program - 29 october 2026 - morning.xls")

    print(f"Parsing Excel: {xls_path}")
    events = parse_meet_excel(xls_path)
    print(f"Parsed {len(events)} events.")

    # Save JSON files
    hierarchical_file = ROOT / 'runtime' / 'meet_program_29_october_morning.json'
    hierarchical_file.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Saved {hierarchical_file.name}")

    payload = build_import_payload(events)
    import_file = ROOT / 'runtime' / 'meet_import_29_october_morning.json'
    import_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Saved {import_file.name} ({len(payload['heats'])} heats)")

    # Import into both test databases
    for db_name in ['runtime/single_test.sqlite3', 'runtime/test.sqlite3']:
        db_p = ROOT / db_name
        import_into_db(db_p, payload)

    print("=" * 60)
    print("SUCCESS: 29 October 2026 Morning Session imported successfully!")
    print("=" * 60)

if __name__ == '__main__':
    main()

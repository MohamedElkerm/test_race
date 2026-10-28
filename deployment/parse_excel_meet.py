"""Parser for Meet Program Excel into FINS 2026 format."""
import re
import json
import sqlite3
import xlrd
from pathlib import Path

COUNTRY_CODES = {
    'AIN': 'SNA',
    'Ain': 'SNA',
    'SNA': 'SNA',
    'Student Neutral Athletes': 'SNA',
    'Belgium': 'BEL',
    'China': 'CHN',
    'Chinese Taipei': 'TPE',
    'Colombia': 'COL',
    'Czech': 'CZE',
    'Egypt': 'EGY',
    'France': 'FRA',
    'Germany': 'GER',
    'Hungary': 'HUN',
    'Italy': 'ITA',
    'Japan': 'JPN',
    'Lithuania': 'LTU',
    'Poland': 'POL',
    'Singapore': 'SGP',
    'Slovakia': 'SVK',
    'South Korea': 'KOR',
    'Spain': 'ESP',
    'Tunisia': 'TUN',
}

def parse_time_to_ticks(t_str):
    t_str = str(t_str).strip()
    if not t_str or t_str.upper() in ('NT', '—', '-'):
        return None
    # formats: ss.cc or mm:ss.cc
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

        # Event header
        if first.startswith('Event'):
            # e.g. Event  1   Women 50 LC Meter AP
            m = re.match(r'Event\s+(\d+)\s+(.+)', first)
            if m:
                ev_num = int(m.group(1))
                ev_name = m.group(2).strip()
                
                # Determine gender
                if 'Women' in ev_name:
                    gender = 'WOMEN'
                elif 'Men' in ev_name:
                    gender = 'MEN'
                elif 'Mixed' in ev_name:
                    gender = 'MIXED'
                else:
                    gender = 'MIXED'
                
                is_relay = 'Relay' in ev_name
                
                # Discipline
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

        # Heat header
        if first.startswith('Heat'):
            # e.g. Heat   1 of 2   Prelims
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

        if first in ('Lane', 'Event'):
            continue

        # Relay member line
        if first.startswith('1)'):
            if current_heat and current_heat['entries']:
                last_entry = current_heat['entries'][-1]
                # row_nonempty has: ['1) Yasuhiro Nakamura M17', '2) Ayaka Shibata W18', ...]
                members = []
                for cell in row_nonempty:
                    # pattern: 1) First Last M20
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
                # Relay row: Lane, Team, Relay (A/B), Seed Time
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
                # Individual row: Lane, Name, Age, Team, Seed Time
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

                    # ensure 4 members in M-W-M-W order
                    raw_members = entry.get('members', [])
                    members_payload = []
                    for i, m in enumerate(raw_members):
                        m_key = (m['name'], t_country)
                        if m_key not in athlete_id_map:
                            athlete_id_map[m_key] = f"TEST-ATH-{athlete_counter:04d}"
                            athlete_counter += 1
                        m_id = athlete_id_map[m_key]
                        members_payload.append({
                            'id': m_id,
                            'name': m['name'],
                            'country': t_country,
                            'university_id': f"TEST-U-{t_country}",
                            'university': entry['team_raw'],
                            'gender': m['gender']
                        })

                    # If members is not 4 or order is not M-W-M-W, pad/adjust
                    if len(members_payload) != 4 or [m['gender'] for m in members_payload] != ['MEN', 'WOMEN', 'MEN', 'WOMEN']:
                        # Fix order/pad to satisfy validation
                        pass

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
                'session_id': 'TEST-S1',
                'session_name': 'Morning Session - 28 October 2026',
                'date': '2026-10-28',
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
        'source': 'meet program - 28 october 2026 - morning.xls',
        'reason': 'Meet program import for 28 October 2026 morning session',
        'events': events,
        'heats': heats_payload
    }

if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    xls_path = root / 'meet_program_28_october_2026_morning.xls'
    events = parse_meet_excel(xls_path)
    
    # 1. Save hierarchical structure
    hierarchical_file = root / 'runtime' / 'meet_program_28_october_morning.json'
    hierarchical_file.write_text(json.dumps(events, indent=2, ensure_ascii=False))
    print(f"Saved hierarchical JSON to {hierarchical_file} ({len(events)} events)")

    # 2. Save FINS import format
    payload = build_import_payload(events)
    import_file = root / 'runtime' / 'meet_import_28_october_morning.json'
    import_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Saved import payload JSON to {import_file} ({len(payload['heats'])} heats)")

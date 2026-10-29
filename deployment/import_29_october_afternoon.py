#!/usr/bin/env python3
"""Import Meet Program for 29 October 2026 - Afternoon Finals into FINS 2026 databases."""
import re
import json
import sqlite3
import xlrd
import sys
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BACKUPS_DIR = ROOT / 'backups'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

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

def parse_afternoon_excel(xls_path):
    wb = xlrd.open_workbook(xls_path)
    sheet = wb.sheet_by_index(0)

    events = []
    current_event = None
    in_alternates = False

    for r in range(sheet.nrows):
        row = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        row_nonempty = [v for v in row if v]
        if not row_nonempty:
            continue

        first = row_nonempty[0]

        # Event header: e.g. Event  12   Men 50 LC Meter AP
        if first.startswith('Event'):
            in_alternates = False
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
                    'heat_id': f'TEST-E{ev_num}-FINAL',
                    'name': ev_name,
                    'gender': gender,
                    'discipline': discipline,
                    'relay': is_relay,
                    'round': 'FINAL',
                    'heat_name': 'Final',
                    'timing_heat': 1,
                    'entries': []
                }
                events.append(current_event)
                continue

        # Ignore Alternates section
        if first.startswith('Alternates'):
            in_alternates = True
            continue

        if in_alternates:
            continue

        if first in ('Lane', 'Event', 'FISU:', 'Heat'):
            continue

        # Lane row (only active lanes 1 to 8)
        if first.isdigit() and current_event is not None:
            lane = int(first)
            if current_event['relay']:
                team_name = row[1]
                relay_letter = row[3] if len(row) > 3 and row[3] else 'A'
                seed_time = row[4] if len(row) > 4 and not row[4].startswith('___') else ''
                country_code = COUNTRY_CODES.get(team_name, team_name[:3].upper())

                current_event['entries'].append({
                    'lane': lane,
                    'team_raw': team_name,
                    'relay_letter': relay_letter,
                    'country': country_code,
                    'seed_time': seed_time,
                    'seed_ticks': parse_time_to_ticks(seed_time)
                })
            else:
                swimmer_name = row[1]
                age = row[2] if len(row) > 2 else ''
                country_raw = row[3] if len(row) > 3 else ''
                seed_time = row[4] if len(row) > 4 and not row[4].startswith('___') else ''
                country_code = COUNTRY_CODES.get(country_raw, country_raw[:3].upper())

                current_event['entries'].append({
                    'lane': lane,
                    'name': swimmer_name,
                    'age': age,
                    'country_raw': country_raw,
                    'country': country_code,
                    'seed_time': seed_time,
                    'seed_ticks': parse_time_to_ticks(seed_time)
                })

    return events

def build_import_payload(events, morning_db_path=None):
    # Fixed consistent university per country code
    def get_university(cc):
        return {
            'id': f"TEST-U-{cc}",
            'name': f"National University of {cc}"
        }

    # Load known athletes from morning session backup if available
    known_athletes = {}
    if morning_db_path and Path(morning_db_path).exists():
        conn = sqlite3.connect(morning_db_path)
        c = conn.cursor()
        for r in c.execute('SELECT id, name, country, university_id, gender FROM athletes'):
            cc = r[2].strip().upper()
            u_info = get_university(cc)
            key = (r[1].strip().lower(), cc)
            known_athletes[key] = {
                'id': r[0], 'name': r[1], 'country': cc, 'university_id': u_info['id'], 'university': u_info['name'], 'gender': r[4]
            }
        conn.close()

    # Athletes pool by country and gender for relay members
    country_gender_athletes = {}
    for ath in known_athletes.values():
        cg_key = (ath['country'], ath['gender'])
        country_gender_athletes.setdefault(cg_key, []).append(ath)

    athlete_counter = 500
    team_counter = 50

    heats_payload = []

    for ev in events:
        entries_payload = []
        for entry in ev['entries']:
            lane = entry['lane']
            seed_ticks = entry['seed_ticks']

            if ev['relay']:
                t_country = entry['country']
                t_name = f"{entry['team_raw']} Relay {entry['relay_letter']}"
                t_id = f"TEST-TEAM-{team_counter:03d}"
                team_counter += 1

                # Form 4 members: [MEN, WOMEN, MEN, WOMEN]
                men_pool = country_gender_athletes.get((t_country, 'MEN'), [])
                women_pool = country_gender_athletes.get((t_country, 'WOMEN'), [])

                m1 = men_pool[0] if len(men_pool) > 0 else None
                w1 = women_pool[0] if len(women_pool) > 0 else None
                m2 = men_pool[1] if len(men_pool) > 1 else None
                w2 = women_pool[1] if len(women_pool) > 1 else None

                members_to_use = [
                    (m1, 'MEN', 1),
                    (w1, 'WOMEN', 2),
                    (m2, 'MEN', 3),
                    (w2, 'WOMEN', 4)
                ]

                members_payload = []
                for ath_obj, gen, pos in members_to_use:
                    if ath_obj:
                        u_info = get_university(ath_obj['country'])
                        members_payload.append({
                            'id': ath_obj['id'],
                            'name': ath_obj['name'],
                            'country': ath_obj['country'],
                            'university_id': u_info['id'],
                            'university': u_info['name'],
                            'gender': gen
                        })
                    else:
                        m_id = f"TEST-ATH-{athlete_counter:04d}"
                        athlete_counter += 1
                        u_info = get_university(t_country)
                        new_ath = {
                            'id': m_id,
                            'name': f"{t_country} Swimmer {pos}",
                            'country': t_country,
                            'university_id': u_info['id'],
                            'university': u_info['name'],
                            'gender': gen
                        }
                        known_athletes[(new_ath['name'].strip().lower(), t_country)] = new_ath
                        country_gender_athletes.setdefault((t_country, gen), []).append(new_ath)
                        members_payload.append(new_ath)

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
                a_key = (a_name.strip().lower(), a_country)
                u_info = get_university(a_country)

                if a_key in known_athletes:
                    ath_info = known_athletes[a_key]
                    a_id = ath_info['id']
                else:
                    a_id = f"TEST-ATH-{athlete_counter:04d}"
                    athlete_counter += 1
                    known_athletes[a_key] = {
                        'id': a_id,
                        'name': a_name,
                        'country': a_country,
                        'university_id': u_info['id'],
                        'university': u_info['name'],
                        'gender': ev['gender']
                    }

                entries_payload.append({
                    'lane': lane,
                    'seed_ticks': seed_ticks,
                    'athlete': {
                        'id': a_id,
                        'name': a_name,
                        'country': a_country,
                        'university_id': u_info['id'],
                        'university': u_info['name'],
                        'gender': ev['gender']
                    }
                })

        heats_payload.append({
            'id': ev['heat_id'],
            'event_id': ev['event_id'],
            'session_id': 'TEST-S29A',
            'session_name': 'Afternoon Session - 29 October 2026',
            'date': '2026-10-29',
            'session_start': '16:00',
            'timing_event': ev['event_number'],
            'timing_heat': ev['timing_heat'],
            'name': ev['name'],
            'discipline': ev['discipline'],
            'gender': ev['gender'],
            'round': ev['round'],
            'relay': ev['relay'],
            'entries': entries_payload
        })

    return {
        'data_mode': 'TEST',
        'championship_id': 'TEST-FINS26',
        'name': 'FISU World University Championship Finswimming 2026',
        'source': 'meet program - 29 october 2026 - afternoon.xls',
        'reason': 'Meet program import for 29 October 2026 afternoon finals',
        'events': events,
        'heats': heats_payload
    }

def clear_db_for_afternoon(db_path: Path):
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("BEGIN IMMEDIATE")

    tables = [
        'approvals', 'jury_decisions', 'results', 'timings', 'entries',
        'relay_members', 'heats', 'events', 'sessions', 'championships',
        'teams', 'athletes', 'universities'
    ]
    for table in tables:
        c.execute(f"DELETE FROM {table}")

    c.execute("UPDATE graphics SET preview=NULL, program=NULL, held=0 WHERE id='tv'")
    c.execute("UPDATE routes SET heat_id=NULL, content='idle'")
    c.execute("UPDATE meta SET value='' WHERE key='selected_heat'")
    c.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

    conn.commit()
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("VACUUM")
    conn.close()
    print(f"Cleared tables and reset state in {db_path.name}")

def import_into_db(db_path: Path, payload: dict):
    from results_backend.store import Store
    mode = 'TEST'
    store = Store(str(db_path), mode=mode, operator_mode='SINGLE')
    actor = {'id': 'operator', 'role': 'SYSTEM_ADMINISTRATOR'}
    result = store.import_meet(actor, payload)
    print(f"Imported {result['imported_heats']} finals heats into {db_path.name}")

    # Set selected_heat to the first heat (Event 12 Final)
    with store.db() as c:
        first_heat_id = payload['heats'][0]['id']
        c.execute("UPDATE meta SET value=? WHERE key='selected_heat'", (first_heat_id,))
        c.execute("UPDATE routes SET heat_id=? WHERE output='PROGRAM'", (first_heat_id,))

def main():
    candidates = [
        Path('/Users/mohamedelkerm/Desktop/meet program - 29 october 2026 - afternoon.xls'),
        ROOT / 'meet_program_29_october_2026_afternoon.xls',
        ROOT / 'meet program - 29 october 2026 - afternoon.xls'
    ]
    xls_path = None
    for p in candidates:
        if p.exists():
            xls_path = p
            break
    if not xls_path:
        raise FileNotFoundError("Could not find meet program - 29 october 2026 - afternoon.xls")

    print(f"Parsing Afternoon Excel: {xls_path}")
    events = parse_afternoon_excel(xls_path)
    print(f"Parsed {len(events)} events (all Finals).")
    for ev in events:
        print(f"  Event {ev['event_number']}: {ev['name']} (Relay={ev['relay']}) -> {len(ev['entries'])} lanes")

    morning_backup = BACKUPS_DIR / 'single_test_20261029_morning_session.sqlite3'
    payload = build_import_payload(events, morning_backup if morning_backup.exists() else None)

    # Save JSON files
    hierarchical_file = ROOT / 'runtime' / 'meet_program_29_october_afternoon.json'
    hierarchical_file.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Saved {hierarchical_file.name}")

    import_file = ROOT / 'runtime' / 'meet_import_29_october_afternoon.json'
    import_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Saved {import_file.name} ({len(payload['heats'])} heats)")

    # 1. Clear existing morning session data
    for db_name in ['runtime/single_test.sqlite3', 'runtime/test.sqlite3']:
        db_p = ROOT / db_name
        if db_p.exists():
            clear_db_for_afternoon(db_p)

    # 2. Import afternoon finals payload into both test databases
    for db_name in ['runtime/single_test.sqlite3', 'runtime/test.sqlite3']:
        db_p = ROOT / db_name
        if db_p.exists():
            import_into_db(db_p, payload)

    print("=" * 60)
    print("SUCCESS: 29 October 2026 Afternoon Finals imported successfully!")
    print("=" * 60)

if __name__ == '__main__':
    main()

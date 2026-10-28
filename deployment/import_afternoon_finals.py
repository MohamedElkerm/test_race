"""Import Afternoon Finals into FINS 2026 database."""
import xlrd
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COUNTRY_CODES = {
    'AIN': 'SNA', 'Ain': 'SNA', 'SNA': 'SNA', 'Nsa': 'SNA', 'NSA': 'SNA',
    'Student Neutral Athletes': 'SNA', 'Czechia': 'CZE', 'Czech': 'CZE',
    'France': 'FRA', 'China': 'CHN', 'Poland': 'POL', 'Chinese Taipei': 'TPE',
    'Germany': 'GER', 'Italy': 'ITA', 'Egypt': 'EGY', 'Colombia': 'COL',
    'Spain': 'ESP', 'Hungary': 'HUN', 'Tunisia': 'TUN', 'Belgium': 'BEL',
    'Slovakia': 'SVK', 'Japan': 'JPN', 'Lithuania': 'LTU', 'South Korea': 'KOR'
}

# Mapping of relay teams by country and discipline
RELAY_TEAMS = {
    # Event 10: Mixed 4x100 SF
    ('SF', 'GER'): 'TEST-TEAM-11',
    ('SF', 'CHN'): 'TEST-TEAM-3',
    ('SF', 'SNA'): 'TEST-TEAM-2',
    ('SF', 'EGY'): 'TEST-TEAM-9',
    ('SF', 'ITA'): 'TEST-TEAM-8',
    ('SF', 'FRA'): 'TEST-TEAM-4',
    ('SF', 'CZE'): 'TEST-TEAM-7',
    ('SF', 'TPE'): 'TEST-TEAM-5',
    # Event 11: Mixed 4x50 BF
    ('BF', 'ESP'): 'TEST-TEAM-14',
    ('BF', 'ITA'): 'TEST-TEAM-16',
    ('BF', 'TPE'): 'TEST-TEAM-22',
    ('BF', 'POL'): 'TEST-TEAM-17',
    ('BF', 'EGY'): 'TEST-TEAM-23',
    ('BF', 'FRA'): 'TEST-TEAM-18',
    ('BF', 'HUN'): 'TEST-TEAM-24',
    ('BF', 'SNA'): 'TEST-TEAM-15',
}

def parse_time_to_ticks(t_str):
    t_str = str(t_str).strip()
    if not t_str or t_str.upper() in ('NT', '—', '-'):
        return None
    try:
        if ':' in t_str:
            parts = t_str.split(':')
            m = float(parts[0])
            sec = float(parts[1])
            total_sec = m * 60 + sec
        else:
            total_sec = float(t_str)
        return int(round(total_sec * 10000))
    except Exception:
        return None

def parse_afternoon_excel(xls_path):
    wb = xlrd.open_workbook(xls_path)
    s = wb.sheet_by_index(0)

    events = []
    current_event = None
    in_alternates = False

    for r in range(s.nrows):
        row = [str(s.cell_value(r, c)).strip() for c in range(s.ncols)]
        if not any(row): continue
        first = row[0]
        
        if first.startswith('Event'):
            in_alternates = False
            m = re.match(r'Event\s+(\d+)\s+(.+)', first)
            if m:
                ev_num = int(m.group(1))
                ev_name = m.group(2).strip()
                
                if 'Women' in ev_name: gender = 'WOMEN'
                elif 'Men' in ev_name: gender = 'MEN'
                elif 'Mixed' in ev_name: gender = 'MIXED'
                else: gender = 'MIXED'
                
                is_relay = 'Relay' in ev_name
                
                if 'BF' in ev_name: discipline = 'BF'
                elif 'AP' in ev_name: discipline = 'AP'
                else: discipline = 'SF'
                
                current_event = {
                    'event_number': ev_num,
                    'event_id': f'TEST-E{ev_num}-F',
                    'heat_id': f'TEST-E{ev_num}-FINAL',
                    'name': ev_name,
                    'gender': gender,
                    'discipline': discipline,
                    'relay': is_relay,
                    'entries': []
                }
                events.append(current_event)
            continue
        
        if first.startswith('Alternates'):
            in_alternates = True
            continue
        
        if in_alternates:
            continue
            
        if first.isdigit() and current_event is not None:
            lane = int(first)
            if current_event['relay']:
                team_raw = row[1]
                relay_letter = row[3] if len(row) > 3 and row[3] else 'A'
                prelim_time = row[4] if len(row) > 4 and not row[4].startswith('___') else ''
                country_code = COUNTRY_CODES.get(team_raw, team_raw[:3].upper())
                current_event['entries'].append({
                    'lane': lane,
                    'team': team_raw,
                    'relay_letter': relay_letter,
                    'country': country_code,
                    'seed_time': prelim_time,
                    'seed_ticks': parse_time_to_ticks(prelim_time)
                })
            else:
                name = row[1]
                age = row[2] if len(row) > 2 else ''
                team_raw = row[3] if len(row) > 3 else ''
                prelim_time = row[4] if len(row) > 4 and not row[4].startswith('___') else ''
                country_code = COUNTRY_CODES.get(team_raw, team_raw[:3].upper())
                current_event['entries'].append({
                    'lane': lane,
                    'name': name,
                    'age': age,
                    'team': team_raw,
                    'country': country_code,
                    'seed_time': prelim_time,
                    'seed_ticks': parse_time_to_ticks(prelim_time)
                })

    return events

def import_into_db(db_path, events):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('PRAGMA foreign_keys = OFF')
    cur.execute('BEGIN TRANSACTION')

    # Ensure heats table constraint is UNIQUE(event_id, timing_heat)
    schema = cur.execute('SELECT sql FROM sqlite_master WHERE name="heats"').fetchone()[0]
    if 'UNIQUE(timing_event,timing_heat)' in schema or 'UNIQUE(timing_event, timing_heat)' in schema:
        cur.execute('''
        CREATE TABLE heats_new(
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id),
            timing_event INTEGER NOT NULL,
            timing_heat INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT "SCHEDULED",
            revision INTEGER NOT NULL DEFAULT 0,
            clock_ticks INTEGER,
            last_timing REAL,
            recovery_hold INTEGER NOT NULL DEFAULT 0,
            published INTEGER NOT NULL DEFAULT 0,
            UNIQUE(event_id, timing_heat)
        )
        ''')
        cur.execute('INSERT INTO heats_new SELECT * FROM heats')
        cur.execute('DROP TABLE heats')
        cur.execute('ALTER TABLE heats_new RENAME TO heats')

    # Load existing athletes
    cur.execute('SELECT name, country, id FROM athletes')
    db_athletes = {(row[0].strip().lower(), row[1].strip()): row[2] for row in cur.fetchall()}

    # Add afternoon session
    cur.execute('''
    INSERT OR REPLACE INTO sessions(id, championship_id, name, date, session_start, source)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('TEST-S2', 'TEST-CHAMP-1', 'Afternoon Session - 28 October 2026', '2026-10-28', '17:00', 'Afternoon Meet Program Excel'))

    for ev in events:
        # Add event
        cur.execute('''
        INSERT OR REPLACE INTO events(id, session_id, name, discipline, gender, round, relay)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ev['event_id'], 'TEST-S2', ev['name'], ev['discipline'], ev['gender'], 'FINAL', int(ev['relay'])))

        # Add heat
        cur.execute('''
        INSERT OR REPLACE INTO heats(id, event_id, timing_event, timing_heat, status, revision)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (ev['heat_id'], ev['event_id'], ev['event_number'], 1, 'READY', 0))

        # Remove old entries for this heat if re-running
        cur.execute('DELETE FROM entries WHERE heat_id = ?', (ev['heat_id'],))

        # Add entries
        for entry in ev['entries']:
            lane = entry['lane']
            seed_ticks = entry['seed_ticks']
            if ev['relay']:
                disc = ev['discipline']
                cc = entry['country']
                team_id = RELAY_TEAMS.get((disc, cc))
                if not team_id:
                    # Look up from teams by country
                    t_row = cur.execute('SELECT id FROM teams WHERE country = ?', (cc,)).fetchone()
                    team_id = t_row[0] if t_row else None
                cur.execute('''
                INSERT INTO entries(heat_id, lane, athlete_id, team_id, seed_ticks)
                VALUES (?, ?, ?, ?, ?)
                ''', (ev['heat_id'], lane, None, team_id, seed_ticks))
            else:
                name_key = (entry['name'].strip().lower(), entry['country'])
                athlete_id = db_athletes.get(name_key)
                if not athlete_id:
                    # try by name only
                    matches = [ath_id for (n, c), ath_id in db_athletes.items() if n == entry['name'].strip().lower()]
                    if matches:
                        athlete_id = matches[0]
                    else:
                        raise ValueError(f"Athlete not found in DB: {entry['name']} ({entry['country']})")
                cur.execute('''
                INSERT INTO entries(heat_id, lane, athlete_id, team_id, seed_ticks)
                VALUES (?, ?, ?, ?, ?)
                ''', (ev['heat_id'], lane, athlete_id, None, seed_ticks))

    cur.execute('PRAGMA foreign_keys = ON')
    conn.commit()
    conn.close()
    print(f"Successfully imported {len(events)} events and finals into {db_path}!")

if __name__ == '__main__':
    xls = '/Users/mohamedelkerm/Desktop/meet program - 28 october 2026 - afternoon.xls'
    evs = parse_afternoon_excel(xls)
    for db in ['runtime/single_test.sqlite3', 'runtime/test.sqlite3']:
        p = ROOT / db
        if p.exists():
            import_into_db(str(p), evs)

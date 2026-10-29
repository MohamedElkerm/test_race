"""Observed SwimTime UDP feed for TEST monitoring; never writes competition timing.

The 03:06 Cairo capture and 03:12 screenshot match all ten LaneTime values
using 10,000 ticks/second, truncated to hundredths. This validates this test
profile, not physical touchpad timing, official lane numbering, or finish rules.
"""
from __future__ import annotations

import asyncio
from collections import Counter, deque
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .swimtime_observed import DiagnosticState, parse_datagram, ProtocolError

PROFILE = 'swimtime-2.4.10.1-network-display-screen-matched-test-v3'
CAPTURE = 'udp26-20261024T000648Z-1792800408138675400.jsonl'
CAPTURE_SHA256 = 'f406de2726311dc569a2bc17fcd6d4a5c34c72f7e68c0497b931bb38553644fe'
DEFAULT_API_BASE_URL = 'https://fasugames2026.eusf.org.eg/v2/api'


def _extract_heats_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('heats', 'docs', 'items', 'results'):
            if isinstance(payload.get(key), list):
                return payload[key]
        data = payload.get('data')
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ('heats', 'docs', 'items', 'results', 'data'):
                if isinstance(data.get(key), list):
                    return data[key]
    return []


def display_ticks(ticks):
    if ticks is None or ticks < 0:
        return None
    hundredths = ticks // 100
    return f'{hundredths // 6000}:{hundredths // 100 % 60:02}.{hundredths % 100:02}'


class FeedState:
    def __init__(self, source_ip):
        self.raw = DiagnosticState(source_ip)
        self.lock = threading.RLock()
        self.channels = {}
        self.finished_channels = {}
        self.race_active = False
        self.clock = None
        self.last_numeric_clock = None
        self.clock_at = None
        self.clock_code = None
        self.clock_held = False
        self.layout = 'LANE ORIENTATION EXPECTED / TEST CAPTURE ONLY'
        self.layout_supported = True
        self.metadata = {}
        self.events = deque(maxlen=30)
        self.warning = None

    def _snapshot_race_end(self, reset_after=False):
        snap = {
            'finished_channels': [dict(self.finished_channels[k]) for k in sorted(self.finished_channels)],
            'heat_number': self.metadata.get('Heat.HeatNumber'),
            'meta': dict(self.metadata),
            'reset_after': bool(reset_after),
        }
        self.race_active = False
        return snap

    def consume(self, raw, sender, at):
        with self.lock:
            row = self.raw.consume(raw, sender, at)
            if not row['accepted']:
                if raw.startswith(b'Layout\t') and raw.rstrip(b'\r\n') != b'Layout\tStartlist':
                    self.layout_supported = False
                    self.clock = None
                    self.channels.clear()
                    self.finished_channels.clear()
                    self.race_active = False
                    self.warning = 'Unsupported layout; times suppressed until LaneOriented is received or the listener is restarted.'
                return row
            for rec in row['records']:
                scope = rec['scope']
                if scope == 'Layout':
                    self.layout = rec['value']
                    self.layout_supported = True
                    self.warning = None
                elif scope != 'Time':
                    key = f"{scope}.{rec['field']}"
                    previous = self.metadata.get(key)
                    if key in ('Session.SessionNumber', 'Event.EventName', 'Heat.HeatNumber') and previous is not None and previous != rec['value']:
                        if self.race_active:
                            row['trigger_race_end'] = self._snapshot_race_end(reset_after=True)
                        else:
                            row['reset_external_sync'] = True
                        self.channels.clear()
                        self.finished_channels.clear()
                        self.clock = None
                        self.last_numeric_clock = None
                        self.clock_held = False
                    self.metadata[key] = rec['value']
                elif self.layout_supported:
                    value, channel, kind = rec['raw_value'], rec['channel'], rec['kind']
                    if kind == 'RunningTime':
                        if value < 0:
                            if self.race_active:
                                row['trigger_race_end'] = self._snapshot_race_end(reset_after=False)
                            self.clock = None
                            self.clock_code = value
                            self.clock_held = False
                            self.last_numeric_clock = None
                        elif self.clock_held:
                            pass
                        elif self.clock is not None and value < self.clock:
                            self.clock = None
                            self.clock_held = True
                            self.warning = 'Clock decreased without an observed idle/ready transition; clock held. Raw data retained.'
                        else:
                            if self.last_numeric_clock is None:
                                self.channels.clear()
                            if not self.race_active:
                                self.race_active = True
                                self.finished_channels.clear()
                                row['trigger_race_start'] = True
                            if self.clock != value:
                                self.clock_at = at
                            self.clock = self.last_numeric_clock = value
                            self.clock_code = None
                    elif kind == 'Ready':
                        if self.race_active:
                            row['trigger_race_end'] = self._snapshot_race_end(reset_after=True)
                        else:
                            row['reset_external_sync'] = True
                        self.finished_channels.clear()
                        self.clock = None
                        self.clock_code = None
                        self.last_numeric_clock = None
                        self.clock_held = False
                        if self.warning and self.warning.startswith('Clock decreased'):
                            self.warning = None
                    elif kind == 'LaneTime' and 0 <= channel <= 10:
                        self.channels[channel] = {
                            'channel': channel, 'raw_value': value,
                            'display_time': display_ticks(value),
                            'source_rank': rec['fields']['Rank'],
                            'source_lap': rec['fields']['Lap'],
                            'source_points': rec['fields']['Points'],
                            'received_at_unix': at,
                            'meaning': 'OBSERVED TIME / TEST ONLY' if value >= 0 else 'UNINTERPRETED NEGATIVE CODE',
                        }
                        if value > 0:
                            self.finished_channels[channel] = dict(self.channels[channel])
                            row['trigger_external_sync'] = True
                    if kind != 'RunningTime':
                        self.events.append({'kind': kind, 'channel': channel, 'raw_value': value, 'at': at})
            return row

    def snapshot(self, now, listening=False, replay=False):
        with self.lock:
            age = None if self.raw.last_valid_at is None else max(0, now - self.raw.last_valid_at)
            fresh = age is not None and age <= 3
            clock_age = None if self.clock_at is None else max(0, now - self.clock_at)
            clock_fresh = listening and fresh and clock_age is not None and clock_age <= 2 and self.layout_supported and not self.clock_held
            status = 'RECORDED TEST REPLAY' if replay else ('STOPPED' if not listening else ('NO FEED' if age is None else ('RECEIVING TEST DATA' if fresh else 'STALE / DATA LOST')))
            return {
                'profile': PROFILE, 'state': status, 'listening': listening,
                'receiving': bool(listening and fresh), 'replay': replay,
                'age_ms': None if age is None else round(age * 1000),
                'clock_display': display_ticks(self.clock) if clock_fresh else None,
                'clock_raw': self.clock, 'clock_code': self.clock_code,
                'clock_fresh': bool(clock_fresh and self.clock is not None),
                'channels': [dict(self.channels[k]) for k in sorted(self.channels, reverse=True)],
                'counts': dict(self.raw.counts), 'recent_events': list(self.events),
                'metadata': dict(self.metadata), 'layout': self.layout,
                'warning': self.warning, 'mode': 'TEST',
                'unit_seconds': '0.0001', 'unit_verification': '10 LaneTime values matched to the supplied TEST screen; running-time rate corroborated',
                'channel_lane_mapping_verified': False, 'hardware_verified': False,
                'official_result': False, 'results_written': False,
                'finish_detection_verified': False, 'sequence_numbers_available': False,
            }


class _Receiver(asyncio.DatagramProtocol):
    def __init__(self, owner):
        self.owner = owner

    def datagram_received(self, raw, addr):
        if not self.owner.listening:
            return
        try:
            row = self.owner.data.consume(raw, addr, time.time())
            reset_sync = row.pop('reset_external_sync', False)
            trigger_start = row.pop('trigger_race_start', False)
            trigger_sync = row.pop('trigger_external_sync', False)
            trigger_end = row.pop('trigger_race_end', None)
            self.owner.write_log(row)
            if reset_sync and trigger_end is None:
                self.owner.reset_sync_session()
            if self.owner.sync_config.get('auto_sync'):
                try:
                    loop = asyncio.get_running_loop()
                    if trigger_end is not None:
                        loop.create_task(self.owner.sync_to_external_api(
                            force=True, complete_heat=True, end_snapshot=trigger_end, reason='auto_race_end'
                        ))
                    elif trigger_sync:
                        loop.create_task(self.owner.sync_to_external_api(reason='auto_lane_touch'))
                    elif trigger_start:
                        loop.create_task(self.owner.sync_to_external_api(check_only=True, reason='auto_race_start'))
                except RuntimeError:
                    pass
            elif trigger_end is not None and trigger_end.get('reset_after'):
                self.owner.reset_sync_session()
        except (OSError, ValueError) as exc:
            self.owner.error = f'Capture failed: {exc}'
            self.owner.stop(write_summary=False)

    def error_received(self, exc):
        self.owner.error = f'UDP error: {exc}'


class SwimTimeNetwork:
    def __init__(self, root: Path, mode='TEST'):
        self.root, self.mode = root, mode
        cfg = self._load_settings_file()
        env_ip = os.environ.get('SWIMTIME_SOURCE_IP') or os.environ.get('FINS_SWIMTIME_SOURCE_IP')
        default_ip = env_ip or cfg.get('swimtime_source_ip', '10.227.186.112')
        self.data = FeedState(default_ip)
        self.listening = self.replay = False
        self.transport = None
        self.log = None
        self.log_bytes = 0
        self.log_part = 0
        self.capture_prefix = None
        env_port = os.environ.get('SWIMTIME_PORT') or os.environ.get('FINS_SWIMTIME_PORT')
        self.port = int(env_port) if env_port else int(cfg.get('swimtime_port', 26))
        self.error = None
        self.log_path = None
        self.sync_config = {
            'api_base_url': str(cfg.get('api_base_url', DEFAULT_API_BASE_URL)).rstrip('/'),
            'bearer_token': str(cfg.get('bearer_token', '')),
            'lane_offset': int(cfg.get('lane_offset', 0)),
            'auto_sync': bool(cfg.get('auto_sync', True)),
        }
        self._sync_lock = None
        self.active_heat_id = None
        self.active_heat_number = None
        self.active_heat_label = None
        self.last_synced_signature = None
        self.last_completed_heat_id = None
        self.sync_status = {
            'state': 'IDLE',
            'last_sync_at': None,
            'matched_heat_id': None,
            'matched_heat_label': None,
            'swimtime_heat_number': None,
            'last_sent_lanes': 0,
            'last_message': 'Ready to sync ONGOING heats with heatNumber verification.',
            'last_error': None,
        }

    def _settings_path(self) -> Path:
        return self.root / 'network_settings.json'

    def _load_settings_file(self) -> dict:
        p = self._settings_path()
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                return {}
        return {}

    def _save_settings_file(self, force_create=False):
        p = self._settings_path()
        if not force_create and not p.is_file():
            return
        if not p.parent.is_dir():
            return
        payload = {
            'swimtime_source_ip': self.data.raw.expected_source or '192.168.43.112',
            'swimtime_port': self.port,
            'api_base_url': self.sync_config['api_base_url'],
            'bearer_token': self.sync_config['bearer_token'],
            'lane_offset': self.sync_config['lane_offset'],
            'auto_sync': self.sync_config['auto_sync'],
        }
        try:
            p.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        except OSError:
            pass

    def reset_sync_session(self):
        self.active_heat_id = None
        self.active_heat_number = None
        self.active_heat_label = None
        self.last_synced_signature = None

    def update_sync_config(self, config: dict):
        if 'api_base_url' in config and config['api_base_url'] is not None:
            url = str(config['api_base_url']).strip().rstrip('/')
            if not url.startswith(('http://', 'https://')):
                raise ValueError('API Base URL must start with http:// or https://')
            self.sync_config['api_base_url'] = url
        if 'bearer_token' in config and config['bearer_token'] is not None:
            token = str(config['bearer_token']).strip()
            if token.lower().startswith('bearer '):
                token = token[7:].strip()
            self.sync_config['bearer_token'] = token
        if 'lane_offset' in config and config['lane_offset'] is not None:
            self.sync_config['lane_offset'] = int(config['lane_offset'])
        if 'auto_sync' in config and config['auto_sync'] is not None:
            self.sync_config['auto_sync'] = bool(config['auto_sync'])
        self._save_settings_file(force_create=True)
        return self.snapshot()

    def build_results_payload(self, end_snapshot: dict | None = None):
        if end_snapshot is not None:
            meta = dict(end_snapshot.get('meta') or {})
            channels = [dict(ch) for ch in (end_snapshot.get('finished_channels') or [])]
            heat_number = end_snapshot.get('heat_number')
        else:
            with self.data.lock:
                meta = dict(self.data.metadata)
                merged = {}
                for k in sorted(set(self.data.channels) | set(self.data.finished_channels)):
                    ch = self.data.channels.get(k)
                    if ch is not None and (ch.get('raw_value') or 0) > 0:
                        merged[k] = dict(ch)
                    elif k in self.data.finished_channels:
                        merged[k] = dict(self.data.finished_channels[k])
                    elif ch is not None:
                        merged[k] = dict(ch)
                channels = [merged[k] for k in sorted(merged)]
                heat_number = meta.get('Heat.HeatNumber')
        offset = int(self.sync_config.get('lane_offset', 0))
        results = []
        for ch in channels:
            val = ch.get('raw_value', -1)
            if val is not None and val > 0:
                results.append({
                    'lane': int(ch['channel']) + offset,
                    'timeMs': (int(val) // 100) * 10,
                    'resultStatus': 'PENDING',
                    'athleteStatus': 'PENDING',
                })
        return results, heat_number, meta

    def _http_json(self, method: str, url: str, body: dict | None = None):
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'FINS2026-LiveResults/0.8',
        }
        token = self.sync_config.get('bearer_token', '').strip()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_text = resp.read().decode('utf-8', 'replace')
                return resp.status, (json.loads(raw_text) if raw_text.strip() else {})
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode('utf-8', 'replace')
            try:
                parsed = json.loads(err_body)
                msg = parsed.get('message') or parsed.get('error') or err_body[:200]
            except Exception:
                msg = err_body[:200] or str(exc)
            raise ValueError(f'HTTP {exc.code}: {msg}') from exc
        except urllib.error.URLError as exc:
            raise ValueError(f'Network error reaching API: {exc.reason}') from exc

    def _sync_worker(self, force: bool, check_only: bool, reason: str, complete_heat: bool = False, end_snapshot: dict | None = None):
        base_url = self.sync_config.get('api_base_url', '').rstrip('/')
        if not base_url:
            raise ValueError('API Base URL is not configured')
        results, st_heat_num, meta = self.build_results_payload(end_snapshot=end_snapshot)
        st_heat_str = str(st_heat_num).strip() if st_heat_num is not None else None

        has_cached_heat = bool(self.active_heat_id) and (not st_heat_str or not self.active_heat_number or self.active_heat_number == st_heat_str)
        need_get_lookup = (not has_cached_heat) or (check_only and reason != 'auto_race_start')

        if need_get_lookup:
            # Step 1: Query GET /heats?status=ONGOING once per heat to locate active heat and verify heatNumber
            heats_url = f'{base_url}/heats?' + urllib.parse.urlencode({'status': 'ONGOING', 'limit': 100})
            _, get_payload = self._http_json('GET', heats_url)
            all_heats = _extract_heats_list(get_payload)
            ongoing_heats = [h for h in all_heats if isinstance(h, dict) and str(h.get('status', '')).upper() == 'ONGOING']

            matched_heat = None
            if st_heat_str:
                matching = [h for h in ongoing_heats if str(h.get('heatNumber', '')).strip() == st_heat_str]
                if matching:
                    matched_heat = matching[0]
                elif has_cached_heat:
                    pass
                else:
                    found_desc = ', '.join(f"Heat #{h.get('heatNumber')} ({h.get('competition', '')})" for h in ongoing_heats) or 'None'
                    raise ValueError(f'HeatNumber verification failed: SwimTime is on Heat #{st_heat_str}, but ONGOING heats in API are: [{found_desc}]')
            else:
                if len(ongoing_heats) == 1:
                    matched_heat = ongoing_heats[0]
                    st_heat_str = str(matched_heat.get('heatNumber', '')).strip() or None
                elif len(ongoing_heats) == 0:
                    if not self.active_heat_id:
                        raise ValueError('No ONGOING heat found in API (mark the heat ONGOING in your platform first)')
                else:
                    found_desc = ', '.join(f"Heat #{h.get('heatNumber')} ({h.get('_id')})" for h in ongoing_heats)
                    raise ValueError(f'Multiple ONGOING heats in API ({found_desc}) and SwimTime has not sent HeatNumber yet')

            if matched_heat is not None:
                self.active_heat_id = str(matched_heat.get('_id') or matched_heat.get('id'))
                self.active_heat_number = str(matched_heat.get('heatNumber', st_heat_str or '')).strip()
                comp = matched_heat.get('competition') or (matched_heat.get('match') or {}).get('competition') or ''
                gender = matched_heat.get('gender') or ''
                rnd = matched_heat.get('roundType') or ''
                self.active_heat_label = f"Heat #{self.active_heat_number} {' '.join(x for x in (comp, gender, rnd) if x)} ({self.active_heat_id})".strip()

        if check_only:
            self.sync_status.update({
                'state': 'VERIFIED',
                'last_sync_at': time.time(),
                'matched_heat_id': self.active_heat_id,
                'matched_heat_label': self.active_heat_label,
                'swimtime_heat_number': st_heat_str or self.active_heat_number,
                'last_message': f'Verified ONGOING heat match: {self.active_heat_label}',
                'last_error': None,
            })
            return self.sync_status

        target_heat_id = self.active_heat_id
        target_heat_label = self.active_heat_label
        target_heat_num = st_heat_str or self.active_heat_number

        try:
            if complete_heat:
                if results:
                    sig = (target_heat_id, tuple((r['lane'], r['timeMs']) for r in results))
                    if sig != self.last_synced_signature:
                        post_url = f'{base_url}/heats/{target_heat_id}/results'
                        self._http_json('POST', post_url, {'results': results})
                        self.last_synced_signature = sig
                if reason == 'manual_complete' or self.last_completed_heat_id != target_heat_id:
                    status_url = f'{base_url}/heats/{target_heat_id}/status'
                    _, patch_resp = self._http_json('PATCH', status_url, {'status': 'COMPLETED', 'startNextHeat': True})
                    self.last_completed_heat_id = target_heat_id
                    api_msg = patch_resp.get('message', 'Heat marked COMPLETED') if isinstance(patch_resp, dict) else 'Heat marked COMPLETED'
                    self.sync_status.update({
                        'state': 'COMPLETED',
                        'last_sync_at': time.time(),
                        'matched_heat_id': target_heat_id,
                        'matched_heat_label': target_heat_label,
                        'swimtime_heat_number': target_heat_num,
                        'last_sent_lanes': len(results),
                        'last_message': f'{api_msg} ({len(results)} lane(s) -> {target_heat_label})',
                        'last_error': None,
                    })
                self.reset_sync_session()
                return self.sync_status

            if not results:
                self.sync_status.update({
                    'state': 'WAITING_RESULTS',
                    'matched_heat_id': target_heat_id,
                    'matched_heat_label': target_heat_label,
                    'swimtime_heat_number': target_heat_num,
                    'last_message': f'Matched {target_heat_label}; waiting for finished lane touches to POST.',
                    'last_error': None,
                })
                return self.sync_status

            sig = (target_heat_id, tuple((r['lane'], r['timeMs']) for r in results))
            if not force and sig == self.last_synced_signature:
                return self.sync_status

            post_url = f'{base_url}/heats/{target_heat_id}/results'
            _, post_resp = self._http_json('POST', post_url, {'results': results})
            self.last_synced_signature = sig
            api_msg = post_resp.get('message', 'Results synced') if isinstance(post_resp, dict) else 'Results synced'
            self.sync_status.update({
                'state': 'SYNCED',
                'last_sync_at': time.time(),
                'matched_heat_id': target_heat_id,
                'matched_heat_label': target_heat_label,
                'swimtime_heat_number': target_heat_num,
                'last_sent_lanes': len(results),
                'last_message': f'{api_msg} ({len(results)} lane(s) -> {target_heat_label})',
                'last_error': None,
            })
            return self.sync_status
        finally:
            if end_snapshot is not None and end_snapshot.get('reset_after'):
                self.reset_sync_session()

    async def sync_to_external_api(self, force=False, check_only=False, reason='manual', complete_heat=False, end_snapshot=None):
        if self._sync_lock is None:
            self._sync_lock = asyncio.Lock()
        async with self._sync_lock:
            try:
                await asyncio.to_thread(self._sync_worker, force, check_only, reason, complete_heat, end_snapshot)
            except Exception as exc:
                self.sync_status.update({
                    'state': 'ERROR',
                    'last_sync_at': time.time(),
                    'swimtime_heat_number': self.data.metadata.get('Heat.HeatNumber'),
                    'last_error': str(exc),
                })
            return dict(self.sync_status)

    def write_log(self, row):
        if not self.log:
            return
        line = json.dumps(row, ensure_ascii=False) + '\n'
        if self.log_bytes > 32 * 1024 * 1024:
            self.log.close()
            self.log_part += 1
            self._open_log()
        self.log.write(line)
        self.log.flush()
        self.log_bytes += len(line.encode('utf-8'))

    def _open_log(self):
        path = self.root / 'runtime' / 'swimtime'
        path.mkdir(parents=True, exist_ok=True)
        self.log_path = path / f'{self.capture_prefix}-{self.log_part:03}.jsonl'
        self.log = self.log_path.open('x', encoding='utf-8')
        self.log_bytes = 0
        self.write_log({'type': 'metadata', 'profile': PROFILE, 'mode': 'TEST',
                        'source_ip': self.data.raw.expected_source, 'port': self.port,
                        'started_at_unix': time.time(), 'hardware_verified': False,
                        'official_result': False, 'part': self.log_part})

    async def start(self, source_ip='10.227.186.112', port=26):
        if self.mode != 'TEST':
            raise ValueError('SwimTime observed profile is available only in TEST mode')
        if self.listening:
            raise ValueError('UDP listener is already active; stop it before changing the source')
        ip = ipaddress.IPv4Address(source_ip)
        if ip.is_multicast or ip.is_unspecified or int(ip) == 0xffffffff:
            raise ValueError('A specific source PC IPv4 address is required')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('UDP port must be 1..65535')
        self.data, self.error, self.replay = FeedState(str(ip)), None, False
        self.port = port
        self.reset_sync_session()
        self._save_settings_file(force_create=False)
        self.log_part = 0
        self.capture_prefix = 'udp26-integrated-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + str(time.time_ns())
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('0.0.0.0', port))
            sock.setblocking(False)
            self.port = sock.getsockname()[1]
            self._open_log()
            self.listening = True
            self.transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(lambda: _Receiver(self), sock=sock)
        except (OSError, ValueError):
            sock.close()
            self.stop()
            raise
        return self.snapshot()

    def stop(self, write_summary=True):
        self.listening = False
        if self.transport:
            self.transport.close()
            self.transport = None
        if self.log:
            try:
                if write_summary:
                    self.write_log({'type': 'summary', **self.snapshot()})
            except OSError as exc:
                self.error = f'Capture close failed: {exc}'
            finally:
                self.log.close()
                self.log = None

    def replay_capture(self):
        if self.mode != 'TEST' or self.listening:
            raise ValueError('Stop the TEST UDP listener before replaying a capture')
        path = self.root / 'evidence' / 'swimtime' / CAPTURE
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != CAPTURE_SHA256:
            raise ValueError('Bundled capture hash mismatch')
        self.data, self.error, self.replay = FeedState('10.227.186.112'), None, True
        for line in raw.decode('utf-8').splitlines():
            row = json.loads(line)
            if 'hex' in row:
                self.data.consume(bytes.fromhex(row['hex']), (row['sender_ip'], row['sender_port']), row['received_at_unix'])
        return self.snapshot()

    def snapshot(self):
        result = self.data.snapshot(time.time(), self.listening, self.replay)
        result.update(enabled=self.mode == 'TEST', source_ip=self.data.raw.expected_source,
                      port=self.port, error=self.error,
                      capture_file=None if self.log_path is None else self.log_path.name,
                      sync_config=dict(self.sync_config),
                      sync_status=dict(self.sync_status))
        return result

"""Read-only SwimTime Network Display diagnostic, observed profile 2026-10-24.

No results database, HTTP API, graphics controls or official time conversions.
Python standard library only. The running-time unit remains unverified.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import time
from collections import Counter, deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

PROFILE = "swimtime-2.4.10.1-network-display-observed-20261024-v2"
SCOPES = {"Meet", "Session", "Event", "Heat"}
TIME_KINDS = {"RunningTime", "Ready", "LaneTime"}


class ProtocolError(ValueError):
    pass


def integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if not digits or len(value) > 20 or not all("0" <= char <= "9" for char in digits):
        raise ProtocolError("Invalid integer")
    result = int(value)
    if not -(2**63) <= result < 2**63:
        raise ProtocolError("Integer outside int64 range")
    return result


def parse_datagram(raw: bytes) -> list[dict]:
    """Decode structure only; channel IDs, units and result meaning are unapproved."""
    # The 02:35 field capture contains this complete control datagram without CR.
    # Recognise only this observed layout; never relax Time record termination.
    if raw in (b"Layout\tLaneOriented", b"Layout\tLaneOriented\r", b"Layout\tLaneOriented\r\n"):
        return [{"scope": "Layout", "value": "LaneOriented",
                 "channel_lane_mapping_verified": False, "official_result": False}]
    if not raw or len(raw) > 65507 or not raw.endswith((b"\r", b"\r\n")):
        raise ProtocolError("Empty, oversized or unterminated datagram")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ProtocolError("Unsupported text encoding; raw bytes retained") from exc
    if "\0" in text:
        raise ProtocolError("NUL in text")
    result = []
    for record in text.split("\r"):
        record = record.lstrip("\n")
        if not record:
            continue
        parts = record.split("\t")
        if parts[0] == "Time":
            if len(parts) < 4 or len(parts) % 2:
                raise ProtocolError("Invalid Time key/value structure")
            channel = integer(parts[1])
            if not 0 <= channel <= 10000:
                raise ProtocolError("Channel outside diagnostic range")
            pairs = list(zip(parts[2::2], parts[3::2]))
            fields = dict(pairs)
            if len(fields) != len(pairs) or not all(key for key, _ in pairs):
                raise ProtocolError("Duplicate or empty Time field")
            kind = pairs[0][0]
            if kind not in TIME_KINDS:
                raise ProtocolError("Unobserved Time message type")
            for key in (kind, "Rank", "Lap"):
                if key not in fields:
                    raise ProtocolError("Required observed field absent: " + key)
                integer(fields[key])
            if "Points" not in fields:
                raise ProtocolError("Points field absent")
            try:
                if not Decimal(fields["Points"]).is_finite():
                    raise ProtocolError("Non-finite Points")
            except InvalidOperation as exc:
                raise ProtocolError("Invalid Points") from exc
            result.append({"scope": "Time", "channel": channel, "kind": kind,
                           "raw_value": integer(fields[kind]), "fields": fields,
                           "time_unit": None, "official_result": False,
                           "channel_lane_mapping_verified": False})
        elif parts[0] in SCOPES and len(parts) == 3 and parts[1]:
            result.append({"scope": parts[0], "field": parts[1], "value": parts[2],
                           "imported_into_results": False})
        else:
            raise ProtocolError("Unobserved record structure")
    if not result:
        raise ProtocolError("No records")
    return result


class DiagnosticState:
    def __init__(self, expected_source: str | None = None):
        self.expected_source = expected_source
        self.counts = Counter()
        self.last_valid_at = None
        self.last_time = None
        self.recent = deque(maxlen=4096)

    def consume(self, raw: bytes, sender: tuple[str, int], at: float) -> dict:
        self.counts["datagrams"] += 1
        row = {"received_at_unix": at, "sender_ip": sender[0],
               "sender_port": sender[1], "length": len(raw), "hex": raw.hex(),
               "hardware_verified": False, "official_result": False}
        if self.expected_source and sender[0] != self.expected_source:
            self.counts["other_source"] += 1
            return {**row, "accepted": False, "error": "Source IP does not match"}
        try:
            records = parse_datagram(raw)
        except ProtocolError as exc:
            self.counts["unparsed"] += 1
            return {**row, "accepted": False, "error": str(exc)}
        digest = hashlib.sha256(raw).digest()
        duplicate = any(value == digest and at - previous <= 2
                        for previous, value in self.recent)
        self.recent.append((at, digest))
        self.counts["accepted"] += 1
        self.counts["duplicate_payload_within_2s"] += int(duplicate)
        self.last_valid_at = at  # repeated Ready records still prove a fresh feed
        for item in records:
            self.counts[item.get("kind", item["scope"])] += 1
            if item["scope"] == "Time":
                self.last_time = item
        return {**row, "accepted": True, "records": records,
                "duplicate_payload_within_2s": duplicate}

    def status(self, now: float, stale_seconds: float = 3) -> dict:
        age = None if self.last_valid_at is None else max(0, now - self.last_valid_at)
        return {"state": "NO FEED" if age is None else
                ("RECEIVING / UNVERIFIED" if age <= stale_seconds else "STALE"),
                "age_seconds": None if age is None else round(age, 3),
                "counts": dict(self.counts), "last_time": self.last_time,
                "hardware_verified": False, "official_result": False}


def receive(seconds: float, port: int, source_ip: str | None, output: Path,
            bind: str = "0.0.0.0", on_ready=None) -> dict:
    state = DiagnosticState(source_ip)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as log, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((bind, port))
        sock.settimeout(0.25)
        started = time.monotonic()
        log.write(json.dumps({"type": "metadata", "profile": PROFILE,
                  "bind": bind, "port": sock.getsockname()[1], "source_ip": source_ip,
                  "started_at_unix": time.time(), "mode": "DIAGNOSTIC TEST",
                  "hardware_verified": False, "official_result": False}) + "\n")
        log.flush()
        if on_ready:
            on_ready(sock.getsockname()[1])
        print("PROFILE", PROFILE, flush=True)
        print("LISTENING UDP", sock.getsockname(), "-- DIAGNOSTIC ONLY", flush=True)
        last_print = 0.0
        try:
            while time.monotonic() - started < seconds:
                try:
                    raw, sender = sock.recvfrom(65535)
                    row = state.consume(raw, sender, time.time())
                    log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    log.flush()
                except socket.timeout:
                    pass
                now = time.monotonic()
                if now - last_print >= 1:
                    status = state.status(time.time())
                    value = status["last_time"] or {}
                    counts = status["counts"]
                    print(time.strftime("%H:%M:%S"), status["state"],
                          "received=" + str(counts.get("datagrams", 0)),
                          "accepted=" + str(counts.get("accepted", 0)),
                          "kind=" + str(value.get("kind", "-")),
                          "channel=" + str(value.get("channel", "-")),
                          "RAW=" + str(value.get("raw_value", "-")), flush=True)
                    last_print = now
        except KeyboardInterrupt:
            print("Stopped by operator", flush=True)
        summary = {"type": "summary", **state.status(time.time()), "output": str(output)}
        log.write(json.dumps(summary) + "\n")
    return summary


def replay(path: Path) -> dict:
    state = DiagnosticState()
    previous = float("-inf")
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "hex" not in row:
                continue
            at = float(row.get("received_at_unix", row.get("timestamp_unix", 0)))
            if at < previous:
                raise ProtocolError("Replay input must be ordered by capture timestamp")
            previous = at
            state.consume(bytes.fromhex(row["hex"]),
                          (row.get("sender_ip", "0.0.0.0"), int(row.get("sender_port", 0))), at)
    return {"mode": "OFFLINE CAPTURE REPLAY", **state.status(previous if previous > 0 else 0)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=26)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--source-ip")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.seconds <= 600:
        parser.error("port must be 1..65535; seconds must be 1..600")
    if args.source_ip:
        try:
            ipaddress.IPv4Address(args.source_ip)
        except ipaddress.AddressValueError:
            parser.error("source-ip must be an IPv4 address")
    try:
        if args.replay:
            result = replay(args.replay)
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output = args.output or Path(__file__).resolve().parent / "captures" / f"udp26-{stamp}-{time.time_ns()}.jsonl"
            result = receive(args.seconds, args.port, args.source_ip, output)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ProtocolError, ValueError) as exc:
        print("DIAGNOSTIC ERROR:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

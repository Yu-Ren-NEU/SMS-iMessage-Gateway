"""Durable local queue and SMS status reports. No network or UI side effects."""
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


def connect(base):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(base / 'delivery.sqlite3'), timeout=10)
    os.chmod(base / 'delivery.sqlite3', 0o600)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA fullfsync=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS incoming (
      signature TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
      last_attempt REAL NOT NULL DEFAULT 0, baseline INTEGER, guid TEXT, error TEXT, last_check REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS outgoing (
      command_id INTEGER PRIMARY KEY, number TEXT NOT NULL, ack_to TEXT NOT NULL,
      created REAL NOT NULL, total INTEGER NOT NULL, capability INTEGER NOT NULL,
      notified TEXT);
    CREATE TABLE IF NOT EXISTS segments (
      command_id INTEGER NOT NULL, part INTEGER NOT NULL, mr INTEGER,
      started REAL NOT NULL, status INTEGER,
      PRIMARY KEY(command_id,part));
    CREATE TABLE IF NOT EXISTS reports (
      digest TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL);
    ''')
    if 'last_check' not in {row[1] for row in db.execute('PRAGMA table_info(incoming)')}:
        db.execute('ALTER TABLE incoming ADD COLUMN last_check REAL NOT NULL DEFAULT 0')
        db.commit()
    return db


def enqueue(db, signature, sender, body, parts, recipient):
    payload = json.dumps({'sender': sender, 'body': body,
                          'parts': [p['digest'] for p in parts],
                          'recipient': recipient}, ensure_ascii=False)
    with db:
        db.execute('INSERT OR IGNORE INTO incoming(signature,payload,created) VALUES(?,?,?)',
                   (signature, payload, time.time()))
    return db.execute('SELECT 1 FROM incoming WHERE signature=?', (signature,)).fetchone() is not None


def stamp(data):
    if len(data) != 7:
        raise ValueError('Invalid SMS timestamp')
    fields = [10 * (b & 15) + (b >> 4) for b in data[:6]]
    zone = data[6]
    quarters = (zone & 7) * 10 + (zone >> 4)
    offset = timedelta(minutes=quarters * 15 * (-1 if zone & 8 else 1))
    return datetime(2000 + fields[0], *fields[1:], tzinfo=timezone(offset)).timestamp()


def decode_report(raw):
    data = bytes.fromhex(raw)
    i = 1 + data[0]
    if i + 4 > len(data) or data[i] & 3 != 2:
        return None
    mr, digits, toa = data[i+1:i+4]
    i += 4
    n = (digits + 1) // 2
    if toa & 0x70 == 0x50 or i + n + 15 > len(data):
        raise ValueError('Unsupported or truncated status report')
    number = ''.join(f'{b & 15:X}{b >> 4:X}' for b in data[i:i+n])[:digits]
    if not number.isdigit():
        raise ValueError('Invalid report recipient')
    if toa & 0x70 == 0x10:
        number = '+' + number
    i += n
    return {'mr': mr, 'number': number, 'submitted': stamp(data[i:i+7]),
            'discharged': stamp(data[i+7:i+14]), 'status': data[i+14],
            'digest': hashlib.sha256(data).hexdigest()}


def record_report(db, report):
    with db:
        db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?)',
                   (report['digest'], json.dumps(report), time.time()))
        # Never match a wrapped reference blindly. Recipient AND timestamp must
        # identify exactly one submitted segment; ambiguous reports stay archived.
        candidates = db.execute('''SELECT s.command_id,s.part,s.status FROM segments s
          JOIN outgoing o ON o.command_id=s.command_id
          WHERE o.number=? AND s.mr=? AND ABS(s.started-?)<=300''',
          (report['number'], report['mr'], report['submitted'])).fetchall()
        if len(candidates) == 1:
            row = candidates[0]
            if row['status'] is None or 32 <= row['status'] < 64:
                db.execute('UPDATE segments SET status=? WHERE command_id=? AND part=?',
                           (report['status'], row['command_id'], row['part']))
    return len(candidates) == 1


def delivery_state(db, command, now=None, timeout=86400):
    parts = db.execute('SELECT mr,status FROM segments WHERE command_id=?',
                       (command['command_id'],)).fetchall()
    if any(p['status'] is not None and 64 <= p['status'] < 128 for p in parts):
        return 'failed'
    if len(parts) == command['total'] and all(p['mr'] is not None and p['status'] == 0 for p in parts):
        return 'delivered'
    if not command['capability']:
        return 'unsupported'
    if (time.time() if now is None else now) - command['created'] >= timeout:
        return 'unconfirmed'
    return 'waiting'

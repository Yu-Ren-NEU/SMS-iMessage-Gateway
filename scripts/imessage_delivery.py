"""Best-effort, read-only Messages delivery observation; queue is authoritative."""
from contextlib import closing
import json
import sqlite3
import subprocess
import time
from pathlib import Path


def open_messages():
    path = Path.home() / 'Library/Messages/chat.db'
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def snapshot():
    with closing(open_messages()) as db:
        return db.execute('SELECT COALESCE(MAX(ROWID),0) FROM message').fetchone()[0]


def observe(item, payload, base):
    with closing(open_messages()) as db:
        columns = {r[1] for r in db.execute('PRAGMA table_info(message)')}
        optional = [x for x in ('date_delivered', 'is_delivered', 'error') if x in columns]
        fields = ','.join('m.' + x for x in ['ROWID', 'guid', 'text', 'attributedBody'] + optional)
        if item['guid']:
            rows = db.execute(f'SELECT {fields} FROM message m WHERE m.guid=?',
                              (item['guid'],)).fetchall()
        else:
            if item['baseline'] is not None:
                boundary = 'm.ROWID>?'
                cutoff = item['baseline']
            elif 'date' in columns:
                boundary = '(CASE WHEN ABS(m.date)>1000000000000 THEN m.date/1000000000.0 ELSE m.date END)>=?'
                cutoff = item['created'] - 978307200 - 5
            else:
                return None, None
            rows = db.execute(f'''SELECT DISTINCT {fields} FROM message m
               LEFT JOIN handle h ON h.ROWID=m.handle_id
               LEFT JOIN chat_message_join cm ON cm.message_id=m.ROWID
               LEFT JOIN chat_handle_join ch ON ch.chat_id=cm.chat_id
               LEFT JOIN handle hh ON hh.ROWID=ch.handle_id
               WHERE {boundary} AND m.is_from_me=1 AND m.service='iMessage'
               AND (h.id=? OR hh.id=?) ORDER BY m.ROWID LIMIT 1000''',
               (cutoff, payload['recipient'], payload['recipient'])).fetchall()
        if len(rows) >= 1000:
            return 'ambiguous', None
        expected = f"SIM7600 received SMS\nFrom: {payload['sender']}\nBody: {payload['body']}"
        matches = []
        for row in rows:
            text = row['text']
            if not text and row['attributedBody']:
                result = subprocess.run([str(Path(base)/'decode_attributed')],
                    input=row['attributedBody'], capture_output=True, timeout=5)
                if result.returncode == 0:
                    text = result.stdout.decode('utf-8', errors='replace')
            if text == expected:
                matches.append(row)
        if len(matches) != 1:
            return ('ambiguous' if len(matches) > 1 else 'not_found'), None
        row = matches[0]
        if 'error' in optional and row['error']:
            return 'failed', row['guid']
        if ('date_delivered' in optional and (row['date_delivered'] or 0) > 0) or (
                'is_delivered' in optional and row['is_delivered'] == 1):
            return 'delivered', row['guid']
        return 'submitted', row['guid']


def process_queue(db, base, send, logger, observer=observe, now=None):
    now = time.time() if now is None else now
    for item in db.execute("SELECT * FROM incoming WHERE status NOT IN ('submitted','delivered') ORDER BY created,rowid LIMIT 50").fetchall():
        with db:
            db.execute('UPDATE incoming SET last_check=? WHERE signature=?', (now, item['signature']))
        payload = json.loads(item['payload'])
        current_status = item['status']
        status = None
        if item['status'] != 'queued':
            try:
                status, guid = observer(item, payload, base)
                if status and status != 'not_found':
                    current_status = status
                    with db:
                        db.execute('UPDATE incoming SET status=?,guid=? WHERE signature=?',
                                   (status, guid, item['signature']))
                    if status != 'failed':
                        continue
            except (sqlite3.Error, OSError, subprocess.SubprocessError) as error:
                logger(f"iMessage delivery observation unavailable: {type(error).__name__}")
                # Accepted/uncertain submissions must not be blindly repeated
                # when privacy permissions prevent checking for duplicates.
                if item['status'] != 'failed':
                    continue
            if current_status in ('submitted', 'ambiguous'):
                continue
            if current_status == 'sending' and ((item['baseline'] is None and status != 'not_found') or now - item['last_attempt'] < 120):
                continue
        delay = min(3600, 60 * (2 ** min(item['attempts'], 6)))
        if item['last_attempt'] and now - item['last_attempt'] < delay:
            continue
        if item['attempts'] >= 8:
            continue  # Persisted for manual recovery; no infinite duplicate storm.
        try:
            baseline = snapshot()
        except (sqlite3.Error, OSError):
            baseline = None
        with db:
            db.execute("UPDATE incoming SET status='sending',attempts=attempts+1,last_attempt=?,baseline=?,guid=NULL WHERE signature=?",
                       (now, baseline, item['signature']))
        message = f"SIM7600 received SMS\nFrom: {payload['sender']}\nBody: {payload['body']}"
        started = time.monotonic()
        try:
            send(message, payload['recipient'])
            with db:
                db.execute("UPDATE incoming SET status='submitted',error=NULL WHERE signature=?", (item['signature'],))
            logger(f"Queued iMessage submitted ({item['signature'][:10]}); forwarding complete; queue_age={max(0, now-item['created']):.2f}s; submit_duration={time.monotonic()-started:.2f}s")
        except Exception as error:
            with db:
                db.execute('UPDATE incoming SET error=? WHERE signature=?',
                           (type(error).__name__, item['signature']))
            logger(f"Queued iMessage submission uncertain ({item['signature'][:10]}); saved for reconciliation")

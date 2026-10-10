#!/usr/bin/env python3
"""Forward newly received SIM7600 SMS to an iMessage address on this Mac."""

import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
import re
import select
import subprocess
import sys
import termios
import time
from pathlib import Path
from delivery_store import connect as delivery_db, enqueue, decode_report, record_report
from imessage_delivery import process_queue


BASE = Path(os.environ.get("SIM7600_BRIDGE_HOME", str(Path.home() / "Library/Application Support/SIM7600Bridge")))
CONFIG = BASE / "bridge_config.json"
_settings = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
PORT = _settings.get("serial_port", "/dev/cu.usbserial-0001")
DESTINATION = _settings.get("forward_to", "")
STATE = BASE / "sms_imessage_state.json"
LOG = BASE / "sms_imessage_bridge.log"
RESTART_MARKER = BASE / "messages_last_restart"


class IMessageSendError(RuntimeError):
    pass


def log(message):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


class Modem:
    def __enter__(self):
        BASE.mkdir(parents=True, exist_ok=True)
        self.lock = (BASE / "serial.lock").open("a+")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            self.fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except Exception:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()
            raise
        settings = termios.tcgetattr(self.fd)
        settings[0] = settings[1] = settings[3] = 0
        settings[2] = (settings[2] & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB)) | termios.CS8 | termios.CLOCAL | termios.CREAD
        settings[4] = settings[5] = termios.B115200
        settings[6][termios.VMIN] = settings[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, settings)
        self.read(0.3)
        return self

    def __exit__(self, *_):
        try:
            os.close(self.fd)
        finally:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()

    def read(self, timeout):
        deadline = time.monotonic() + timeout
        data = b""
        while time.monotonic() < deadline:
            if select.select([self.fd], [], [], 0.2)[0]:
                try:
                    data += os.read(self.fd, 4096)
                except BlockingIOError:
                    pass
                if b"\r\nOK\r\n" in data or b"\r\nERROR\r\n" in data:
                    break
        return data.decode("ascii", errors="replace")

    def command(self, command, timeout=3):
        os.write(self.fd, (command + "\r").encode("ascii"))
        answer = self.read(timeout)
        if "\r\nOK\r\n" not in answer:
            raise RuntimeError(f"{command}: {answer.strip()}")
        return answer


GSM = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
GSM_EXT = {10: "\f", 20: "^", 40: "{", 41: "}", 47: "\\", 60: "[", 61: "~", 62: "]", 64: "|", 101: "€"}


def septets(data, count, skip_bits=0):
    value = int.from_bytes(data, "little") >> skip_bits
    codes = [(value >> (7 * i)) & 127 for i in range(count)]
    output = ""
    escape = False
    for code in codes:
        if escape:
            output += GSM_EXT.get(code, "?")
            escape = False
        elif code == 27:
            escape = True
        else:
            output += GSM[code] if code < len(GSM) else "?"
    return output


def phone(data, digits, international=False):
    value = "".join(f"{byte & 15:X}{byte >> 4:X}" for byte in data)[:digits]
    return ("+" if international else "") + value.rstrip("F")


def decode_pdu(raw):
    data = bytes.fromhex(raw)
    smsc_len = data[0]
    i = 1 + smsc_len
    flags = data[i]
    i += 1
    if flags & 3 != 0:  # Only SMS-DELIVER; never forward sent messages.
        return None
    address_len = data[i]
    toa = data[i + 1]
    i += 2
    address_bytes = (address_len + 1) // 2 if toa & 0x70 != 0x50 else (address_len * 7 + 7) // 8
    address_data = data[i:i + address_bytes]
    sender = septets(address_data, address_len) if toa & 0x70 == 0x50 else phone(address_data, address_len, toa & 0x90 == 0x90)
    i += address_bytes
    _pid, dcs = data[i:i + 2]
    i += 2
    timestamp = data[i:i + 7].hex().upper()
    i += 7
    udl = data[i]
    i += 1
    user_data = data[i:]
    header_bytes = user_data[0] + 1 if flags & 0x40 else 0
    ref = part = total = None
    if header_bytes:
        j = 1
        while j + 2 <= header_bytes:
            iei, length = user_data[j:j + 2]
            value = user_data[j + 2:j + 2 + length]
            if iei == 0 and length == 3:
                ref, total, part = value
            elif iei == 8 and length == 4:
                ref = int.from_bytes(value[:2], "big")
                total, part = value[2:]
            j += 2 + length
    if dcs & 0x0C == 0x08:
        content = user_data[header_bytes:udl].decode("utf-16-be", errors="replace")
    elif dcs & 0x0C == 0x00:
        skipped = (header_bytes * 8 + 6) // 7 if header_bytes else 0
        content = septets(user_data, udl - skipped, skipped * 7)
    else:
        content = user_data[header_bytes:udl].decode("latin-1", errors="replace")
    return {"sender": sender, "timestamp": timestamp, "content": content, "ref": ref, "part": part, "total": total}


def inbox(modem):
    answer = modem.command("AT+CMGL=4", 8)
    messages = []
    for index, status, raw in re.findall(r'\+CMGL: (\d+),(\d+),"",\d+\r\n([0-9A-Fa-f]+)', answer):
        if int(status) not in (0, 1):
            continue
        decoded = decode_pdu(raw)
        if decoded:
            decoded.update(index=int(index), digest=hashlib.sha256(bytes.fromhex(raw)).hexdigest())
            messages.append(decoded)
    return messages


def groups(messages):
    def received_at(sms):
        # The SMSC timestamp uses swapped decimal nibbles in each byte.
        stamp = sms["timestamp"]
        try:
            digits = "".join(stamp[i + 1] + stamp[i] for i in range(0, 12, 2))
            return datetime.strptime(digits, "%y%m%d%H%M%S")
        except (IndexError, ValueError):
            return None

    # Fragments of one SMS can have different SMSC timestamps. Keep the
    # multipart reference, but limit matching to a one-hour arrival window
    # so a reused reference cannot silently combine old and new messages.
    grouped = {}
    for sms in messages:
        key = ((sms["sender"], sms["ref"], sms["total"])
               if sms["ref"] is not None else (sms["digest"],))
        grouped.setdefault(key, []).append(sms)
    batches = []
    for key, candidates in grouped.items():
        if len(key) == 1:
            batches.append(candidates)
            continue
        pending = []
        for sms in sorted(candidates, key=lambda item: received_at(item) or datetime.min):
            when = received_at(sms)
            match = next((batch for batch in reversed(pending)
                          if when is not None and batch["start"] is not None
                          and 0 <= (when - batch["start"]).total_seconds() <= 3600
                          and all(part["part"] != sms["part"] for part in batch["parts"])), None)
            if match is None:
                match = {"start": when, "parts": []}
                pending.append(match)
            match["parts"].append(sms)
        batches.extend(batch["parts"] for batch in pending)
    for parts in batches:
        total = parts[0]["total"] or 1
        if total > 1 and set(p["part"] for p in parts) != set(range(1, total + 1)):
            continue
        ordered = sorted(parts, key=lambda p: p["part"] or 1)
        signature = hashlib.sha256("|".join(p["digest"] for p in ordered).encode()).hexdigest()
        yield signature, ordered, "".join(p["content"] for p in ordered)


def recover_messages_app():
    try:
        last_restart = float(RESTART_MARKER.read_text())
    except (OSError, ValueError):
        last_restart = 0
    if time.time() - last_restart < 30:
        return False
    RESTART_MARKER.write_text(str(time.time()))
    subprocess.run(["pkill", "-TERM", "-x", "Messages"], check=False, capture_output=True, timeout=5)
    for _ in range(15):
        if subprocess.run(["pgrep", "-x", "Messages"], capture_output=True, timeout=2).returncode != 0:
            break
        time.sleep(0.2)
    subprocess.run(["open", "-a", "Messages"], check=True, capture_output=True, timeout=10)
    for _ in range(4):
        time.sleep(1)
        try:
            result = subprocess.run(["osascript", "-e", 'tell application "Messages" to get count of services'],
                                    check=True, capture_output=True, text=True, timeout=5)
            if result.stdout.strip().isdigit():
                log("Restarted unresponsive Messages app; service is responsive")
                return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    raise RuntimeError("Messages is still unresponsive after restart")


def send_imessage(message, recipient=DESTINATION):
    script = '''on run argv
tell application "Messages"
set theService to first service whose service type is iMessage
set theRecipient to buddy (item 1 of argv) of theService
send (item 2 of argv) to theRecipient
end tell
end run'''
    try:
        subprocess.run(["osascript", "-e", script, recipient, message], check=True, timeout=30, capture_output=True, text=True)
    except subprocess.TimeoutExpired as error:
        try:
            restarted = recover_messages_app()
        except Exception as recovery_error:
            log(f"Messages restart failed: {recovery_error}")
            raise IMessageSendError("Messages timed out and recovery failed") from error
        if restarted:
            raise IMessageSendError("Messages timed out; restarted and awaiting reconciliation") from error
        raise IMessageSendError("Messages timed out; awaiting restart cooldown") from error
    except subprocess.CalledProcessError as error:
        raise IMessageSendError(f"Messages submission failed (exit code {error.returncode})") from error


def modem_health(modem):
    sim = modem.command("AT+CPIN?")
    if "+CPIN: READY" not in sim:
        return "SIM is not ready"
    registration = modem.command("AT+CEREG?")
    match = re.search(r"\+CEREG:\s*\d+,\s*(\d+)", registration)
    if not match or match.group(1) not in ("1", "5"):
        return "Cellular network is not registered"
    signal = modem.command("AT+CSQ")
    match = re.search(r"\+CSQ:\s*(\d+)", signal)
    if not match or int(match.group(1)) == 99:
        return "Cellular signal is unavailable"
    storage = modem.command("AT+CPMS?")
    match = re.search(r'\+CPMS:\s*"[^"]+",(\d+),(\d+)', storage)
    if match and int(match.group(2)) and int(match.group(1)) >= int(match.group(2)) - 2:
        return f"SIM SMS storage is almost full ({match.group(1)}/{match.group(2)})"
    return None


def update_health(state, issue):
    health = state.setdefault("health", {"issue": None, "failures": 0, "last_alert": 0})
    previous = health["issue"]
    if issue:
        health["failures"] = health["failures"] + 1 if issue == health.get("candidate") else 1
        health["candidate"] = issue
        if health["failures"] < 3:
            save(state)
            return
        if previous != issue or time.time() - health["last_alert"] >= 3600:
            health["last_alert"] = time.time()
            try:
                send_imessage(f"SIM7600 health alert: {issue}. Monitoring will continue.")
            except Exception as error:
                log(f"Could not send health alert: {error}")
        health["issue"] = issue
    else:
        health["candidate"] = None
        health["failures"] = 0
        if previous:
            try:
                send_imessage("SIM7600 recovered; SMS forwarding remains active.")
            except Exception as error:
                log(f"Could not send recovery alert: {error}")
        health["issue"] = None
    save(state)


def save(state):
    temporary = STATE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, STATE)


def cleanup_persisted(modem, queue, messages):
    persisted = {digest for row in queue.execute('SELECT payload FROM incoming')
                 for digest in json.loads(row['payload'])['parts']}
    for part in messages:
        if part['digest'] in persisted:
            modem.command(f'AT+CMGD={part["index"]}')


def collect_reports(modem, db):
    """Archive reports before deleting, preserving unmatchable reports locally."""
    try:
        modem.command('AT+CPMS="SR"')
        answer = modem.command('AT+CMGL=4', 8)
        for index, raw in re.findall(r'\+CMGL:\s*(\d+),[^\r\n]*\r\n([0-9A-Fa-f]+)', answer):
            try:
                report = decode_report(raw)
                if report is not None:
                    record_report(db, report)
                    modem.command(f'AT+CMGD={int(index)}')
            except (ValueError, IndexError) as error:
                log(f"Invalid status report retained: {type(error).__name__}")
    finally:
        modem.command('AT+CPMS="SM","SM","SM"')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delivery-status", action="store_true", help="Show queue counts without message contents")
    args = parser.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    if not DESTINATION:
        raise SystemExit("Set forward_to in bridge_config.json before starting")
    if args.delivery_status:
        db = delivery_db(BASE)
        print('Incoming queue:', dict(db.execute('SELECT status,COUNT(*) FROM incoming GROUP BY status')))
        print('Outgoing tracked:', db.execute('SELECT COUNT(*) FROM outgoing').fetchone()[0])
        print('Archived reports:', db.execute('SELECT COUNT(*) FROM reports').fetchone()[0])
        return
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"seen": [], "archive": []}
    first_run = not STATE.exists()
    seen = set(state["seen"])
    next_health_check = 0
    next_report_check = 0
    queue = delivery_db(BASE)
    while True:
        try:
            with Modem() as modem:
                modem.command("AT")
                modem.command("AT+CMGF=0")
                modem.command('AT+CPMS="SM","SM","SM"')
                if not args.dry_run and time.monotonic() >= next_report_check:
                    try:
                        modem.command('AT+CNMI=2,1,0,2,0')
                        collect_reports(modem, queue)
                        next_report_check = time.monotonic() + 30
                    except RuntimeError as error:
                        log(f"Stored SMS reports unavailable: {error}")
                        next_report_check = time.monotonic() + 1800
                if time.monotonic() >= next_health_check:
                    update_health(state, modem_health(modem))
                    next_health_check = time.monotonic() + 60
                current_messages = inbox(modem)
                found = list(groups(current_messages))
                if first_run:
                    seen.update(signature for signature, _, _ in found)
                    state["seen"] = sorted(seen)
                    save(state)
                    log(f"Initial scan: {len(found)} existing message(s) recorded; waiting for new SMS")
                    first_run = False
                else:
                    for signature, parts, body in found:
                        queued = queue.execute('SELECT 1 FROM incoming WHERE signature=?', (signature,)).fetchone()
                        if signature in seen and not queued:
                            continue  # Preserve historical first-scan semantics.
                        sender = parts[0]["sender"]
                        if args.dry_run:
                            log(f"DRY RUN from {sender}: {body!r}")
                            continue
                        # FULL-synchronous SQLite commit MUST precede SIM deletion.
                        enqueue(queue, signature, sender, body, parts, DESTINATION)
                        if signature not in seen:
                            seen.add(signature)
                            state["seen"] = sorted(seen)
                            state["archive"].append({"sender": sender, "body": body,
                                "parts": [p["digest"] for p in parts], "queued_at": time.strftime("%Y-%m-%d %H:%M:%S")})
                            save(state)
                    if not args.dry_run:
                        # A previous pass may have deleted only some multipart
                        # segments. Cleanup uses durable digests, not regrouping.
                        cleanup_persisted(modem, queue, current_messages)
            if not args.dry_run:
                process_queue(queue, BASE, send_imessage, log)
            if args.once:
                break
        except Exception as error:
            log(f"ERROR: {error}")
            issue = "iMessage forwarding failed" if isinstance(error, IMessageSendError) else "Serial or modem communication failed"
            update_health(state, issue)
            if not args.dry_run:
                process_queue(queue, BASE, send_imessage, log)
            if args.once:
                raise
        time.sleep(5)


if __name__ == "__main__":
    main()

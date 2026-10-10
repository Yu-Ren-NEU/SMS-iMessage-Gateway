#!/usr/bin/env python3
"""Accept explicit iMessage commands and send SMS through the SIM7600 modem.

This process must be given macOS Full Disk Access to read ~/Library/Messages/chat.db.
It refuses to start until an allowed iMessage sender is configured.
"""

import argparse
import json
import plistlib
import random
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from sms_imessage_bridge import BASE, Modem, send_imessage


CONFIG = BASE / "sender_config.json"
STATE = BASE / "sender_state.json"
DB = Path.home() / "Library/Messages/chat.db"
DECODER = BASE / "decode_attributed"
COMMAND = re.compile(r"^#短信\s+(\+[1-9]\d{5,14})\s+([\s\S]{1,1000})$")


def parse_command(text):
    match = COMMAND.fullmatch(text.strip())
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def body_text(text, attributed_body):
    if text:
        return text
    if not attributed_body:
        return ""
    result = subprocess.run([str(DECODER)], input=attributed_body, capture_output=True, timeout=5)
    if result.returncode:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def semi_octets(number):
    digits = number[1:]
    padded = digits + ("F" if len(digits) % 2 else "")
    return "".join(padded[i + 1] + padded[i] for i in range(0, len(padded), 2))


def chunks(text, maximum_bytes):
    items = []
    current = ""
    for char in text:
        candidate = current + char
        if len(candidate.encode("utf-16-be")) > maximum_bytes:
            if not current:
                raise ValueError("A character is too large for an SMS part")
            items.append(current)
            current = char
        else:
            current = candidate
    if current:
        items.append(current)
    return items


def pdus(number, body):
    if not re.fullmatch(r"\+[1-9]\d{5,14}", number):
        raise ValueError("Phone number must be in international +country format")
    if not body or len(body) > 1000:
        raise ValueError("Message must be 1–1000 characters")
    parts = chunks(body, 140)
    if len(parts) > 1:
        parts = chunks(body, 134)
    if len(parts) > 255:
        raise ValueError("Too many SMS parts")
    reference = random.randrange(256)
    result = []
    for position, part in enumerate(parts, 1):
        udh = bytes([5, 0, 3, reference, len(parts), position]) if len(parts) > 1 else b""
        content = udh + part.encode("utf-16-be")
        tpdu = bytes([0x51 if udh else 0x11, 0, len(number) - 1, 0x91])
        tpdu += bytes.fromhex(semi_octets(number))
        tpdu += bytes([0, 8, 0xAA, len(content)]) + content
        result.append((len(tpdu), "00" + tpdu.hex().upper()))
    return result


def send_sms(number, body):
    receipts = []
    with Modem() as modem:
        modem.command("AT")
        modem.command("AT+CMGF=0")
        for length, pdu in pdus(number, body):
            import os

            os.write(modem.fd, f"AT+CMGS={length}\r".encode())
            prompt = modem.read(5)
            if ">" not in prompt:
                raise RuntimeError(f"No SMS prompt: {prompt.strip()}")
            os.write(modem.fd, pdu.encode() + b"\x1a")
            answer = modem.read(45)
            match = re.search(r"\+CMGS:\s*(\d+)", answer)
            if not match or "\r\nOK\r\n" not in answer:
                raise RuntimeError(f"SMS send status uncertain: {answer.strip()}")
            receipts.append(match.group(1))
    return receipts


def message_db():
    # Opening the Messages database requires explicit macOS privacy permission.
    uri = f"file:{DB}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=3)
    connection.execute("PRAGMA query_only=ON")
    return connection


def ensure_messages_running():
    running = subprocess.run(["pgrep", "-x", "Messages"], capture_output=True, timeout=3)
    if running.returncode == 0:
        return
    subprocess.run(["open", "-a", "Messages"], check=True, capture_output=True, timeout=10)
    print("Messages was closed; reopened it for iMessage commands", flush=True)


def save(state):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def deliver_pending_acks(state):
    for result in state["results"]:
        if result.get("ack_sent") or not result.get("ack_to"):
            continue
        if time.time() - result.get("last_ack_attempt", 0) < 60:
            continue
        result["last_ack_attempt"] = time.time()
        save(state)
        try:
            send_imessage(result["ack_text"], result["ack_to"])
            result["ack_sent"] = True
            save(state)
        except Exception as error:
            print(f"Could not send status for command {result['id']}: {error}", file=sys.stderr, flush=True)


def failure_reason(error):
    description = str(error)
    cms = re.search(r"\+CMS ERROR:\s*\d+", description)
    if cms:
        return cms.group(0)
    if "No SMS prompt" in description:
        return "模块未进入发送状态"
    if isinstance(error, (OSError, TimeoutError)):
        return "串口或模块无响应"
    return "模块未返回明确结果"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-access", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    try:
        database = message_db()
        database.execute("SELECT COUNT(*) FROM message").fetchone()
    except sqlite3.Error as error:
        print(f"Messages database access denied: {error}", file=sys.stderr)
        return 2
    if args.check_access:
        print("Messages database is readable")
        return 0
    if args.inspect:
        columns = [row[1] for row in database.execute("PRAGMA table_info(message)")]
        print("message columns:", ", ".join(columns))
        rows = database.execute("""SELECT m.ROWID, m.is_from_me, h.id, m.service,
          CASE WHEN m.text LIKE '#短信 %' THEN 1 ELSE 0 END, m.text,
          length(m.attributedBody), m.attributedBody
          FROM message m LEFT JOIN handle h ON h.ROWID=m.handle_id
          ORDER BY m.ROWID DESC LIMIT 3""").fetchall()
        for row in rows:
            print("recent message:", row[:-1], "decoded:", repr(body_text(row[5], row[7])))
        blob = database.execute("SELECT attributedBody FROM message ORDER BY ROWID DESC LIMIT 1").fetchone()[0]
        print("attributedBody prefix:", blob[:40].hex() if blob else None)
        if blob:
            marker = blob.find(b"#")
            print("command bytes at:", marker, "prefix:", blob[max(0,marker-24):marker].hex(), "snippet:", repr(blob[marker:marker + 130]))
        try:
            decoded = plistlib.loads(blob)
            print("attributedBody plist:", repr(decoded)[:1000])
        except Exception as error:
            print("attributedBody decode error:", error)
        print("decoded text:", repr(body_text(None, blob)))
        return 0
    if not CONFIG.exists():
        print("Sender allowlist is not configured; refusing to run", file=sys.stderr)
        return 2
    allowed = set(json.loads(CONFIG.read_text())["allowed_senders"])
    if not allowed:
        print("Sender allowlist is empty; refusing to run", file=sys.stderr)
        return 2
    state = json.loads(STATE.read_text()) if STATE.exists() else {"last_id": database.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0], "results": []}
    save(state)
    next_app_check = 0
    while True:
        if time.monotonic() >= next_app_check:
            try:
                ensure_messages_running()
            except (OSError, subprocess.SubprocessError) as error:
                print(f"Could not reopen Messages: {error}", file=sys.stderr, flush=True)
            next_app_check = time.monotonic() + 30
        deliver_pending_acks(state)
        rows = database.execute("""SELECT m.ROWID, m.text, m.attributedBody, m.is_from_me, h.id, m.service
          FROM message m LEFT JOIN handle h ON h.ROWID=m.handle_id
          WHERE m.ROWID>? ORDER BY m.ROWID""", (state["last_id"],)).fetchall()
        for rowid, text, attributed_body, from_me, sender, service in rows:
            state["last_id"] = rowid
            save(state)  # Record before sending: never resend after an uncertain modem result.
            if service != "iMessage" or sender not in allowed:
                continue
            content = body_text(text, attributed_body)
            command = parse_command(content)
            if command is None:
                if content.strip().startswith("#短信"):
                    outcome = {"id": rowid, "status": "invalid", "ack_to": sender,
                               "ack_text": "SIM7600：指令格式不对，请用 #短信 +国家区号手机号 正文", "ack_sent": False}
                    state["results"].append(outcome)
                    save(state)
                    deliver_pending_acks(state)
                continue
            number, body = command
            try:
                receipts = send_sms(number, body)
                outcome = {"id": rowid, "number": number, "status": "sent", "receipts": receipts}
                acknowledgement = f"SIM7600：已提交短信至 {number}（模块回执 {', '.join(receipts)}；不代表对方已收到）。"
            except Exception as error:
                outcome = {"id": rowid, "number": number, "status": "error", "error": str(error)}
                acknowledgement = f"SIM7600：发往 {number} 的短信未能确认提交（{failure_reason(error)}）。为避免重复，不会自动重发。"
            outcome.update(ack_to=sender, ack_text=acknowledgement, ack_sent=False)
            state["results"].append(outcome)
            save(state)
            print(outcome, flush=True)
            deliver_pending_acks(state)
        time.sleep(3)


if __name__ == "__main__":
    raise SystemExit(main())

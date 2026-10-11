#!/usr/bin/env python3
"""Preserve the original installation and its existing two LaunchAgent labels."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parent
BASE = Path.home() / 'Library/Application Support/SIM7600Bridge'
AGENTS = Path.home() / 'Library/LaunchAgents'
LABELS = ['com.yren.sim7600-sms-imessage', 'com.yren.sim7600-imessage-sms']
FILES = ['sms_imessage_bridge.py', 'imessage_sms_sender.py', 'delivery_store.py', 'imessage_delivery.py']


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Run this on the original Mac installation.')
    plists = [AGENTS / (label + '.plist') for label in LABELS]
    if not all(p.exists() for p in plists) or not (BASE/'decode_attributed').exists():
        raise SystemExit('Original installation not found; use install.py for a new installation.')
    legacy = {}
    for node in ast.parse((BASE / 'sms_imessage_bridge.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('PORT', 'DESTINATION'):
                    legacy[target.id] = node.value.value
    configuration = BASE / 'bridge_config.json'
    if not configuration.exists() and not legacy.get('DESTINATION'):
        raise SystemExit('Cannot safely infer forwarding destination; no files changed.')
    domain = 'gui/' + str(os.getuid())
    backup = BASE / ('backup-delivery-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir()
    stopped = []
    installed = []
    config_created = False
    try:
        for plist in plists:
            result = subprocess.run(['launchctl', 'bootout', domain, str(plist)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError('Could not stop an existing service; aborting upgrade.')
            stopped.append(plist)
        for source in BASE.iterdir():
            if source.is_file() and (source.suffix in ('.py', '.json', '.sqlite3') or source.name.endswith(('-wal', '-shm'))):
                shutil.copy2(source, backup / source.name)
        if not configuration.exists():
            configuration.write_text(json.dumps({'serial_port':legacy.get('PORT','/dev/cu.usbserial-0001'),
                                                 'forward_to':legacy['DESTINATION']}, indent=2))
            os.chmod(configuration, 0o600)
            config_created = True
        for name in FILES:
            temporary = BASE / (name + '.upgrade')
            shutil.copy2(SOURCE/name, temporary)
            temporary.replace(BASE/name)
            installed.append(name)
        # Terminal's TCC responsibility differs from the existing LaunchAgents.
        # Validate Python syntax here; database access is checked by the actual
        # background sender using its original interpreter and permissions.
        for name in FILES:
            compile((BASE/name).read_text(), str(BASE/name), 'exec')
    except Exception:
        for name in installed:
            if (backup/name).exists():
                shutil.copy2(backup/name, BASE/name)
            else:
                (BASE/name).unlink(missing_ok=True)
        if config_created:
            configuration.unlink(missing_ok=True)
        raise
    finally:
        for plist in stopped:
            subprocess.run(['launchctl','bootstrap',domain,str(plist)], check=True)
    print('Upgraded both existing services. Configuration and state retained.')
    print('Database permission is checked by the background sender; Terminal need not read Messages.')
    print('Backup:', backup)
    print('Send a new SMS command and check the submission success notice; then test inbound forwarding.')


if __name__ == '__main__':
    main()

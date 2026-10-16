#!/usr/bin/env python3
"""Independent forwarding queue/LaunchAgent monitor; never resends SMS itself."""
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

BASE = Path(os.environ.get('SIM7600_BRIDGE_HOME', str(Path.home()/'Library/Application Support/SIM7600Bridge')))
STATE = BASE/'watchdog_state.json'
THRESHOLD = 180
COOLDOWN = 1800
MAX_DAILY_RESTARTS = 3


def save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state))
    os.chmod(temp, 0o600)
    temp.replace(STATE)


def decide(state, records, running, heartbeat, now):
    """Pure policy. Return updated state and actions for deterministic testing."""
    state = json.loads(json.dumps(state))
    actions = []
    pending = [r for r in records if r['status'] not in ('submitted','delivered')]
    old = [r for r in pending if now-r['created'] >= THRESHOLD]
    stale = heartbeat is not None and now-heartbeat >= THRESHOLD
    unhealthy = not all(running.values()) or stale or bool(old)
    episode = state.get('episode')
    if unhealthy and episode is None:
        episode = {'started':now, 'tracked':[], 'alerted':False, 'restarts':0}
        state['episode'] = episode
    if episode is not None:
        episode['tracked'] = sorted(set(episode['tracked']) | {r['signature'] for r in pending})
        if unhealthy and not episode['alerted']:
            actions.append(('alert', len(pending), 0))
        lookup = {r['signature']:r['status'] for r in records}
        recovered = not unhealthy and all(lookup.get(k) in ('submitted','delivered') for k in episode['tracked'])
        if recovered:
            actions.append(('recovered', len(episode['tracked']), max(0,int(now-episode['started']))))
        else:
            # Submitted messages are complete; only unresolved work can block.
            blocked = any(r['status'] not in ('submitted','delivered') for r in old)
            targets = [label for label, alive in running.items() if not alive]
            receiver = state['receiver']
            if (stale or blocked) and receiver not in targets:
                targets.append(receiver)
            history = [t for t in state.get('restart_history',[]) if now-t < 86400]
            state['restart_history'] = history
            if targets and len(history)<MAX_DAILY_RESTARTS and (not history or now-history[-1]>=COOLDOWN):
                # Persist reservation before executing; failed starts are limited too.
                state['restart_history'].append(now)
                episode['restarts'] += 1
                actions.extend(('restart', label, 0) for label in targets)
    return state, actions


def service_running(label):
    r = subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{label}'], capture_output=True,text=True,timeout=10)
    return r.returncode == 0 and re.search(r'^\s*state = running\s*$',r.stdout,re.M) is not None


def restart(label):
    target=f'gui/{os.getuid()}/{label}'
    r=subprocess.run(['launchctl','kickstart','-k',target],capture_output=True,timeout=15)
    if r.returncode:
        plist=Path.home()/'Library/LaunchAgents'/(label+'.plist')
        subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True,capture_output=True,timeout=15)


def notify(kind, count, duration, zh):
    from sms_imessage_bridge import send_imessage
    if zh:
        text = (f'SIM7600：短信转发异常，当前 {count} 条待确认；已启动自动检查与恢复（自动重启最多每 30 分钟一次、每天 3 次）。' if kind=='alert' else
                f'SIM7600：短信转发已恢复。本次监测异常持续约 {max(1,duration//60)} 分钟，积压 {count} 条已全部完成 iMessage 提交。')
    else:
        text = (f'SIM7600: Forwarding needs attention; {count} message(s) pending. Automatic recovery is active (at most once per 30 minutes, three times per 24 hours).' if kind=='alert' else
                f'SIM7600: Forwarding recovered after about {max(1,duration//60)} minute(s). All {count} tracked message(s) have been submitted to iMessage.')
    send_imessage(text)


def tick():
    config=json.loads((BASE/'watchdog_config.json').read_text())
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    state['receiver']=config['receiver']
    running={label:service_running(label) for label in (config['receiver'],config['sender'])}
    with sqlite3.connect('file:'+str(BASE/'delivery.sqlite3')+'?mode=ro',uri=True,timeout=5) as db:
        db.row_factory=sqlite3.Row
        records=[dict(r) for r in db.execute('SELECT signature,status,created FROM incoming')]
    hb=BASE/'receive_heartbeat'
    heartbeat=hb.stat().st_mtime if hb.exists() else None
    # Allow startup grace when no heartbeat has been written yet.
    if heartbeat is None:
        state.setdefault('first_check',time.time())
        heartbeat=state['first_check']
    state, actions=decide(state,records,running,heartbeat,time.time())
    save(state)
    for kind,value,duration in actions:
        try:
            if kind=='restart':
                restart(value)
                print('Watchdog restarted '+value,flush=True)
            else:
                notify(kind,value,duration,config.get('language')=='zh')
                if kind=='alert':
                    state['episode']['alerted']=True
                else:
                    state['last_recovery']={'at':time.time(),'messages':value,'duration':duration}
                    state['episode']=None
                save(state)
        except Exception as error:
            print(f'Watchdog {kind} deferred: {type(error).__name__}',flush=True)


def main():
    import fcntl
    BASE.mkdir(parents=True,exist_ok=True)
    with (BASE/'watchdog.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try: tick()
            except Exception as error:
                print(f'Watchdog check failed: {type(error).__name__}',flush=True)
            time.sleep(30)


if __name__=='__main__':main()

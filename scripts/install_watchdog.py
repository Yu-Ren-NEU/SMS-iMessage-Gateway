#!/usr/bin/env python3
"""Register the independent watchdog using the existing receiver interpreter."""
import json,os,plistlib,shutil,subprocess
from pathlib import Path


def install(base=None, language=None):
    base=base or Path.home()/'Library/Application Support/SIM7600Bridge'
    agents=Path.home()/'Library/LaunchAgents'
    old=agents/'com.yren.sim7600-sms-imessage.plist'
    receiver='com.yren.sim7600-sms-imessage' if old.exists() else 'com.sim7600bridge.receive'
    sender='com.yren.sim7600-imessage-sms' if old.exists() else 'com.sim7600bridge.send'
    p=plistlib.loads((agents/(receiver+'.plist')).read_bytes())
    shutil.copy2(Path(__file__).with_name('forwarding_watchdog.py'),base/'forwarding_watchdog.py')
    cfg=base/'watchdog_config.json'
    data=json.loads(cfg.read_text()) if cfg.exists() else {}
    data.update(receiver=receiver,sender=sender)
    if language:data['language']=language
    cfg.write_text(json.dumps(data));os.chmod(cfg,0o600)
    label='com.sim7600bridge.watchdog'
    dest=agents/(label+'.plist')
    dest.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':[p['ProgramArguments'][0],str(base/'forwarding_watchdog.py')],
        'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'WorkingDirectory':str(base),
        'StandardOutPath':str(base/'watchdog.out.log'),'StandardErrorPath':str(base/'watchdog.err.log')}))
    domain='gui/'+str(os.getuid())
    subprocess.run(['launchctl','bootout',domain,str(dest)],capture_output=True)
    subprocess.run(['launchctl','bootstrap',domain,str(dest)],check=True)
    print('Forwarding watchdog installed and started.')


if __name__=='__main__':install()

#!/usr/bin/env python3
"""Install per-user scripts and LaunchAgents. Run only on the target Mac."""
import argparse,json,plistlib,shutil,subprocess,sys
from pathlib import Path
SOURCE=Path(__file__).resolve().parent
HOME=Path.home()
BASE=HOME/'Library/Application Support/SIM7600Bridge'
AGENTS=HOME/'Library/LaunchAgents'
JOBS={'receive':'sms_imessage_bridge.py','send':'imessage_sms_sender.py'}
p=argparse.ArgumentParser();p.add_argument('--start',action='store_true');args=p.parse_args()
if sys.platform!='darwin':raise SystemExit('This bridge requires macOS.')
BASE.mkdir(parents=True,exist_ok=True);AGENTS.mkdir(parents=True,exist_ok=True)
for name in ['sms_imessage_bridge.py','imessage_sms_sender.py','decode_attributed.m','delivery_store.py','imessage_delivery.py']:
 shutil.copy2(SOURCE/name,BASE/name)
for name in ['bridge_config','sender_config']:
 target=BASE/(name+'.json')
 if not target.exists():shutil.copy2(SOURCE/(name+'.example.json'),target)
subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(BASE/'decode_attributed.m'),'-o',str(BASE/'decode_attributed')],check=True)
for role,script in JOBS.items():
 label='com.sim7600bridge.'+role
 agent={'Label':label,'ProgramArguments':[str(Path(sys.executable).resolve()),str(BASE/script)],'RunAtLoad':True,'KeepAlive':True,'WorkingDirectory':str(BASE),'StandardOutPath':str(BASE/(role+'.out.log')),'StandardErrorPath':str(BASE/(role+'.err.log'))}
 (AGENTS/(label+'.plist')).write_bytes(plistlib.dumps(agent))
print('Installed in',BASE)
print('Python requiring Full Disk Access:',Path(sys.executable).resolve())
if args.start:
 cfg=json.loads((BASE/'bridge_config.json').read_text());allowed=json.loads((BASE/'sender_config.json').read_text()).get('allowed_senders',[])
 if not cfg.get('forward_to') or cfg['forward_to']=='YOUR_IPHONE_IMESSAGE_ADDRESS' or not allowed:raise SystemExit('Edit both configuration files before starting. See README.')
 import os
 for role in JOBS:
  agent=AGENTS/('com.sim7600bridge.'+role+'.plist')
  subprocess.run(['launchctl','bootout','gui/'+str(os.getuid()),str(agent)],capture_output=True)
  subprocess.run(['launchctl','bootstrap','gui/'+str(os.getuid()),str(agent)],check=True)
 print('Started both LaunchAgents.')

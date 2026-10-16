import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from forwarding_watchdog import decide

class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.state={'receiver':'rx'}
        self.running={'rx':True,'tx':True}
    def row(self,status='sending',created=0):
        return {'signature':'a','status':status,'created':created}
    def test_grace_then_alert_and_restart(self):
        _,a=decide(self.state,[self.row()],self.running,100,100)
        self.assertEqual(a,[])
        s,a=decide(self.state,[self.row()],self.running,200,200)
        self.assertIn(('alert',1,0),a);self.assertIn(('restart','rx',0),a)
        s['episode']['alerted']=True
        _,a=decide(s,[self.row()],self.running,230,230)
        self.assertEqual(a,[])
    def test_submitted_message_never_alerts_or_restarts(self):
        _,a=decide(self.state,[self.row('submitted')],self.running,200,200)
        self.assertEqual(a,[])
    def test_hung_or_dead_service(self):
        _,a=decide(self.state,[],self.running,0,200)
        self.assertIn(('restart','rx',0),a)
        _,a=decide(self.state,[],{'rx':True,'tx':False},200,200)
        self.assertIn(('restart','tx',0),a)
    def test_daily_restart_limit_survives_restart(self):
        self.state['restart_history']=[100,2000,4000]
        _,a=decide(self.state,[self.row()],self.running,6000,6000)
        self.assertFalse(any(x[0]=='restart' for x in a))
    def test_recovery_tracks_multiple_messages_and_duration(self):
        s,_=decide(self.state,[self.row()],self.running,200,200)
        s['episode']['alerted']=True
        records=[self.row(),dict(signature='b',status='sending',created=210)]
        s,_=decide(s,records,self.running,250,250)
        records=[dict(r,status='delivered') for r in records]
        _,a=decide(s,records,self.running,300,300)
        self.assertEqual(a,[('recovered',2,100)])
    def test_submitted_message_completes_existing_incident(self):
        s,_=decide(self.state,[self.row()],self.running,200,200)
        _,a=decide(s,[self.row('submitted')],self.running,250,250)
        self.assertIn(('recovered',1,50),a)

    def test_runtime_persists_alert_and_recovery_without_resending_sms(self):
        import tempfile,json,sqlite3
        from unittest.mock import patch
        import forwarding_watchdog as w
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            (base/'watchdog_config.json').write_text(json.dumps({'receiver':'rx','sender':'tx'}))
            db=sqlite3.connect(base/'delivery.sqlite3')
            db.execute('CREATE TABLE incoming(signature TEXT,status TEXT,created REAL)')
            db.execute("INSERT INTO incoming VALUES('a','sending',0)");db.commit()
            (base/'receive_heartbeat').touch()
            with patch.object(w,'BASE',base),patch.object(w,'STATE',base/'watchdog_state.json'),patch.object(w,'service_running',return_value=True),patch.object(w,'restart') as restart,patch.object(w,'notify') as notify,patch.object(w.time,'time',return_value=200):
                w.tick();w.tick()
                restart.assert_called_once_with('rx')
                notify.assert_called_once_with('alert',1,0,False)
                db.execute("UPDATE incoming SET status='delivered'");db.commit()
                w.tick();w.tick()
                self.assertEqual(notify.call_count,2)
                self.assertEqual(notify.call_args.args,('recovered',1,0,False))
                self.assertIsNone(json.loads((base/'watchdog_state.json').read_text())['episode'])
            db.close()

if __name__=='__main__':unittest.main()

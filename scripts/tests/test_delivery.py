import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_store import connect, enqueue, decode_report, stamp, record_report, delivery_state
from imessage_delivery import process_queue
from sms_imessage_bridge import cleanup_persisted
from imessage_sms_sender import pdus

NUMBER = '+15550000000'

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = connect(self.base)
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()
    def enqueue(self):
        enqueue(self.db, 'sig', NUMBER, '\u6d4b\u8bd5', [{'digest':'a'}, {'digest':'b'}], NUMBER)
    def outgoing(self, total=1):
        with self.db:
            self.db.execute('INSERT INTO outgoing VALUES(1,?,?,100,?,1,NULL)', (NUMBER, NUMBER,total))
            for part in range(1,total+1):
                self.db.execute('INSERT INTO segments VALUES(1,?,?,100,NULL)', (part,part))
        return self.db.execute('SELECT * FROM outgoing').fetchone()
    def test_queue_survives_restart_and_is_idempotent(self):
        self.enqueue(); self.enqueue(); self.db.close(); self.db=connect(self.base)
        row=self.db.execute('SELECT * FROM incoming').fetchone()
        self.assertEqual(json.loads(row['payload'])['body'],'\u6d4b\u8bd5')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM incoming').fetchone()[0],1)
    def test_partial_delete_retries_only_saved_digests_and_current_slots(self):
        self.enqueue()
        calls=[]
        class Modem:
            def command(self, command):calls.append(command)
        cleanup_persisted(Modem(),self.db,[{'index':7,'digest':'b'},{'index':8,'digest':'unrelated'}])
        self.assertEqual(calls,['AT+CMGD=7'])
    def test_submission_preserves_queue_until_delivery(self):
        self.enqueue(); calls=[]
        with patch('imessage_delivery.snapshot',return_value=10):
            process_queue(self.db,self.base,lambda *a:calls.append(a),lambda _:None,now=100)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.db.execute('SELECT status FROM incoming').fetchone()[0],'submitted')
        process_queue(self.db,self.base,lambda *a:calls.append(a),lambda _:None,
                      observer=lambda *a:('delivered','guid'),now=200)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.db.execute('SELECT status FROM incoming').fetchone()[0],'delivered')
    def test_uncertain_submission_with_permission_loss_never_blindly_retries(self):
        import sqlite3
        self.enqueue();calls=[]
        def send(*args):calls.append(args);raise TimeoutError()
        def denied(*args):raise sqlite3.DatabaseError('authorization denied')
        with patch('imessage_delivery.snapshot',return_value=10):
            process_queue(self.db,self.base,send,lambda _:None,now=100)
        process_queue(self.db,self.base,send,lambda _:None,observer=denied,now=1000)
        self.assertEqual(len(calls),1)
    def test_timeout_then_observed_submission_not_resent(self):
        self.enqueue();calls=[]
        def send(*args):calls.append(args);raise TimeoutError()
        with patch('imessage_delivery.snapshot',return_value=10):
            process_queue(self.db,self.base,send,lambda _:None,now=100)
        process_queue(self.db,self.base,send,lambda _:None,observer=lambda *a:('submitted','g'),now=1000)
        self.assertEqual(len(calls),1)
    def test_missing_db_baseline_never_resends_uncertain_message(self):
        import sqlite3
        self.enqueue();calls=[]
        def send(*args):calls.append(args);raise TimeoutError()
        with patch('imessage_delivery.snapshot',side_effect=sqlite3.DatabaseError()):
            process_queue(self.db,self.base,send,lambda _:None,now=100)
        process_queue(self.db,self.base,send,lambda _:None,observer=lambda *a:(None,None),now=1000)
        self.assertEqual(len(calls),1)
    def test_reports_require_all_parts(self):
        command=self.outgoing(2)
        report={'digest':'r1','number':NUMBER,'mr':1,'submitted':100,'status':0}
        record_report(self.db,report)
        self.assertEqual(delivery_state(self.db,command,now=200),'waiting')
        report.update(digest='r2',mr=2);record_report(self.db,report)
        self.assertEqual(delivery_state(self.db,command,now=200),'delivered')
    def test_wrapped_reference_ambiguity_not_confirmed(self):
        command=self.outgoing()
        with self.db:
            self.db.execute('INSERT INTO outgoing VALUES(2,?,?,110,1,1,NULL)',(NUMBER,NUMBER))
            self.db.execute('INSERT INTO segments VALUES(2,1,1,110,NULL)')
        self.assertFalse(record_report(self.db,{'digest':'r','number':NUMBER,'mr':1,'submitted':105,'status':0}))
        self.assertEqual(delivery_state(self.db,command,now=200),'waiting')
    def test_report_wrong_recipient_does_not_match(self):
        command=self.outgoing()
        self.assertFalse(record_report(self.db,{'digest':'r','number':'+15550000001','mr':1,'submitted':100,'status':0}))
        self.assertEqual(delivery_state(self.db,command,now=200),'waiting')
    def test_temporary_status_timeout_is_not_failure_and_late_delivery_upgrades(self):
        command=self.outgoing()
        report={'digest':'r','number':NUMBER,'mr':1,'submitted':100,'status':32}
        record_report(self.db,report)
        self.assertEqual(delivery_state(self.db,command,now=100000),'unconfirmed')
        report.update(digest='r2',status=0);record_report(self.db,report)
        self.assertEqual(delivery_state(self.db,command,now=100001),'delivered')
    def test_permanent_failure(self):
        command=self.outgoing()
        record_report(self.db,{'digest':'r','number':NUMBER,'mr':1,'submitted':100,'status':64})
        self.assertEqual(delivery_state(self.db,command,now=200),'failed')
    def test_status_report_pdu_timezone(self):
        raw='0002010B915155000000F0620101010200236201010102012300'
        report=decode_report(raw)
        self.assertEqual(report['number'],NUMBER)
        self.assertEqual(report['status'],0)
        self.assertEqual(report['discharged']-report['submitted'],10)
        self.assertIsNone(decode_report('00000000'))
        with self.assertRaises(ValueError):decode_report('0002010B91')
    def test_requests_delivery_report_on_each_pdu(self):
        for body in ('hello','\u6d4b\u8bd5'*100):
            for _, raw in pdus(NUMBER,body):
                self.assertTrue(bytes.fromhex(raw)[1]&0x20)


class MessageObservationTests(unittest.TestCase):
    def test_observation_recipient_direction_and_delivery(self):
        import sqlite3
        from imessage_delivery import observe
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'messages.sqlite3'
            db=sqlite3.connect(path)
            db.executescript('''CREATE TABLE message(guid,text,attributedBody,is_from_me,service,handle_id,date_delivered,error,date);
              CREATE TABLE handle(id); CREATE TABLE chat_message_join(message_id,chat_id);
              CREATE TABLE chat_handle_join(chat_id,handle_id);''')
            db.execute('INSERT INTO handle VALUES(?)',(NUMBER,))
            body='SIM7600 received SMS\nFrom: x\nBody: hello'
            db.execute("INSERT INTO message VALUES(?,?,NULL,1,'iMessage',1,100,0,1)",('g',body))
            db.commit();db.close()
            def opened():
                c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
            payload={'recipient':NUMBER,'sender':'x','body':'hello'}
            item={'guid':None,'baseline':0,'created':978307201}
            with patch('imessage_delivery.open_messages',side_effect=opened):
                self.assertEqual(observe(item,payload,folder),('delivered','g'))
                self.assertEqual(observe(item,dict(payload,recipient='+15550000001'),folder),(None,None))
                self.assertEqual(observe(dict(item,baseline=None),payload,folder),('delivered','g'))
                db=opened();db.execute('UPDATE message SET error=1');db.commit();db.close()
                self.assertEqual(observe(item,payload,folder),('failed','g'))

if __name__=='__main__':unittest.main()

import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sms_imessage_bridge import groups
from imessage_sms_sender import parse_command,pdus,chunks

def fragment(part,stamp,digest,ref=9):
 return {'sender':'+15550000000','timestamp':stamp,'ref':ref,'total':2,'part':part,'digest':digest,'content':str(part)}
class ProtocolTests(unittest.TestCase):
 def test_multipart_different_seconds(self):
  items=[fragment(2,'62901201039023','b'),fragment(1,'62901201036023','a')]
  result=list(groups(items));self.assertEqual(len(result),1);self.assertEqual(result[0][2],'12')
 def test_reference_reused_next_day(self):
  items=[fragment(1,'62901201036023','a'),fragment(2,'62901201039023','b'),fragment(1,'62902201036023','c'),fragment(2,'62902201039023','d')]
  self.assertEqual(len(list(groups(items))),2)
 def test_missing_part_is_retained(self):
  self.assertEqual(list(groups([fragment(1,'62901201036023','a')])),[])
 def test_single_sms(self):
  item=fragment(1,'62901201036023','a');item.update(ref=None,total=None,part=None,content='hello')
  self.assertEqual(list(groups([item]))[0][2],'hello')
 def test_invalid_timestamp_does_not_mix(self):
  self.assertEqual(list(groups([fragment(1,'bad','a'),fragment(2,'bad','b')])),[])
 def test_reused_sim_slots_do_not_reverse_chronology(self):
  newer=fragment(1,'62901201039023','new');newer.update(ref=None,total=None,part=None,index=1,content='new')
  older=fragment(1,'62901201036023','old');older.update(ref=None,total=None,part=None,index=19,content='old')
  self.assertEqual([r[2] for r in groups([newer,older])],['old','new'])
 def test_multipart_order_uses_earliest_fragment_timestamp(self):
  short=fragment(1,'62901201038023','s');short.update(ref=None,total=None,part=None,content='short')
  parts=[fragment(2,'62901201039023','b'),fragment(1,'62901201036023','a')]
  self.assertEqual([r[2] for r in groups([short]+parts)],['12','short'])
 def test_explicit_command(self):
  self.assertEqual(parse_command("#sms +15550000000 Hello"),("+15550000000","Hello"))
  self.assertIsNone(parse_command("#sms 15550000000 Hello"))
  self.assertEqual(parse_command('#\u77ed\u4fe1 +15550000000 Hello\u5b9d'),('+15550000000','Hello\u5b9d'))
  self.assertIsNone(parse_command('#\u77ed\u4fe1 15550000000 hello'))
 def test_pdu_payload_lengths_and_unicode(self):
  body='\u6d4b\u8bd5🙂'*50
  result=pdus('+15550000000',body);self.assertGreater(len(result),1)
  for n,raw in result:
   self.assertEqual(len(bytes.fromhex(raw))-1,n)
  pieces=chunks(body,134);self.assertEqual(''.join(pieces),body)
  self.assertTrue(all(len(s.encode('utf-16-be'))<=134 for s in pieces))
if __name__=='__main__':unittest.main()

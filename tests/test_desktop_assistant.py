import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop_assistant import Assistant


class Physical:
    allowed=True
    def quiet(self):return self.allowed


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.now=datetime(2026,10,28,23,59,58).timestamp()
        self.physical=Physical()
        self.a=Assistant(self.temp.name,self.physical,lambda:self.now)
    def tearDown(self):self.temp.cleanup()
    def call(self,action,body=None,offline=False):return self.a.handle(action,body or {},offline)
    def test_physical_protection_and_rate(self):
        self.call('configure',{'settings':{'enabled':True,'speed':10}})
        self.assertTrue(self.call('tick')['allowed'])
        self.assertFalse(self.call('tick')['allowed'])
        self.now+=.11
        self.physical.allowed=False
        self.assertFalse(self.call('tick')['allowed'])
        self.physical.allowed=True
        self.assertTrue(self.call('tick')['allowed'])
    def test_session_reset_does_not_reset_daily(self):
        self.call('observe',{'total':100,'account':'a'})
        self.call('observe',{'total':109,'account':'a'})
        self.call('tick',{'sent':1,'confirmed':1})
        value=self.call('reset')
        self.assertEqual(value['session'],0)
        self.assertEqual(value['weekly']['normal'][-1]['count'],9)
    def test_days_accounts_and_decreasing_counter(self):
        self.call('observe',{'total':100,'account':'a'})
        self.call('observe',{'total':110,'account':'a'})
        self.call('observe',{'total':10000,'account':'b'})
        self.call('observe',{'total':2,'account':'a'})
        self.call('observe',{'total':5,'account':'a'})
        self.now+=5
        value=self.call('observe',{'total':9,'account':'a'})
        self.assertEqual(value['weekly']['normal'][-2]['count'],13)
        self.assertEqual(value['weekly']['normal'][-1]['count'],4)
        self.assertEqual(value['weekly']['local'][-1]['count'],0)
    def test_real_counts_shared_and_fake_chest_retired(self):
        self.call('observe',{'total':3000,'account':'a'},True)
        self.call('observe',{'total':3004,'account':'a'},False)
        value=self.call('observe',{'total':3007,'account':'a'},True)
        self.assertEqual(value['weekly']['normal'][-1]['count'],7)
        self.assertNotIn('local',value)
        for mode in (True,False):
            with self.assertRaises(ValueError):self.call('local-chest',{'side':'left'},mode)
    def test_room_history_favorites_and_offline_guard(self):
        self.call('room',{'code':'123456','host':'Alice'})
        self.call('favorite',{'code':'123456','favorite':True})
        self.call('room',{'code':'654321','host':'Bob'})
        value=self.call('room',{'code':'123456','host':'Alice 2'})
        self.assertEqual(len(value['rooms']),2)
        self.assertEqual(value['rooms'][0]['host'],'Alice 2')
        self.assertTrue(value['rooms'][0]['favorite'])
        with self.assertRaises(ValueError):self.call('room',{'code':'123'},True)
    def test_persistence_preserves_settings(self):
        self.call('configure',{'settings':{'enabled':True}})
        self.call('monitor',{'monitor':{'name':'DISPLAY2','position':{'x':1920,'y':0}}})
        other=Assistant(self.temp.name,self.physical,lambda:self.now)
        self.assertTrue(other.snapshot()['settings']['enabled'])
        self.assertEqual(other.snapshot()['monitor']['name'],'DISPLAY2')
    def test_setting_validation_and_private_scope(self):
        for changes in [{'speed':1000},{'enabled':1},{'threshold':0},{'unknown':True}]:
            with self.assertRaises(ValueError):self.call('configure',{'settings':changes})
        self.call('observe',{'total':1,'account':'private-account-id'})
        self.a.save(True)
        self.assertNotIn('private-account-id',self.a.path.read_text())
    def test_flush_handshake_and_mode_switch(self):
        self.call('configure',{'settings':{'enabled':True}})
        self.assertTrue(self.call('tick',{'mode':'normal'},True)['allowed'])
        value=self.call('flush-request')
        generation=value['flush_generation']
        self.assertEqual(self.call('tick')['flush_generation'],generation)
        self.call('flush-ack',{'generation':generation})
        self.assertEqual(self.call('tick')['flush_generation'],0)
        self.call('observe',{'total':100,'account':'a'},True)
        self.call('observe',{'total':102,'account':'a'},False)
        value=self.call('observe',{'total':105,'account':'a'},True)
        self.assertEqual(value['weekly']['normal'][-1]['count'],5)
    def test_renderer_restart_keeps_background_preferences_and_session(self):
        self.call('configure',{'settings':{'enabled':True}})
        self.call('tick',{'sent':1,'confirmed':1})
        value=self.call('renderer-start')
        self.assertTrue(value['settings']['enabled'])
        self.assertEqual(value['session'],1)
    def test_rewards_confirmed_deduplicated_and_persisted(self):
        reward={'id':'test-event','confirmed':True,'side':'left','asset_name':'test.png','name':'测试奖励','cost':1000}
        self.call('reward',{'reward':reward},True)
        value=self.call('reward',{'reward':reward},False)
        self.assertEqual(len(value['rewards']),1)
        self.assertEqual(value['session_chests'],1)
        other=Assistant(self.temp.name,self.physical,lambda:self.now)
        self.assertEqual(other.snapshot()['rewards'][0]['name'],'测试奖励')
        with self.assertRaises(ValueError):self.call('reward',{'reward':{**reward,'confirmed':False}})
    def test_mandatory_update_pauses_without_destroying_settings(self):
        self.call('configure',{'settings':{'enabled':True}})
        self.a.update_required=True
        self.assertFalse(self.call('tick')['allowed'])
        self.assertTrue(self.call('state')['settings']['enabled'])
    def test_view_navigation_is_validated_consumed_once_and_keeps_settings(self):
        self.call('configure',{'settings':{'enabled':True,'auto_chest':True}})
        self.call('open-settings',{'view':'rewards'})
        first=self.call('tick')
        self.assertEqual(first['open_settings'],'rewards')
        self.assertTrue(first['settings']['enabled'])
        self.assertTrue(first['settings']['auto_chest'])
        self.assertFalse(self.call('tick')['open_settings'])
        with self.assertRaises(ValueError):self.call('open-settings',{'view':'javascript:invalid'})


if __name__=='__main__':unittest.main()

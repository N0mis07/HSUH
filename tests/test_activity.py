import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from hsuh.activity import ActivityReader


class ActivityTests(unittest.TestCase):
    def test_read_only_metadata_excludes_prompts_paths_and_message_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / 'state.db'
            with sqlite3.connect(path) as db:
                db.executescript('''CREATE TABLE sessions (
                    id TEXT,title TEXT,source TEXT,model TEXT,started_at REAL,ended_at REAL,
                    last_activity_at REAL,api_call_count INTEGER,tool_call_count INTEGER,
                    input_tokens INTEGER,output_tokens INTEGER,cache_read_tokens INTEGER,
                    reasoning_tokens INTEGER,parent_session_id TEXT,system_prompt TEXT,cwd TEXT);
                    CREATE TABLE session_turn_leases(expires_at REAL);
                    CREATE TABLE async_delegations(state TEXT);
                    CREATE TABLE messages(content TEXT);''')
                now = time.time()
                db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('fictional','A task','telegram','fixture-model',now,None,now,2,3,100,10,40,5,None,
                            'PRIVATE_SYSTEM_CANARY','PRIVATE_PATH_CANARY'))
                db.executemany('INSERT INTO session_turn_leases VALUES (?)', [(now+60,), (now-60,)])
                db.execute('INSERT INTO async_delegations VALUES (?)', ('running',))
                db.execute('INSERT INTO messages VALUES (?)', ('PRIVATE_MESSAGE_CANARY',))
            db.close()
            before = hashlib.sha256(path.read_bytes()).digest()
            reader = ActivityReader(home)
            result = reader.read()
            self.assertTrue(result['available'])
            self.assertEqual(result['totals']['open'], 1)
            self.assertEqual(result['totals']['input_tokens'], 100)
            self.assertEqual(result['turn_leases'], 1)
            self.assertEqual(result['sessions'][0]['state'], 'open')
            self.assertNotIn('CANARY', json.dumps(result))
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).digest())
            self.assertIs(reader.read(), result, 'Cached reads must not repeatedly query the live database')

    def test_missing_database_is_not_created_and_does_not_report_zero_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            reader = ActivityReader(temporary)
            result = reader.read()
            self.assertFalse(result['available'])
            self.assertNotIn('totals', result)
            self.assertFalse((Path(temporary) / 'state.db').exists())

    def test_gateway_age_is_explicit_and_private_fields_are_projected_out(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / 'gateway_state.json').write_text(json.dumps({
                'updated_at':'2020-01-01T00:00:00+00:00','active_agents':2,
                'gateway_state':'running','code_version':'fixture','argv':['PRIVATE_CANARY'],
                'platforms':{'telegram':{'state':'connected','error_message':'PRIVATE_CANARY'}},
            }))
            result = ActivityReader(home).read()['gateway']
            self.assertTrue(result['available'])
            self.assertTrue(result['stale'])
            self.assertNotIn('PRIVATE_CANARY', json.dumps(result))


if __name__ == '__main__':
    unittest.main()

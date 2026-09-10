import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claude_subagents_mcp as server

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name).resolve()
        self.previous = server.ROOT
        server.ROOT = self.root / 'state'
        self.workspace = self.root / 'workspace'; self.workspace.mkdir()
        self.state = {'workspace': str(self.workspace), 'allow_writes': False, 'changed_files': []}
    def tearDown(self):
        server.ROOT = self.previous
        self.tmp.cleanup()
    def test_scoped_access_and_readonly(self):
        (self.workspace / 'a.txt').write_text('hello')
        self.assertEqual(server.file_action(self.state, 'read_file', {'path': 'a.txt'}), 'hello')
        for p in ('../outside.txt', '.codex/config.toml', '.git/config'):
            with self.assertRaises(ValueError): server.scoped_path(self.state,p)
        with self.assertRaises(ValueError): server.file_action(self.state,'write_file',{'path':'a.txt','content':'changed'})
        self.assertEqual((self.workspace / 'a.txt').read_text(),'hello')
    def test_cancelled_or_old_worker_cannot_resume(self):
        with self.assertRaises(InterruptedError): server.check_live({'status':'cancelled','turn':1},1)
        with self.assertRaises(InterruptedError): server.check_live({'status':'running','turn':2},1)
    def run_responses(self, responses):
        with patch.object(server,'start_worker'):
            s=server.spawn({'task':'Review sources and report findings','workspace':str(self.workspace),'allow_writes':True,'max_tokens':100,'max_steps':2})
        with patch.object(server,'api',side_effect=responses) as api:
            server.worker(s['agent_id'],1)
            return server.load(s['agent_id']),api
    def test_thinking_only_limit_continues_to_actual_report(self):
        state,api=self.run_responses([
            {'content':[{'type':'thinking','thinking':'internal','signature':'stub'}],'stop_reason':'max_tokens'},
            {'content':[{'type':'text','text':'Report: verified finding.'}],'stop_reason':'end_turn'}])
        self.assertEqual(state['status'],'completed')
        self.assertEqual(state['result'],'Report: verified finding.')
        self.assertTrue(state['report_mode'])
        self.assertEqual(state['continuations'],1)
        self.assertGreater(state['max_tokens'],100)
    def test_text_parts_are_preserved(self):
        state,api=self.run_responses([
            {'content':[{'type':'text','text':'Part one. '}],'stop_reason':'max_tokens'},
            {'content':[{'type':'text','text':'Part two.'}],'stop_reason':'end_turn'}])
        self.assertEqual(state['result'],'Part one. Part two.')
    def test_truncated_tool_call_is_never_executed(self):
        state,api=self.run_responses([
            {'content':[{'type':'tool_use','id':'t1','name':'write_file','input':{'path':'bad.txt','content':'partial'}}],'stop_reason':'max_tokens'},
            {'content':[{'type':'text','text':'No edits needed.'}],'stop_reason':'end_turn'}])
        self.assertFalse((self.workspace/'bad.txt').exists())
        self.assertEqual(state['status'],'completed')
    def test_repeated_truncation_is_not_completed(self):
        response={'content':[{'type':'text','text':'partial '}],'stop_reason':'max_tokens'}
        state,api=self.run_responses([response]*4)
        self.assertEqual(state['status'],'failed')
        self.assertEqual(state['error_kind'],'output_limit')
        self.assertIsNone(state['result'])
        self.assertTrue(state['partial_result'])
    def test_empty_final_is_not_completed(self):
        state,api=self.run_responses([{'content':[{'type':'thinking','thinking':'internal'}],'stop_reason':'end_turn'}])
        self.assertEqual(state['status'],'failed')
        self.assertEqual(state['error_kind'],'missing_report')
    def test_pending_consultation_returns_immediately_and_deduplicates(self):
        with patch.object(server, 'start_worker') as start:
            t=time.monotonic()
            first=server.call_tool('ask_claude',{'prompt':'Review the full argument','max_tokens':4096})
            self.assertLess(time.monotonic()-t,1)
            second=server.call_tool('ask_claude',{'prompt':'Review the full argument','max_tokens':100})
            self.assertEqual(first['agent_id'],second['agent_id'])
            self.assertTrue(second['reused_existing_task'])
            self.assertEqual(start.call_count,1)
            self.assertEqual(server.load(first['agent_id'])['max_tokens'],4096)
            pending=server.get(first['agent_id'])
            self.assertEqual(pending['status'],'queued')
            self.assertEqual(pending['next_action'],'wait_claude_agents')
            self.assertNotIn('error',pending)
    def test_wait_delivers_once_without_listing(self):
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'A'});b=server.spawn({'task':'B'})
        with server.locked():
            s=server.load(a['agent_id']);s.update(status='completed',result='Report A');server.save(s)
        result=server.wait_agents([a['agent_id'],b['agent_id']],0)
        self.assertEqual(result['results'][0]['result'],'Report A')
        self.assertEqual(result['pending'][0]['agent_id'],b['agent_id'])
        again=server.wait_agents([a['agent_id'],b['agent_id']],0,result['cursors'])
        self.assertEqual(again['results'],[])
        self.assertEqual(again['reason'],'pending')
    def test_request_id_recovers_completed_task_and_rejects_conflict(self):
        with patch.object(server,'start_worker') as start:
            a=server.spawn({'task':'A','request_id':'request-one'})
            with server.locked():
                s=server.load(a['agent_id']);s.update(status='completed',result='Done');server.save(s)
            again=server.spawn({'task':'A','request_id':'request-one'})
            self.assertEqual(again['agent_id'],a['agent_id'])
            self.assertEqual(again['result'],'Done')
            self.assertEqual(start.call_count,1)
            with self.assertRaises(ValueError):server.spawn({'task':'B','request_id':'request-one'})
    def test_followup_to_active_agent_is_applied_before_completion(self):
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'Initial task'})
        calls=[]
        def answer(state):
            calls.append(state)
            if len(calls)==1:
                reply=server.call_tool('send_claude_message',{'agent_id':a['agent_id'],'message':'Include the correction'})
                self.assertEqual(reply['message_status'],'queued_for_next_response')
                return {'content':[{'type':'text','text':'Original'}],'stop_reason':'end_turn'}
            self.assertEqual(state['messages'][-1]['content'],'Include the correction')
            return {'content':[{'type':'text','text':'Corrected'}],'stop_reason':'end_turn'}
        with patch.object(server,'api',side_effect=answer):server.worker(a['agent_id'],1)
        self.assertEqual(server.load(a['agent_id'])['result'],'Corrected')
    def test_dead_worker_is_reported_before_long_deadline(self):
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'A','timeout_seconds':900})
        with server.locked():
            s=server.load(a['agent_id']);s.update(status='running',heartbeat_at=time.time()-30);server.save(s)
        self.assertEqual(server.get(a['agent_id'])['error_kind'],'worker_lost')
    def test_batch_read_is_scoped_and_bounded(self):
        (self.workspace/'a.txt').write_text('A')
        (self.workspace/'b.txt').write_text('B'*100001)
        result=json.loads(server.file_action(self.state,'read_files',{'paths':['a.txt','b.txt','../outside']}))
        self.assertEqual(result[0]['text'],'A')
        self.assertEqual(len(result[1]['text']),100000)
        self.assertTrue(result[1]['truncated'])
        self.assertIn('error',result[2])
    def test_cross_process_lock_contention_does_not_fail(self):
        env=os.environ.copy();env['CLAUDE_AGENT_STATE_DIR']=str(server.ROOT)
        code='import claude_subagents_mcp as server;\nwith server.locked(): print("acquired",flush=True)'
        with server.locked():
            p=subprocess.Popen([sys.executable,'-c',code],cwd=Path(server.__file__).parent,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            time.sleep(0.3)
            self.assertIsNone(p.poll())
        out,err=p.communicate(timeout=5)
        self.assertEqual(p.returncode,0,err)
        self.assertIn('acquired',out)
    def test_wait_wakes_on_completion(self):
        import threading
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'A'})
        def finish():
            time.sleep(0.2)
            with server.locked():
                s=server.load(a['agent_id']);s.update(status='completed',result='Done');server.save(s)
        thread=threading.Thread(target=finish);thread.start()
        t=time.monotonic();result=server.wait_agents([a['agent_id']],5);thread.join()
        self.assertLess(time.monotonic()-t,2)
        self.assertEqual(result['results'][0]['result'],'Done')
    def test_model_and_effort_are_part_of_task_identity(self):
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'Review','model':'claude-fable-5-1','reasoning_effort':'low'})
            b=server.spawn({'task':'Review','model':'claude-fable-5-1','reasoning_effort':'high'})
            c=server.spawn({'task':'Review','model':'claude-sonnet-4-6','reasoning_effort':'low'})
            self.assertEqual(len({a['agent_id'],b['agent_id'],c['agent_id']}),3)
            self.assertEqual(c['model'],'claude-sonnet-4-6')
            self.assertEqual(c['reasoning_effort'],'low')
    def test_default_and_explicit_effort_payloads(self):
        import io
        for effort in ('default','low','medium','high','xhigh','max'):
            with patch.dict(os.environ, {'ANTHROPIC_PROXY_API_KEY':'test-key'}), patch.object(server.urllib.request,'build_opener') as factory:
                factory.return_value.open.return_value=io.BytesIO(b'{"content":[{"type":"text","text":"ok"}]}')
                server.api({'model':'custom-model','reasoning_effort':effort,'messages':[],'max_tokens':100,'workspace':None,'deadline':time.time()+10})
                req=factory.return_value.open.call_args.args[0]
                payload=json.loads(req.data)
                self.assertEqual(payload['model'],'custom-model')
                if effort=='default':self.assertNotIn('output_config',payload)
                else:self.assertEqual(payload['output_config'],{'effort':effort})
    def test_defaults_and_large_effort_budget(self):
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'Default'})
            b=server.call_tool('ask_claude',{'prompt':'Difficult','model':'claude-opus-5','reasoning_effort':'max'})
        self.assertEqual(a['model'],server.MODEL)
        self.assertEqual(a['reasoning_effort'],server.DEFAULT_EFFORT)
        self.assertEqual(server.load(b['agent_id'])['max_tokens'],65536)
        with self.assertRaises(ValueError):server.spawn({'task':'Bad','reasoning_effort':'ultra'})
    def test_inherited_effort_adapts_but_explicit_choice_rejected(self):
        with patch.object(server,'DEFAULT_EFFORT','medium'),patch.object(server,'start_worker') as start:
            a=server.spawn({'task':'Review','model':'claude-sonnet-4-5-20250929'})
            self.assertEqual(a['reasoning_effort'],'default')
            self.assertEqual(a['requested_reasoning_effort'],'medium')
            self.assertEqual(a['effort_source'],'inherited')
            self.assertIn('omitted',a['configuration_note'])
            with self.assertRaises(server.UnsupportedEffortError):
                server.spawn({'task':'Review','model':'claude-sonnet-4-5-20250929','reasoning_effort':'high'})
            self.assertEqual(start.call_count,1)
    def test_unknown_model_inherited_rejection_retries_once(self):
        with patch.object(server,'DEFAULT_EFFORT','medium'),patch.object(server,'start_worker'):
            a=server.spawn({'task':'Review','model':'custom-new-model'})
        with patch.object(server,'api',side_effect=[server.UnsupportedEffortError('unsupported'),{'content':[{'type':'text','text':'Done'}],'stop_reason':'end_turn'}]) as api:
            server.worker(a['agent_id'],1)
        state=server.load(a['agent_id'])
        self.assertEqual(api.call_count,2)
        self.assertEqual(state['status'],'completed')
        self.assertEqual(state['reasoning_effort'],'default')
    def test_explicit_effort_is_not_silently_retried(self):
        with patch.object(server,'start_worker'):
            a=server.spawn({'task':'Review','model':'custom-new-model','reasoning_effort':'high'})
        with patch.object(server,'api',side_effect=server.UnsupportedEffortError('unsupported')) as api:
            server.worker(a['agent_id'],1)
        self.assertEqual(api.call_count,1)
        self.assertEqual(server.load(a['agent_id'])['error_kind'],'unsupported_effort')
    def test_provider_unsupported_effort_is_learned(self):
        import io,urllib.error
        error=urllib.error.HTTPError('http://localhost:8317',400,'Bad request',{},io.BytesIO(b'{"error":{"message":"This model does not support the effort parameter."}}'))
        with patch.dict(os.environ,{'ANTHROPIC_PROXY_API_KEY':'test'}),patch.object(server.urllib.request,'build_opener') as factory:
            factory.return_value.open.side_effect=error
            with self.assertRaises(server.UnsupportedEffortError):
                server.api({'model':'new-legacy','reasoning_effort':'medium','messages':[],'max_tokens':100,'workspace':None,'deadline':time.time()+30})
        self.assertIs(server.effort_support('new-legacy'),False)
    def test_request_uses_remaining_task_budget(self):
        import io
        with patch.dict(os.environ, {'ANTHROPIC_PROXY_API_KEY':'test-key'}), patch.object(server.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=io.BytesIO(b'{"content":[{"type":"text","text":"ok"}]}')
            state={'messages':[], 'max_tokens':20, 'workspace':None, 'deadline':time.time()+120}
            result=server.api(state)
            timeout=factory.return_value.open.call_args.kwargs['timeout']
            self.assertGreater(timeout,115)
            self.assertLessEqual(timeout,120)
            self.assertEqual(result['content'][0]['text'],'ok')
    def test_deadline_stops_stalled_worker(self):
        state={'agent_id':'a'*32,'model':server.MODEL,'status':'queued','workspace':None,'allow_writes':False,'turn':1,'steps':0,'activity':'Starting','messages':[], 'changed_files':[], 'max_steps':2, 'deadline':time.time()+2}
        with server.locked(): server.save(state)
        env=os.environ.copy();env['CLAUDE_AGENT_STATE_DIR']=str(server.ROOT)
        code='import claude_subagents_mcp as server,time; server.api=lambda s: time.sleep(60); server.worker("'+'a'*32+'",1)'
        t=time.monotonic()
        p=subprocess.run([sys.executable,'-c',code],cwd=Path(server.__file__).parent,env=env,capture_output=True,timeout=8)
        self.assertLess(time.monotonic()-t,6)
        self.assertEqual(server.load('a'*32)['status'],'failed')
        self.assertIn('time limit',server.load('a'*32)['error'])
    def test_proxy_failure_is_recorded_without_secret(self):
        state={'agent_id':'b'*32,'model':server.MODEL,'status':'queued','workspace':None,'allow_writes':False,'turn':1,'steps':0,'activity':'Starting','messages':[], 'changed_files':[], 'max_steps':2, 'deadline':time.time()+10}
        with server.locked(): server.save(state)
        previous=server.api
        def fail(s): raise ValueError('secret-value')
        server.api=fail
        try: server.worker('b'*32,1)
        finally: server.api=previous
        result=server.load('b'*32)
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('secret-value',result['error'])

if __name__=='__main__': unittest.main()

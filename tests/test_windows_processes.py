"""Real native Windows checks; no SW launched and no WMI/COM prerequisite."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'windows-b'))
import windows_processes as native


@unittest.skipUnless(os.name=='nt','Windows native API')
class NativeProcessTests(unittest.TestCase):
    def test_snapshot_has_current_pid_and_session_without_com_initialization(self):
        results=[]
        errors=[]
        def run():
            try: results.append((native.process_snapshot(),native.process_session()))
            except Exception as exc: errors.append(exc)
        thread=threading.Thread(target=run)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertTrue(any(pid==os.getpid() for pid,name in results[0][0]))
        self.assertGreaterEqual(results[0][1],0)

    def test_real_child_is_detected_only_in_its_session(self):
        process=subprocess.Popen([sys.executable,'-c',"print('ready',flush=True); input()"],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            self.assertEqual(process.stdout.readline().strip(),'ready')
            current=native.process_session()
            self.assertIn(process.pid,native.processes_in_session(Path(sys.executable).name,current))
            self.assertNotIn(process.pid,native.processes_in_session(Path(sys.executable).name,current+10000))
        finally:
            process.communicate('\n',timeout=10)
        self.assertEqual(process.returncode,0)

    def test_names_are_case_insensitive_and_other_sessions_are_excluded(self):
        with patch.object(native,'process_snapshot',return_value=[(1,'sldworks.EXE'),(2,'SLDWORKS.exe'),(3,'python.exe')]), \
             patch.object(native,'process_session',side_effect=lambda pid:{1:4,2:5}[pid]):
            self.assertEqual(native.processes_in_session('SLDWORKS.exe',4),[1])


if __name__=='__main__': unittest.main()

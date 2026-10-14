"""The startup URL must be usable from the host, not Docker's bind address."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import web

class StartupUrlTests(unittest.TestCase):
    def output(self,environment,host='0.0.0.0',port=8080):
        server=SimpleNamespace(server_port=port,serve_forever=Mock(side_effect=KeyboardInterrupt),server_close=Mock())
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as folder,patch.object(web.interview_controller,'ROOT',Path(folder)),patch.dict(os.environ,environment,clear=True),patch.object(sys,'argv',['web.py','--provider','demo','--host',host,'--port',str(port)]),patch.object(web,'ThreadingHTTPServer',return_value=server),redirect_stdout(output):
            web.main()
        server.server_close.assert_called_once()
        return output.getvalue()

    def test_docker_published_port_is_shown(self):
        self.assertEqual(self.output({'COACH_BROWSER_URL':'http://localhost:8082'}),'Interview practice: http://localhost:8082 (demo)\n')

    def test_direct_launch_uses_actual_port_and_browser_host(self):
        self.assertEqual(self.output({},port=8090),'Interview practice: http://localhost:8090 (demo)\n')
        self.assertEqual(self.output({},host='127.0.0.1',port=8082),'Interview practice: http://127.0.0.1:8082 (demo)\n')

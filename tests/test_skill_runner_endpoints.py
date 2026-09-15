"""The sandbox runner: argv restrictions, secret-free env, cleanup."""
import base64
import os
import unittest

os.environ["SKILL_RUNNER_TOKEN"] = "skill-test-token"  # before importing the app

from fastapi.testclient import TestClient

from skill_runner.main import app

_HDR = {"X-Skill-Runner-Token": "skill-test-token"}


def _f(path: str, body: str) -> dict:
    return {"path": path, "content_b64": base64.b64encode(body.encode()).decode()}


class TestSkillRunner(unittest.TestCase):
    def setUp(self):
        self._ctx = TestClient(app)
        self.client = self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _run(self, **body):
        return self.client.post("/run", json=body, headers=_HDR)

    def test_requires_its_own_token(self):
        r = self.client.post("/run", json={"argv": ["python3", "x.py"]})
        self.assertEqual(r.status_code, 401)

    def test_runs_a_script_from_the_bundle(self):
        r = self._run(argv=["python3", "scripts/x.py", "world"],
                      timeout=20, files=[_f("scripts/x.py", "import sys; print('hi', sys.argv[1])")])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["stdout"].strip(), "hi world")
        self.assertEqual(r.json()["exit_code"], 0)

    def test_script_can_read_its_sibling_bundle_files(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py", "print(open('refs/a.txt').read().strip())"),
            _f("refs/a.txt", "sibling-ok"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "sibling-ok")

    def test_child_environment_carries_no_token(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py",
               "import os; print([k for k in os.environ if 'TOKEN' in k.upper()])"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "[]")

    def test_script_may_write_only_to_scratch(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py",
               "import os\n"
               "open(os.path.join(os.environ['TMPDIR'], 'out.txt'), 'w').write('ok')\n"
               "try:\n"
               "    open('scripts/x.py', 'a').write('tampered')\n"
               "    print('BUNDLE WRITABLE')\n"
               "except OSError:\n"
               "    print('bundle read-only')\n"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "bundle read-only")

    def test_rejects_interpreters_other_than_python3_and_sh(self):
        r = self._run(argv=["/bin/cat", "scripts/x.py"], timeout=20,
                      files=[_f("scripts/x.py", "print(1)")])
        self.assertEqual(r.status_code, 400)

    def test_rejects_interpreter_flags(self):
        # python3 -c would let the caller carry its own inline program.
        r = self._run(argv=["python3", "-c", "print(1)"], timeout=20, files=[])
        self.assertEqual(r.status_code, 400)

    def test_rejects_an_entrypoint_missing_from_the_bundle(self):
        r = self._run(argv=["python3", "scripts/nope.py"], timeout=20,
                      files=[_f("scripts/x.py", "print(1)")])
        self.assertEqual(r.status_code, 400)

    def test_rejects_traversal_in_the_payload(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20,
                      files=[{"path": "../evil.py", "content_b64": ""}])
        self.assertEqual(r.status_code, 400)

    def test_timeout_kills_the_script(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=1,
                      files=[_f("scripts/x.py", "import time; time.sleep(30)")])
        self.assertTrue(r.json()["timed_out"])

    def test_temp_root_is_removed_afterwards(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20,
                      files=[_f("scripts/x.py", "import os; print(os.getcwd())")])
        cwd = r.json()["stdout"].strip()
        self.assertTrue(cwd)
        self.assertFalse(os.path.exists(cwd))

    def test_temp_root_is_removed_after_a_timeout_too(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=1, files=[
            _f("scripts/x.py",
               "import os, sys, time; sys.stderr.write(os.getcwd()); "
               "sys.stderr.flush(); time.sleep(30)"),
        ])
        self.assertTrue(r.json()["timed_out"])
        leaked = r.json()["stderr"].strip()
        if leaked:
            self.assertFalse(os.path.exists(leaked))

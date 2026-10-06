"""Tests for tools/kgpu that run offline: packaging, kernel metadata and the job script itself."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("kgpu", str(REPO / "tools" / "kgpu"))
spec = importlib.util.spec_from_loader("kgpu", loader)
kgpu = importlib.util.module_from_spec(spec)
loader.exec_module(kgpu)


class Project:
    """A throwaway git repo with a kgpu config."""

    def __init__(self, files: dict[str, str | bytes]):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.cfg = kgpu.load_config(self.root)

    def run_job(self, command: str) -> tuple[dict, str, Path]:
        """Render the Kaggle job script and execute it locally with /kaggle paths redirected."""
        files, _ = kgpu.collect_files(self.root, self.cfg)
        job = kgpu.render_job("test-run", command, self.cfg, kgpu.build_payload(self.root, files))
        out = self.root / "kaggle-working"
        out.mkdir()
        script = self.root / "kgpu_job.py"
        script.write_text(job)
        env = dict(os.environ, KGPU_OUT=str(out), KGPU_SRC=str(self.root / "kaggle-src"))
        proc = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not (out / "kgpu_result.json").exists():
            raise AssertionError(f"job script failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        result = json.loads((out / "kgpu_result.json").read_text())
        return result, proc.stdout, out

    def close(self):
        self.tmp.cleanup()


class KgpuTest(unittest.TestCase):
    def project(self, files):
        project = Project(files)
        self.addCleanup(project.close)
        return project

    def test_collect_files_respects_gitignore_excludes_and_size(self):
        project = self.project(
            {
                ".gitignore": "secret.txt\n",
                "secret.txt": "token",
                "src/model.py": "print('hi')\n",
                "runs/old/kgpu.log": "old",
                ".devcontainer/devcontainer.json": "{}",
                "weights.bin": b"0" * (6 * 1024 * 1024),
            }
        )
        files, skipped = kgpu.collect_files(project.root, project.cfg)
        self.assertEqual(files, [".gitignore", "src/model.py"])
        self.assertEqual(skipped, ["weights.bin"])

    def test_job_runs_command_and_collects_outputs(self):
        project = self.project({"src/job.py": "import os\nprint('hello from job')\nopen('outputs/r.txt','w').write(os.environ['KGPU_RUN_ID'])\n"})
        result, stdout, out = project.run_job("python src/job.py")
        self.assertEqual(result["run_id"], "test-run")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual([step["name"] for step in result["steps"]], ["command"])
        self.assertIn("hello from job", stdout)
        self.assertIn("hello from job", (out / "kgpu.log").read_text())
        self.assertEqual((out / "outputs" / "r.txt").read_text(), "test-run")

    def test_job_reports_failure_exit_code(self):
        project = self.project({"src/fail.py": "import sys\nprint('boom')\nsys.exit(3)\n"})
        result, _, _ = project.run_job("python src/fail.py")
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["steps"][-1]["exit_code"], 3)

    def test_requirements_step_only_when_file_lists_packages(self):
        project = self.project({"requirements-gpu.txt": "# nothing yet\n\n", "a.py": "print(1)\n"})
        result, _, _ = project.run_job("python a.py")
        self.assertEqual([step["name"] for step in result["steps"]], ["command"])

    def test_setup_runs_before_command_and_stops_on_failure(self):
        project = self.project({"a.py": "print(1)\n"})
        project.cfg["job"]["setup"] = "echo setting up && exit 5"
        result, stdout, _ = project.run_job("python a.py")
        self.assertEqual([step["name"] for step in result["steps"]], ["setup"])
        self.assertEqual(result["exit_code"], 5)
        self.assertIn("setting up", stdout)

    def test_kernel_metadata_for_t4_and_cpu(self):
        project = self.project({"a.py": ""})
        with tempfile.TemporaryDirectory() as folder:
            kgpu.write_kernel(Path(folder), "someone", "id", "python a.py", project.cfg, b"")
            meta = json.loads((Path(folder) / "kernel-metadata.json").read_text())
            self.assertEqual(meta["id"], "someone/open-code-gpu")
            self.assertEqual(meta["machine_shape"], "NvidiaTeslaT4")
            self.assertTrue(meta["enable_gpu"])
            self.assertFalse(meta["enable_tpu"])
            compile((Path(folder) / "kgpu_job.py").read_text(), "kgpu_job.py", "exec")

            project.cfg["kernel"]["accelerator"] = "none"
            kgpu.write_kernel(Path(folder), "someone", "id", "python a.py", project.cfg, b"")
            meta = json.loads((Path(folder) / "kernel-metadata.json").read_text())
            self.assertNotIn("machine_shape", meta)
            self.assertFalse(meta["enable_gpu"])

    def test_job_command(self):
        self.assertIsNone(kgpu.job_command([]))
        self.assertEqual(kgpu.job_command(["python", "x.py", "--n", "a b"]), "python x.py --n 'a b'")
        self.assertEqual(kgpu.job_command(["a && b"]), "a && b")

    def test_parse_args_splits_command_at_double_dash(self):
        args = kgpu.parse_args(["run", "--no-follow", "--", "python", "x.py", "--timeout", "5"])
        self.assertTrue(args.no_follow)
        self.assertIsNone(args.timeout)
        self.assertEqual(args.command, ["python", "x.py", "--timeout", "5"])
        args = kgpu.parse_args(["package", "out", "--user", "me"])
        self.assertEqual((args.dir, args.user, args.command), ("out", "me", []))

    def test_describe_gpus(self):
        self.assertEqual(kgpu.describe_gpus(["Tesla T4, 15360 MiB", "Tesla T4, 15360 MiB"]), "2 x Tesla T4")
        self.assertEqual(kgpu.describe_gpus([]), "CPU")

    def test_console_text(self):
        raw = json.dumps([{"stream_name": "stdout", "time": 1.0, "data": "a\n"}, {"stream_name": "stderr", "data": "b\n"}])
        self.assertEqual(kgpu.console_text(raw), "a\nb\n")
        self.assertEqual(kgpu.console_text("plain"), "plain")

    def test_repo_config_loads(self):
        cfg = kgpu.load_config(REPO)
        self.assertEqual(cfg["kernel"]["accelerator"], "NvidiaTeslaT4")
        self.assertEqual(cfg["job"]["command"], "python src/infer.py")


if __name__ == "__main__":
    unittest.main()

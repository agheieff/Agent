import os
import subprocess
import sys
import pytest
import tempfile


RUN_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..",
    "run.py"
)

@pytest.mark.parametrize("env_vars, args, expected_in_output, expected_rc", [

    (
        {},
        ["--test", "--headless"],
        "No providers found. Please set an API key.",
        1
    ),

    (
        {"OPENAI_API_KEY": "test-key-here"},
        ["--test", "--headless"],
        "Agent session ended.",
        0
    ),

    (
        {"ANTHROPIC_API_KEY": "anthropic-test-key"},
        ["--test", "--headless"],
        "Agent session ended.",
        0
    ),

    (
        {"DEEPSEEK_API_KEY": "deepseek-test-key"},
        ["--test", "--headless"],
        "Agent session ended.",
        0
    ),
])
def test_run_script(env_vars, args, expected_in_output, expected_rc):
\
\
\
\

    if not os.path.isfile(RUN_SCRIPT):
        pytest.skip(f"run.py not found at: {RUN_SCRIPT}")

    env_copy = os.environ.copy()

    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"]:
        env_copy[k] = ""

    for k, v in env_vars.items():
        env_copy[k] = v

    cmd = [sys.executable, RUN_SCRIPT] + args

    with tempfile.TemporaryDirectory() as tmp_home:

        env_copy["HOME"] = tmp_home
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env_copy,
            cwd=tmp_home,
            stdin=subprocess.DEVNULL,
            text=True
        )
        stdout, stderr = process.communicate()
        rc = process.returncode





    assert expected_in_output in stdout or expected_in_output in stderr, (
        f"Expected '{expected_in_output}' in output.\n"
        f"stdout:\n{stdout}\nstderr:\n{stderr}"
    )
    assert rc == expected_rc, (
        f"Expected return code {expected_rc}, got {rc}.\n"
        f"stdout:\n{stdout}\nstderr:\n{stderr}"
    )

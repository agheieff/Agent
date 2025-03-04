import os
import subprocess
import sys
import pytest
import tempfile

# Adjust the RUN_SCRIPT path so that it points to Agent/run.py
RUN_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..",  # one level up from Tests/ to Agent/
    "run.py"
)

@pytest.mark.parametrize("env_vars, args, expected_in_output, expected_rc", [
    # 1) No environment variables: available_providers will be empty, so the script prints an error and exits.
    (
        {},
        ["--test", "--headless"],
        "No providers found. Please set an API key.",
        1
    ),
    # 2) With OPENAI_API_KEY: available_providers is not empty and in headless mode the agent runs and finishes.
    (
        {"OPENAI_API_KEY": "test-key-here"},
        ["--test", "--headless"],
        "Agent session ended.",
        0
    ),
    # 3) With ANTHROPIC_API_KEY
    (
        {"ANTHROPIC_API_KEY": "anthropic-test-key"},
        ["--test", "--headless"],
        "Agent session ended.",
        0
    ),
    # 4) With DEEPSEEK_API_KEY
    (
        {"DEEPSEEK_API_KEY": "deepseek-test-key"},
        ["--test", "--headless"],
        "Agent session ended.",
        0
    ),
])
def test_run_script(env_vars, args, expected_in_output, expected_rc):
    """
    Basic run.py tests. We run run.py in a subprocess so the actual argument parsing,
    environment, and execution are used. We also set the working directory to a temporary
    directory to prevent loading any external .env or config files.
    """
    if not os.path.isfile(RUN_SCRIPT):
        pytest.skip(f"run.py not found at: {RUN_SCRIPT}")

    env_copy = os.environ.copy()
    # Remove any existing API key environment variables and force them to empty
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"]:
        env_copy[k] = ""
    # Now insert the test API keys from the parameter if provided
    for k, v in env_vars.items():
        env_copy[k] = v

    cmd = [sys.executable, RUN_SCRIPT] + args

    with tempfile.TemporaryDirectory() as tmp_home:
        # Set HOME and change cwd to tmp_home to avoid reading project .env files
        env_copy["HOME"] = tmp_home
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env_copy,
            cwd=tmp_home,  # use temporary directory as current working directory
            stdin=subprocess.DEVNULL,  # simulate EOF for any input() calls
            text=True
        )
        stdout, stderr = process.communicate()
        rc = process.returncode

    # Debug output if needed:
    # print("stdout:", stdout)
    # print("stderr:", stderr)

    assert expected_in_output in stdout or expected_in_output in stderr, (
        f"Expected '{expected_in_output}' in output.\n"
        f"stdout:\n{stdout}\nstderr:\n{stderr}"
    )
    assert rc == expected_rc, (
        f"Expected return code {expected_rc}, got {rc}.\n"
        f"stdout:\n{stdout}\nstderr:\n{stderr}"
    )

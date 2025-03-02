import asyncio
import logging
from typing import Tuple
from pathlib import Path
import json
import pexpect
import sys
import time

logger = logging.getLogger(__name__)

class ShellAdapter:
    def __init__(self, test_mode: bool = False, working_dir: Path = None):
        self.test_mode = test_mode
        self.working_dir = working_dir or Path.cwd()
        self.command_history = []

    async def execute(self, command: str, timeout: int = 120) -> Tuple[str, str, int]:
        if self.test_mode:
            msg = f"[TEST MODE] Not executed: {command}"
            logger.info(msg)
            return (msg, "", 0)
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                stdout_str = stdout.decode() if stdout else ""
                stderr_str = stderr.decode() if stderr else ""
                code = process.returncode
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception as kill_error:
                    logger.error(f"Killing process failed: {kill_error}")
                return ("", f"ERROR: timed out after {timeout}s", 1)
            self.command_history.append({'command': command, 'exit_code': code, 'timestamp': time.time()})
            return (stdout_str, stderr_str, code)
        except Exception as e:
            err = f"Error executing command: {str(e)}"
            logger.error(err)
            return ("", err, 1)

    async def execute_interactive(self, command: str, timeout: int = 180) -> Tuple[str, str, int]:
        if self.test_mode:
            msg = f"[TEST MODE] Interactive not executed: {command}"
            logger.info(msg)
            return (msg, "", 0)
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_pexpect_blocking, command, timeout),
                timeout=timeout + 30
            )
            return result
        except asyncio.TimeoutError:
            return ("", f"ERROR: Interactive timed out after {timeout}s", 1)

    def _run_pexpect_blocking(self, command: str, timeout: int = 180) -> Tuple[str, str, int]:
        start_time = time.time()
        output_buffer = []
        try:
            child = pexpect.spawn(
                "/bin/bash",
                ["-c", command],
                cwd=str(self.working_dir),
                encoding='utf-8',
                echo=False,
                timeout=min(30, timeout)
            )
            child.logfile_read = sys.stdout
            while True:
                if time.time() - start_time > timeout:
                    try:
                        child.sendintr()
                        child.terminate(force=True)
                    except:
                        pass
                    return ("\n".join(output_buffer), f"ERROR: Exceeded {timeout}s", 1)
                try:
                    index = child.expect([
                        r'\[Y/n\]', r'\[y/N\]', r'(y/n)', r'(Y/n)', r'(y/N)', r'Do you want to continue', 
                        r'password', r'continue\?', pexpect.EOF, pexpect.TIMEOUT
                    ], timeout=30)
                    if child.before:
                        output_buffer.append(child.before)
                    if index in (0,1,2,3,4,5,7):
                        child.sendline("y")
                    elif index == 6:
                        child.sendline("")
                    elif index == 8:
                        break
                    elif index == 9:
                        pass
                except pexpect.EOF:
                    break
                except pexpect.TIMEOUT:
                    pass
            wait_result = child.wait(timeout=30)
            exit_code = child.exitstatus if child.exitstatus is not None else 0
            remainder = child.read() if not child.closed else ""
            if remainder:
                output_buffer.append(remainder)
            child.close()
            self.command_history.append({
                'command': command,
                'exit_code': exit_code,
                'timestamp': time.time(),
                'interactive': True,
                'duration': time.time() - start_time
            })
            return ("\n".join(output_buffer), "", exit_code)
        except Exception as e:
            err = f"Interactive error: {str(e)}"
            logger.error(err)
            return ("\n".join(output_buffer) if output_buffer else "", err, 1)

    def get_command_history(self):
        return self.command_history

    def clear_history(self):
        self.command_history = []

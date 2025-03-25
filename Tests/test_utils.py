import os
import tempfile
import shutil
import unittest
from Tools.base import ToolResult
from Tools.error_codes import ErrorCodes

class FileTestCase(unittest.TestCase):
    """Base class for tests that need file operations"""
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_file(self, filename, content):
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path
    
def assertToolSuccess(self, result: ToolResult):
    self.assertTrue(result.success, 
                   f"Expected success but got error: {result.code} - {result.message}")
    self.assertEqual(result.code, ErrorCodes.SUCCESS)

def assertToolFailure(self, result: ToolResult, expected_code: ErrorCodes):
    self.assertFalse(result.success)
    self.assertEqual(result.code, expected_code,
                    f"Expected {expected_code.name} but got {result.code.name}")

class ProviderTestCase(unittest.TestCase):
    """Base class for provider API tests"""
    provider = None  # Override in subclass
    
    def setUp(self):
        if not os.getenv(f"{self.provider.upper()}_API_KEY"):
            self.skipTest(f"No API key found for {self.provider}")

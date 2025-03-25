import os
import unittest
import tempfile
import shutil
from unittest.mock import patch

from Tools.File.write import WriteFile
from Tools.error_codes import ErrorCodes

class TestWriteFile(unittest.TestCase):
    def setUp(self):
        self.tool = WriteFile()
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        self.test_content = "This is test content."

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_file_success(self):
        result = self.tool.execute(path=self.test_file, content=self.test_content)
        self.assertEqual(result.code, ErrorCodes.SUCCESS)
        self.assertTrue(result.success)

        with open(self.test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertEqual(content, self.test_content)

    def test_file_already_exists(self):
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("Existing content")

        result = self.tool.execute(path=self.test_file, content=self.test_content)
        self.assertEqual(result.code, ErrorCodes.RESOURCE_EXISTS)
        self.assertFalse(result.success)
        self.assertIn("already exists", result.message)

        with open(self.test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertEqual(content, "Existing content")

    def test_path_is_directory(self):
        directory_path = os.path.join(self.temp_dir, "test_dir")
        os.mkdir(directory_path)

        result = self.tool.execute(path=directory_path, content=self.test_content)
        self.assertEqual(result.code, ErrorCodes.RESOURCE_EXISTS)
        self.assertFalse(result.success)
        self.assertIn("is a directory", result.message)

    def test_permission_denied_directory(self):
        with patch('os.access', return_value=False):
            result = self.tool.execute(path=self.test_file, content=self.test_content)
        
        self.assertEqual(result.code, ErrorCodes.PERMISSION_DENIED)
        self.assertFalse(result.success)
        self.assertIn("No write permission", result.message)

    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    def test_permission_denied_file(self, mock_open):
        result = self.tool.execute(path=self.test_file, content=self.test_content)
        
        self.assertEqual(result.code, ErrorCodes.PERMISSION_DENIED)
        self.assertFalse(result.success)
        self.assertIn("Permission denied", result.message)

    def test_directory_does_not_exist(self):
        nonexistent_path = os.path.join(self.temp_dir, "nonexistent_dir", "test_file.txt")

        result = self.tool.execute(path=nonexistent_path, content=self.test_content)
        self.assertEqual(result.code, ErrorCodes.RESOURCE_NOT_FOUND)
        self.assertFalse(result.success)
        self.assertIn("does not exist", result.message)

    @patch('builtins.open', side_effect=OSError("Mock OS error"))
    def test_os_error(self, mock_open):
        result = self.tool.execute(path=self.test_file, content=self.test_content)
        
        self.assertEqual(result.code, ErrorCodes.OPERATION_FAILED)
        self.assertFalse(result.success)
        self.assertIn("OS error", result.message)

    def test_large_file_content(self):
        large_content = "Test line\n" * 10000

        result = self.tool.execute(path=self.test_file, content=large_content)
        self.assertEqual(result.code, ErrorCodes.SUCCESS)
        self.assertTrue(result.success)

        self.assertTrue(os.path.getsize(self.test_file) > 90000)

if __name__ == '__main__':
    unittest.main()

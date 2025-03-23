import os
import unittest
import tempfile
import shutil
from unittest.mock import patch, mock_open

from Tools.File.write import WriteFile

class TestWriteFile(unittest.TestCase):
    def setUp(self):
        self.tool = WriteFile()
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        self.test_content = "This is test content."
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_write_file_success(self):
        """Test successful file creation."""
        exit_code, message = self.tool.execute(self.test_file, self.test_content)
        
        self.assertEqual(exit_code, 0)
        self.assertEqual(message, "")
        
        # Verify file was created with correct content
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertEqual(content, self.test_content)
        
    def test_file_already_exists(self):
        """Test error when file already exists."""
        # Create the file first
        with open(self.test_file, 'w') as f:
            f.write("Existing content")
            
        exit_code, message = self.tool.execute(self.test_file, self.test_content)
        
        self.assertEqual(exit_code, 1)
        self.assertIn("already exists", message)
        
        # Verify original content wasn't changed
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertEqual(content, "Existing content")
        
    def test_path_is_directory(self):
        """Test error when path is a directory."""
        directory_path = os.path.join(self.temp_dir, "test_dir")
        os.mkdir(directory_path)
        
        exit_code, message = self.tool.execute(directory_path, self.test_content)
        
        self.assertEqual(exit_code, 2)
        self.assertIn("is a directory", message)
        
    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    def test_permission_denied(self, mock_open):
        """Test error when permission is denied."""
        exit_code, message = self.tool.execute(self.test_file, self.test_content)
        
        self.assertEqual(exit_code, 3)
        self.assertIn("Permission denied", message)
        
    def test_directory_does_not_exist(self):
        """Test error when directory doesn't exist."""
        nonexistent_path = os.path.join(self.temp_dir, "nonexistent_dir", "test_file.txt")
        
        exit_code, message = self.tool.execute(nonexistent_path, self.test_content)
        
        self.assertEqual(exit_code, 4)
        self.assertIn("Directory", message)
        self.assertIn("does not exist", message)
        
    @patch('builtins.open', side_effect=Exception("Unknown error"))
    def test_unknown_error(self, mock_open):
        """Test handling of unknown errors."""
        exit_code, message = self.tool.execute(self.test_file, self.test_content)
        
        self.assertEqual(exit_code, 5)
        self.assertIn("Error creating file", message)
        
    def test_large_file_content(self):
        """Test writing a large file (10,000 lines)."""
        large_content = "Test line\n" * 10000
        
        exit_code, message = self.tool.execute(self.test_file, large_content)
        
        self.assertEqual(exit_code, 0)
        self.assertEqual(message, "")
        
        # Check file size to verify content was written
        self.assertTrue(os.path.getsize(self.test_file) > 90000)  # Approx 10 bytes per line

if __name__ == '__main__':
    unittest.main() 
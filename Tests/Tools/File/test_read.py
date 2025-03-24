import os
import unittest
import tempfile
import shutil
from unittest.mock import patch
from Tools.File.read import ReadFile
from Tools.base import ErrorCodes

class TestReadFile(unittest.TestCase):
    def setUp(self):
        self.tool = ReadFile()
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test file with 200 lines
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        with open(self.test_file, 'w') as f:
            for i in range(1, 201):
                f.write(f"Line {i}\n")
                
        # Create a file with invalid encoding
        self.binary_file = os.path.join(self.temp_dir, "binary_file.bin")
        with open(self.binary_file, 'wb') as f:
            f.write(b'\x80\x81\x82\x83')
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_read_file_success(self):
        """Test reading a file successfully."""
        exit_code, content = self.tool.execute(self.test_file)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("Line 1", content)
        self.assertIn("Line 100", content)
        self.assertNotIn("Line 101", content)  # Default is 100 lines
        self.assertIn("Showing 100 out of 200 lines", content)
        self.assertEqual(self.tool.last_read_file, self.test_file)
    
    def test_read_file_all_lines(self):
        """Test reading all lines of a file."""
        exit_code, content = self.tool.execute(self.test_file, lines=0)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("Line 1", content)
        self.assertIn("Line 200", content)
        self.assertNotIn("Showing", content)  # No line count message when reading all
    
    def test_read_file_custom_lines(self):
        """Test reading a custom number of lines."""
        exit_code, content = self.tool.execute(self.test_file, lines=50)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("Line 1", content)
        self.assertIn("Line 50", content)
        self.assertNotIn("Line 51", content)
        self.assertIn("Showing 50 out of 200 lines", content)
    
    def test_read_file_from_end(self):
        """Test reading lines from the end of a file."""
        exit_code, content = self.tool.execute(self.test_file, lines=50, from_end=True)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertNotIn("Line 150", content)
        self.assertIn("Line 151", content)
        self.assertIn("Line 200", content)
        self.assertIn("Showing 50 out of 200 lines", content)
    
    def test_read_nonexistent_file(self):
        """Test reading a file that doesn't exist."""
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.txt")
        exit_code, message = self.tool.execute(nonexistent_file)
        
        self.assertEqual(exit_code, ErrorCodes.RESOURCE_NOT_FOUND)
        self.assertIn("does not exist", message)
    
    def test_read_directory(self):
        """Test reading a directory instead of a file."""
        exit_code, message = self.tool.execute(self.temp_dir)
        
        self.assertEqual(exit_code, ErrorCodes.RESOURCE_EXISTS)
        self.assertIn("is a directory", message)
    
    def test_read_no_permission(self):
        """Test reading a file without permission."""
        # Skip on Windows as permissions work differently
        if os.name == 'nt':
            return
            
        # Create a file and remove read permissions
        no_read_file = os.path.join(self.temp_dir, "no_read.txt")
        with open(no_read_file, 'w') as f:
            f.write("test content")
        os.chmod(no_read_file, 0o200)  # Write-only permission
        
        try:
            exit_code, message = self.tool.execute(no_read_file)
            
            self.assertEqual(exit_code, ErrorCodes.PERMISSION_DENIED)
            self.assertIn("No read permission", message)
        finally:
            # Restore permissions for cleanup
            os.chmod(no_read_file, 0o600)
    
    def test_read_invalid_encoding(self):
        """Test reading a file with an invalid encoding."""
        exit_code, message = self.tool.execute(self.binary_file)
        
        self.assertEqual(exit_code, ErrorCodes.INVALID_ARGUMENT_VALUE)
        self.assertIn("Unable to decode file", message)
    
    def test_read_with_custom_encoding(self):
        """Test reading a file with a specified encoding."""
        # Create a file with Latin-1 encoding
        latin1_file = os.path.join(self.temp_dir, "latin1.txt")
        with open(latin1_file, 'w', encoding='latin-1') as f:
            f.write("Café\n" * 10)  # Latin-1 encoded text
        
        exit_code, content = self.tool.execute(latin1_file, encoding="latin-1")
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("Café", content)
    
    def test_exception_handling(self):
        """Test handling of unexpected exceptions."""
        with patch('builtins.open', side_effect=Exception("Unexpected error")):
            exit_code, message = self.tool.execute(self.test_file)
            
            self.assertEqual(exit_code, ErrorCodes.UNKNOWN_ERROR)
            self.assertIn("Error reading file", message)

if __name__ == '__main__':
    unittest.main() 
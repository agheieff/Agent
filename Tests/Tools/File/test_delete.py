import os
import unittest
import tempfile
import shutil
from unittest.mock import patch
from Tools.File.delete import DeleteFile
from Tools.base import ErrorCodes, ToolResult

class TestDeleteFile(unittest.TestCase):
    def setUp(self):
        self.tool = DeleteFile()
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test file
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        with open(self.test_file, 'w') as f:
            f.write("test content")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_delete_file_success(self):
        """Test deleting a file successfully."""
        result = self.tool.execute(filename=self.test_file)
        self.assertTrue(result.ok)
        self.assertEqual(result.code, ErrorCodes.SUCCESS)
        self.assertIn("deleted successfully", result.message)
        self.assertFalse(os.path.exists(self.test_file))
    
    def test_delete_nonexistent_file(self):
        """Test deleting a file that doesn't exist."""
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.txt")
        result = self.tool.execute(filename=nonexistent_file)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, ErrorCodes.RESOURCE_NOT_FOUND)
        self.assertIn("does not exist", result.message)
    
    def test_delete_directory(self):
        """Test deleting a directory instead of a file."""
        result = self.tool.execute(filename=self.temp_dir)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, ErrorCodes.RESOURCE_EXISTS)
        self.assertIn("is a directory", result.message)
        # Ensure directory still exists
        self.assertTrue(os.path.exists(self.temp_dir))
    
    def test_delete_no_write_permission_directory(self):
        """Test deleting a file when parent directory has no write permission."""
        # Skip on Windows as permissions work differently
        if os.name == 'nt':
            return
            
        # Create a subdirectory with restricted permissions
        no_write_dir = os.path.join(self.temp_dir, "no_write_dir")
        os.makedirs(no_write_dir)
        
        # Create a file in the directory
        file_path = os.path.join(no_write_dir, "test.txt")
        with open(file_path, 'w') as f:
            f.write("test content")
        
        # Remove write permission from the directory
        os.chmod(no_write_dir, 0o500)  # r-x permission
        
        try:
            result = self.tool.execute(filename=file_path)
            self.assertFalse(result.ok)
            self.assertEqual(result.code, ErrorCodes.PERMISSION_DENIED)
            self.assertIn("No write permission", result.message)
            # Ensure file still exists
            self.assertTrue(os.path.exists(file_path))
        finally:
            # Restore permissions for cleanup
            os.chmod(no_write_dir, 0o700)
    
    def test_delete_with_permission_error(self):
        """Test handling of permission errors during deletion."""
        with patch('os.remove', side_effect=PermissionError("Permission denied")):
            result = self.tool.execute(filename=self.test_file)
            self.assertFalse(result.ok)
            self.assertEqual(result.code, ErrorCodes.PERMISSION_DENIED)
            self.assertIn("Permission denied", result.message)
    
    def test_delete_with_os_error(self):
        """Test handling of OS errors during deletion."""
        with patch('os.remove', side_effect=OSError(123, "OS error message")):
            result = self.tool.execute(filename=self.test_file)
            self.assertFalse(result.ok)
            self.assertEqual(result.code, ErrorCodes.OPERATION_FAILED)
            self.assertIn("OS error", result.message)
            self.assertIn("OS error message", result.message)
    
    def test_delete_with_unexpected_error(self):
        """Test handling of unexpected errors during deletion."""
        with patch('os.remove', side_effect=Exception("Unexpected error")):
            result = self.tool.execute(filename=self.test_file)
            self.assertFalse(result.ok)
            self.assertEqual(result.code, ErrorCodes.UNKNOWN_ERROR)
            self.assertIn("Unexpected error", result.message)
    
    def test_delete_with_force_parameter(self):
        """Test the force parameter is received correctly."""
        with patch.object(self.tool, '_execute', wraps=self.tool._execute) as mock_execute:
            self.tool.execute(filename=self.test_file, force=True)
            # Check that _execute was called with the right parameters
            # _execute gets the parameters as kwargs only, not as args
            self.assertEqual(mock_execute.call_args.kwargs['filename'], self.test_file)
            self.assertEqual(mock_execute.call_args.kwargs['force'], True)

if __name__ == '__main__':
    unittest.main() 

import os
import json
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from Tools.File.edit import EditFile
from Tools.File.read import ReadFile
from Tools.base import ErrorCodes

class TestEditFile(unittest.TestCase):
    def setUp(self):
        self.edit_tool = EditFile()
        self.read_tool = ReadFile()
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test file
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        with open(self.test_file, 'w') as f:
            f.write("Line 1: Hello World\n")
            f.write("Line 2: Python Testing\n")
            f.write("Line 3: EditFile Tool\n")
        
        # Read the file first to set last_read_file
        self.read_tool.execute(path=self.test_file)
                
        # Create a binary file (cannot be edited with text encoding)
        self.binary_file = os.path.join(self.temp_dir, "binary_file.bin")
        with open(self.binary_file, 'wb') as f:
            f.write(b'\x80\x81\x82\x83')
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_edit_file_success(self):
        """Test editing a file successfully."""
        replacements = {
            "Hello World": "Hello Universe",
            "Python Testing": "Python Rules"
        }
        
        # Ensure the file has been read first
        self.edit_tool.read_tool.last_read_file = self.test_file
        
        exit_code, message = self.edit_tool.execute(
            filename=self.test_file, 
            replacements=json.dumps(replacements)
        )
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("Made 2 replacements", message)
        self.assertIn("Hello World", message)
        self.assertIn("Hello Universe", message)
        
        # Verify the file was actually changed
        with open(self.test_file, 'r') as f:
            content = f.read()
            self.assertIn("Hello Universe", content)
            self.assertIn("Python Rules", content)
            self.assertNotIn("Hello World", content)
            self.assertNotIn("Python Testing", content)
    
    def test_edit_nonexistent_file(self):
        """Test editing a file that doesn't exist."""
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.txt")
        exit_code, message = self.edit_tool.execute(
            filename=nonexistent_file, 
            replacements=json.dumps({"test": "replacement"})
        )
        
        self.assertEqual(exit_code, ErrorCodes.RESOURCE_NOT_FOUND)
        self.assertIn("not found", message)
    
    def test_edit_directory(self):
        """Test editing a directory instead of a file."""
        exit_code, message = self.edit_tool.execute(
            filename=self.temp_dir,
            replacements=json.dumps({"test": "replacement"})
        )
        
        self.assertEqual(exit_code, ErrorCodes.RESOURCE_EXISTS)
        self.assertIn("is a directory", message)
    
    def test_edit_without_read_first(self):
        """Test editing a file without reading it first."""
        new_file = os.path.join(self.temp_dir, "new_file.txt")
        with open(new_file, 'w') as f:
            f.write("test content")
            
        # Try to edit without reading
        exit_code, message = self.edit_tool.execute(
            filename=new_file, 
            replacements=json.dumps({"test": "replacement"})
        )
        
        self.assertEqual(exit_code, ErrorCodes.INVALID_OPERATION)
        self.assertIn("must be read first", message)
    
    def test_edit_pattern_not_found(self):
        """Test editing with a pattern that doesn't exist."""
        # Ensure the file has been read first
        self.edit_tool.read_tool.last_read_file = self.test_file
        
        exit_code, message = self.edit_tool.execute(
            filename=self.test_file, 
            replacements=json.dumps({"NonexistentPattern": "replacement"})
        )
        
        self.assertEqual(exit_code, ErrorCodes.RESOURCE_NOT_FOUND)
        self.assertIn("Pattern not found", message)
    
    def test_edit_pattern_multiple_occurrences(self):
        """Test editing when a pattern appears multiple times."""
        # Create file with repeating pattern
        repeat_file = os.path.join(self.temp_dir, "repeat.txt")
        with open(repeat_file, 'w') as f:
            f.write("repeat pattern\n" * 3)
        
        # Read the file first - make sure we directly set the last_read_file
        self.read_tool.execute(path=repeat_file)
        self.edit_tool.read_tool.last_read_file = repeat_file
        
        # Try to edit
        exit_code, message = self.edit_tool.execute(
            filename=repeat_file, 
            replacements=json.dumps({"repeat pattern": "replaced"})
        )
        
        self.assertEqual(exit_code, ErrorCodes.INVALID_OPERATION)
        self.assertIn("found multiple times", message)
    
    def test_invalid_json_replacements(self):
        """Test editing with invalid JSON replacements."""
        # Ensure the file has been read first
        self.edit_tool.read_tool.last_read_file = self.test_file
        
        exit_code, message = self.edit_tool.execute(
            filename=self.test_file, 
            replacements="invalid json"
        )
        
        self.assertEqual(exit_code, ErrorCodes.INVALID_ARGUMENT_VALUE)
        self.assertIn("Invalid JSON format", message)
    
    def test_non_dict_replacements(self):
        """Test editing with non-dict JSON replacements."""
        # Ensure the file has been read first
        self.edit_tool.read_tool.last_read_file = self.test_file
        
        exit_code, message = self.edit_tool.execute(
            filename=self.test_file, 
            replacements=json.dumps(["array", "not", "dict"])
        )
        
        self.assertEqual(exit_code, ErrorCodes.INVALID_ARGUMENT_VALUE)
        self.assertIn("JSON object", message)
    
    def test_edit_no_write_permission(self):
        """Test editing a file without write permission."""
        # Skip on Windows as permissions work differently
        if os.name == 'nt':
            return
            
        # Create a file and remove write permissions
        no_write_file = os.path.join(self.temp_dir, "no_write.txt")
        with open(no_write_file, 'w') as f:
            f.write("test content")
        
        # Read the file first
        self.read_tool.execute(path=no_write_file)
        
        # Remove write permissions
        os.chmod(no_write_file, 0o400)  # Read-only permission
        
        try:
            exit_code, message = self.edit_tool.execute(
                filename=no_write_file, 
                replacements=json.dumps({"test": "replacement"})
            )
            
            self.assertEqual(exit_code, ErrorCodes.PERMISSION_DENIED)
            self.assertIn("No write permission", message)
            # Ensure file still exists
            self.assertTrue(os.path.exists(no_write_file))
        finally:
            # Restore permissions for cleanup
            os.chmod(no_write_file, 0o600)
    
    def test_edit_invalid_encoding(self):
        """Test editing a file with an invalid encoding."""
        # Directly set last_read_file for this test
        self.edit_tool.read_tool.last_read_file = self.binary_file
        
        exit_code, message = self.edit_tool.execute(
            filename=self.binary_file, 
            replacements=json.dumps({"test": "replacement"})
        )
        
        self.assertEqual(exit_code, ErrorCodes.INVALID_OPERATION)
        self.assertIn("Unable to decode file", message)
    
    def test_exception_handling(self):
        """Test handling of unexpected exceptions."""
        # Ensure the file has been read first
        self.edit_tool.read_tool.last_read_file = self.test_file
        
        with patch('builtins.open', side_effect=Exception("Unexpected error")):
            exit_code, message = self.edit_tool.execute(
                filename=self.test_file, 
                replacements=json.dumps({"Hello World": "Hello Universe"})
            )
            
            self.assertEqual(exit_code, ErrorCodes.UNKNOWN_ERROR)
            self.assertIn("Error editing file", message)

if __name__ == '__main__':
    unittest.main()

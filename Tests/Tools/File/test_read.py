import os
import unittest
from unittest.mock import patch
from Tools.File.read import ReadFile
from Tools.base import ToolResult, ErrorCode
from Tests.test_utils import FileTestCase

class TestReadFile(FileTestCase):
    def setUp(self):
        super().setUp()
        self.tool = ReadFile()
        self.test_file = self.create_test_file("test.txt", "Line 1\nLine 2\nLine 3")

    def test_read_full_file(self):
        result = self.tool.execute(path=self.test_file)
        self.assertToolSuccess(result)
        self.assertEqual(result.message, "Line 1\nLine 2\nLine 3")

    def test_read_partial_file(self):
        result = self.tool.execute(path=self.test_file, lines=2)
        self.assertToolSuccess(result)
        self.assertEqual(result.message, "Line 1\nLine 2")

    def test_file_not_found(self):
        result = self.tool.execute(path="nonexistent.txt")
        self.assertToolFailure(result, ErrorCode.NOT_FOUND)

    def test_directory_instead_of_file(self):
        result = self.tool.execute(path=self.temp_dir)
        self.assertToolFailure(result, ErrorCode.INVALID_INPUT)

    @patch("builtins.open", side_effect=PermissionError)
    def test_permission_denied(self, mock_open):
        result = self.tool.execute(path=self.test_file)
        self.assertToolFailure(result, ErrorCode.PERMISSION_DENIED)

    def test_invalid_line_count(self):
        result = self.tool.execute(path=self.test_file, lines="not_an_integer")
        self.assertToolFailure(result, ErrorCode.INVALID_INPUT)

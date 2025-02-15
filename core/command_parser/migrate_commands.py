import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple
import json
import logging
import unittest

logger = logging.getLogger(__name__)

class CommandMigrator:
    """Migrates XML-formatted commands to new ANTLR format"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.backup_path = storage_path / "xml_backup"
        self.backup_path.mkdir(parents=True, exist_ok=True)
        
    def migrate_file(self, file_path: Path) -> bool:
        """Migrate a single file containing XML commands"""
        try:
            # Read original content
            content = file_path.read_text()
            
            # Backup original file
            backup_file = self.backup_path / file_path.name
            backup_file.write_text(content)
            
            # Convert XML to new format
            converted = self._convert_xml_to_antlr(content)
            
            # Write converted content
            file_path.write_text(converted)
            
            return True
            
        except Exception as e:
            logger.error(f"Error migrating file {file_path}: {e}")
            return False
            
    def _convert_xml_to_antlr(self, content: str) -> str:
        """Convert XML command format to ANTLR format with nested structure support"""
        try:
            # Replace XML commands with new format
            converted = content
            
            def convert_nested_commands(xml_str: str) -> str:
                """Convert nested command structures"""
                try:
                    root = ET.fromstring(xml_str)
                    result = []
                    
                    # Process attributes
                    attrs = []
                    for key, value in root.attrib.items():
                        if key != 'type':
                            attrs.append(f'{key}="{value}"')
                    attrs_str = ' '.join(attrs)
                    
                    # Start tag
                    tag_name = root.tag
                    result.append(f'<{tag_name} {attrs_str}>')
                    
                    # Process children
                    for child in root:
                        if child.tag == 'description':
                            result.append(f'<description>{child.text}</description>')
                        elif child.tag == 'commands':
                            result.append('<commands>')
                            # Handle nested commands
                            for cmd in child:
                                if cmd.tag in ['bash', 'python', 'task']:
                                    result.append(convert_nested_commands(ET.tostring(cmd).decode()))
                                else:
                                    result.append(self._escape_content(cmd.text))
                            result.append('</commands>')
                        elif child.tag == 'dependencies':
                            result.append('<dependencies>')
                            deps = [d.strip() for d in child.text.split(',')]
                            result.append(','.join(deps))
                            result.append('</dependencies>')
                            
                    # End tag
                    result.append(f'</{tag_name}>')
                    return '\n'.join(result)
                    
                except Exception as e:
                    logger.error(f"Error converting nested commands: {e}")
                    return xml_str
            
            # Convert top-level commands
            def convert_command(match):
                try:
                    return convert_nested_commands(match.group(0))
                except Exception as e:
                    logger.error(f"Error converting command: {e}")
                    return match.group(0)
                    
            # Convert each command type
            for cmd_type in ['bash', 'python', 'task', 'service', 'package']:
                pattern = f'<{cmd_type}.*?</{cmd_type}>'
                converted = re.sub(
                    pattern,
                    convert_command,
                    converted,
                    flags=re.DOTALL
                )
                
            return converted
            
        except Exception as e:
            logger.error(f"Error converting XML to ANTLR: {e}")
            return content
            
    def _escape_content(self, content: str) -> str:
        """Escape angle brackets in command content"""
        if content:
            return content.replace('<', '\\<').replace('>', '\\>')
        return ""
        
    def migrate_directory(self, directory: Path) -> Tuple[int, int]:
        """Migrate all files in a directory"""
        success = 0
        failed = 0
        
        for file_path in directory.glob("**/*"):
            if file_path.is_file() and file_path.suffix in ['.txt', '.md', '.json']:
                if self.migrate_file(file_path):
                    success += 1
                else:
                    failed += 1
                    
        return success, failed
        
    def validate_migration(self, file_path: Path) -> List[str]:
        """Validate migrated file format"""
        errors = []
        content = file_path.read_text()
        
        # Check for unclosed tags
        tags = ['bash', 'python', 'task', 'description', 'commands', 'service', 'package']
        for tag in tags:
            opens = len(re.findall(f'<{tag}[^>]*>', content))
            closes = len(re.findall(f'</{tag}>', content))
            if opens != closes:
                errors.append(f"Mismatched {tag} tags: {opens} opens, {closes} closes")
                
        # Check for invalid attributes
        for tag in ['task', 'service', 'package']:
            tag_blocks = re.finditer(f'<{tag}(.*?)>', content)
            for block in tag_blocks:
                attrs = block.group(1).strip()
                if attrs:
                    try:
                        # Validate attribute format
                        for attr in attrs.split():
                            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*="[^"]*"$', attr):
                                errors.append(f"Invalid attribute format in {tag}: {attr}")
                    except Exception as e:
                        errors.append(f"Error parsing attributes in {tag}: {str(e)}")
                        
        # Check for required blocks
        required_blocks = {
            'task': ['description', 'commands'],
            'service': ['description', 'commands'],
            'package': ['description', 'commands']
        }
        
        for tag, required in required_blocks.items():
            tag_contents = re.finditer(f'<{tag}.*?>(.*?)</{tag}>', content, re.DOTALL)
            for match in tag_contents:
                content = match.group(1)
                for req in required:
                    if f'<{req}>' not in content:
                        errors.append(f"{tag} missing {req} block")
                        
        # Check for nested structure validity
        def check_nesting(content: str, depth: int = 0) -> List[str]:
            if depth > 10:
                return ["Maximum nesting depth exceeded"]
                
            errors = []
            # Find all command blocks
            blocks = re.finditer(r'<(bash|python|task|service|package).*?>(.*?)</\1>', content, re.DOTALL)
            
            for block in blocks:
                tag = block.group(1)
                inner = block.group(2)
                
                # Check inner content
                if tag in ['task', 'service', 'package']:
                    errors.extend(check_nesting(inner, depth + 1))
                    
            return errors
            
        errors.extend(check_nesting(content))
        
        return errors

class TestCommandMigration(unittest.TestCase):
    """Test cases for command migration"""
    
    def setUp(self):
        self.migrator = CommandMigrator(Path("test_storage"))
        
    def test_nested_task_conversion(self):
        """Test conversion of nested task structures"""
        input_xml = '''
        <task priority="1">
        <description>Parent task</description>
        <commands>
        <task priority="2">
        <description>Child task</description>
        <commands>
        echo "nested command"
        </commands>
        </task>
        </commands>
        </task>
        '''
        
        converted = self.migrator._convert_xml_to_antlr(input_xml)
        self.assertIn('<task priority="1">', converted)
        self.assertIn('<task priority="2">', converted)
        self.assertIn('echo "nested command"', converted)
        
    def test_escaped_brackets(self):
        """Test handling of commands with angle brackets"""
        input_xml = '''
        <bash>
        echo "redirect > file.txt"
        </bash>
        '''
        
        converted = self.migrator._convert_xml_to_antlr(input_xml)
        self.assertIn('\\>', converted)
        
    def test_dependency_conversion(self):
        """Test conversion of dependencies"""
        input_xml = '''
        <task id="task1">
        <description>Task with deps</description>
        <commands>
        echo "command"
        </commands>
        <dependencies>#dep1,@task2</dependencies>
        </task>
        '''
        
        converted = self.migrator._convert_xml_to_antlr(input_xml)
        self.assertIn('#dep1,@task2', converted)
        
def main():
    """Main migration script"""
    storage_path = Path("storage")
    migrator = CommandMigrator(storage_path)
    
    print("Starting command format migration...")
    
    # Run tests first
    unittest.main(argv=['dummy'])
    
    success, failed = migrator.migrate_directory(storage_path)
    print(f"Migration complete: {success} successful, {failed} failed")
    
    # Validate all migrated files
    total_errors = 0
    for file_path in storage_path.glob("**/*"):
        if file_path.is_file() and file_path.suffix in ['.txt', '.md', '.json']:
            errors = migrator.validate_migration(file_path)
            if errors:
                print(f"\nErrors in {file_path}:")
                for error in errors:
                    print(f"  - {error}")
                total_errors += len(errors)
                
    print(f"\nValidation complete: {total_errors} total errors found")
    
if __name__ == "__main__":
    main() 
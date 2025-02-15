import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple
import json
import logging

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
        """Convert XML command format to ANTLR format"""
        try:
            # Replace XML commands with new format
            converted = content
            
            # Convert <bash>...</bash>
            converted = re.sub(
                r'<command type="bash">(.*?)</command>',
                r'<bash>\1</bash>',
                converted,
                flags=re.DOTALL
            )
            
            # Convert <python>...</python>
            converted = re.sub(
                r'<command type="python">(.*?)</command>',
                r'<python>\1</python>',
                converted,
                flags=re.DOTALL
            )
            
            # Convert task commands with attributes
            def convert_task(match):
                try:
                    xml = ET.fromstring(match.group(0))
                    attrs = []
                    for key, value in xml.attrib.items():
                        if key != 'type':
                            attrs.append(f'{key}="{value}"')
                    attrs_str = ' '.join(attrs)
                    return f'<task {attrs_str}>{xml.text}</task>'
                except Exception as e:
                    logger.error(f"Error converting task: {e}")
                    return match.group(0)
                    
            converted = re.sub(
                r'<command type="task".*?</command>',
                convert_task,
                converted,
                flags=re.DOTALL
            )
            
            return converted
            
        except Exception as e:
            logger.error(f"Error converting XML to ANTLR: {e}")
            return content
            
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
        tags = ['bash', 'python', 'task']
        for tag in tags:
            opens = len(re.findall(f'<{tag}', content))
            closes = len(re.findall(f'</{tag}>', content))
            if opens != closes:
                errors.append(f"Mismatched {tag} tags: {opens} opens, {closes} closes")
                
        # Check for invalid attributes in task blocks
        task_blocks = re.finditer(r'<task(.*?)>', content)
        for block in task_blocks:
            attrs = block.group(1).strip()
            if attrs:
                try:
                    # Validate attribute format
                    for attr in attrs.split():
                        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*="[^"]*"$', attr):
                            errors.append(f"Invalid attribute format: {attr}")
                except Exception as e:
                    errors.append(f"Error parsing attributes: {str(e)}")
                    
        return errors
        
def main():
    """Main migration script"""
    storage_path = Path("storage")
    migrator = CommandMigrator(storage_path)
    
    print("Starting command format migration...")
    
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
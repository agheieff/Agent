import os
import re
from datetime import datetime
from enum import Enum
from typing import Any, Union, Callable, Dict, Optional

class ArgumentType(Enum):
    STRING = "string"
    BOOLEAN = "boolean"
    INT = "int"
    FLOAT = "float"
    FILEPATH = "filepath"
    DATETIME = "datetime"

# Type validation functions
def validate_string(value: str) -> str:
    return value

def validate_boolean(value: str) -> bool:
    value = value.lower().strip()
    if value in ('true', 'yes', 'y', '1'):
        return True
    elif value in ('false', 'no', 'n', '0'):
        return False
    raise ValueError(f"Invalid boolean value: {value}")

def validate_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer value: {value}")

def validate_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Invalid float value: {value}")

def validate_filepath(value: str) -> str:
    """
    Validate a file path string for format correctness.
    
    This function:
    1. Ensures the path isn't empty
    2. Handles home directory expansion (~)
    3. Normalizes the path to use consistent separators
    
    Note: This only validates the path format, not existence or permissions.
    The actual tool will check those when executing.
    
    Args:
        value: The file path to validate
        
    Returns:
        The normalized file path
        
    Raises:
        ValueError: If the path is empty or invalid
    """
    if not value:
        raise ValueError("Empty filepath")
    
    try:
        # Expand user directory if path starts with ~
        if value.startswith('~'):
            value = os.path.expanduser(value)
            
        # Normalize path (resolve .. and . components and ensure consistent separators)
        normalized_path = os.path.normpath(value)
        
        return normalized_path
    except Exception as e:
        raise ValueError(f"Invalid file path: {str(e)}")

def validate_datetime(value: str) -> datetime:
    """
    Parse datetime in format: yyyy-mm-dd hh:mm:ss.mmm
    Any part from the rightmost can be omitted and will default
    """
    # Define patterns for different parts
    year_pattern = r'(?P<year>\d{4})'
    month_pattern = r'(?:-(?P<month>\d{1,2}))?'
    day_pattern = r'(?:-(?P<day>\d{1,2}))?'
    hour_pattern = r'(?:\s+(?P<hour>\d{1,2}))?'
    minute_pattern = r'(?::(?P<minute>\d{1,2}))?'
    second_pattern = r'(?::(?P<second>\d{1,2}))?'
    ms_pattern = r'(?:\.(?P<ms>\d{1,3}))?'
    
    datetime_pattern = f'^{year_pattern}{month_pattern}{day_pattern}{hour_pattern}{minute_pattern}{second_pattern}{ms_pattern}$'
    
    match = re.match(datetime_pattern, value)
    if not match:
        raise ValueError(f"Invalid datetime format: {value}. Use format yyyy-mm-dd hh:mm:ss.mmm")
    
    parts = match.groupdict()
    
    # Set defaults for missing parts
    year = int(parts['year'])
    month = int(parts['month']) if parts['month'] else 1
    day = int(parts['day']) if parts['day'] else 1
    hour = int(parts['hour']) if parts['hour'] else 0
    minute = int(parts['minute']) if parts['minute'] else 0
    second = int(parts['second']) if parts['second'] else 0
    ms = int(parts['ms']) if parts['ms'] else 0
    
    try:
        return datetime(year, month, day, hour, minute, second, ms * 1000)
    except ValueError as e:
        raise ValueError(f"Invalid datetime values: {str(e)}")

# Mapping of types to validation functions
VALIDATORS: Dict[ArgumentType, Callable[[str], Any]] = {
    ArgumentType.STRING: validate_string,
    ArgumentType.BOOLEAN: validate_boolean,
    ArgumentType.INT: validate_int,
    ArgumentType.FLOAT: validate_float,
    ArgumentType.FILEPATH: validate_filepath,
    ArgumentType.DATETIME: validate_datetime
}

def validate_and_convert(value: str, arg_type: ArgumentType) -> Any:
    """Validate and convert a string value to the specified type."""
    validator = VALIDATORS.get(arg_type, validate_string)
    return validator(value) 
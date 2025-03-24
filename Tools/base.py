from .error_codes import ErrorCodes, DEFAULT_MESSAGES

class Argument:
    def __init__(self, name: str, is_optional: bool = False):
        self.name = name
        self.is_optional = is_optional
    
    def __repr__(self):
        return f"Argument(name='{self.name}', is_optional={self.is_optional})"

class Tool:
    def __init__(self, name=None, description=None, help_text=None, 
                 allowed_in_test_mode=False, requires_sudo=False, requires_internet=False,
                 examples=None, timeout=None, arguments=None):
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.help_text = help_text or self.description
        self.allowed_in_test_mode = allowed_in_test_mode
        self.requires_sudo = requires_sudo
        self.requires_internet = requires_internet
        self.examples = examples or []
        self.timeout = timeout
        
        # List of arguments the tool accepts
        self.arguments = []
        if arguments:
            for arg in arguments:
                if isinstance(arg, Argument):
                    self.arguments.append(arg)
                elif isinstance(arg, tuple):
                    # Support for (name, is_optional) tuples
                    name, is_optional = arg if len(arg) > 1 else (arg[0], False)
                    self.arguments.append(Argument(name, is_optional))
                elif isinstance(arg, str):
                    # Support for just argument names as strings (required by default)
                    self.arguments.append(Argument(arg))
                else:
                    raise ValueError(f"Invalid argument specification: {arg}")
    
    def execute(self, *args, **kwargs):
        raise NotImplementedError("Tool subclasses must implement execute()")
    
    def get_error_message(self, code: int, message: str = None) -> str:
        """
        Get the error message for a given code. If a specific message is provided,
        use that instead of the default message.
        """
        if code == ErrorCodes.SUCCESS:
            return message or ""
        return message or DEFAULT_MESSAGES.get(code, DEFAULT_MESSAGES[ErrorCodes.UNKNOWN_ERROR])
    
    def __str__(self):
        return f"{self.name}: {self.description}"
    
    def __repr__(self):
        return (f"Tool(name='{self.name}', description='{self.description}', "
                f"allowed_in_test_mode={self.allowed_in_test_mode}, "
                f"requires_sudo={self.requires_sudo}, "
                f"requires_internet={self.requires_internet})") 
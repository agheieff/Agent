class Tool:
    def __init__(self, name=None, description=None, help_text=None, 
                 allowed_in_test_mode=False, requires_sudo=False, requires_internet=False,
                 examples=None, timeout=None):
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.help_text = help_text or self.description
        self.allowed_in_test_mode = allowed_in_test_mode
        self.requires_sudo = requires_sudo
        self.requires_internet = requires_internet
        self.examples = examples or []
        self.timeout = timeout
        
        self.exit_codes = {
            0: "Success",
            -1: "Tool does not exist"
            # Subclasses should define their own exit codes and messages
        }
    
    def execute(self, *args, **kwargs):
        raise NotImplementedError("Tool subclasses must implement execute()")
    
    def __str__(self):
        return f"{self.name}: {self.description}"
    
    def __repr__(self):
        return (f"Tool(name='{self.name}', description='{self.description}', "
                f"allowed_in_test_mode={self.allowed_in_test_mode}, "
                f"requires_sudo={self.requires_sudo}, "
                f"requires_internet={self.requires_internet})") 
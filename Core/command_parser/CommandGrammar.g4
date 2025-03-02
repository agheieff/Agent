grammar CommandGrammar;

command_sequence : (command_block)+;

command_block : bash_block | python_block | task_block | service_block | package_block;

bash_block : BASH_START command_content BASH_END;
python_block : PYTHON_START command_content PYTHON_END;
task_block : 
    TASK_START attributes TASK_END 
    (description_block nested_command_block dependency_block?)+ 
    TASK_CLOSE;

nested_command_block : 
    command_block |
    CMD_START command_content CMD_END;

service_block :
    SERVICE_START attributes SERVICE_END
    (description_block nested_command_block dependency_block?)+
    SERVICE_CLOSE;

package_block :
    PACKAGE_START attributes PACKAGE_END
    (description_block nested_command_block dependency_block?)+
    PACKAGE_CLOSE;

attributes : (attribute WS*)*;
attribute : NAME '=' STRING;

description_block : DESC_START command_content DESC_END;
dependency_block : DEP_START dependency_list DEP_END;
dependency_list : dependency (',' dependency)*;
dependency : ID_REF | TASK_REF;

command_content : (ESCAPED_BRACKET | ~[<>])+;
ESCAPED_BRACKET : '\\<' | '\\>';

output_format : 
    'json' |
    'table' |
    'list' |
    'record';

BASH_START : '<bash>';
BASH_END : '</bash>';
PYTHON_START : '<python>';
PYTHON_END : '</python>';
TASK_START : '<task';
TASK_END : '>';
TASK_CLOSE : '</task>';
SERVICE_START : '<service';
SERVICE_END : '>';
SERVICE_CLOSE : '</service>';
PACKAGE_START : '<package';
PACKAGE_END : '>';
PACKAGE_CLOSE : '</package>';
DESC_START : '<description>';
DESC_END : '</description>';
CMD_START : '<commands>';
CMD_END : '</commands>';
DEP_START : '<dependencies>';
DEP_END : '</dependencies>';

NAME : [a-zA-Z_][a-zA-Z0-9_]*;
STRING : '"' (~["])* '"';
WS : [ \t\r\n]+ -> skip;

ID_REF : '#' [a-zA-Z0-9_]+;
TASK_REF : '@' [a-zA-Z0-9_]+;

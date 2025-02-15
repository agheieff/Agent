grammar CommandGrammar;

command_sequence : (bash_block | python_block | task_block | service_block | package_block)+;

bash_block : BASH_START CONTENT BASH_END;
python_block : PYTHON_START CONTENT PYTHON_END;
task_block : 
    TASK_START attributes TASK_END 
    (description_block command_block dependency_block?)+ 
    TASK_CLOSE;

service_block :
    SERVICE_START attributes SERVICE_END
    (description_block command_block dependency_block?)+
    SERVICE_CLOSE;

package_block :
    PACKAGE_START attributes PACKAGE_END
    (description_block command_block dependency_block?)+
    PACKAGE_CLOSE;

attributes : (attribute WS*)*;
attribute : NAME '=' STRING;

description_block : DESC_START CONTENT DESC_END;
command_block : CMD_START CONTENT CMD_END;
dependency_block : DEP_START dependency_list DEP_END;
dependency_list : dependency (',' dependency)*;
dependency : ID_REF | TASK_REF;

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
CONTENT : ~[<>]+;
ID_REF : '#' [a-zA-Z0-9_-]+;
TASK_REF : '@' [a-zA-Z0-9_-]+;
WS : [ \t\r\n]+ -> skip; 
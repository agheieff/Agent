grammar CommandGrammar;

command_sequence : (bash_block | python_block | task_block)+;

bash_block : BASH_START CONTENT BASH_END;
python_block : PYTHON_START CONTENT PYTHON_END;
task_block : 
    TASK_START attributes TASK_END 
    (description_block command_block)+ 
    TASK_CLOSE;

attributes : (attribute WS*)*;
attribute : NAME '=' STRING;

description_block : DESC_START CONTENT DESC_END;
command_block : CMD_START CONTENT CMD_END;

BASH_START : '<bash>';
BASH_END : '</bash>';
PYTHON_START : '<python>';
PYTHON_END : '</python>';
TASK_START : '<task';
TASK_END : '>';
TASK_CLOSE : '</task>';
DESC_START : '<description>';
DESC_END : '</description>';
CMD_START : '<commands>';
CMD_END : '</commands>';

NAME : [a-zA-Z_][a-zA-Z0-9_]*;
STRING : '"' (~["])* '"';
CONTENT : ~[<>]+;
WS : [ \t\r\n]+ -> skip; 
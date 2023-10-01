import re
from enum import IntEnum, auto
from dataclasses import dataclass
from typing import Iterator, Tuple


class TokenType(IntEnum):
    NUMBER = auto()
    STRING = auto()
    STRING_VAR = auto()
    STYLED_TEXT = auto()
    IDENTIFIER = auto()

    OPEN_PAREN = auto()
    CLOSE_PAREN = auto()
    OPEN_SQUARE = auto()
    CLOSE_SQUARE = auto()
    OPEN_BRACE = auto()
    CLOSE_BRACE = auto()

    SEMICOLON = auto()
    COLON = auto()
    QUESTION_MARK = auto()
    DOT = auto()
    COMMA = auto()
    
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    BANG = auto()
    SLASH = auto()
    PIPE = auto()
    EQUALS = auto()
    PRECENT = auto()
    ARROW_UP = auto()
    AMPERSAND = auto()
    POINTER_ARROW = auto()

    VARARGS = auto()
    
    AND = auto()
    OR = auto()
    DEQUALS = auto()
    NEQUALS = auto()
    GREATER = auto()
    GEQUALS = auto()
    LOWER = auto()
    LEQUALS = auto()
    
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    BREAK = auto()
    RETURN = auto()
    TRUE = auto()
    FALSE = auto()
    # NEW = auto()

    CONST = auto()
    VAR = auto()
    LOCAL = auto()
    GAME = auto()
    SAVE = auto()
    # EXTERNAL = auto()

    PROC = auto()
    FUNC = auto()
    TYPE = auto()
    CODEBLOCK = auto()
    # STRUCT = auto()
    OUT = auto()
    # ENUM = auto()
    # CLASS = auto()

    # DEFINE = auto()
    # INCLUDE = auto()
    TARGET = auto()

    EOF = auto()

TokenLocation = Tuple[str, int, int]

@dataclass
class Token:
    type: TokenType
    value: any
    location: TokenLocation


class ScannerError(Exception):
    def __init__(self, msg, location: TokenLocation) -> None:
        self.msg = msg
        self.location = location

    def __repr__(self) -> str:
        return "%s:%d:%d: [ERROR]: %s" % (self.location + (self.msg,))

    def __str__(self) -> str:
        return "%s:%d:%d: [ERROR]: %s" % (self.location + (self.msg,))


class Scanner:
    ws_skip = re.compile(r'[^\t\r ]')

    token_definitions = {
        'NEWLINE':                     r'\n',
        'IGNORE':                      r'\/\/.*',
        TokenType.NUMBER:              r'\d+', # TODO: Add float

        TokenType.STAR:                r'\*',
        TokenType.PLUS:                r'\+',
        TokenType.POINTER_ARROW:       r'->',
        TokenType.MINUS:               r'-',
        TokenType.SLASH:               r'\/',
        TokenType.OPEN_PAREN:          r'\(',
        TokenType.CLOSE_PAREN:         r'\)',
        TokenType.OPEN_SQUARE:         r'\[',
        TokenType.CLOSE_SQUARE:        r'\]',
        TokenType.OPEN_BRACE:          r'{',
        TokenType.CLOSE_BRACE:         r'}',
        TokenType.COMMA:               r',',
        TokenType.VARARGS:             r'\.\.\.',
        TokenType.DOT:                 r'\.',
        TokenType.SEMICOLON:           r';',
        TokenType.COLON:               r':',
        TokenType.OR:                  r'\|\||\bor\b',
        TokenType.AND:                 r'&&|\band\b',
        TokenType.ARROW_UP:            r'\^',
        TokenType.PIPE:                r'\|',
        TokenType.AMPERSAND:           r'&',
        TokenType.NEQUALS:             r'!=',
        TokenType.BANG:                r'!',
        TokenType.QUESTION_MARK:       r'\?',
        TokenType.DEQUALS:             r'==',
        TokenType.EQUALS:              r'=',
        TokenType.GEQUALS:             r'>=',
        TokenType.GREATER:             r'>',
        TokenType.LEQUALS:             r'<=',
        TokenType.LOWER:               r'<',

        TokenType.TYPE:                r'\bnum\b|\bstr\b|\bdict\b|\blist\b|\bgval\b|\bvec\b|\bpot\b|\btxt\b|\bpar\b|\bany\b|\bitem\b|\bblock\b',
        TokenType.PROC:                r'\bproc\b',
        TokenType.FUNC:                r'\bfunc\b',
        TokenType.CODEBLOCK:           r'\bcodeblock\b',
        # TokenType.STRUCT:              r'\bstruct\b',
        TokenType.OUT:                 r'\bout\b',
        # TokenType.CLASS:               r'\bclass\b',
        # TokenType.ENUM:                r'\benum\b',

        TokenType.CONST:               r'\bconst\b',
        TokenType.LOCAL:               r'\blocal\b',
        TokenType.GAME:                r'\bgame\b',
        TokenType.SAVE:                r'\bsave\b',
        TokenType.VAR:                 r'\bvar\b',
        TokenType.BREAK:               r'\bbreak\b',
        # TokenType.EXTERNAL:            r'\bexternal\b',
        TokenType.RETURN:              r'\breturn\b',
        # TokenType.NEW:                 r'\bnew\b',
        TokenType.TRUE:                r'\btrue\b',
        TokenType.FALSE:               r'\bfalse\b',
        TokenType.WHILE:               r'\bwhile\b',
        TokenType.IF:                  r'\bif\b',
        TokenType.ELSE:                r'\belse\b',
        # TokenType.HERE:                r'\bhere\b',
        
        # TokenType.DEFINE:              r'%define\b',
        # TokenType.INCLUDE:             r'%include\b',
        TokenType.TARGET:              r'@all\b|@allmobs\b|@default\b|@damager\b|@victim\b|@selection\b|@killer\b|@shooter\b',
        TokenType.PRECENT:             r'%',

        TokenType.STRING:              r'[ubf]?r?("(?!"").*?(?<!\\)(\\\\)*?")',
        TokenType.STRING_VAR:              r'\$[ubf]?r?("(?!"").*?(?<!\\)(\\\\)*?")',
        TokenType.STYLED_TEXT:         r'[ubf]?r?(`(?!``).*?(?<!\\)(\\\\)*?`)',
        TokenType.IDENTIFIER:          r'[a-zA-Z_][a-zA-Z0-9_]*'
        # TokenType.CHAR:                 r"'\\0'|'\\n'|'\\r'|'\\''|'\\t'|'\\\\'|'[ -&(-~]'",
    }

    master_regex = re.compile('|'.join(
        f"(?P<G{name}>{pattern})" for name, pattern in token_definitions.items()
    ))

    def input(self, code: str, file: str) -> None:
        self.buffer = code
        self.pos = 0
        self.col = 1
        self.row = 1
        self.file = file

    def next_token(self) -> Token:
        # if position is at end, no more tokens
        if self.pos >= len(self.buffer):
            return None

        # Find first non whitespace character
        m = self.ws_skip.search(self.buffer, self.pos)

        if m:
            old_pos = self.pos
            self.pos = m.start()
            self.col += self.pos - old_pos
        else:
            # this means we didn't find a character meaning we're at the end
            return None

        # match against main regex
        m = self.master_regex.match(self.buffer, self.pos)

        if m:
            token_type = m.lastgroup

            if token_type == 'GIGNORE':
                self.pos = m.end()
                return self.next_token()

            elif token_type == 'GNEWLINE':
                self.row += 1
                self.col = 1
                self.pos = m.end()
                return self.next_token()

            string_repr = m.string[m.start():m.end()]
            token = Token(type= TokenType(int(token_type[1:])), value=string_repr, location=(self.file, self.row, self.col))

            old_pos = self.pos
            self.pos = m.end()

            self.col += self.pos - old_pos
            return token

        raise ScannerError(f"Unexpected character '{self.buffer[self.pos]}'", (self.file, self.row, self.col))

    def tokens(self) -> Iterator[Token]:
        # custom iterator
        while True:
            tok = self.next_token()
            if tok is None:
                yield Token(type=TokenType.EOF, value=None, location=(self.file, self.row, self.col))
                break
            yield tok
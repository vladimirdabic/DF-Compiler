from dataclasses import dataclass
from typing import List
from .scanner import TokenLocation, Token


@dataclass
class Type:
    name: str
    parameters: List[object] # List of types
    data: object = None

    def __str__(self):
        if len(self.parameters) == 0:
            return f"{self.name}"
        
        return f"{self.name}<{', '.join(str(param) for param in self.parameters)}>"

@dataclass
class NumberValue:
    value: float

@dataclass
class StringValue:
    value: str

@dataclass
class StyledTextValue:
    value: str

@dataclass
class Variable:
    name: str
    location: TokenLocation
    scope: str = None

@dataclass
class VectorValue:
    x: float
    y: float
    z: float

@dataclass
class ListValue:
    values: List[object]

@dataclass
class DictValue:
    values: List[tuple[str, object]]

@dataclass
class TopDefinitions:
    source: str
    definitions: List[object]

@dataclass
class FuncDefinition:
    name: str
    args: List[tuple[str, Type, bool, bool, bool, str]] # name, type, optional, pural, is out, desc
    # return_type: Type
    body: List[object]

@dataclass
class VarDefintion:
    name: str
    type: Type
    scope: str = "line"
    value: object = None

@dataclass
class AssignVar:
    name: str
    value: object 

@dataclass
class CallFunction:
    name: str
    args: List[object]

@dataclass
class CodeBlockStatement:
    action: str
    category: str
    target: str = None

@dataclass
class CallCB:
    codeblock: CodeBlockStatement
    args: List[object]

@dataclass
class BinaryOperation:
    left: object
    right: object
    operation: Token

@dataclass
class Cast:
    value: object
    type: Type

@dataclass
class Dictionary:
    data: List[tuple[str, object]] # (key, value) pairs

@dataclass
class ListValue:
    data: List[object] # value list

@dataclass
class Index:
    obj: object
    index: object
    location: TokenLocation

@dataclass
class SetIndex:
    obj: object
    index: object
    value: object
    location: TokenLocation
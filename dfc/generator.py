from . import nodes
from .scanner import TokenLocation, TokenType
from typing import List
from dataclasses import dataclass
import json
from . import diamondfire as df


class Environment:
    parent: object
    variables: dict[str, tuple[nodes.Type, str, bool]] # type, scope, is out
    functions: dict[str, nodes.FuncDefinition]

    def __init__(self, parent: object):
        self.parent = parent
        self.variables = {}
        self.functions = {}

    def get(self, var: str):
        if var in self.variables:
            return self.variables[var]
        
        if self.parent:
            return self.parent.get(var)
        
        return None
    
    def define(self, var: str, var_type: nodes.Type, scope: str, is_out: bool = False):
        self.variables[var] = (var_type, scope, is_out)

    def get_func(self, name: str):
        if name in self.functions:
            return self.functions[name]
        
        if self.parent:
            return self.parent.get_func(name)
        
        return None


class Generator:
    scope_bindings = {
        "line": "line",
        "var": "line",
        "game": "unsaved",
        "save": "saved",
        "local": "local"
    }

    # TODO: others
    type_bindings = {
        "str": "txt",
        "txt": "comp",
        "num": "num",
        "list": "list",
        "dict": "dict",
        "loc": "loc",
        "par": "part", # particle
        "pot": "pot", # potion
        "item": "item",
        "block": "block", # GOTTA CHECK THIS
        "any": "any",
    }

    arg_type_bindings = {
        "str": "TEXT",
        "txt": "COMPONENT",
        "num": "NUMBER",
        "loc": "LOCATION",
        "par": "PARTICLE",
        "vec": "VECTOR",
        "item": "ITEM",
        "block": "BLOCK",
        "any": "ANY_TYPE",
        "pot": "POTION",
        "dict": "DICT",
        "list": "LIST"
    }

    arg_type_bindings_inv = {v: k for k, v in arg_type_bindings.items()}

    # TODO: Entity bindings
    target_bindings = {
        "all": "AllPlayers",
        "allmobs": "AllMobs",
        "default": "Default",
        "damager": "Damager",
        "killer": "Killer",
        "victim": "Victim",
        "selection": "Selection",
        "shooter": "Shooter"
    }

    def set_action_data(self, df_action_dump):
        self.action_data = {
            "category": {},
            "ids": {}
        }

        df_data = json.loads(df_action_dump)
        for action in df_data["actions"]:
            if not action["codeblockName"] in self.action_data["category"]:
                self.action_data["category"][action["codeblockName"]] = {}

            self.action_data["category"][action["codeblockName"]][action["name"]] = action

        for cb in df_data["codeblocks"]:
            if cb["name"] in self.action_data["category"]:
                self.action_data["category"][cb["name"]]["id"] = cb["identifier"]

            if cb["identifier"] not in self.action_data["ids"]:
                self.action_data["ids"][cb["identifier"]] = cb
        
        df.ACTION_DATA = self.action_data

    def generate(self, tree) -> List[List[dict]]:
        if not isinstance(tree, nodes.TopDefinitions):
            raise ValueError("Tree must be definitions")
        
        self.env = Environment(parent=None)
        self.code_lines: List[df.Codeline] = []
        self.current_line: df.Codeline = None
        
        for definition in tree.definitions:
            if isinstance(definition, nodes.VarDefintion):
                self.env.define(definition.name, definition.type, definition.scope)

            elif isinstance(definition, nodes.FuncDefinition):
                self._generate_node(definition)

        return self.code_lines


    def _generate_node(self, node, expr_var_name: str = "__dfc_res"):
        name = type(node).__name__
        method = getattr(self, f"_generate_{name}", None)

        if not method:
            raise NotImplementedError(f"Generator for node type '{name}' hasn't been implemented.")

        return method(node, expr_var_name)

    def _generate_FuncDefinition(self, node: nodes.FuncDefinition, expr_var_name: str):
        self.env.functions[node.name] = node

        # external definition
        if node.body == None: return

        self.env = Environment(parent=self.env)

        self.current_line = df.Codeline(blocks=[])
        func_block = df.Codeblock(type='func', data=node.name, args=[])

        # generate arguments
        for i, arg in enumerate(node.args):
            # if it's plural it should be a list
            if arg[3]:
                self.env.define(arg[0], nodes.Type(name='list', parameters=[arg[1]]), "line", arg[4])
            else:
                self.env.define(arg[0], arg[1], "line", arg[4])

            arg_item = df.ParameterItem(
                slot=i,
                name=arg[0],
                type="var" if arg[4] else self.type_bindings[arg[1].name], # if its an out var use 'var' otherwise use the proper type
                desc=f"Argument #{i + 1}" if arg[5] == None else arg[5],
                plural=arg[3],
                optional=arg[2]
            )

            func_block.args.append(arg_item)


        self.current_line.append(func_block)

        # generate body
        for stmt in node.body:
            self._generate_node(stmt)

        # add code line to list of codelines
        self.code_lines.append(self.current_line)
        self.env = self.env.parent

    def _generate_VarDefintion(self, node: nodes.VarDefintion, expr_var_name: str):
        self.env.define(node.name, node.type, node.scope)

        if node.value:
            # should return tuple (type, dfitem)
            value = self._generate_node(node.value, expr_var_name=node.name)

            if not self.compare_types(node.type, value[0]):
                raise GeneratorError(f"Assigning a value of type '{value[0]}' to variable defined as '{node.type}'", node.location)
            
            if not isinstance(value[1], df.VariableItem):
                value[1].slot = 1
                self.current_line.append(df.Codeblock(
                    type='set_var',
                    action="=",
                    args=[
                        df.VariableItem(slot=0, name=node.name, scope=self.scope_bindings[node.scope]),
                        value[1]
                    ]
                ))

    def _generate_AssignVar(self, node: nodes.AssignVar, expr_var_name: str):
        var_data = self.env.get(node.name)

        if not var_data:
            raise GeneratorError(f"Assigning an undefined variable '{node.name}'", node.location)

        # tuple (type, dfitem)
        value = self._generate_node(node.value, expr_var_name=node.name)

        if not self.compare_types(var_data[0], value[0]):
            #raise GeneratorError(f"Assigning a value of type '{value[0].name}' to variable defined as '{var_data[0].name}'", node.location)
            raise GeneratorError(f"Assigning a value of type '{value[0]}' to variable defined as '{var_data[0]}'", node.location)
        
        if not isinstance(value[1], df.VariableItem):
            value[1].slot = 1
            self.current_line.append(df.Codeblock(
                    type='set_var',
                    action="=",
                    args=[
                        df.VariableItem(slot=0, name=node.name, scope=self.scope_bindings[var_data[1]]),
                        value[1]
                    ]
                ))

    def _generate_CallFunction(self, node: nodes.CallFunction, expr_var_name: str):
        func_data = self.env.get_func(node.name)

        if not func_data:
            raise GeneratorError(f"Undefined function '{node.name}'", node.location)

        if len(func_data.args) == 0 and len(node.args) != 0:
            raise GeneratorError(f"Function '{node.name}' takes no arguments", node.location)
                
        func_arg_iter = enumerate(func_data.args)
        current_func_arg = None
        is_plural = False
        is_optional = False
        is_last = False
        evaluated_args = []
        for i, arg in enumerate(node.args):
            # (type, dfitem)
            value = self._generate_node(arg, expr_var_name=f'__carg_{i}')
            arg_type: nodes.Type = value[0]
            dfitem: df.Item = value[1]

            # type checking
            if not is_plural and (not is_last):
                current_func_arg = next(func_arg_iter)
                is_plural = current_func_arg[1][3]
                is_optional = current_func_arg[1][2]

                if current_func_arg[0] == len(func_data.args) - 1:
                    is_last = True
                
            if not self.compare_types(current_func_arg[1][1], arg_type):
                if (is_plural or is_optional) and not is_last:
                    current_func_arg = next(func_arg_iter)
                    is_plural = current_func_arg[1][3]
                    is_optional = current_func_arg[1][2]

                    if current_func_arg[0] == len(func_data.args) - 1:
                        is_last = True

                    if not self.compare_types(current_func_arg[1][1], arg_type):
                        raise GeneratorError(f"Function parameter #{i + 1} expected '{current_func_arg[1][1]}' but got '{arg_type}'", node.location)

                else:
                    raise GeneratorError(f"Function parameter #{i + 1} expected '{current_func_arg[1][1]}' but got '{arg_type}'", node.location)

            dfitem.slot = i
            evaluated_args.append(dfitem)

        self.current_line.append(df.Codeblock(
            type="call_func",
            data=node.name,
            args = evaluated_args
        ))

    def _generate_CallCB(self, node: nodes.CallCB, expr_var_name: str):
        if node.codeblock.category not in self.action_data["category"]:
            raise GeneratorError(f"Unknown codeblock category '{node.codeblock.category}'", node.location)

        if node.codeblock.action not in self.action_data["category"][node.codeblock.category]:
            raise GeneratorError(f"Unknown action '{node.codeblock.action}' in codeblock category '{node.codeblock.category}'", node.location)

        action_data = self.action_data["category"][node.codeblock.category][node.codeblock.action]
        arg_data = action_data["icon"]["arguments"]


        cb_arg_iter = enumerate(arg_data)
        current_cb_arg = None
        is_plural = False
        is_optional = False
        is_last = False
        evaluated_args = []
        for i, arg in enumerate(node.args):
            # (type, dfitem)

            value = self._generate_node(arg, expr_var_name=f'__carg_{i}')
            arg_type: nodes.Type = value[0]
            dfitem: df.Item = value[1]

            # type checking
            if not is_plural and (not is_last):
                current_cb_arg = next(cb_arg_iter)
                is_plural = current_cb_arg[1]["plural"]
                is_optional = current_cb_arg[1]["optional"]

                if current_cb_arg[0] == len(arg_data) - 1:
                    is_last = True

            if not (current_cb_arg[1]["type"] == "VARIABLE" and type(arg) is nodes.Variable):
                if not self.compare_types_simple(current_cb_arg[1]["type"], self.arg_type_bindings[arg_type.name]):
                    if (is_plural or is_optional) and not is_last:
                        current_cb_arg = next(cb_arg_iter)
                        is_plural = current_cb_arg[1]["plural"]
                        is_optional = current_cb_arg[1]["optional"]

                        if current_cb_arg[0] == len(arg_data) - 1:
                            is_last = True

                        if not self.compare_types_simple(current_cb_arg[1]["type"], self.arg_type_bindings[arg_type.name]):
                            raise GeneratorError(f"Codeblock parameter #{i + 1} expected '{self.arg_type_bindings_inv[current_cb_arg[1]['type']]}' but got '{arg_type}'", node.location)

                    else:
                        raise GeneratorError(f"Codeblock parameter #{i + 1} expected '{self.arg_type_bindings_inv[current_cb_arg[1]['type']]}' but got '{arg_type}'", node.location)

            dfitem.slot = i
            evaluated_args.append(dfitem)

        block = df.Codeblock(
            type=self.action_data["category"][node.codeblock.category]["id"],
            action=node.codeblock.action,
            args=evaluated_args
        )

        if node.codeblock.target:
            block.target = self.target_bindings[node.codeblock.target]

        self.current_line.append(block)

    def _generate_BinaryOperation(self, node: nodes.BinaryOperation, expr_var_name: str):
        left = self._generate_node(node.left, expr_var_name="__bin_l")
        right = self._generate_node(node.right, expr_var_name="__bin_r")

        # TODO: MAKE WORK WITH OTHER TYPES (STR, COMBINING LISTS, VECTOR)
        if right[0].name != "num" or left[0].name != "num":
            raise GeneratorError(f"Currently only numbers are suppored for binary operations", node.operation.location)
        
        action = None

        match node.operation.type:
            case TokenType.PLUS:
                action = "+"
            
            case TokenType.MINUS:
                action = "-"

            case TokenType.STAR:
                action = "x"

            case TokenType.SLASH:
                action = "/"

            case TokenType.ARROW_UP:
                action = "Exponent"

        left[1].slot = 1
        right[1].slot = 2

        self.current_line.append(df.Codeblock(
            type='set_var',
            action=action,
            args=[
                df.VariableItem(slot=0, name=expr_var_name, scope='line'),
                left[1],
                right[1]
            ]
        ))

        return (nodes.Type(name='num', parameters=[]), df.VariableItem(slot=0, name=expr_var_name, scope='line'))
    
    def _generate_Index(self, node: nodes.Index, expr_var_name: str):
        # (type, dfitem)
        (obj_type, obj_item) = self._generate_node(node.obj)
        
        # TODO: Allow indexing into vector (.x, .y, .z)
        if obj_type.name not in ("str", "dict", "list"):
            raise GeneratorError(f"Cannot index into object of type '{obj_type}'", node.location)

        (idx_type, idx_item) = self._generate_node(node.index, expr_var_name='__idx')

        # TODO: Make this smaller, a lot of code is similar or same
        if obj_type.name == 'dict':
            if idx_type.name != 'str':
                raise GeneratorError(f"Cannot index into dictionary with key of type '{idx_type}' (must be a str)", node.location)
            
            obj_item.slot = 1
            idx_item.slot = 2
            self.current_line.append(df.Codeblock(
                type='set_var',
                action='GetDictValue',
                args=[
                    df.VariableItem(slot=0, name=expr_var_name, scope='line'),
                    obj_item,
                    idx_item
                ]
            ))

            expected_type = obj_type.parameters[0] if len(obj_type.parameters) != 0 else nodes.Type(name='any', parameters=[])
            return (expected_type, df.VariableItem(slot=0, name=expr_var_name, scope='line'))

        elif obj_type.name == 'list':
            # TODO: if str, check if it's a list function (.pop, .insert, .append, .sort, .expand, .index, .reverse, .trim) 
            # and generate the appropriate codeblocks for that, same goes for dict

            if idx_type.name != 'num':
                raise GeneratorError(f"Cannot index into list with key of type '{idx_type}' (must be a num)", node.location)
            
            obj_item.slot = 1
            idx_item.slot = 2
            self.current_line.append(df.Codeblock(
                type='set_var',
                action='GetListValue',
                args=[
                    df.VariableItem(slot=0, name=expr_var_name, scope='line'),
                    obj_item,
                    idx_item
                ]
            ))

            expected_type = obj_type.parameters[0] if len(obj_type.parameters) != 0 else nodes.Type(name='any', parameters=[])
            return (expected_type, df.VariableItem(slot=0, name=expr_var_name, scope='line'))

        elif obj_type.name == 'str':
            pass


    def _generate_SetIndex(self, node: nodes.SetIndex, expr_var_name: str):
        # (type, dfitem)
        (obj_type, obj_item) = self._generate_node(node.obj)
        
        # TODO: Allow indexing into vector (.x, .y, .z)
        if obj_type.name not in ("dict", "list"):
            raise GeneratorError(f"Cannot index into object of type '{obj_type}'", node.location)

        (idx_type, idx_item) = self._generate_node(node.index, expr_var_name='__idx')
        (value_type, value_item) = self._generate_node(node.value, expr_var_name='__value')

        if obj_type.name == 'dict':
            if idx_type.name != 'str':
                raise GeneratorError(f"Cannot index into dictionary with key of type '{idx_type}' (must be a str)", node.location)
            
            # compare types
            expected_type = obj_type.parameters[0] if len(obj_type.parameters) != 0 else nodes.Type(name='any', parameters=[])
            if not self.compare_types(expected_type, value_type):
                raise GeneratorError(f"Dictionary expected value of type '{expected_type}' but instead got '{value_type}'", node.location)

            #obj_item.slot = 0
            idx_item.slot = 1
            value_item.slot = 2
            self.current_line.append(df.Codeblock(
                type='set_var',
                action='SetDictValue',
                args=[
                    obj_item,
                    idx_item,
                    value_item
                ]
            ))

            return (value_type, value_item)

        # TODO
        elif obj_type.name == 'list':
            if idx_type.name != 'num':
                raise GeneratorError(f"Cannot index into list with key of type '{idx_type}' (must be a num)", node.location)
            
            # compare types
            expected_type = obj_type.parameters[0] if len(obj_type.parameters) != 0 else nodes.Type(name='any', parameters=[])
            if not self.compare_types(expected_type, value_type):
                raise GeneratorError(f"List expected value of type '{expected_type}' but instead got '{value_type}'", node.location)

            #obj_item.slot = 0
            idx_item.slot = 1
            value_item.slot = 2
            self.current_line.append(df.Codeblock(
                type='set_var',
                action='SetListValue',
                args=[
                    obj_item,
                    idx_item,
                    value_item
                ]
            ))

            return (value_type, value_item)

    def _generate_Cast(self, node: nodes.Cast, expr_var_name: str):
        (val_type, dfitem) = self._generate_node(node.value)

        node.type.data = val_type.data
        return (node.type, dfitem)

    def _generate_Variable(self, node: nodes.Variable, expr_var_name: str):
        # TODO: Check if scope is not None

        # check if defined
        var_type = self.env.get(node.name)
        if not var_type:
            raise GeneratorError(f"Undefined variable '{node.name}'", node.location)

        return (var_type[0], df.VariableItem(slot=0, name=node.name, scope=self.scope_bindings[var_type[1]]))
    
    def _generate_NumberValue(self, node: nodes.NumberValue, expr_var_name: str):
        return (nodes.Type(name='num', parameters=[]), df.NumberItem(slot=0, value=node.value))
    
    def _generate_StringValue(self, node: nodes.StringValue, expr_var_name: str):
        return (nodes.Type(name='str', parameters=[]), df.StringItem(slot=0, value=node.value))
    
    def _generate_StyledTextValue(self, node: nodes.StyledTextValue, expr_var_name: str):
        return (nodes.Type(name='txt', parameters=[]), df.StyledTextItem(slot=0, value=node.value))
    
    def _generate_VectorValue(self, node: nodes.VectorValue, expr_var_name: str):
        return (nodes.Type(name='vec', parameters=[]), df.VectorItem(slot=0, x=node.x, y=node.y, z=node.z))
    
    def _generate_Dictionary(self, node: nodes.Dictionary, expr_var_name: str):
        self.current_line.append(df.Codeblock(
            type = 'set_var',
            action = 'CreateDict',
            args = [
                df.VariableItem(slot=0, name=expr_var_name, scope='line')
            ]
        ))


        data = []
        # set values
        for (key, value) in node.data:
            evaluated_value = self._generate_node(value) # using default variable evaluation name, maybe change in future but probably not needed
            evaluated_value[1].slot = 2
            
            self.current_line.append(df.Codeblock(
                type = 'set_var',
                action = 'SetDictValue',
                args = [
                    df.VariableItem(slot=0, name=expr_var_name, scope='line'),
                    df.StringItem(slot=1, value=key),
                    evaluated_value[1]
                ]
            ))

            data.append((key, evaluated_value))

        return (nodes.Type(name='dict', parameters=[nodes.Type(name='any', parameters=[])], data=data), df.VariableItem(slot=0, name=expr_var_name, scope='line'))
    
    # TODO: List, Potion, Particle, Game Value
    def _generate_ListValue(self, node: nodes.ListValue, expr_var_name: str):
        items = []
        data = []
        # items
        for i, value in enumerate(node.data):
            evaluated_value = self._generate_node(value, expr_var_name=f"__list_{i}") # using default variable evaluation name, maybe change in future but probably not needed
            evaluated_value[1].slot = i + 1

            items.append(evaluated_value[1])
            data.append(evaluated_value)

        self.current_line.append(df.Codeblock(
            type = 'set_var',
            action = 'CreateList',
            args = [
                df.VariableItem(slot=0, name=expr_var_name, scope='line'),
                *items
            ]
        ))

        return (nodes.Type(name='list', parameters=[nodes.Type(name='any', parameters=[])], data=data), df.VariableItem(slot=0, name=expr_var_name, scope='line'))

    def compare_types(self, type1: nodes.Type, type2: nodes.Type) -> bool:
        if type1.name == 'any': return True
        if type1.name != type2.name: return False

        if len(type1.parameters) != len(type2.parameters): return False

        # dictionary checking
        if type1.name == 'dict' and type2.name == 'dict':
            expected_value_type = type1.parameters[0] if len(type1.parameters) != 0 else nodes.Type(name='any', parameters=[])

            if type2.data is None:
                t2_type = type2.parameters[0] if len(type2.parameters) != 0 else nodes.Type(name='any', parameters=[])
                return self.compare_types(expected_value_type, t2_type)

            # key (str), value (tuple[type, dfitem])
            for (key, (entry_type, entry_item)) in type2.data:
                if not self.compare_types(expected_value_type, entry_type):
                    return False
                
            return True
        
        if type1.name == 'list' and type2.name == 'list':
            expected_value_type = type1.parameters[0] if len(type1.parameters) != 0 else nodes.Type(name='any', parameters=[])

            if type2.data is None:
                t2_type = type2.parameters[0] if len(type2.parameters) != 0 else nodes.Type(name='any', parameters=[])
                return self.compare_types(expected_value_type, t2_type)

            # value (tuple[type, dfitem])
            for (entry_type, entry_item) in type2.data:
                if not self.compare_types(expected_value_type, entry_type):
                    return False
                
            return True


        for arg1, arg2 in zip(type1.parameters, type2.parameters):
            if not self.compare_types(arg1, arg2): return False

        return True
    
    def compare_types_simple(self, type1: str, type2: str) -> bool:
        if type1 == 'any': return True
        if type1 == 'ANY_TYPE': return True
        return type1 == type2


    def give_command(self):
        items = []
        for i, code_line in enumerate(self.code_lines):
            items.append(code_line._nbt(i))

        return f"""/give @p minecraft:shulker_box{{BlockEntityTag:{{Items:[{','.join(items)}]}}, display:{{Name:'[{{"text": "DFCompiler Program", "color": "light_purple", "italic": "false"}}]'}}}}"""
    
class GeneratorError(Exception):
    def __init__(self, msg, location: TokenLocation) -> None:
        self.msg = msg
        self.location = location

    def __repr__(self) -> str:
        return "%s:%d:%d: [ERROR]: %s" % (self.location + (self.msg,))

    def __str__(self) -> str:
        return "%s:%d:%d: [ERROR]: %s" % (self.location + (self.msg,))
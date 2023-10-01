from . import nodes
from .scanner import Token, TokenLocation, TokenType
from typing import List


class Parser:
    tokens: List[Token]
    current: int
    constants: dict[str, object]
    precedence: dict[TokenType, int] = {
        TokenType.PLUS: (10, True),
        TokenType.MINUS: (10, True),
        TokenType.STAR: (20, True),
        TokenType.SLASH: (20, True),
        TokenType.ARROW_UP: (30, False), # False = right associativity
    }

    def parse(self, tokens: List[Token], source: str) -> nodes.TopDefinitions:
        self.tokens = tokens
        self.current = 0
        self.constants = {}
        defs = []

        while self.available():
            vdef = self.parse_def()
            if vdef:
                defs.append(vdef)

        return nodes.TopDefinitions(source=source, definitions=defs)


    def parse_def(self):
        if self.match(TokenType.GAME, TokenType.SAVE):
            tok = self.prev()
            #name = self.consume(TokenType.IDENTIFIER, "Expected variable name")
            name = self.prev().value[2:-1] if self.match(TokenType.STRING_VAR) else self.consume(TokenType.IDENTIFIER, "Expected variable name").value
            self.consume(TokenType.COLON, "Expected variable type")
            var_type = self.parse_type("Expected variable type")
            self.consume(TokenType.SEMICOLON, "Expected ';' after variable definition")
            return nodes.VarDefintion(scope=tok.value, name=name, type=var_type)

        if self.match(TokenType.FUNC):
            return self.parse_func()

        if self.match(TokenType.CONST):
            name = self.consume(TokenType.IDENTIFIER, "Expected constant name")
            self.consume(TokenType.EQUALS, "Expected '='")
            value = self.parse_expr()
            self.consume(TokenType.SEMICOLON, "Expected ';' after expression")
            self.constants[name.value] = value
            return None


        self.error("Expected definition")

    def parse_func(self):
        name = self.consume(TokenType.IDENTIFIER, "Expected function name")
        self.consume(TokenType.OPEN_PAREN, "Expected '('")
        
        args = []
        while self.peek().type != TokenType.CLOSE_PAREN:
            out = self.match(TokenType.OUT)
            arg_name = self.consume(TokenType.IDENTIFIER, "Expected function argument name")
            self.consume(TokenType.COLON, "Expected function argument type")
            arg_type = self.parse_type("Expected function argument type")

            pural = self.match(TokenType.VARARGS)
            optional = self.match(TokenType.QUESTION_MARK)

            desc = self.prev() if self.match(TokenType.STRING) else None

            if self.peek().type != TokenType.CLOSE_PAREN:
                self.consume(TokenType.COMMA, "Expected ',' or ')' after function argument")

            args.append((arg_name.value, arg_type, optional, pural, out, None if desc == None else desc.value[1:-1]))

        self.consume(TokenType.CLOSE_PAREN, "Expected ')'")

        # external function definition [ func a(x: num); ]
        if self.match(TokenType.SEMICOLON):
            return nodes.FuncDefinition(name = name.value, args=args, body=None)

        self.consume(TokenType.OPEN_BRACE, "Expected '{' to start function body")

        body = []
        while self.peek().type != TokenType.CLOSE_BRACE:
            loc = self.peek().location
            stmt = self.parse_statement()
            stmt.location = loc
            body.append(stmt)

        self.consume(TokenType.CLOSE_BRACE, "Expected '}' to close function body")
        return nodes.FuncDefinition(name = name.value, args=args, body=body)
    
    def parse_statement(self):
        if self.match(TokenType.GAME, TokenType.SAVE, TokenType.VAR, TokenType.LOCAL):
            tok = self.prev()
            name = self.prev().value[2:-1] if self.match(TokenType.STRING_VAR) else self.consume(TokenType.IDENTIFIER, "Expected variable name").value
            self.consume(TokenType.COLON, "Expected variable type")
            var_type = self.parse_type("Expected variable type")
            value = self.parse_expr() if self.match(TokenType.EQUALS) else None
            self.consume(TokenType.SEMICOLON, "Expected ';' after variable definition")
            return nodes.VarDefintion(scope=tok.value, name=name, type=var_type, value=value)
        
        tok = self.peek()
        expr = self.parse_expr()
        # TODO: Check if it's only a valid statement (assignment)

        if not isinstance(expr, (nodes.AssignVar, nodes.CallFunction, nodes.CodeBlockStatement, nodes.CallCB, nodes.SetIndex)):
            self.error("Expected statement, got expression", tok)

        self.consume(TokenType.SEMICOLON, "Expected ';' after statement")
        return expr
        
    def parse_expr(self):
        return self.parse_assign()
    
    def parse_assign(self):
        left = self.parse_bin_op()

        if self.match(TokenType.EQUALS):
            eq = self.prev()
            if type(left) is nodes.Variable:
                value = self.parse_expr()
                left = nodes.AssignVar(name=left.name, value=value)

            elif type(left) is nodes.Index:
                value = self.parse_expr()
                left = nodes.SetIndex(obj=left.obj, index=left.index, value=value, location=eq.location)

        return left
    
    def parse_bin_op(self, prec_level: int = 0):
        left = self.parse_call()

        while True:
            if not self.available(): break
            token = self.peek()
            if token.type not in self.precedence: break # not an operator
            prec_data = self.precedence[token.type]
            if prec_data[0] < prec_level: break # precedence is too low, skip

            self.advance() # consume operator token

            right = self.parse_bin_op(prec_level + 1 if prec_data[1] else prec_level)
            left = nodes.BinaryOperation(left=left, right=right, operation=token)

        return left
    
    def parse_call(self):
        left = self.parse_index()

        if self.match(TokenType.OPEN_PAREN):
            if isinstance(left, nodes.Variable):
                args = []

                while self.peek().type != TokenType.CLOSE_PAREN:
                    args.append(self.parse_expr())

                    if self.peek().type != TokenType.CLOSE_PAREN:
                        self.consume(TokenType.COMMA, "Expected ',' after argument")

                self.consume(TokenType.CLOSE_PAREN, "Expected ')' after function call arguments")
                left = nodes.CallFunction(name=left.name, args=args)

            elif isinstance(left, nodes.CodeBlockStatement):
                args = []

                while self.peek().type != TokenType.CLOSE_PAREN:
                    args.append(self.parse_expr())

                    if self.peek().type != TokenType.CLOSE_PAREN:
                        self.consume(TokenType.COMMA, "Expected ',' after argument")

                self.consume(TokenType.CLOSE_PAREN, "Expected ')' after call arguments")
                left = nodes.CallCB(codeblock=left, args=args)


        return left
    
    def parse_index(self):
        left = self.parse_primary()

        while True:
            if self.match(TokenType.OPEN_SQUARE):
                loc = self.prev().location
                idx = self.parse_expr()
                self.consume(TokenType.CLOSE_SQUARE, "Expected ']' after index")
                left = nodes.Index(obj=left, index=idx, location=loc)
            elif self.match(TokenType.DOT):
                loc = self.prev().location
                idx = self.consume(TokenType.IDENTIFIER, "Expected index name after '.'")
                left = nodes.Index(obj=left, index=nodes.StringValue(value=idx.value), location=loc)
            else:
                break

        return left

    def parse_primary(self):
        target = None
        if self.match(TokenType.TARGET):
            target = self.prev().value[1:]

        if self.match(TokenType.CODEBLOCK):
            action = self.consume(TokenType.STRING, "Expected codeblock action (as string)")
            self.consume(TokenType.LOWER, "Expected '<'")
            category = self.consume(TokenType.STRING, "Expected codeblock category as string")
            self.consume(TokenType.GREATER, "Expected '>'")
            return nodes.CodeBlockStatement(action=action.value[1:-1], category=category.value[1:-1], target=target)

        if self.match(TokenType.IDENTIFIER):
            # CONST VALUE
            name = self.prev().value
            if name in self.constants:
                value = self.constants[name]

                if isinstance(value, nodes.CodeBlockStatement):
                    return nodes.CodeBlockStatement(action=value.action, category=value.category, target=target if target != None else value.target)

                return value

            return nodes.Variable(name=name, location=self.prev().location)
        
        if self.match(TokenType.STRING_VAR):
            # CONST VALUE
            name = self.prev().value[2:-1]
            if name in self.constants:
                value = self.constants[name]

                if isinstance(value, nodes.CodeBlockStatement):
                    return nodes.CodeBlockStatement(action=value.action, category=value.category, target=target if target != None else value.target)

                return value

            return nodes.Variable(name=name, location=self.prev().location)

        if self.match(TokenType.NUMBER):
            return nodes.NumberValue(value=float(self.prev().value))
        
        if self.match(TokenType.STRING):
            return nodes.StringValue(value=self.prev().value[1:-1])
        
        if self.match(TokenType.STYLED_TEXT):
            return nodes.StyledTextValue(value=self.prev().value[1:-1])
        
        # vector
        if self.match(TokenType.LOWER):
            x_component = self.consume(TokenType.NUMBER, "Expected x component of vector")
            self.consume(TokenType.COMMA, "Expected ','")
            y_component = self.consume(TokenType.NUMBER, "Expected y component of vector")
            self.consume(TokenType.COMMA, "Expected ','")
            z_component = self.consume(TokenType.NUMBER, "Expected z component of vector")
            self.consume(TokenType.GREATER, "Expected '>' after vector components")

            return nodes.VectorValue(x=float(x_component.value), y=float(y_component.value), z=float(z_component.value))
        
        if self.match(TokenType.OPEN_PAREN):
            if self.match(TokenType.TYPE):
                self.current -= 1
                cast_type = self.parse_type("Expected type in cast")
                self.consume(TokenType.CLOSE_PAREN, "Expected ')' after cast type")
                expr = self.parse_expr()
                return nodes.Cast(value=expr, type=cast_type)

            expr = self.parse_expr()
            self.consume(TokenType.CLOSE_PAREN, "Expected ')' after expression")
            return expr
        
        if self.match(TokenType.OPEN_BRACE):
            data = []

            if self.peek().type != TokenType.CLOSE_BRACE:
                while True:
                    key = self.consume(TokenType.STRING, "Expected dictionary key (string)")
                    self.consume(TokenType.COLON, "Expected ':' after dictionary key")
                    value = self.parse_expr()
                    data.append((key.value[1:-1], value))
                    if self.peek().type == TokenType.CLOSE_BRACE: break
                    self.consume(TokenType.COMMA, "Expected ',' after dictionary entry")


            self.consume(TokenType.CLOSE_BRACE, "Expected '}' after dictionary")
            return nodes.Dictionary(data=data)

        if self.match(TokenType.OPEN_SQUARE):
            data = []

            if self.peek().type != TokenType.CLOSE_SQUARE:
                while True:
                    value = self.parse_expr()
                    data.append(value)
                    if self.peek().type == TokenType.CLOSE_SQUARE: break
                    self.consume(TokenType.COMMA, "Expected ',' after list value")


            self.consume(TokenType.CLOSE_SQUARE, "Expected ']' after list")
            return nodes.ListValue(data=data)

        self.error("Expected expression")

    def parse_type(self, msg: str = "Expected type"):
        args = []
        typ = self.consume(TokenType.TYPE, msg)
        
        if self.match(TokenType.LOWER):
            while True:
                args.append(self.parse_type())

                if self.peek().type != TokenType.GREATER:
                    self.consume(TokenType.COMMA, "Expected ',' after type in type template")
                else:
                    break

            self.consume(TokenType.GREATER, "Expected '>' to close type template")

        return nodes.Type(name=typ.value, parameters=args)

    # helper funcs
    def consume(self, type: TokenType, err: str) -> Token:
        if self.peek().type != type:
            raise ParserError(err, self.peek().location)
        
        return self.advance()

    def peek(self, ahead: int = 0) -> Token:
        return self.tokens[self.current + ahead]

    def available(self) -> bool:
        return self.peek().type != TokenType.EOF

    def match(self, *types: TokenType) -> bool:
        for type in types:
            if self.peek().type == type:
                self.current += 1
                return True
        
        return False

    def prev(self) -> Token:
        return self.tokens[self.current - 1]

    def advance(self) -> Token:
        token = self.tokens[self.current]
        self.current += 1
        return token
    
    def error(self, err: str, token: Token = None) -> Token:
        if not token: token = self.peek()
        raise ParserError(err, token.location)
        
    

class ParserError(Exception):
    def __init__(self, msg, location: TokenLocation) -> None:
        self.msg = msg
        self.location = location

    def __repr__(self) -> str:
        return "%s:%d:%d: [ERROR]: %s" % (self.location + (self.msg,))

    def __str__(self) -> str:
        return "%s:%d:%d: [ERROR]: %s" % (self.location + (self.msg,))
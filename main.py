import dfc

scanner = dfc.Scanner()
parser = dfc.Parser()
generator = dfc.Generator()

f = open("test.dfc", "r")
code = f.read()
f.close()

f = open("actiondump.json", "rb")
actiondump = f.read()
f.close()

scanner.input(code, "test.dfc")
tokens = list(scanner.tokens())
tree = parser.parse(tokens, "test.dfc")

generator.set_action_data(actiondump)
lines = generator.generate(tree)

#print(lines)
#print(lines[1].generate())

print(generator.give_command())
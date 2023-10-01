from dataclasses import dataclass
from typing import List
from abc import ABC, abstractmethod
import gzip, base64, json

ACTION_DATA: dict = None

class Item(ABC):
    slot: int
    id: str

    def __init__(self, slot: int = 0) -> None:
        self.slot = slot

    @abstractmethod
    def generate(self) -> dict:
        return {
            "item": {
                "id": self.id,
                "data": {}
            },
            "slot": self.slot
        }

class TagItem(Item):
    block: str
    action: str
    tag: str
    option: str = None

    def __init__(self, slot: int, block: str, action: str, tag: str) -> None:
        super().__init__(slot = slot)
        self.id = "bl_tag"
        self.block = block
        self.action = action
        self.tag = tag

    def generate(self) -> dict:
        obj = super().generate()

        obj["item"]["data"]["block"] = self.block
        obj["item"]["data"]["action"] = self.action
        obj["item"]["data"]["option"] = self.option
        obj["item"]["data"]["tag"] = self.tag
        
        return obj


class StringItem(Item):
    value: str

    def __init__(self, slot: int, value: str) -> None:
        super().__init__(slot=slot)
        self.id = "txt"
        self.value = value

    def generate(self) -> dict:
        obj = super().generate()
        obj["item"]["data"]["name"] = self.value
        return obj
    
class NumberItem(Item):
    value: float

    def __init__(self, slot: int, value: float) -> None:
        super().__init__(slot=slot)
        self.id = "num"
        self.value = value

    def generate(self) -> dict:
        obj = super().generate()
        obj["item"]["data"]["name"] = str(self.value)
        return obj
    
# NEW NAME: TEXT
class StyledTextItem(Item):
    value: str

    def __init__(self, slot: int, value: str) -> None:
        super().__init__(slot=slot)
        self.id = "comp"
        self.value = value

    def generate(self) -> dict:
        obj = super().generate()
        obj["item"]["data"]["name"] = self.value
        return obj
    
class VariableItem(Item):
    name: str
    scope: str

    def __init__(self, slot: int, name: str, scope: str) -> None:
        super().__init__(slot=slot)
        self.id = "var"
        self.name = name
        self.scope = scope

    def generate(self) -> dict:
        obj = super().generate()
        obj["item"]["data"]["name"] = self.name
        obj["item"]["data"]["scope"] = self.scope
        return obj
    
class VectorItem(Item):
    x: float
    y: float
    z: float

    def __init__(self, slot: int, x: float, y: float, z: float) -> None:
        super().__init__(slot=slot)
        self.id = "vec"
        self.x = x
        self.y = y
        self.z = z

    def generate(self) -> dict:
        obj = super().generate()
        obj["item"]["data"]["x"] = self.x
        obj["item"]["data"]["y"] = self.y
        obj["item"]["data"]["z"] = self.z
        return obj

class ParameterItem(Item):
    name: str
    type: str
    description: str
    plural: bool
    optional: bool

    def __init__(self, slot: int, name: str, type: str, desc: str, plural: bool = False, optional: bool = False) -> None:
        super().__init__(slot=slot)
        self.id = "pn_el"
        self.name = name
        self.type = type
        self.description = desc
        self.plural = plural
        self.optional = optional

    def generate(self) -> dict:
        obj = super().generate()
        obj["item"]["data"]["name"] = self.name
        obj["item"]["data"]["type"] = self.type
        obj["item"]["data"]["optional"] = self.optional
        obj["item"]["data"]["plural"] = self.plural
        obj["item"]["data"]["description"] = self.description
        return obj


@dataclass
class Codeblock:
    type: str
    data: str = None # for func, proc, call func, call proc
    action: str = None
    args: List[Item] = None
    target: str = None
    tags: dict = None
    # tag_items: List[TagItem] = None

    def __post_init__(self):
        self.tags = {}

        # ODD CASES: FUNCTION, PROCESS, CALL FUNCTION, START PROCESS

        cb_name = ACTION_DATA["ids"][self.type]["name"]

        if self.type in ('func', 'call_func', 'process', 'start_process'):
            self.action = 'dynamic'

        tag_data = ACTION_DATA["category"][cb_name][self.action]["tags"]

        for tag in tag_data:
            # tag_item = TagItem(slot=tag["slot"], block=self.type, action=self.action, tag=tag["name"])
            # tag_item.option = tag["defaultOption"]

            self.tags[tag["name"]] = tag["defaultOption"]


    def generate(self) -> dict:
        args = [arg.generate() for arg in self.args]
        self._setup_tags(args)

        obj = {
            "id": "block",
            "block": self.type,
            "args": {"items": args}
        }

        if self.data:
            obj["data"] = self.data

        if self.action and self.action != 'dynamic':
            obj["action"] = self.action

        if self.target:
            obj["target"] = self.target
            
        return obj
    
    def _setup_tags(self, args: List[Item]):
        cb_name = ACTION_DATA["ids"][self.type]["name"]
        tag_data = ACTION_DATA["category"][cb_name][self.action]["tags"]

        for tag in tag_data:
            current_option = self.tags[tag["name"]]
            for option in tag["options"]:
                if current_option == option["name"]:
                    break
            else:
                raise ValueError(f"Invalid value '{current_option}' of tag '{tag['name']}' for action '{self.action}' in codeblock '{cb_name}'")
    
            tag_item = TagItem(slot=tag["slot"], block=self.type, action=self.action, tag=tag["name"])
            tag_item.option = current_option

            args.append(tag_item.generate())

@dataclass
class Codeline:
    blocks: List[Codeblock]

    def append(self, block: Codeblock):
        self.blocks.append(block)

    def generate(self) -> List[dict]:
        return [block.generate() for block in self.blocks]

    # Use this to return base64 template data
    def template_data(self):
        compressed = gzip.compress(json.dumps({"blocks": self.generate()}).encode('utf-8'))
        return base64.b64encode(compressed).decode("utf-8")

    # _nbt is only used internally
    def _nbt(self, curslot):
        return f"""{{id: "minecraft:ender_chest", Slot: {curslot}b, Count:1b, tag:{{display:{{Name:'{{"text":"Template #{curslot + 1}", "color": "aqua"}}'}}, PublicBukkitValues:{{"hypercube:codetemplatedata":'{{"author":"DFCompiler","name":"&bDFCompiler Template","version":1,"code":"{self.template_data()}"}}'}}}}}}"""
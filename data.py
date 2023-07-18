import redis
from redis.commands.json.path import Path
import redis.commands.search.aggregation as aggregations
import redis.commands.search.reducers as reducers
from redis.commands.search.field import TextField, NumericField, TagField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import NumericFilter, Query

class DatabaseMissingValueException(Exception):
    pass

def check(val, name=""):
    if val is None:
        raise DatabaseMissingValueException(f"Value {name+' '} is None in database")
    return val

CLASSES = {
    "BIOH":"Biohacker",
    "ENVO":"Envoy",
    "EVOL":"Evolucionist",
    "MECH":"Mechanic",
    "MYST":"Mystic",
    "NANO":"Nanocyte",
    "OPER":"Operative",
    "PREC":"Precog",
    "SOLA":"Solarian",
    "SOLD":"Soldier",
    "TECH":"Technomancer",
    "VANG":"Vanguard",
    "WITC":"Witchwarper",
}

def new_pc(_name:str, _floor:int, _class:str):
    if _class not in CLASSES.keys():
        raise Exception("New PC: Invalid class key")
    return {
        "name":_name,
        "credits":0,
        "floor":int(_floor),
        "dt":0,
        "classes":[_class]
    }

class database:
    r:redis.Redis = None
    
    def __init__(self, connection:redis.Redis):
        self.r = connection
    def user_list(self):
        return self.r.lrange("USER_LIST", 0, -1)
    def get_pc_name(self, user_id):
        return check(self.r.get(user_id)).decode("utf-8")
    
    def get_pc(self, user_id, pc_name):
        return check(self.r.json().get(f"{user_id}:{pc_name}", "$"))[0]

    def register(self, user_id, pc_name, pc_floor, pc_class):
        pc = new_pc(pc_name, pc_floor, pc_class)
        self.r.json().set(f"{user_id}:{pc_name}", "$", pc)
        self.r.set(user_id, pc_name)
        self.r.lpush("USER_LIST", user_id)

    def unregister(self, user_id):
        self.r.delete(user_id)
        self.r.lrem("USER_LIST", 1, user_id)

    def update_pc(self, user_id, pc_name, updated_pc):
        self.r.json().set(f"{user_id}:{pc_name}", "$", updated_pc)

    def replace_val(self, user_id, pc_name, key:str, new_val):
        self.r.json().set(f"{user_id}:{pc_name}", f"$.{key}", new_val)

    def update_int_val(self, user_id, pc_name, key:str, delta:int, replace=False, can_go_negative=False):
        old_value = check(self.r.json().get(f"{user_id}:{pc_name}", f"$.{key}"))[0]
        updated_value = delta if replace else old_value+delta
        if not can_go_negative and updated_value<0:
            return (False, old_value, old_value)
        else:
            self.r.json().set(f"{user_id}:{pc_name}", f"$.{key}", updated_value)
            return (True, old_value, updated_value)

    




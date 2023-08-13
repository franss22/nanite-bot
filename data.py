import redis
import os
from redis.commands.json.path import Path
import redis.commands.search.aggregation as aggregations
import redis.commands.search.reducers as reducers
from redis.commands.search.field import TextField, NumericField, TagField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import NumericFilter, Query
import functools


class DatabaseMissingValueException(Exception):
    pass


def check(val, name=""):
    if val is None:
        raise DatabaseMissingValueException(f"Value {name+' '} is None in database")
    return val


CLASSES = {
    "BIOH": "Biohacker",
    "ENVO": "Envoy",
    "EVOL": "Evolucionist",
    "MECH": "Mechanic",
    "MYST": "Mystic",
    "NANO": "Nanocyte",
    "OPER": "Operative",
    "PREC": "Precog",
    "SOLA": "Solarian",
    "SOLD": "Soldier",
    "TECH": "Technomancer",
    "VANG": "Vanguard",
    "WITC": "Witchwarper",
}


def new_pc(_name: str, _floor: int, _class: str):
    if _class not in CLASSES.keys():
        raise Exception("New PC: Invalid class key")
    return {
        "name": _name,
        "credits": 0,
        "floor": int(_floor),
        "dt": 0,
        "classes": [_class],
    }


class database:
    r: redis.Redis = None

    def __init__(self):
        # self.connect()
        pass

    def connect(self):
        self.r = redis.StrictRedis.from_url(
            os.environ.get("REDIS_URL"), 
            health_check_interval=30,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            socket_keepalive=True
        )

    def disconnect(self):
        self.r.close()

    def check_connection(self, retry=5):
        pass
        # if retry <= 0:
        #     raise Exception("Connection to redis server lost, retries finished.")
        # try:
        #     self.r.ping()
        # except:
        #     self.connect()
        #     self.check_connection(retry - 1)

    def redis_connection(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            self.connect()
            a = func(self, *args, **kwargs)
            self.disconnect()
            return a
        return wrapper

    @redis_connection
    def user_list(self):
        return self.r.lrange("USER_LIST", 0, -1)

    @redis_connection
    def get_pc_name(self, user_id):
        self.check_connection()
        return check(self.r.get(user_id)).decode("utf-8")

    @redis_connection
    def get_pc(self, user_id, pc_name):
        return check(self.r.json().get(f"{user_id}:{pc_name}", "$"))[0]

    @redis_connection
    def register(self, user_id, pc_name, pc_floor, pc_class):
        pc = new_pc(pc_name, pc_floor, pc_class)
        self.r.json().set(f"{user_id}:{pc_name}", "$", pc)
        self.r.set(user_id, pc_name)
        self.r.lpush("USER_LIST", user_id)

    @redis_connection
    def unregister(self, user_id):
        self.r.delete(user_id)
        self.r.lrem("USER_LIST", 1, user_id)

    @redis_connection
    def update_pc(self, user_id, pc_name, updated_pc):
        self.r.json().set(f"{user_id}:{pc_name}", "$", updated_pc)

    @redis_connection
    def replace_val(self, user_id, pc_name, key: str, new_val):
        self.r.json().set(f"{user_id}:{pc_name}", f"$.{key}", new_val)

    @redis_connection
    def update_int_val(
        self,
        user_id,
        pc_name,
        key: str,
        delta: int,
        replace=False,
        can_go_negative=False,
    ):
        old_value = check(self.r.json().get(f"{user_id}:{pc_name}", f"$.{key}"))[0]
        updated_value = delta if replace else old_value + delta
        if not can_go_negative and updated_value < 0:
            return (False, old_value, old_value)
        else:
            self.r.json().set(f"{user_id}:{pc_name}", f"$.{key}", updated_value)
            return (True, old_value, updated_value)

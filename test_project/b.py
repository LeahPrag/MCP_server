import utils.e as e
from utils.c import add as add_nums, multiply
from utils.e import AuditLogger
from a import Divider
from utils.d import User


def process(value: int) -> float:
    e.log("b.process")                  # function -> function
    x = add_nums(value, 7)              # alias -> utils/c.py:add
    y = multiply(value, 3)              # function -> utils/c.py:multiply -> Multiplier.mul -> log
    d = Divider()
    out = d.divide(x, y)                # method call -> a.py:Divider.divide -> div + log
    AuditLogger().audit("process done") # method call -> AuditLogger.audit -> log
    return out



def entry() -> float:
    User().login("b.entry")                # method call -> utils/d.py:User.log -> log
    return process(5)

from utils.e import log


def add(a: int, b: int) -> int:
    return a + b


class Multiplier:
    def mul(self, a: int, b: int) -> int:
        log("Multiplier.mul")
        return a * b


def multiply(a: int, b: int) -> int:
    m = Multiplier()
    return m.mul(a, b)  # function -> method call

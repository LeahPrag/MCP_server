from utils.e import log


def div(a: float, b: float) -> float:
    return a / b


class Divider:
    def divide(self, a: float, b: float) -> float:
        log("Divider.divide")
        return div(a, b)  # method -> function call

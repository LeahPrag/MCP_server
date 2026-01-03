# utils/models.py
from utils.e import log


class User:
    def __init__(self, name: str):
        self.name = name

    def login(self) -> None:
        log(f"{self.name} logged in")


class Admin(User):
    def audit(self) -> None:
        log(f"Admin {self.name} performed audit")

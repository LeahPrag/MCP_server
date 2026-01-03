def log(msg: str) -> None:
    print(f"[LOG] {msg}")


class AuditLogger:
    def audit(self, msg: str) -> None:
        # method -> function call
        log(f"AUDIT: {msg}")

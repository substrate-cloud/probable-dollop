"""After: idempotent deploy. Safe to re-run from CI; never duplicate-launches."""

from substrate import Substrate

inst = Substrate().apply("substrate.yaml")
print(inst.ip_address)

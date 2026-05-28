"""After: launch the cheapest A100 with the fluent one-call API."""

from substrate import Substrate

inst = Substrate().launch(name="exp-1", gpu="A100", budget=10)
print(inst.ip_address)

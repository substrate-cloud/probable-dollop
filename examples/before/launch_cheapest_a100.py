"""Before: launch the cheapest A100 with the old imperative API."""

from substrate import Substrate

client = Substrate()
item = client.inventory.find_cheapest(gpu_type="A100")
inst = client.instances.create(inventory_gpu_id=item.id, name="exp-1")
client.instances.wait_until_active(inst.id, timeout=600)
print(inst.ip_address)

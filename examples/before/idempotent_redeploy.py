"""Before: there is no idempotent deploy. The pattern below is what a CI
job has to do today — and it's still racy. Re-running the script after a
network blip can leak a duplicate, billed instance."""

from substrate import Substrate

client = Substrate()

# 1. Look for an existing instance by tag (no first-class identity).
matches = [
    i
    for i in client.instances.list()
    if "manifest:my-app" in i.tags and not i.status.is_terminal
]

if matches:
    inst = matches[0]
else:
    item = client.inventory.find_cheapest(gpu_type="A100")
    inst = client.instances.create(
        inventory_gpu_id=item.id,
        name="my-app",
        tags=["manifest:my-app"],
    )
    client.instances.wait_until_active(inst.id, timeout=600)

print(inst.ip_address)

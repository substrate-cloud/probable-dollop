# Escape hatches: the existing typed API

The v0.2 redesign adds a fluent builder and a declarative manifest layer.
**The existing typed managers are unchanged** and still available for cases
where you want fine-grained control.

## Direct manager access

```python
from substratecloud import SubstrateCloud

client = SubstrateCloud()

# Inventory
items = client.inventory.list(gpu_type="A100", max_price=3)
cheapest = client.inventory.find_cheapest(gpu_type="A100")

# Instances
instances = client.instances.list()
inst = client.instances.create(inventory_gpu_id=cheapest.id, name="x")
client.instances.wait_until_active(inst.id, timeout=600)
client.instances.delete(inst.id)

# SSH keys
keys = client.ssh_keys.list()
key = client.ssh_keys.find_by_name("my-key")
```

## When to use which surface

| You want… | Use |
|---|---|
| Launch with one Python line | `SubstrateCloud().launch(...)` |
| Compose a launch in steps | `SubstrateCloud().gpu(...).docker(...).launch(...)` |
| Idempotent CI redeploy | `SubstrateCloud().apply("substratecloud.yaml")` |
| Browse capacity | `client.inventory.list(...)` |
| Manage SSH keys | `client.ssh_keys` |
| Custom polling / state machine | `client.instances.get(...) + loop` |
| Drop into async | `client.instances.alist()` / `aget` / `adelete` |

The fluent / declarative surfaces internally call the same managers, so
you can mix freely: `apply` to launch, then `client.instances.get(...)`
to read state.

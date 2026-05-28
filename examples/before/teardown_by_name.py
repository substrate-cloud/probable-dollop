"""Before: tear down by name. Names are not unique per the API, so this is fiddly."""

from substrate import Substrate

client = Substrate()
for inst in client.instances.find_by_name("my-app"):
    if not inst.status.is_terminal:
        client.instances.delete(inst.id)

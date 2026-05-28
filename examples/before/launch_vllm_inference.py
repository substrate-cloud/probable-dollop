"""Before: launch vLLM serving Mistral-7B on the cheapest A100."""

from substrate import DockerWorkload, Secret, Substrate

client = Substrate()
wl = DockerWorkload(
    image="vllm/vllm-openai:latest",
    args=["--model", "mistralai/Mistral-7B-v0.1"],
    env={"HF_TOKEN": Secret.from_env("HF_TOKEN")},
    ports={8000: 8000},
)
inst = client.run(workload=wl, gpu="A100", name="vllm-mistral", tags=["team:platform"])
print(inst.ip_address)

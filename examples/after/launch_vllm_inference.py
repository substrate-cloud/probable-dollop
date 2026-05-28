"""After: launch vLLM serving Mistral-7B with the fluent API."""

from substrate import Substrate

inst = Substrate().launch(
    name="vllm-mistral",
    gpu="A100",
    image="vllm/vllm-openai:latest",
    args=["--model", "mistralai/Mistral-7B-v0.1"],
    env={"HF_TOKEN": "$HF_TOKEN"},
    ports={8000: 8000},
    budget=10,
    tags=["team:platform"],
)
print(inst.ip_address)

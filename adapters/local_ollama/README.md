# Local Ollama adapter

The shared contracts and workflow semantics are in
[templates/CORE_RULES.md](../../templates/CORE_RULES.md). This adapter supplies
only conservative local model defaults for a host with about 10 GB of usable
RAM.

Review [config.yaml](config.yaml), install Ollama and the configured model
separately, then start a prompt with:

```text
python adapters/local_ollama/run.py
```

Pass `--model MODEL` to select an already available model. The adapter does not
silently download models or start network services.

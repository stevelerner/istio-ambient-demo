# Delegation

This repo follows the standing delegation rule: evaluate at the start of each task whether to hand it to local Qwen, and skip delegation entirely if Ollama is not reachable.

Rule, gate and commands: `/Volumes/external/code/ai/DELEGATION.md`.
Tooling: `/Volumes/external/code/inferencerouter/delegate/`.

The specs in `tasks/` were run with it against the TinyOlly repo:

```bash
export LOCAL_BASE=http://192.168.68.71:11434 LOCAL_MODEL=qwen3.8:27b-mtp-q4_K_M
python3 /Volumes/external/code/inferencerouter/delegate/implement.py docs/tasks/f5-mesh-edges.md --repo /Volumes/external/code/tinyolly --in-place
```

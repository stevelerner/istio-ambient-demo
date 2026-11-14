# Delegation tooling lives elsewhere

Claude + local Qwen delegation tooling is in `/Volumes/external/code/inferencerouter/delegate/` (`implement.py`, `bench/`, `WORKFLOW.md`).
The task specs in `tasks/` were run with it against the TinyOlly repo:

```bash
export LOCAL_BASE=http://192.168.68.71:11434 LOCAL_MODEL=qwen3.8:27b-mtp-q4_K_M
python3 /Volumes/external/code/inferencerouter/delegate/implement.py docs/tasks/f5-mesh-edges.md --repo /Volumes/external/code/tinyolly --in-place
```

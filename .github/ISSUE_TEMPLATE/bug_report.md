---
name: Bug report
about: Something isn't working as expected
title: '[Bug] '
labels: bug
assignees: ''
---

## Describe the bug
A clear description of what went wrong.

## Steps to reproduce
1.
2.
3.

## Expected behavior
What you expected to happen.

## Log output
Please paste the relevant lines from `~/Library/Logs/LRCGenerator.log`:

```
(paste log here)
```

Or run the diagnostic script and paste its output:
```bash
bash diagnose.sh
```

## Environment
- macOS version:
- Python version (`python3 --version`):
- Python path (`which python3`):
- stable-ts version (`python3 -c "import stable_whisper; print(stable_whisper.__version__)"`):
- Audio format of the problematic file(s):

import re, pathlib
files=[
"oracle/acquirers/guard.py",
"oracle/acquirers/guarded_import.py",
"oracle/acquirers/realdebrid.py",
"oracle/agent.py",
"oracle/architect.py",
"oracle/async_scanner.py",
"oracle/cli.py",
"oracle/console.py",
"oracle/curator.py",
"oracle/dna.py",
"oracle/embedders/clap_embedder.py",
"oracle/fast_batch.py",
"oracle/hunter.py",
"oracle/lore.py",
"oracle/ops.py",
"oracle/radio.py",
"oracle/repair.py",
"oracle/scout.py",
]
for path in files:
    p=pathlib.Path(path)
    if not p.exists():
        continue
    text=p.read_text(encoding='utf-8')
    lines=text.splitlines(keepends=True)
    changed=False
    newlines=[]
    for line in lines:
        def repl(match):
            s=match.group(0)
            content=s[2:-1] if s.startswith("f\"") or s.startswith("f'") else s
            if "{" in content or "}" in content:
                return s
            return s[1:]
        newline=re.sub(r"f(['\"]).*?\1", repl, line)
        if newline!=line:
            changed=True
        newlines.append(newline)
    if changed:
        p.write_text(''.join(newlines), encoding='utf-8')
        print(f"Updated {path}")

# Agent-visible files for fam05/T3 (frozen seal)

VISIBLE TO AGENT:
- prompt.md
- task fixtures: a.txt b.txt manifest.env sub top.txt 
- task-provided fetch harness, if required

NOT VISIBLE (seal violation voids the run):
- truth.json, check.py, K.md, DESIGN-T4.md (family root)
- sibling task directories (T0-T4)
- any other family directory
- GitHub/network access to the benchmark repo

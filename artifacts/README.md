# Artifacts

This folder holds **small example outputs** only.

- Full evaluation JSON/CSV/PNG trees that accompany a paper release belong on **Zenodo** (frozen with a DOI).
- Everything needed to regenerate results is in `scripts/`.

## Regenerate

```bash
python scripts/validate_l5_l9.py
python scripts/run_phi_swarm.py --minutes 2 --round-interval 2
python scripts/run_full_validation.py
python scripts/export_paper_artifacts.py
```

Outputs are written under `zerotwin/results/` (gitignored except `.gitkeep`).

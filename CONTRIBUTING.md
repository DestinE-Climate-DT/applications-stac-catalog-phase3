# Contributing

## Adding a New Application

1. Copy `templates/` into `apps/<your-app-name>/`
2. Fill in `catalog_config.yaml` with your collection metadata
3. Write your staging script in `apps/<your-app-name>/staging/`
4. Adapt `run_pipeline.sh` with your data paths
5. Add `.env` with your S3 credentials (never commit it)
6. Update the application table in `README.md`
7. Open a merge request

See `templates/README.md` for the full step-by-step guide.

## Modifying Shared Core (`stac_dedl_core/`)

The shared package tracks the upstream
[DestinE-DataLake-Lab/HDA/Usergenerated](https://github.com/destination-earth/DestinE-DataLake-Lab/tree/main/HDA/Usergenerated)
reference implementation. Before modifying it:

- Check whether the change is truly shared (affects all apps) or app-specific
- If shared: modify `stac_dedl_core/` and test with at least one app
- If app-specific: add the logic to your app's staging script instead
- When the upstream reference updates, sync the changes here

## Branching Strategy

- `main` — stable, always runnable
- `feature/<name>` — new app migration or shared-core change
- `fix/<name>` — bug fixes

## PR Checklist

- [ ] `pip install -e .` succeeds
- [ ] `conda env create -f environment.yml` succeeds (or `environment.yml` updated if deps changed)
- [ ] No `.env` files committed
- [ ] No large data files committed
- [ ] App `README.md` updated if workflow changed
- [ ] `README.md` app table updated if new app added

# Adding a New Application

This directory contains templates for onboarding a new application.

## Steps

### 1. Create your app folder

```bash
cp -r templates/ apps/<your-app-name>/
cd apps/<your-app-name>/
```

### 2. Fill in `catalog_config.yaml`

Edit `catalog_config.yaml.template` (rename to `catalog_config.yaml`) with your collection's
metadata. The collection ID format is `EO.<ORG>.<TYPE>.<NAME>` (uppercase, dots and underscores only).

### 3. Create `collection.json`

Use `collection.json.template` as a starting point. This file must pass STAC validation.
Required fields: `id`, `title`, `description`, `dedl:short_description`, `license`, `extent`,
`links`, `keywords`, `stac_extensions`, `providers`.

### 4. Create `collection_config.json`

Use `collection_config.json.template`. Key field: `item_folder_level` (`YYYY`, `MM`, or `DD`).

### 5. Write your staging script

Create `staging/<your-app>_staging.py` that reorganises your raw application output into:
```
<COLLECTION_ID>/data/YYYY/[MM/[DD/]]<item-folder>/
```
Where each item folder contains the data files and an optional `item_config.json` with `bbox`.

### 6. Set credentials

```bash
cp .env.example .env
# Edit .env — add AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
```

### 7. Adapt `run_pipeline.sh`

Set `COLLECTION_ID` and adjust the staging command to call your script.

### 8. Test

```bash
# Dry run — IS_UPLOAD_S3 is False by default, so no data will be uploaded
bash run_pipeline.sh
```

### 9. Add your app to the repo

- Add a row to the application table in `README.md`
- Open a merge request

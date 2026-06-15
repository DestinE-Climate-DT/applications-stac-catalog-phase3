"""Write metadata/collection.json + metadata/collection_config.json from an AppConfig.

Generalised from apps/hydroland/staging/hydroland_data_preparation.py so that
every app produces identical collection-level metadata structure.
"""
from __future__ import annotations

import json
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig
from stac_dedl_core.config import STAC_VERSION

SCIENTIFIC_EXTENSION = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"


def build_collection_dict(cfg: AppConfig) -> dict:
    """Build the collection.json payload as a dict.

    Key order matches hydroland's published collection.json:
    type, id, stac_version, description, links, stac_extensions,
    dedl:short_description, [sci:publications], title, extent, license,
    keywords, providers, assets.

    stac_extensions is ALWAYS present (DEDL collection validation requires the
    field): it holds the scientific extension when cfg.doi is set, otherwise an
    empty list. sci:publications is included only when cfg.doi is set. Missing doi
    sub-keys (url/code/citation) serialise as null; the yaml author is responsible
    for providing them.
    """
    links = []
    if cfg.license_url:
        links.append(
            {
                "rel": "license",
                "href": cfg.license_url,
                "title": cfg.license_name or cfg.license,
            }
        )
    if cfg.doi:
        links.append(
            {
                "rel": "cite-as",
                "href": cfg.doi.get("url"),
                "title": cfg.doi.get("title"),
            }
        )
    if cfg.related:
        links.append(
            {
                "rel": "describedby",
                "href": cfg.related.get("url"),
                "title": cfg.related.get("title"),
            }
        )

    collection: dict = {
        "type": "Collection",
        "id": cfg.id,
        "stac_version": STAC_VERSION,
        "description": cfg.description,
        "links": links,
    }

    # Always present: DEDL collection validation requires the stac_extensions field.
    collection["stac_extensions"] = [SCIENTIFIC_EXTENSION] if cfg.doi else []

    collection["dedl:short_description"] = cfg.short_description

    if cfg.doi:
        collection["sci:publications"] = [
            {
                "sci:doi": cfg.doi.get("code"),
                "sci:citation": cfg.doi.get("citation") or cfg.doi.get("title"),
            }
        ]

    collection["title"] = cfg.title
    collection["extent"] = {
        "spatial": {"bbox": [cfg.bbox]},
        "temporal": {"interval": [[cfg.temporal_start, cfg.temporal_end]]},
    }
    collection["license"] = cfg.license
    collection["keywords"] = cfg.keywords
    collection["providers"] = cfg.providers

    if cfg.thumbnail_url:
        collection["assets"] = {
            "thumbnail": {
                "href": cfg.thumbnail_url,
                "type": cfg.thumbnail_mime,
                "title": "overview",
                "roles": ["thumbnail"],
            }
        }

    return collection


def build_collection_config_dict(cfg: AppConfig) -> dict:
    return {
        "id": cfg.id,
        "item_asset_ignore_list": ["item_config.json"],
        "item_config_optional": cfg.item_config_optional,
        "item_folder_level": cfg.item_folder_level,
        "thumbnail_regex": "^thumbnail",
        "overview_regex": "^overview",
        "additional_property_keys": cfg.property_order,
        "bbox": cfg.bbox,
    }


def _write_json(path: Path, payload: dict, overwrite: bool, indent: int) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Pass overwrite=True to replace.")
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent)
        f.write("\n")


def write_collection_files(
    cfg: AppConfig, overwrite: bool = False, indent: int = 2
) -> tuple[Path, Path]:
    """Create <collection>/data and <collection>/metadata, write both JSON files."""
    metadata_dir = cfg.collection_dir / "metadata"
    (cfg.collection_dir / "data").mkdir(parents=True, exist_ok=True)  # pre-created because ItemGenerator expects it to exist
    metadata_dir.mkdir(parents=True, exist_ok=True)

    collection_path = metadata_dir / "collection.json"
    config_path = metadata_dir / "collection_config.json"
    _write_json(collection_path, build_collection_dict(cfg), overwrite, indent)
    _write_json(config_path, build_collection_config_dict(cfg), overwrite, indent)
    return collection_path, config_path

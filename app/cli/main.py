"""This module provides different commands to help
setting up search-a-licious
or doing maintenance operations.
"""

from inspect import cleandoc as cd_
from pathlib import Path
from typing import Optional

import typer

import app

cli = typer.Typer()


INDEX_ID_HELP = (
    "Each index has its own configuration in the configuration file, "
    "and the ID is used to know which index to use. "
    "If there is only one index, this option is not needed."
)


def _get_index_config(
    config_path: Optional[Path], index_id: Optional[str]
) -> tuple[str, "app.config.IndexConfig"]:

    from app import config
    from app.config import set_global_config

    if config_path:
        set_global_config(config_path)

    global_config = config.get_config()
    index_id, index_config = global_config.get_index_config(index_id)
    if index_config is None:
        raise typer.BadParameter(
            "You must specify an index ID when there are multiple indices"
        )
    return index_id, index_config


@cli.command(name="import")
def import_data(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Path of the JSONL data file",
    ),
    skip_updates: bool = typer.Option(
        default=False,
        help="Skip fetching fresh records from redis",
    ),
    partial: bool = typer.Option(
        default=False,
        help=cd_(
            """Only run a partial update, on current index
            while the default run a full import in a new index.

            Use this if instead of re-importing the whole data,
            you only want to update the data that has changed.

            You will loose the *rollback* capability in case of failure.
            """
        ),
    ),
    num_processes: int = typer.Option(
        default=2, help="How many import processes to run in parallel"
    ),
    num_items: Optional[int] = typer.Option(
        default=None, help="How many items to import (mainly for testing)"
    ),
    config_path: Optional[Path] = typer.Option(
        default=None,
        help="path of the yaml configuration file, it overrides CONFIG_PATH envvar",
        dir_okay=False,
        file_okay=True,
        exists=True,
    ),
    index_id: Optional[str] = typer.Option(
        default=None,
        help=INDEX_ID_HELP,
    ),
):
    """Import data into Elasticsearch.

    This command is used to initialize or refresh your index with data.

    File must contains one JSON document per line,
    each document must have same format as a document returned by the API.
    """
    import time

    from app._import import run_items_import
    from app.utils import get_logger

    logger = get_logger()

    start_time = time.perf_counter()
    index_id, index_config = _get_index_config(config_path, index_id)
    num_errors = run_items_import(
        input_path,
        num_processes,
        index_config,
        num_items=num_items,
        skip_updates=skip_updates,
        partial=partial,
    )
    end_time = time.perf_counter()
    logger.info("Import time: %s seconds", end_time - start_time)
    if num_errors:
        logger.error("There were %s errors during import", num_errors)
        typer.Exit(1)


@cli.command()
def import_taxonomies(
    config_path: Optional[Path] = typer.Option(
        default=None,
        help="path of the yaml configuration file, it overrides CONFIG_PATH envvar",
        dir_okay=False,
        file_okay=True,
        exists=True,
    ),
    index_id: Optional[str] = typer.Option(
        default=None,
        help=INDEX_ID_HELP,
    ),
    skip_indexing: bool = typer.Option(
        default=False,
        help="Skip putting taxonomies in the ES index",
    ),
    skip_synonyms: bool = typer.Option(
        default=False,
        help="Skip creating synonyms files for ES analyzers",
    ),
):
    """Import taxonomies into Elasticsearch.

    It download taxonomies json files as specified in the configuration file.

    It creates taxonomies indexes (for auto-completion).

    It creates synonyms files for ElasticSearch analyzers
    (enabling full text search to benefits from synonyms).
    """
    import time

    from app._import import perform_refresh_synonyms, perform_taxonomy_import
    from app.utils import connection, get_logger

    logger = get_logger()

    index_id, index_config = _get_index_config(config_path, index_id)

    # open a connection for this process
    connection.get_es_client(request_timeout=120, retry_on_timeout=True)

    if skip_indexing:
        logger.info("Skipping indexing of taxonomies")
    else:
        start_time = time.perf_counter()
        perform_taxonomy_import(index_config)
        end_time = time.perf_counter()
        logger.info("Import time: %s seconds", end_time - start_time)
    if skip_synonyms:
        logger.info("Skipping synonyms generation")
    else:
        start_time = time.perf_counter()
        perform_refresh_synonyms(
            index_id,
            index_config,
        )
        end_time = time.perf_counter()
        logger.info("Synonyms generation time: %s seconds", end_time - start_time)


@cli.command()
def sync_scripts(
    config_path: Optional[Path] = typer.Option(
        default=None,
        help="path of the yaml configuration file, it overrides CONFIG_PATH envvar",
        dir_okay=False,
        file_okay=True,
        exists=True,
    ),
    index_id: Optional[str] = typer.Option(
        default=None,
        help=INDEX_ID_HELP,
    ),
):
    """Synchronize scripts defined in configuration with Elasticsearch.

    This command must be run after adding, modifying or removing scripts.
    """
    from app import es_scripts
    from app.utils import connection, get_logger

    logger = get_logger()
    index_id, index_config = _get_index_config(config_path, index_id)
    connection.get_es_client()
    stats = es_scripts.sync_scripts(index_id, index_config)
    logger.info(
        f"Synced scripts (removed: {stats['removed']}, added: {stats['added']})"
    )


@cli.command()
def cleanup_indexes(
    config_path: Optional[Path] = typer.Option(
        default=None,
        help="path of the yaml configuration file, it overrides CONFIG_PATH envvar",
        dir_okay=False,
        file_okay=True,
        exists=True,
    ),
    index_id: Optional[str] = typer.Option(
        default=None,
        help=f"{INDEX_ID_HELP}\nIf not specified, all indexes are cleaned",
    ),
):
    """Clean old indexes that are not active anymore (no aliases)

    As you do full import of data or update taxonomies,
    old indexes are not removed automatically.
    (in the case you want to roll back or compare).

    This command will remove all indexes that are not active anymore.
    """
    import time

    from app._import import perform_cleanup_indexes
    from app.utils import get_logger

    logger = get_logger()
    if index_id:
        _, index_config = _get_index_config(config_path, index_id)
        index_configs = [index_config]
    else:
        _get_index_config(config_path, None)  # just to set global config variable
        from app.config import get_config

        index_configs = list(get_config().indices.values())
    start_time = time.perf_counter()
    removed = 0
    for index_config in index_configs:
        removed += perform_cleanup_indexes(index_config)
    end_time = time.perf_counter()
    logger.info("Removed %d indexes in %s seconds", removed, end_time - start_time)


@cli.command()
def run_update_daemon(
    config_path: Optional[Path] = typer.Option(
        default=None,
        help="path of the yaml configuration file, it overrides CONFIG_PATH envvar",
        dir_okay=False,
        file_okay=True,
        exists=True,
    ),
):
    """Run the daemon responsible for listening to document updates from Redis
    Stream and updating the Elasticsearch index.

    This command must be run in a separate process to the api server.

    It is optional but enables having an always up-to-date index,
    for applications where data changes.
    """

    from app import config
    from app._import import run_update_daemon
    from app.config import set_global_config, settings
    from app.utils import get_logger, init_sentry

    # Create root logger
    get_logger()
    # Initialize sentry for bug tracking
    init_sentry(settings.sentry_dns)

    if config_path:
        set_global_config(config_path)

    global_config = config.get_config()
    run_update_daemon(global_config)


@cli.command()
def export_openapi(
    target_path: Path = typer.Argument(
        exists=None,
        file_okay=True,
        dir_okay=False,
        help="Path of the YAML or JSON data file",
    )
):
    """Export OpenAPI specification to a file."""
    import json

    import yaml

    from app.api import app as app_api

    openapi = app_api.openapi()
    version = openapi.get("openapi", "unknown version")

    print(f"writing openapi spec v{version}")
    with open(target_path, "w") as f:
        if str(target_path).endswith(".json"):
            json.dump(openapi, f, indent=2)
        else:
            yaml.dump(openapi, f, sort_keys=False)

    print(f"spec written to {target_path}")


def export_schema(
    class_: type["app.config.Config"] | type["app.config.Settings"], target_path: Path
):
    """Export schema to a file."""
    import json

    import yaml

    from app.config import Config, ConfigGenerateJsonSchema, SettingsGenerateJsonSchema

    schema_generator = (
        ConfigGenerateJsonSchema
        if issubclass(class_, Config)
        else SettingsGenerateJsonSchema
    )
    schema = class_.model_json_schema(schema_generator=schema_generator)

    print("writing json schema")
    with open(target_path, "w") as f:
        if str(target_path).endswith(".json"):
            json.dump(schema, f, indent=2)
        else:
            yaml.safe_dump(schema, f, sort_keys=False)

    print(f"schema written to {target_path}")


schema_target_path = typer.Argument(
    exists=None,
    file_okay=True,
    dir_okay=False,
    help="Path of the YAML or JSON data file",
)


@cli.command()
def export_config_schema(target_path: Path = schema_target_path):
    """Export Configuration json schema to a file."""
    from app.config import Config

    export_schema(Config, target_path)


@cli.command()
def export_settings_schema(target_path: Path = schema_target_path):
    """Export Configuration json schema to a file."""
    from app.config import Settings

    export_schema(Settings, target_path)


def main() -> None:
    cli()

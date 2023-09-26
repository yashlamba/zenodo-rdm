# -*- coding: utf-8 -*-
#
# Copyright (C) 2023 CERN.
#
# ZenodoRDM is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""ZenodoRDM statistics CLI commands."""

import csv
import glob
import re
import sys
from datetime import datetime as dt

import click
from dateutil.parser import parse as dateutil_parse
from flask.cli import with_appcontext
from invenio_stats.cli import stats
from invenio_stats.proxies import current_stats
from six.moves import filter, map
from six.moves.urllib.parse import urlparse

from zenodo.modules.stats.tasks import update_record_statistics
from zenodo.modules.stats.utils import (
    chunkify,
    extract_event_record_metadata,
    fetch_record,
    fetch_record_file,
)

PY3 = sys.version_info[0] == 3


def _verify_date(ctx, param, value):
    if value:
        dateutil_parse(value)
        return value


def parse_record_url(url):
    """Parses a recid and filename from a record-like URL."""
    record_url = urlparse(url)
    assert record_url.hostname.lower().endswith("zenodo.org"), "non-Zenodo url"
    match = re.match(
        # matches "/record/(123)", "/record/(123)/export", etc
        r"^\/record\/(?P<recid>\d+)"
        # matches "/record/(123)/files/(some.pdf)"
        r"(?:\/files\/(?P<filename>.+)$)?",
        record_url.path,
    ).groupdict()
    return match.get("recid"), match.get("filename")


def build_common_event(record, data):
    """Build common fields of a stats event from a record and request data."""
    return dict(
        timestamp=dt.utcfromtimestamp(float(data["timestamp"])).isoformat(),
        pid_type="recid",
        pid_value=str(record.get("recid")),
        referrer=data["referrer"],
        ip_address=data["ipAddress"],
        user_agent=data["userAgent"],
        user_id=None,
        **extract_event_record_metadata(record)
    )


def build_record_view_event(data):
    """Build a 'record-view' event from request data."""
    try:
        recid, _ = parse_record_url(data["url"])
        assert recid, "no recid in url"
        _, record = fetch_record(recid)
    except Exception:
        return

    return build_common_event(record, data)


def build_file_download_event(data):
    """Build a 'file-download' event from request data."""
    try:
        recid, filename = parse_record_url(data["url"])
        assert recid and filename, "no recid and filename in url"
        _, record = fetch_record(recid)
        obj = fetch_record_file(recid, filename)
    except Exception:
        return

    return dict(
        bucket_id=str(obj.bucket_id),
        file_id=str(obj.file_id),
        file_key=obj.key,
        size=obj.file.size,
        **build_common_event(record, data)
    )


EVENT_TYPE_BUILDERS = {
    "record-view": build_record_view_event,
    "file-download": build_file_download_event,
}


@stats.command("import")
@click.argument("event-type", type=click.Choice(EVENT_TYPE_BUILDERS.keys()))
@click.argument("csv-dir", type=click.Path(file_okay=False, resolve_path=True))
@click.option("--chunk-size", "-s", type=int, default=100)
@with_appcontext
def import_events(event_type, csv_dir, chunk_size):
    r"""Import stats events from a directory of CSV files.

    Available event types: "file-download", "record-view"

    The following columns should always be present:

    \b
    - ipAddress
    - userAgent
    - url ("https://zenodo.org/record/1234/files/article.pdf")
    - timestamp (1388506249)
    - referrer ("Google", "example.com", etc)
    """
    csv_files = glob.glob(csv_dir + "/*.csv")
    with click.progressbar(csv_files, len(csv_files)) as csv_files_bar:
        for csv_path in csv_files_bar:
            with open(csv_path, "r" if PY3 else "rb") as fp:
                reader = csv.DictReader(fp, delimiter=",")
                events = filter(None, map(EVENT_TYPE_BUILDERS[event_type], reader))
                for event_chunk in chunkify(events, chunk_size):
                    current_stats.publish(event_type, event_chunk)
    click.secho(
        'Run the "invenio_stats.tasks.process_events" to index the events...',
        fg="yellow",
    )


@stats.command("update-records")
@click.option("--start-date", callback=_verify_date)
@click.option("--end-date", callback=_verify_date)
@click.option("--eager", "-e", is_flag=True)
@with_appcontext
def update_records(start_date=None, end_date=None, eager=False):
    """Update records' statistics on ES."""
    if eager:
        update_record_statistics.apply(
            kwargs=dict(start_date=start_date, end_date=end_date), throw=True
        )
        click.secho(
            "Records sent for bulk indexing. Wait for the scheduled "
            "indexer or run `zenodo index run ...`",
            fg="yellow",
        )
    else:
        update_record_statistics.delay(start_date=start_date, end_date=end_date)
        click.secho("Update records statistics task sent...", fg="yellow")

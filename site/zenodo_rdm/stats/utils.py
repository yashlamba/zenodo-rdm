# -*- coding: utf-8 -*-
#
# Copyright (C) 2023 CERN.
#
# ZenodoRDM is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Statistics utilities."""

import itertools

from elasticsearch.exceptions import NotFoundError
from flask import request
from invenio_search.api import RecordsSearch
from invenio_search.proxies import current_search_client
from invenio_search.utils import build_alias_name
from invenio_stats import current_stats

from zenodo.modules.records.resolvers import record_resolver

try:
    from functools import lru_cache
except ImportError:
    from functools32 import lru_cache


def get_record_from_context(**kwargs):
    """Get the cached record object from kwargs or the request context."""
    if "record" in kwargs:
        return kwargs["record"]
    else:
        if request and hasattr(request._get_current_object(), "current_file_record"):
            return request.current_file_record


def extract_event_record_metadata(record):
    """Extract from a record the payload needed for a statistics event."""
    return dict(
        record_id=str(record.id),
        recid=str(record["recid"]) if record.get("recid") else None,
        conceptrecid=record.get("conceptrecid"),
        doi=record.get("doi"),
        conceptdoi=record.get("conceptdoi"),
        access_right=record.get("access_right"),
        resource_type=record.get("resource_type"),
        communities=record.get("communities"),
        owners=record.get("owners"),
    )


def build_record_stats(recid, conceptrecid):
    """Build the record's stats."""
    stats = {}
    stats_sources = {
        "record-view": {
            "params": {"recid": recid},
            "fields": {
                "views": "count",
                "unique_views": "unique_count",
            },
        },
        "record-download": {
            "params": {"recid": recid},
            "fields": {
                "downloads": "count",
                "unique_downloads": "unique_count",
                "volume": "volume",
            },
        },
        "record-view-all-versions": {
            "params": {"conceptrecid": conceptrecid},
            "fields": {
                "version_views": "count",
                "version_unique_views": "unique_count",
            },
        },
        "record-download-all-versions": {
            "params": {"conceptrecid": conceptrecid},
            "fields": {
                "version_downloads": "count",
                "version_unique_downloads": "unique_count",
                "version_volume": "volume",
            },
        },
    }
    for query_name, cfg in stats_sources.items():
        try:
            query_cfg = current_stats.queries[query_name]
            query = query_cfg.cls(name=query_name, **query_cfg.params)
            result = query.run(**cfg["params"])
            for dst, src in cfg["fields"].items():
                stats[dst] = result.get(src)
        except Exception:
            pass
    return stats


def get_record_stats(recordid, throws=True):
    """Fetch record statistics from Elasticsearch."""
    try:
        res = current_search_client.get(
            index=build_alias_name("records"),
            id=recordid,
            params={"_source_includes": "_stats"},
        )
        return res["_source"]["_stats"]
    except NotFoundError:
        return None
    except Exception:
        if throws:
            raise
        pass


def chunkify(iterable, n):
    """Create equally sized tuple-chunks from an iterable."""
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk


@lru_cache(maxsize=1024)
def fetch_record(recid):
    """Cached record fetch."""
    return record_resolver.resolve(recid)


@lru_cache(maxsize=1024)
def fetch_record_file(recid, filename):
    """Cached record file fetch."""
    _, record = fetch_record(recid)
    return record.files[filename].obj

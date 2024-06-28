# -*- coding: utf-8 -*-
#
# Copyright (C) 2024 CERN.
#
# Zenodo-RDM is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Subcommunities request implementation for ZenodoRDM."""

from invenio_access.permissions import system_identity
from invenio_communities.subcommunities.services.request import (
    AcceptSubcommunity,
    DeclineSubcommunity,
    SubCommunityRequest,
)
from invenio_rdm_records.proxies import (
    current_community_records_service,
    current_rdm_records,
)
from invenio_requests.customizations import actions
from invenio_requests.customizations.event_types import CommentEventType
from invenio_requests.proxies import current_events_service


class SubcommunityAcceptAction(AcceptSubcommunity):
    """Represents an accept action used to accept a subcommunity.

    Zenodo re-implementation of the accept action, to also move the records.
    """

    def _get_community_records(self, community_id):
        """Get the records of a community."""
        return current_community_records_service.search(
            system_identity, community_id=community_id
        )

    def execute(self, identity, uow):
        """Execute approve action."""
        to_be_moved = self.request.topic.resolve().id
        move_to = self.request.receiver.resolve().id

        # Move records
        records = self._get_community_records(to_be_moved)
        current_rdm_records.record_communities_service.bulk_add(
            system_identity, move_to, (x["id"] for x in records), uow=uow
        )
        super().execute(identity, uow)


class SubcommunityCreateAction(actions.CreateAndSubmitAction):
    """Represents an create action used to create a subcommunity request.

    Zenodo re-implementation of the create action, to also create the system comment.
    """

    def execute(self, identity, uow):
        """Execute create action."""

        subcommunity = self.request.topic.resolve()
        _data = dict(
            payload={
                "content": f"""
            <p>
            We have created your community for your project <a href='/communities/{subcommunity.slug}'>{subcommunity['metadata']['title']}</a>.
            </p>

            <p>
            While we review your request, you can get started using your community by:
            <ul>
                <li><a href="https://help.zenodo.org/docs/communities/manage-community-settings/edit-profile/">Edit your community profile</a>, to add a logo and other information.</li>
                <li><a href="https://help.zenodo.org/docs/communities/manage-members/">Invite new members</a> to join your community.</li>
                <li>Learn more about how to <a href="https://help.zenodo.org/docs/communities/review-submissions/"> review submissions</a> and <a href="https://help.zenodo.org/docs/communities/curate/">curate records.</a></li>
            </ul>
            </p>
            """
            }
        )
        super().execute(identity, uow)
        current_events_service.create(
            system_identity,
            self.request,
            _data,
            CommentEventType,
            uow=uow,
        )


class ZenodoSubCommunityRequest(SubCommunityRequest):
    """Request to add a subcommunity to a Zenodo community."""

    available_actions = {
        "delete": actions.DeleteAction,
        "create": SubcommunityCreateAction,
        "cancel": actions.CancelAction,
        "accept": SubcommunityAcceptAction,
        "decline": DeclineSubcommunity,
    }

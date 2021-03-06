# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import random
from compiler.ast import flatten
from datetime import datetime, timedelta
from sets import Set

import requests
from celery.utils.log import get_task_logger
from flask import current_app

from udata import mail
from udata.i18n import lazy_gettext as _
from udata.models import Organization, Activity, Metrics, Topic
from udata.tasks import job

from .models import (
    Dataset, DatasetIssue, DatasetDiscussion, FollowDataset, UPDATE_FREQUENCIES
)

log = get_task_logger(__name__)


@job('purge-datasets')
def purge_datasets(self):
    for dataset in Dataset.objects(deleted__ne=None):
        log.info('Purging dataset "{0}"'.format(dataset))
        # Remove followers
        FollowDataset.objects(following=dataset).delete()
        # Remove issues
        DatasetIssue.objects(subject=dataset).delete()
        # Remove discussions
        DatasetDiscussion.objects(subject=dataset).delete()
        # Remove activity
        Activity.objects(related_to=dataset).delete()
        # Remove metrics
        Metrics.objects(object_id=dataset.id).delete()
        # Remove topics' related dataset
        for topic in Topic.objects(datasets=dataset):
            datasets = topic.datasets
            datasets.remove(dataset)
            topic.update(datasets=datasets)
        # Remove
        dataset.delete()


@job('crawl-resources')
def crawl_resources(self):
    """Ask croquemort to crawl 500 random URLs from datasets."""
    urls = [r.url
            for d in Dataset.objects.only('resources.url')
            for r in d.resources]
    random.shuffle(urls)
    checked_urls = urls[:500]
    CROQUEMORT_URL = current_app.config.get('CROQUEMORT_URL')
    if CROQUEMORT_URL is None:
        return
    check_many_url = '{CROQUEMORT_URL}/check/many'.format(
        CROQUEMORT_URL=CROQUEMORT_URL)
    group_name = 'datagouvfr'
    log.info('Checking URLs under group {name}'.format(name=group_name))
    response = requests.post(check_many_url, data=json.dumps({
        'urls': checked_urls,
        'group': group_name,
    }))
    log.info('URLs checked with group hash {hash}'.format(
        hash=response.json()['group-hash']))


@job('send-frequency-reminder')
def send_frequency_reminder(self):
    # We exclude irrelevant frequencies.
    frequencies = [f for f in UPDATE_FREQUENCIES.keys()
                   if f not in ('unknown', 'realtime', 'punctual')]
    now = datetime.now()
    reminded_orgs = {}
    reminded_people = []
    allowed_delay = current_app.config['DELAY_BEFORE_REMINDER_NOTIFICATION']
    for org in Organization.objects.visible():
        outdated_datasets = []
        for dataset in Dataset.objects.filter(
                frequency__in=frequencies, organization=org).visible():
            if dataset.next_update + timedelta(days=allowed_delay) < now:
                dataset.outdated = now - dataset.next_update
                dataset.frequency_str = UPDATE_FREQUENCIES[dataset.frequency]
                outdated_datasets.append(dataset)
        if outdated_datasets:
            reminded_orgs[org] = outdated_datasets
    for reminded_org, datasets in reminded_orgs.iteritems():
        print(u'{org.name} will be emailed for {datasets_nb} datasets'.format(
              org=reminded_org, datasets_nb=len(datasets)))
        recipients = [m.user for m in reminded_org.members]
        reminded_people.append(recipients)
        subject = _('You need to update some frequency-based datasets')
        mail.send(subject, recipients, 'frequency_reminder',
                  org=reminded_org, datasets=datasets)

    print('{nb_orgs} orgs concerned'.format(nb_orgs=len(reminded_orgs)))
    reminded_people = flatten(reminded_people)
    print('{nb_emails} people contacted ({nb_emails_twice} twice)'.format(
        nb_emails=len(reminded_people),
        nb_emails_twice=len(reminded_people) - len(Set(reminded_people))))
    print('Done')

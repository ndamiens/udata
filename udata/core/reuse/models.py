# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from blinker import Signal
from flask import url_for
from mongoengine.signals import pre_save, post_save

from udata.core.storages import images, default_image_basename
from udata.i18n import lazy_gettext as _
from udata.models import (
    db, BadgeMixin, WithMetrics, Issue, Discussion, Follow, OwnedByQuerySet
)
from udata.utils import hash_url

__all__ = (
    'Reuse', 'ReuseIssue', 'ReuseDiscussion', 'FollowReuse', 'REUSE_TYPES'
)


REUSE_TYPES = {
    'api': _('API'),
    'application': _('Application'),
    'idea': _('Idea'),
    'news_article': _('News Article'),
    'paper': _('Paper'),
    'post': _('Post'),
    'visualization': _('Visualization'),
    'hardware': _('Connected device'),
}


IMAGE_SIZES = [100, 50, 25]
IMAGE_MAX_SIZE = 800


class ReuseQuerySet(OwnedByQuerySet):
    def visible(self):
        return self(private__ne=True, datasets__0__exists=True, deleted=None)

    def hidden(self):
        return self(db.Q(private=True) |
                    db.Q(datasets__0__exists=False) |
                    db.Q(deleted__ne=None))


class Reuse(db.Datetimed, WithMetrics, BadgeMixin, db.Document):
    title = db.StringField(max_length=255, required=True)
    slug = db.SlugField(
        max_length=255, required=True, populate_from='title', update=True)
    description = db.StringField(required=True)
    type = db.StringField(required=True, choices=REUSE_TYPES.keys())
    url = db.StringField(required=True)
    urlhash = db.StringField(required=True, unique=True)
    image_url = db.StringField()
    image = db.ImageField(
        fs=images, basename=default_image_basename, max_size=IMAGE_MAX_SIZE,
        thumbnails=IMAGE_SIZES)
    datasets = db.ListField(
        db.ReferenceField('Dataset', reverse_delete_rule=db.PULL))
    tags = db.TagListField()
    # badges = db.ListField(db.EmbeddedDocumentField(ReuseBadge))

    private = db.BooleanField()
    owner = db.ReferenceField('User', reverse_delete_rule=db.NULLIFY)
    organization = db.ReferenceField(
        'Organization', reverse_delete_rule=db.NULLIFY)

    ext = db.MapField(db.GenericEmbeddedDocumentField())
    extras = db.ExtrasField()

    featured = db.BooleanField()
    deleted = db.DateTimeField()

    def __str__(self):
        return self.title or ''

    __unicode__ = __str__

    __badges__ = {}

    meta = {
        'allow_inheritance': True,
        'indexes': ['-created_at', 'owner', 'urlhash'],
        'ordering': ['-created_at'],
        'queryset_class': ReuseQuerySet,
    }

    before_save = Signal()
    after_save = Signal()
    on_create = Signal()
    on_update = Signal()
    before_delete = Signal()
    after_delete = Signal()
    on_delete = Signal()

    verbose_name = _('reuse')

    @classmethod
    def pre_save(cls, sender, document, **kwargs):
        # Emit before_save
        cls.before_save.send(document)

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        cls.after_save.send(document)
        if kwargs.get('created'):
            cls.on_create.send(document)
        else:
            cls.on_update.send(document)

    def url_for(self, *args, **kwargs):
        return url_for('reuses.show', reuse=self, *args, **kwargs)

    display_url = property(url_for)

    @property
    def external_url(self):
        return self.url_for(_external=True)

    @property
    def type_label(self):
        return REUSE_TYPES[self.type]

    def clean(self):
        '''Auto populate urlhash from url'''
        if not self.urlhash or 'url' in self._get_changed_fields():
            self.urlhash = hash_url(self.url)
        super(Reuse, self).clean()

    @classmethod
    def get(cls, id_or_slug):
        obj = cls.objects(slug=id_or_slug).first()
        return obj or cls.objects.get_or_404(id=id_or_slug)

    @classmethod
    def url_exists(cls, url):
        urlhash = hash_url(url)
        return cls.objects(urlhash=urlhash).count() > 0


pre_save.connect(Reuse.pre_save, sender=Reuse)
post_save.connect(Reuse.post_save, sender=Reuse)


class ReuseIssue(Issue):
    subject = db.ReferenceField(Reuse)


class ReuseDiscussion(Discussion):
    subject = db.ReferenceField(Reuse)


class FollowReuse(Follow):
    following = db.ReferenceField(Reuse)

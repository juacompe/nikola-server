from __future__ import unicode_literals, print_function

import codecs
from contextlib import contextmanager
import json
import os

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.template import Context, loader

import django_rq

LANGUAGE_CHOICES = (
    ('en', 'English'),
    ('es', 'Spanish'),
)

MARKUP_CHOICES = (
    ('rest', 'RestructuredText'),
    ('markdown', 'MarkDown'),
    ('textile', 'Textile'),
)


BASE_BLOG_PATH = getattr(settings, "BASE_BLOG_PATH", "/tmp/blogs")
BASE_OUTPUT_PATH = getattr(settings, "BASE_OUTPUT_PATH", "/tmp/sites")
URL_SUFFIX = getattr(settings, "URL_SUFFIX", "donewithniko.la:80")


class Blog(models.Model):
    owner = models.ForeignKey(User, related_name="owner_of")
    members = models.ManyToManyField(User, related_name="member_of")
    name = models.CharField(max_length=64, unique=True)
    domain = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=128, unique=True)
    language = models.CharField(max_length=9, choices=LANGUAGE_CHOICES, default='en')
    description = models.TextField(max_length=500, blank=True)
    dirty = models.BooleanField(default=False)

    def path(self):
        return os.path.join(BASE_BLOG_PATH, self.name)

    def output_path(self):
        return os.path.join(BASE_OUTPUT_PATH, self.name + URL_SUFFIX)

    def url(self):
        if self.domain:
            return self.domain
        else:
            return self.name+".donewithniko.la"

    def save(self, *args, **kwargs):
        r=super(Blog, self).save(*args, **kwargs)
        if self.dirty:
            blog_sync.delay(self.id)
        return r

    def __unicode__(self):
        return self.title

class Post(models.Model):
    author = models.ForeignKey(User)
    blog = models.ForeignKey(Blog)
    title = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128)
    date = models.DateTimeField()
    tags = models.CharField(max_length=512, blank=True)
    text = models.TextField(max_length=100000, blank=True)
    description = models.TextField(max_length=1024, blank=True)
    dirty = models.BooleanField(default=True)
    markup = models.CharField(max_length=30, choices=MARKUP_CHOICES, default='restructuredtext')

    folder = "posts"

    class Meta:
        unique_together = (('slug', 'blog'),)
        ordering = ['-date']

    def path(self):
        return os.path.join(self.blog.path(), self.folder, "%d.%s" % (self.id, self.markup))

    def save_to_disk(self):
        template = loader.get_template('blogs/%s.tmpl' % self.markup)
        context = Context(dict(
            TITLE=self.title,
            DESCRIPTION=self.description,
            DATE=self.date.strftime('%Y/%m/%d %H:%M'),
            SLUG=self.slug,
            TAGS=self.tags,
            AUTHOR=" ".join([self.author.first_name, self.author.last_name]),
            TEXT=self.text,
            ))
        data = template.render(context)
        with codecs.open(self.path(), "wb+", "utf8") as f:
            f.write(data)

    def save(self, *args, **kwargs):
        r = super(Post, self).save(*args, **kwargs)
        if self.dirty:
            blog_sync.delay(self.blog.id)
        return r

    def __unicode__(self):
        return "{0} ({1}) in {2}".format(self.title, self.date.strftime('%Y-%m-%d %H:%M'), self.blog)

class Story(Post):

    folder = "stories"


# Tasks that are delegated to RQ

@django_rq.job
def init_blog(blog_id):
    """Create the initial structure of the blog."""
    blog = Blog.objects.get(id=blog_id)
    os.system("nikola init {0}".format(blog.path()))

@django_rq.job
def save_blog_config(blog_id):
    blog = Blog.objects.get(id=blog_id)
    config_path = os.path.join(blog.path(), "conf.py")
    conf_data_path = os.path.join(blog.path(), "conf.json")
    with codecs.open(config_path, "wb+", "utf-8") as f:
        template = loader.get_template('blogs/conf.tmpl')
        context = Context()
        data = template.render(context)
        f.write(data)
    with codecs.open(conf_data_path, "wb+", "utf-8") as f:
        data = json.dump(dict(
            BLOG_AUTHOR=" ".join([blog.owner.first_name, blog.owner.last_name]),
            BLOG_TITLE=blog.title,
            SITE_URL=blog.url(),
            BLOG_EMAIL=blog.owner.email,
            BLOG_DESCRIPTION=blog.description,
            DEFAULT_LANG=blog.language,
            OUTPUT_FOLDER=blog.output_path(),
            ), f, skipkeys=True, sort_keys=True)


@django_rq.job
def blog_sync(blog_id):
    """Dump the blog to disk, as smartly as possible."""
    needs_build = False
    blog = Blog.objects.get(id=blog_id)
    if not os.path.isdir(blog.path()):
        init_blog(blog_id)

    if blog.dirty:
        needs_build = True
        save_blog_config(blog_id)

    post_ids = set([])
    for post in blog.post_set.all():
        post_ids.add(str(post.id))
        if post.dirty or not os.path.exists(post.path()):
            print("Saving: %s" % post)
            needs_build = True
            post.dirty=False
            post.save_to_disk()
        else:
            print("Not Saving: %s" % post)

    post_folder = os.path.join(blog.path(), Post.folder)
    for fname in os.listdir(post_folder):
        if fname.split('.')[0] not in post_ids:
            needs_build = True
            print("Unlinking: %s" % fname)
            os.unlink(os.path.join(post_folder, fname))

    if needs_build:
        build_blog(blog_id)

@django_rq.job
def build_blog(blog_id):
    blog = Blog.objects.get(id=blog_id)
    with cd(blog.path()):
        os.system("nikola build")
        # This is not yet available on any Nikola release
        #os.system("nikola check --clean-files")
    blog.dirty = False
    blog.save()

# Utility thingies

@contextmanager
def cd(path):
    old_dir = os.getcwd()
    os.chdir(path)
    yield
    os.chdir(old_dir)

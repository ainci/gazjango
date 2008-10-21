from gazjango.diff_match_patch.diff_match_patch import diff_match_patch
from datetime import datetime
from gazjango.scrapers.BeautifulSoup import BeautifulSoup
import re

from django.db                   import models
from django.contrib.auth.models  import User
from django.contrib.contenttypes import generic

from gazjango.accounts.models            import UserProfile
from gazjango.comments.models            import PublicComment
from gazjango.media.models               import MediaFile, ImageFile, MediaBucket
from gazjango.misc.exceptions            import RelationshipMismatch
import gazjango.articles.formats as formats
from gazjango.misc.templatetags.extras import join_authors


class PublishedArticlesManager(models.Manager):
    "A custom manager for Articles, returning only published articles."
    
    def get_query_set(self):
        orig = super(PublishedArticlesManager, self).get_query_set()
        return orig.filter(status='p')
    
    def get_stories(self, num_top=1, num_mid=2, num_low=6, base=None):
        """
        Returns stories organized by priority. This method will do some
        rearranging to always get you the number of stories of each
        type that you request: if there are two topstories, one of them
        gets bumped down to a midstory, and if there's not enough midstories,
        we pull up the most recent article that can be a midstary, and other
        such operations.
        
        The return format looks like:
        [
            [topstory],
            [midstory1, midstory2]
            [lowstory1, lowstory2, lowstory3, ...]
        ]
        Note that these are lists, *not* QuerySets.
        
        If you need to do something more specific, you can pass `base`;
        then all the stories will come out of there. For example,
        get_stories(base=section.articles) would return stories from
        the articles in `section` (but see Section's get_stories method).
        """
        base = base or self
        
        tops = list(base.filter(position='1').order_by('?'))
        if len(tops) < num_top:
            cands = base.filter(possible_position='1').order_by('-pub_date')
            cands = cands.exclude(pk__in=[top.pk for top in tops])
            needed = num_top - len(tops)
            tops += list(cands[:needed])
        else:
            tops = tops[:num_top]
        
        exclude_pks = [top.pk for top in tops]
        mids = base.filter(position__in=('1', '2')).exclude(pk__in=exclude_pks)
        mids = list(mids.order_by('-pub_date'))
        if len(mids) < num_mid:
            cands = base.filter(possible_position__in=('1', '2'))
            
            exclude_pks += [el.pk for el in mids]
            cands = cands.exclude(pk__in=exclude_pks).order_by('-pub_date')
            
            needed = num_mid - len(mids)
            mids += list(cands[:needed])
            lows = []
        else:
            lows = mids[num_mid:]
            mids = mids[:num_mid]
        
        if len(lows) < num_low:
            exclude_pks = [el.pk for el in (tops + mids + lows)]
            cands = base.exclude(pk__in=exclude_pks).order_by('-pub_date')
            
            needed = num_low - len(lows)
            lows += cands[:needed]
        else:
            lows = lows[:num_low]
        
        return [tops, mids, lows]
    
    
    def get_top_story(self):
        """
        Returns a random article with is_topstory set. (Most of the time,
        there will only be one.)
        """
        return self.get_stories(num_top=1, num_mid=0, num_low=0)[0][0]
    

class Article(models.Model):
    """
    A story or other article to be published. Includes news stories,
    editorials, etc, but not announcements or jobs.
    
    Note that although there are a ton of summaries, only major stories (ie
    thoe that go in the topstories bit) need a long_summary or a short_summary.
    All stories, however, should have a regular summary.
    
    Stores major revisions of the article: whatever the author decides to
    save manually while writing, changes editors make afterwards, and then
    any changes made after publication. Comments can (and should) be attached
    to these revisions.
    """
    
    headline    = models.CharField(max_length=200)
    short_title = models.CharField(blank=True, max_length=80)
    slug        = models.SlugField(unique_for_date="pub_date", max_length=100)
    
    summary = models.TextField()
    short_summary = models.CharField(max_length=150, blank=True)
    long_summary  = models.TextField(blank=True)
    
    text   = models.TextField()
    format = models.ForeignKey('Format')
    
    pub_date = models.DateTimeField(default=datetime.now)
    authors  = models.ManyToManyField(UserProfile, related_name="articles", through='Writing')
    section = models.ForeignKey('articles.Section', related_name="articles")
    subsection = models.ForeignKey('articles.Subsection', related_name="articles", null=True, blank=True)
    
    highlighters = models.ManyToManyField(UserProfile, related_name='top_stories', through='Highlighting')
    
    front_image = models.ForeignKey(ImageFile, null=True, blank=True,
                                        related_name="articles_with_front")
    issue_image = models.ForeignKey(ImageFile, null=True, blank=True,
                                        related_name="articles_with_issue")
                                    
    thumbnail   = models.ForeignKey(ImageFile, null=True, blank=True,
                                    related_name="articles_with_thumbnail")
    media  = models.ManyToManyField(MediaFile, related_name="articles", blank=True)
    bucket = models.ForeignKey(MediaBucket, null=True, related_name="articles")
    
    comments = generic.GenericRelation(PublicComment,
                                       content_type_field='subject_type',
                                       object_id_field='subject_id')
    
    is_racy = models.BooleanField(default=False)
    
    STATUS_CHOICES = (
        ('d', 'Draft'),
        ('e', 'Pending Review'),
        ('w', 'Scheduled'),
        ('p', 'Published')
    )
    status = models.CharField(max_length=1, choices=STATUS_CHOICES)
    
    comments_allowed = models.BooleanField(default=True)
    
    POSITION_CHOICES = (
        ('3', 'low'),
        ('2', 'middle'),
        ('1', 'top')
    )
    pos_args = {'max_length': 1, 'choices': POSITION_CHOICES, 'default': '3'}
    position = models.CharField(**pos_args)
    possible_position = models.CharField(**pos_args)
    
    objects = models.Manager()
    published = PublishedArticlesManager()
    
    def get_title(self):
        return (self.short_title or self.headline)
    
    def longest_summary(self):
        """Returns long_summary if we have it, else summary."""
        return (self.long_summary or self.summary)
    
    def shortest_summary(self):
        """Returns short_summary if we have it, else summary."""
        return (self.short_summary or self.summary)
    
    def allow_edit(self, user):
        return self.authors.filter(user__pk=user.pk).count() > 0 \
            or user.has_perm('articles.change_article');
    
    def add_author(self, *authors):
        for author in authors:
            Writing.objects.create(article=self, user=author)
    
    def text_at_revision(self, revision):
        """Returns the text as it was at the specified revision."""
        if revision.article != self:
            raise RelationshipMismatch()
        d = diff_match_patch()
        rewound = self.text
        for r in self.revisions.filter(date__gte=revision.date):
            rewound = d.patch_apply(d.patch_fromText(r.delta), rewound)[0]
        return rewound
    
    def revise_text(self, revised_text, reviser=None):
        if reviser is None:
            try:
                reviser = self.authors_in_order().all()[0]
            except IndexError:
                # TODO: better error handling when there's no authors
                reviser = None
        d = diff_match_patch()
        patch = d.patch_toText(d.patch_make(revised_text, self.text))
        
        ArticleRevision.objects.create(article=self, delta=patch, reviser=reviser)
        self.text = revised_text
        self.save()
    
    
    def formatted_text(self, revision=None):
        text = self.text_at_revision(revision) if revision else self.text
        formatter = getattr(formats, self.format.function)
        return formatter(text)
    
    
    _not_http = re.compile(r'^\s*(?!https?://)', re.IGNORECASE)
    _img = re.compile(r'^img://', re.IGNORECASE)
    def resolved_text(self, revision=None):
        """
        Formats the text (at the revision specified by ``revision``, if
        passed) and then goes through and replaces the image references within
        it to links that will actually work.
        """
        text = self.formatted_text(revision)
        if self.media.count() > 0 or re.search("<img", text, re.IGNORECASE):
            soup = BeautifulSoup(text)
            
            for image in soup.findAll("img", src=self._not_http):
                src = image['src']
                if src.startswith('img://'):
                    src = src[6:]
                image['src'] = self.resolve_image_link(src)
            for a in soup.findAll("a", href=self._img):
                a['href'] = self.resolve_image_link(a['href'][6:])
            return unicode(soup)
        else:
            return text
    
    def resolve_image_link(self, image_path, complain=False):
        """
        Turns relative image links in articles into absolute URLs. For
        example, if an article's text includes "<img src='cool-pic'/>",
        ``resolved_text`` will call this function to replace 'cool-pic' with
        '/files/some-bucket/cool-pic'.
        
        If the path in the image includes a '/', it's parsed as 
        'bucket-slug/image-slug'. Otherwise, we first check the media files
        that are explicitly associated with this article, and then this
        article's bucket. This can potentially cause confusion if the
        article is associated with 'lame-bucket', 'awesome-bucket/cool-pic'
        is in the article's media m2m, and 'lame-bucket' has a file called 
        'cool-pic'. In this case, we use 'awesome-bucket/cool-pic'.
        
        This function will throw a MediaFile.MultipleObjectsReturned
        error, or return "[ambiguous reference to (slug)]", depending on the
        value of ``complain``, if article.media has more than one file (in
        different buckets) with the same slug, and the bucket slug is not
        explicit. Don't let this happen. The UI for setting associated media
        should either not allow this, or give stern warnings.
        """
        if "/" in image_path:
            bucket_slug, slug = image_path.split("/", 1)
            args = {'bucket__slug': bucket_slug, 'slug': slug}
        else:
            args = {'slug': image_path}
        
        if complain:
            def error(exception, message): raise exception
        else:
            def error(exception, message): return message
        
        try: # self.media should be cached, so we try it first
            image = self.media.get(**args)
        except MediaFile.DoesNotExist:
            try:
                args.setdefault('bucket__slug', self.bucket.slug)
                image = ImageFile.objects.get(**args)
                self.media.add(image)
            except ImageFile.DoesNotExist, e:
                return error(e, "")
        except MediaFile.MultipleObjectsReturned, e:
            return error(e, "[ambiguous reference to '%s']" % image_path)
        
        return image.get_absolute_url()
    
    
    def related_list(self, num=None):
        """Returns a QuerySet of related stories."""
        # TODO: improve related_list
        rel = self.section.published_articles().exclude(pk=self.pk).order_by('-pub_date')
        return rel[:num] if num else rel
    
    def authors_in_order(self):
        return self.authors.order_by('writing___order')
    
    def author_names(self):
        return join_authors(self.authors_in_order(), 'ptx')
    
    def section_if_special(self):
        """
        Returns the name of the subsection if it's special, 
        section if that's special, else None.
        """
        if self.subsection and self.subsection.is_special:
            return self.subsection.name
        elif self.section.is_special:
            return self.section.name
        else:
            return None
    
    def __unicode__(self):
        return self.slug
    
    @models.permalink
    def get_absolute_url(self):
        d = self.pub_date
        a = [str(x) for x in (d.year, d.month, d.day)]
        return ('article', a + [self.slug])
    
    class Meta:
        app_label = 'articles'
    

class Writing(models.Model):
    """
    Represents an author's having written a story.
    
    Its main purpose is to allow for ordering the authors.
    """
    article = models.ForeignKey(Article)
    user    = models.ForeignKey(UserProfile)
    
    class Meta:
        order_with_respect_to = 'article'
        unique_together = ('article', 'user')
        app_label = 'articles'
    
    def __unicode__(self):
        return "%s wrote %s" % (self.user.username, self.article.slug)
    

class Highlighting(models.Model):
    """
    Represents an author's having chosen to highlight a story on 
    their profile page.
    
    Mainly to allow for ordering.
    """
    article = models.ForeignKey(Article)
    user = models.ForeignKey(UserProfile)
    
    class Meta:
        order_with_respect_to = 'article'
        unique_together = ('article', 'user')
        app_label = 'articles'
    
    def __unicode__(self):
        return "%s highlited %s" % (self.user.username, self.article.slug)
    

class ArticleRevision(models.Model):
    """
    A revision of an article. Only deltas are stored.
    
    Note that the most recent text is stored in the article's text attribute,
    while earlier versions are stored as revisions...as such, these are 
    "reverse diffs." For example, if an article has versions 1, 2, and 3, 
    version 3 is stored directly with the article, and there are 
    ArticleRevisions to go from 3 to 2 and from 2 to 1.
    """
    article = models.ForeignKey(Article, related_name='revisions')
    reviser = models.ForeignKey(UserProfile, related_name='revisions')
    delta   = models.TextField()
    date    = models.DateTimeField(default=datetime.now)
    
    class Meta:
        ordering = ['-date']
        app_label = 'articles'
    
    def __unicode__(self):
        return u"%s - %s" % (self.article.slug, self.date)
    

class Format(models.Model):
    """ A format: html, textile, etc. """
    
    name     = models.CharField(max_length=30, unique=True)
    function = models.CharField(max_length=30)
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        app_label = 'articles'
    

from django.template  import RequestContext
from django.shortcuts import render_to_response, get_object_or_404
from helpers          import get_by_date_or_404, filter_by_date
from articles.models      import Article, Category, Special, PhotoSpread
from announcements.models import Announcement
from comments.models      import PublicComment
from issues.models        import Menu, Weather, WeatherJoke
from jobs.models          import JobListing
from datetime import date, timedelta


def article(request, slug, year, month, day, print_view=False, template="story.html"):
    story = get_by_date_or_404(Article, year, month, day, slug=slug)
    data = {
        'story': story,
        'related': story.related_list(3),
        'topstory': Article.published.get_top_story(),
        'comments': Article.comments.all().order_by('time'),
        'print_view': print_view
    }
    rc = RequestContext(request)
    return render_to_response(template, data, context_instance=rc)

def articles(request, year=None, month=None, day=None, template="article_list.html"):
    articles = filter_by_date(Article.published.all(), year, month, day)
    data = {'articles': articles, 'year': year, 'month': month, 'day': day}
    rc = RequestContext(request)
    return render_to_response(template, data, context_instance=rc)


def homepage(request, template="index.html"):
    data = {
        'topstory': Article.published.get_top_story(),
        'midstories': Article.published.get_secondary_stories(2),
        'lowstories': Article.published.get_tertiary_stories(6),
        
        'comments': PublicComment.visible.order_by('-time').all()[:5],
        'weather': Weather.objects.for_today(),
        'joke': WeatherJoke.objects.latest(),
        
        'specials': Special.objects.order_by('-date').all()[:10],
        'announcements': Announcement.community.now_running(),
        'jobs': JobListing.objects.filter(is_filled=False)[:3]
    }
    rc = RequestContext(request)
    return render_to_response(template, data, context_instance=rc)


def menu_partial(request):
    menu = Menu.objects.for_today()
    return render_to_response("scraped/menu.html", { 'menu': menu })


def spread(request, slug, year, month, day, num=None):
    spread = get_by_date_or_404(PhotoSpread, year, month, day, slug=slug)
    data = {'spread': spread}
    if num:
        data['page'] = spread.get_photo_number(num)
    rc = RequestContext(request)
    return render_to_response("photo_spread.html", data, context_instance=rc)


search        = lambda request, **kwargs: render_to_response("base.html", locals())
comment       = lambda request, **kwargs: render_to_response("base.html", locals())
email_article = lambda request, **kwargs: render_to_response("base.html", locals())

def category(request, slug, year=None, month=None, day=None, recurse=True, template="category.html"):
    category = get_object_or_404(Category, slug=slug)
    all_articles = category.all_articles() if recurse else category.articles
    data = {
        'category': category,
        'articles': filter_by_date(all_articles, year, month, day),
        'year': year,
        'month': month,
        'day': day
    }
    rc = RequestContext(request)
    return render_to_response(template, data, context_instance=rc)

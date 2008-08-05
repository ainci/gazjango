# Note: run this INSTEAD of init_dev_data; do not run both as they conflict

import MySQLdb as db
from optparse import OptionParser
import os,sys,re

sys.path.append("..")
sys.path.append("../gazjango")

import settings
from django.core.management import setup_environ
setup_environ(settings)


from django.contrib.auth.models         import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models        import Site
from django.contrib.flatpages.models    import FlatPage
import tagging

from accounts.models      import UserProfile, UserKind, Position
from accounts.models      import ContactMethod, ContactItem
from announcements.models import Announcement
from articles.models      import Article, Section, Subsection, Format
from articles.models      import Special, SpecialsCategory, DummySpecialTarget
from comments.models      import PublicComment
from issues.models        import Issue, Menu, Weather, WeatherJoke, Event
from media.models         import ImageFile, MediaBucket
from polls.models         import Poll, Option
from jobs.models          import JobListing

from collections import defaultdict

parser = OptionParser()
parser.add_option("-d", "--dbhost", dest="host", help="connect to HOST", metavar="HOST")
parser.add_option("-u", "--user", dest="user", help="authenticate as USER", metavar="USER")
parser.add_option("-p", "--passwd", dest="passwd", help="using PASSWD", metavar="PASSWD")

(options, args) = parser.parse_args()

conn = db.connect(
    host=options.host,
    user=options.user,
    passwd=options.passwd,
    db="gazette_daily"
)

cursor = conn.cursor()

### Site

Site.objects.all().delete()
site = Site.objects.create(name="The Daily Gazette", domain="daily.swarthmore.edu", pk=1)

### Groups

reader_group       = Group.objects.create(name="Readers")
reporter_group     = Group.objects.create(name="Reporters")
photographer_group = Group.objects.create(name="Photographers")
editor_group       = Group.objects.create(name="Editors")
admin_group        = Group.objects.create(name="Admins")
ex_staff_group     = Group.objects.create(name="Ex-Staff")

ct = ContentType.objects.get_for_model(PublicComment)

reader_group.permissions.add(
    Permission.objects.get(content_type=ct, codename='can_post_directly')
)

ab = Permission.objects.get(content_type=ct,codename='can_moderate_absolutely')
for g in (editor_group, admin_group):
    g.permissions.add(ab)


### Users

student = UserKind.objects.create(kind='s')

yim        = ContactMethod.objects.create(name="YIM")
aim        = ContactMethod.objects.create(name="AIM")
gtalk      = ContactMethod.objects.create(name="GTalk / Jabber")

def make_user(username, first, last, email=None, contact={}, bio=None, kind=student, groups=None):
    print email
    user = User.objects.create_user(username, email)
    user.first_name = first
    user.last_name  = last
    if groups:
        user.groups = groups
        user.is_staff = (reporter_group in groups or photographer_group in groups or admin_group in groups or editor_group in groups)
    user.save()
    
    profile = UserProfile.objects.create(user=user, bio=bio, kind=kind)
    for method in contact:
        profile.contact_items.create(method=method, value=contact[method])
    
    return user

users = {}
cursor.execute("SELECT id, user_nicename, user_email, display_name FROM gazette_users")
while True:
    row = cursor.fetchone()
    if row is None:
        break
    old_id, username, email, display_name = row
    
    users[int(old_id)] = defaultdict(lambda:"",
                                     username= username,
                                     email=email,
                                     display_name=display_name
                                     )

cursor.execute("SELECT user_id, meta_key, meta_value FROM gazette_usermeta WHERE NOT meta_key IN ('rich_editing', 'admin_color', 'closedpostboxes_post', 'gazette_autosave_draft_ids')")
capabilities_regex = re.compile('s:\d+:\"(?P<id>\w+)\";b:\d+;')
while True:
    row = cursor.fetchone()
    if row is None:
        break
    old_id, key, val = row
    if key == "gazette_capabilities":
        print "lsdkglkfjgfg"
        val = capabilities_regex.findall(val)
    users[old_id][key] = val

print users
for id in users:
    u = users[id]
    groups = []
    if "administrator" in u["gazette_capabilities"]:
        groups.append(admin_group)
    if "reader" in u["gazette_capabilities"]:
        groups.append(reader_group)
    if "photographer" in u["gazette_capabilities"]:
        groups.append(photographer_group)
    if "editor" in u["gazette_capabilities"]:
        groups.append(editor_group)
    if "old_writers" in u["gazette_capabilities"]:
        groups.append(ex_staff_group)

    contact = {}
    contact[aim] = u['aim']
    contact[gtalk] = u['jabber']
    contact[yim] = u['yim']
    print id,u['email']
    make_user(username=u["username"], first=u["first_name"], last=u["last_name"], email=u['email'], contact=contact, bio=u['description'], groups=groups)


### Posts

posts = {}
cursor.execute("SELECT id, post_author, post_date, post_title, post_content, post_excerpt, post_status, post_name, post_modified FROM gazette_posts")


cursor.close()
conn.close()

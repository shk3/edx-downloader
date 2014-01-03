#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python 2/3 compatibility imports
from __future__ import print_function
from __future__ import unicode_literals

try:
    from http.cookiejar import CookieJar
except ImportError:
    from cookielib import CookieJar

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

try:
    from urllib.request import urlopen
    from urllib.request import build_opener
    from urllib.request import install_opener
    from urllib.request import HTTPCookieProcessor
    from urllib.request import Request
    from urllib.request import URLError
except ImportError:
    from urllib2 import urlopen
    from urllib2 import build_opener
    from urllib2 import install_opener
    from urllib2 import HTTPCookieProcessor
    from urllib2 import Request
    from urllib2 import URLError

# we alias the raw_input function for python 3 compatibility
try:
    input = raw_input
except:
    pass

import argparse
import getpass
import json
import os
import os.path
import re
import sys

from subprocess import Popen, PIPE
from datetime import timedelta, datetime

from bs4 import BeautifulSoup


def get_initial_token(base_url):
    """
    Create initial connection to get authentication token for future requests.

    Returns a string to be used in subsequent connections with the
    X-CSRFToken header or the empty string if we didn't find any token in
    the cookies.
    """
    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))
    install_opener(opener)
    opener.open(base_url)

    for cookie in cj:
        if cookie.name == 'csrftoken':
            return cookie.value

    return ''


def get_page_contents(url, headers):
    """
    Get the contents of the page at the URL given by url. While making the
    request, we use the headers given in the dictionary in headers.
    """
    result = urlopen(Request(url, None, headers))
    try:
        charset = result.headers.get_content_charset(failobj="utf-8")  # for python3
    except:
        charset = result.info().getparam('charset') or 'utf-8'
    return result.read().decode(charset)


def directory_name(initial_name):
    """ cleans the string from non-allowed characters """
    import string
    allowed_chars = string.digits+string.ascii_letters+" _."
    result_name = ""
    for ch in initial_name:
        if allowed_chars.find(ch) != -1:
            result_name += ch
    return result_name if result_name != "" else "course_folder"


def edx_json2srt(o):
    """ converts subtitles from the json format to srt """
    i = 1
    output = ''
    for (s, e, t) in zip(o['start'], o['end'], o['text']):
        if t == "":
            continue
        output += str(i) + '\n'
        s = datetime(1, 1, 1) + timedelta(seconds=s/1000.)
        e = datetime(1, 1, 1) + timedelta(seconds=e/1000.)
        output += "%02d:%02d:%02d,%03d --> %02d:%02d:%02d,%03d" % \
            (s.hour, s.minute, s.second, s.microsecond/1000,
             e.hour, e.minute, e.second, e.microsecond/1000) + '\n'
        output += t + "\n\n"
        i += 1
    return output


def edx_get_subtitle(url, headers):
    """ returns a string with the subtitles content from the url """
    """ or None if no subtitles are available """
    try:
        jsonString = get_page_contents(url, headers)
        jsonObject = json.loads(jsonString)
        return edx_json2srt(jsonObject)
    except URLError as e:
        print('[warning] edX subtitles (error:%s)' % e.reason)
        return None


def parse_args():
    """
    Parse the arguments/options passed to the program on the command line.
    """
    parser = argparse.ArgumentParser(prog='edx-dl',
                                     description='Get videos from edx.org',
                                     epilog='For further use information,'
                                     'see the file README.md',)
    # optional
    parser.add_argument('-u',
                        '--username',
                        action='store',
                        help='your edX username (email)')
    parser.add_argument('-p',
                        '--password',
                        action='store',
                        help='your edX password')
    parser.add_argument('-f',
                        '--format',
                        dest='format',
                        action='store',
                        default=None,
                        help='maximum resolution format to download')
    parser.add_argument('-s',
                        '--with-subtitles',
                        dest='subtitles',
                        action='store_true',
                        default=False,
                        help='download subtitles with the videos')
    parser.add_argument('-o',
                        '--output-dir',
                        action='store',
                        dest='output_dir',
                        help='store the files to the specified directory',
                        default='Downloaded')
    parser.add_argument('--course-url',
                        action='store',
                        default=None,
                        help='target course url'
                        '(e.g., https://courses.edx.org/courses/BerkeleyX/CS191x/2013_Spring/info/)'
                        )

    args = parser.parse_args()
    return args


def get_website_info(url):
    """ returns a dict with the appropriate url schemas needed to access """
    """ the courses: """

    """ * base_url: the base url e.g. https://courses.edx.org """
    """ * login_url: the login url e.g. https://courses.edx.org/login_ajax """
    """ * dashboard_url: the dashboard url e.g. https://courses.edx.org/dashboard """

    website_info = {}
    if not url:
        # FIXME: we default to edx if no url is passed for the interactive version
        url = 'https://courses.edx.org'
    website_info['base_url'] = url
    website_info['login_url'] = url + '/login_ajax'
    website_info['dashboard_url'] = url + '/dashboard'
    return website_info


def get_course_list(website_info, headers):
    """
    Returns a list of dicts with each dict consisting of:

    * id: the 'id' of the course, e.g. 'HarvardX/SPU27x/2013_Oct'
    * name: name of the course we are currently enrolled in.
    * state: a string saying if the course has started or not.
    * url: url of the course e.g. https://courses.edx.org/courses/HarvardX/SPU27x/2013_Oct/info
    
    """
    dash = get_page_contents(website_info['dashboard_url'], headers)
    soup = BeautifulSoup(dash)
    courses_list = []
    courses = soup.find_all('article', 'course')
    for course in courses:
        c = {}
        c['name'] = course.h3.text.strip()
        c['url'] = website_info['base_url'] + course.a['href']
        c['id'] = course.a['href'].lstrip('/courses/')
        if c['id'].endswith('info') or c['id'].endswith('info/'):
            c['id'] = c['id'].rstrip('/info/')
            c['state'] = 'Started'
        else:
            c['id'] = c['id'].rstrip('/about/')
            c['state'] = 'Not started'
        courses_list.append(c)
    return courses_list


def build_headers(base_url):
    # If nothing else is chosen, we chose the default user agent:
    default_user_agents = {"chrome": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.31 (KHTML, like Gecko) Chrome/26.0.1410.63 Safari/537.31",
                           "firefox": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:24.0) Gecko/20100101 Firefox/24.0",
                           "edx": 'edX-downloader/0.01'}
    user_agent = default_user_agents['edx']
    headers = {
        'User-Agent': user_agent,
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
        'Referer': base_url,
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': get_initial_token(base_url),
    }
    return headers


def main():
    args = parse_args()

    # if no args means we are calling the interactive version
    is_interactive = len(sys.argv) == 1
    if is_interactive:
        args.username = input('Username: ')
        args.password = getpass.getpass()

    if not args.username or not args.password:
        print("You must supply username AND password to log-in")
        sys.exit(2)

    #FIXME: When we remove the interactive version course_url will be mandatory
    website_url = None
    if args.course_url:
        urlparse_res = urlparse(args.course_url)
        website_url = urlparse_res.scheme + "://" + urlparse_res.netloc

    website_info = get_website_info(website_url)

    # Prepare Headers
    headers = build_headers(website_info['base_url'])

    # Login
    post_data = urlencode({'email': args.username, 'password': args.password,
                           'remember': False}).encode('utf-8')
    request = Request(website_info['login_url'], post_data, headers)
    response = urlopen(request)
    resp = json.loads(response.read().decode('utf-8'))
    if not resp.get('success', False):
        print(resp.get('value', "Wrong Email or Password."))
        exit(2)

    # Get user courses
    courses = get_course_list(website_info, headers)
    selected_course = None
    if is_interactive or not args.course_url:
        print('You can access %d courses on edX' % len(courses))
        i = 0
        for c in courses:
            i += 1
            print('%d - %s -> %s' % (i, c['name'], c['state']))

        c_number = int(input('Enter Course Number: '))
        while c_number > len(courses) or courses[c_number - 1]['state'] != 'Started':
            print('Enter a valid Number for a Started Course ! between 1 and ',
                  len(courses))
            c_number = int(input('Enter Course Number: '))
        selected_course = courses[c_number - 1]
    else:
        for c in courses:
            if c['url'] == args.course_url:
                selected_course = c
                break
        if not selected_course:
            print('[error] Invalid course url, or user not registered (course_url=%s)' % args.course_url)
            sys.exit(3)

    ## Getting Available Weeks
    courseware_url = selected_course['url'].replace('info', 'courseware')
    courseware = get_page_contents(courseware_url, headers)
    soup = BeautifulSoup(courseware)

    data = soup.find("section",
                     {"class": "content-wrapper"}).section.div.div.nav
    WEEKS = data.find_all('div')
    weeks = [(w.h3.a.string, ['https://courses.edx.org' + a['href'] for a in
             w.ul.find_all('a')]) for w in WEEKS]
    numOfWeeks = len(weeks)

    # Choose Week or choose all
    print('%s has %d weeks so far' % (selected_course['name'], numOfWeeks))
    w = 0
    for week in weeks:
        w += 1
        print('%d - Download %s videos' % (w, week[0].strip()))
    print('%d - Download them all' % (numOfWeeks + 1))

    w_number = int(input('Enter Your Choice: '))
    while w_number > numOfWeeks + 1:
        print('Enter a valid Number between 1 and %d' % (numOfWeeks + 1))
        w_number = int(input('Enter Your Choice: '))

    if w_number == numOfWeeks + 1:
        links = [link for week in weeks for link in week[1]]
    else:
        links = weeks[w_number - 1][1]

    video_id = []
    subsUrls = []
    regexpSubs = re.compile(r'data-caption-asset-path=(?:&#34;|")([^"&]*)(?:&#34;|")')
    splitter = re.compile(r'data-streams=(?:&#34;|").*1.0[0]*:')
    extra_youtube = re.compile(r'//w{0,3}\.youtube.com/embed/([^ \?&]*)[\?& ]')
    for link in links:
        print("Processing '%s'..." % link)
        page = get_page_contents(link, headers)

        id_container = splitter.split(page)[1:]
        # 11 is the length of a basic youtube url
        video_id += [link[:11] for link in
                     id_container]
        subsUrls += [website_info['base_url'] +
                     regexpSubs.search(container).group(1) + id + ".srt.sjson"
                     for id, container in zip(video_id[-len(id_container):],id_container)]
        # Try to download some extra videos which is referred by iframe
        extra_ids = extra_youtube.findall(page)
        video_id += [link[:YOUTUBE_VIDEO_ID_LENGTH] for link in
                     extra_ids]
        subsUrls += ['' for link in extra_ids]

    video_link = ['http://youtube.com/watch?v=' + v_id
                  for v_id in video_id]

    if len(video_link) < 1:
        print('WARNING: No downloadable video found.')
        sys.exit(0)

    if is_interactive:
        # Get Available Video formats
        os.system('youtube-dl -F %s' % video_link[-1])
        print('Choose a valid format or a set of valid format codes e.g. 22/17/...')
        args.format = input('Choose Format code: ')

        args.subtitles = input('Download subtitles (y/n)? ').lower() == 'y'

    print("[info] Output directory: " + args.output_dir)

    # Download Videos
    c = 0
    for v, s in zip(video_link, subsUrls):
        c += 1
        target_dir = os.path.join(args.output_dir,
                                  directory_name(selected_course['name']))
        filename_prefix = str(c).zfill(2)
        cmd = ["youtube-dl",
               "-o", os.path.join(target_dir, filename_prefix + "-%(title)s.%(ext)s")]
        if args.format:
            cmd.append("--max-quality")
            cmd.append(args.format)
        if args.subtitles:
            cmd.append('--write-sub')
        cmd.append(str(v))

        popen_youtube = Popen(cmd, stdout=PIPE, stderr=PIPE)

        youtube_stdout = b''
        enc = sys.getdefaultencoding()
        while True:  # Save output to youtube_stdout while this being echoed
            tmp = popen_youtube.stdout.read(1)
            youtube_stdout += tmp
            print(tmp.decode(enc), end="")
            sys.stdout.flush()
            # do it until the process finish and there isn't output
            if tmp == b"" and popen_youtube.poll() is not None:
                break

        if args.subtitles:
            filename = get_filename(target_dir, filename_prefix)
            subs_filename = os.path.join(target_dir, filename + '.srt')
            if not os.path.exists(subs_filename):
                subs_string = edx_get_subtitle(s, headers)
                if subs_string:
                    print('[info] Writing edX subtitles: %s' % subs_filename)
                    open(os.path.join(os.getcwd(), subs_filename),
                         'wb+').write(subs_string.encode('utf-8'))


def get_filename(target_dir, filename_prefix):
    """ returns the basename for the corresponding filename_prefix """
    # this whole function is not the nicest thing, but isolating it makes
    # things clearer , a good refactoring would be to get
    # the info from the video_url or the current output, to avoid the
    # iteration from the current dir
    filenames = os.listdir(target_dir)
    subs_filename = filename_prefix
    for name in filenames:  # Find the filename of the downloaded video
        if name.startswith(filename_prefix):
            (basename, ext) = os.path.splitext(name)
            return basename

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCTRL-C detected, shutting down....")
        sys.exit(0)

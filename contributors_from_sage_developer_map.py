# Adapted from scripts/geocode.py

import certifi
import urllib3
import pprint

from xml.dom.minidom import parseString


def sage_contributors():
    http = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',
        ca_certs=certifi.where()
    )

    ack = parseString(http.request('GET', 'https://raw.githubusercontent.com/sagemath/website/master/conf/contributors.xml').data.decode('utf-8'))
    yield from sage_contributors_from_xmldoc(ack)


def sage_contributors_from_xmldoc(ack):
    for c in ack.getElementsByTagName("contributors")[0].childNodes:
        if c.nodeType != ack.ELEMENT_NODE:
            continue
        if c.tagName != "contributor":
            continue
        yield c


# API
def trac_to_github(contributors=None):
    if contributors is None:
        contributors = sage_contributors()
    usernames = {}
    for c in contributors:
        trac = c.getAttribute("trac")
        github = c.getAttribute("github")
        if trac:
            for t in trac.split(','):
                t = t.strip()
                if t:
                    if github:
                        usernames[t] = github
                    elif t not in usernames:
                        usernames[t] = None
    return usernames


# API
def trac_full_names(contributors=None):
    if contributors is None:
        contributors = sage_contributors()
    usernames = {}
    for c in contributors:
        trac = c.getAttribute("trac")
        if not trac:
            gh = c.getAttribute("github")
            if gh:
                trac = 'gh-' + gh
        name = c.getAttribute("name")
        if trac and name:
            for t in trac.split(','):
                t = t.strip()
                if t:
                    usernames[t] = name
    return usernames


if __name__ == "__main__":

    usernames = trac_to_github()
    pprint.pp(usernames)

    print('# Trac accounts without github account: ' + ','.join(
        t for t, g in usernames.items() if not g))

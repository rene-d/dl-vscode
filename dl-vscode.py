#! /usr/bin/env python3

import sys
import argparse
import subprocess
import re
import os
import requests
import pprint
import datetime
import email.utils
import dateutil.parser
import yaml
import bz2
import json


check_mark = "\033[32m\N{check mark}\033[0m"            # ✔
heavy_ballot_x = "\033[31m\N{heavy ballot x}\033[0m"    # ✘



my_extensions = ['ms-vscode.cpptools',
                 'ms-python.python',
                 'MS-CEINTL.vscode-language-pack-fr',
                 'vector-of-bool.cmake-tools']


def reorder_extensions(f):
    if f in my_extensions:
        return my_extensions.index(f)
    return len(my_extensions) + 1


def my_parsedate(text):
    return datetime.datetime(*email.utils.parsedate(text)[:6])


def download(url, file):
    r = requests.get(url, allow_redirects=True)
    if r.status_code == 200:
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, 'wb') as f:
            f.write(r.content)
        if r.headers.get('last-modified'):
            d = my_parsedate(r.headers['last-modified'])
            ts = d.timestamp()
            os.utime(file, (ts, ts))
        return True
    else:
        print(heavy_ballot_x, r.status_code, url)
        return False



def dl_extensions(extensions):

    # markdown skeliton
    md = []
    md.append(['Logo', 'Nom', 'Description', 'Auteur', 'Version', 'Date'])
    md.append(['-' * len(i) for i in md[0]])

    # prepare the REST query
    data = {
        "filters": [
            {
                "criteria": [
                    { "filterType": 8, "value": "Microsoft.VisualStudio.Code" },
                    { "filterType": 12, "value": "4096" },
                ],
            }
        ],
        "flags": 0x200 + 0x80       # IncludeLatestVersionOnly IncludeAssetUri
    }                               # cf. vs/platform/extensionManagement/node/extensionGalleryService.ts

    for ext in extensions:
        data['filters'][0]['criteria'].append({'filterType': 7, 'value': ext})

    headers = {'Content-type': 'application/json', 'Accept': 'application/json;api-version=3.0-preview.1'}

    # query the gallery
    req = requests.post("https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery", json=data, headers=headers)
    res = req.json()
    # if args.verbose: pprint.pprint(res)

    # analyze the response
    if 'results' in res and 'extensions' in res['results'][0]:
        for e in res['results'][0]['extensions']:

            # print(e['displayName'])
            # print(e['shortDescription'])
            # print(e['publisher']['displayName'])
            # for v in e['versions']:
            #     print(v['version'])
            #     print(v['assetUri'] + '/Microsoft.VisualStudio.Services.VSIXPackage')
            # print()

            row = []

            key =  e['publisher']['publisherName'] + '.' + e['extensionName']
            version = e['versions'][0]['version']
            vsix = 'vsix/' + key + '-' + version + '.vsix'
            icon = 'icons/' + key + '.png'

            # colonne 1: icône + nom avec lien
            row.append("![{}]({})".format(e['displayName'], icon))

            row.append("[{}]({})".format(
                e['displayName'],
                'https://marketplace.visualstudio.com/items?itemName=' + key))

            # colonne 2: description
            row.append(e['shortDescription'])

            # colonne 3: auteur
            row.append('[{}]({})'.format(
                e['publisher']['displayName'],
                'https://marketplace.visualstudio.com/publishers/' + e['publisher']['publisherName']))

            # colonne 4: version
            row.append("[{}]({})".format(e['versions'][0]['version'], vsix))

            # colonne 5: date de mise à jour
            d = dateutil.parser.parse(e['versions'][0]['lastUpdated'])
            row.append(str(d))

            md.append(row)



            if not os.path.exists(vsix):
                if os.path.exists(icon):
                    os.unlink(icon)

                url = e['versions'][0]['assetUri'] + '/Microsoft.VisualStudio.Services.VSIXPackage'

                print("{:20} {:35} {:10} {} downloading...".format(e['publisher']['publisherName'], e['extensionName'], version, heavy_ballot_x))
                download(url, vsix)
            else:
                print("{:20} {:35} {:10} {}".format(e['publisher']['publisherName'], e['extensionName'], version, check_mark))


            if key == "ms-vscode.cpptools":
                for platform in ['linux', 'win32', 'osx', 'linux32']:
                    url = f"https://github.com/Microsoft/vscode-cpptools/releases/download/v{version}/cpptools-{platform}.vsix"
                    vsix = f'vsix/{key}-{platform}-{version}.vsix'
                    if not os.path.exists(vsix):
                        print("{:20} {:35} {:10} {} downloading...".format("", "cpptools-" + platform, version, heavy_ballot_x))
                        download(url, vsix)
                    else:
                        print("{:20} {:35} {:10} {}".format("", "cpptools-" + platform, version, check_mark))


            if not os.path.exists(icon):
                os.makedirs("icons", exist_ok=True)
                url = e['versions'][0]['assetUri'] + '/Microsoft.VisualStudio.Services.Icons.Small'
                ok = download(url, icon)
                if not ok:
                    # default icon: { visual studio code }
                    url = 'https://cdn.vsassets.io/v/20180521T120403/_content/Header/default_icon.png'
                    download(url, icon)


    with open("extensions.md", "w") as f:
        for i in md:
            print('|'.join(i), file=f)



def dl_code():

    repo = "http://packages.microsoft.com/repos/vscode"
    url = f"{repo}/dists/stable/main/binary-amd64/Packages.bz2"
    r = requests.get(url)
    if r.status_code == 200:
        data = bz2.decompress(r.content).decode('utf-8')

        packages = []
        sect = {}
        key, value = None, None

        def _add_value():                       # save key/value into current section
            nonlocal key, value, sect
            if key and value:
                sect[key] = value

                if key == 'version':
                    # crée une chaîne qui devrait être l'ordre des numéros de version
                    sect['_version'] = '|'.join(x.rjust(16, '0') if x.isdigit() else x.ljust(16) for x in re.split(r'\W', value))

                key = value = None

        def _add_sect():
            nonlocal sect, packages
            _add_value()
            if len(sect) != 0:
                packages.append(sect)
                sect = {}                       # start a new section

        for line in data.split('\n'):
            if line == '':                      # start a new section
                _add_sect()
            elif line[0] == ' ':                # continue a key/value
                if value is not None:
                    value += line
            else:                               # start a new key/value
                _add_value()
                key, value = line.split(':', maxsplit=1)
                key = key.lower()               # make key always lowercase
                value = value.lstrip()

        _add_sect()                             # flush section if any

        #packages.sort(key=lambda x: re.split(r'\W', x['version']))
        packages.sort(key=lambda x: x['_version'], reverse=True)

        latest = None
        for p in packages:
            if p['package'] == 'code':
                latest = p
                break

        if latest:
            filename = latest['filename']
            url = f"{repo}/{filename}"
            deb_filename = os.path.basename(filename)
            filename = os.path.join("code", deb_filename)

            if os.path.exists(filename):
                print("{:50} {:20} {}".format(latest['package'], latest['version'], check_mark))
            else:
                print("{:50} {:20} {} downloading...".format(latest['package'], latest['version'], heavy_ballot_x))
                download(url, filename)

            with open("code.json", "w") as f:
                json.dump({'code_url': filename, 'code_deb': deb_filename}, f)


def main():
    parser = argparse.ArgumentParser()
    #parser.add_argument("--scan", help="scan and download installed extensions", action='store_true')
    parser.add_argument("-f", "--conf", help="configuration file", default="extensions.yaml")
    parser.add_argument("-i", "--installed", help="scan installed extensions", action='store_true')
    parser.add_argument("-x", help="extra feature", action='store_true')
    parser.add_argument("-v", "--verbose", help="increase verbosity", action='store_true')

    args = parser.parse_args()

    dl_code()
    print()

    extensions = list()

    # get the listed extensions
    if os.path.exists(args.conf):
        conf = yaml.load(open(args.conf))
        if 'extensions' in conf:
            listed = set(conf['extensions'])
            extensions = list(listed.union(extensions))
        conf = None

    if args.installed:
        # get installed extensions
        s = subprocess.check_output("code --list-extensions", shell=True)
        installed = set(s.decode().split())

        # conf = yaml.load(open(args.conf))
        # conf['installed'] = list(installed)
        # conf['extensions'] = list(listed - installed)
        # yaml.dump(conf, stream=sys.stdout, default_flow_style=False)

        extensions = list(installed.union(extensions))

    dl_extensions(extensions)


if __name__ == '__main__':
    main()
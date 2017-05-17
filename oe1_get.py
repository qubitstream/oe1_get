#!/usr/bin/env python3

# This script downloads, converts and tags broadcasts of Austria's Ö1 radio station.
# It is compatible with the current 2017 program schedule.
#
# Written by: Christoph Haunschmidt 2017
# License: GNU GPL 2.0

import os
import sys
import json
import re
import bz2
import argparse
import configparser
import datetime
import shutil
import subprocess
from collections import defaultdict, namedtuple

import requests
import mutagen
import html2text
from tqdm import tqdm

__version__ = '2017-05-18.0'

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
HTML_CACHE_FN = 'oe1cache.json.bz2'
FFMPEG_EXECUTABLE = 'ffmpeg'

# URL for last 7 days json data
CURRENT_URL = r'https://audioapi.orf.at/oe1/api/json/current/broadcasts'
DOWNLOAD_BASE_URL = r'http://loopstream01.apa.at/?channel=oe1&id='

INI_SECTION_DEFAULTS = {
    'TimeWindow':'00:00-24:00',
    'Days': '0,1,2,3,4,5,6',  # 0 = Monday, ... 6 = Sunday
    'TargetDir': '{DOWNLOAD_BASEDIR}/{SECTION}',
    'TargetName': '{scheduled_start:%Y-%m-%d %Hh%M} Ö1 {title} {info_1line_limited}',
    'KeepOriginal': 'True',
    'FFmpegArguments': '-c:a libopus -b:a 36k -vbr on -compression_level 10 -frame_duration 60 -application voip',
    'title': '.*',
    # Keys starting with "Tag" will be used for tagging the output file
    # E.g. "TagArtist"" will contain the "artist" tag
    'TagArtist': 'Ö1',
    'TagAlbum': '{SECTION}',
    'TagTitle': '{scheduled_start:%Y-%m-%d %H:%M} {title} {info_1line_limited} (id:{id})',
    'TagDate': '{scheduled_start:%Y}',
    'TagGenre': 'Podcast',
    'TagComment': '{extended_info}',
}


def repl_unsave(file_name):
    """Replace unsave characters for a windows file system"""
    tmp_str = re.sub(r'[:?]+', '', file_name)
    return re.sub(r'[\\/:"*?<>|]+', '_', tmp_str)


def tag_media_file(media_fn, tag_dict):
    if not os.path.isfile(media_fn):
        print('No such file to tag: {}'.format(media_fn), file=sys.stderr)
        return
    mf = mutagen.File(media_fn, easy=True)
    for key, value in tag_dict.items():
        value = re.sub(r'\r\n|\r|\n', '\r\n', value)
        try:
            mf[key] = value
            if key == 'comment':
                mf['description'] = value
        except mutagen.MutagenError as e:
            print('Error tagging {}: {}'.format(media_fn, e), file=sys.stderr)
            return
    mf.save()

def encode_audiofile(media_fn, conv_fn, *, length=None, ffmpeg_options=None, ffmpeg_executable=FFMPEG_EXECUTABLE):
    command_list = [ffmpeg_executable, '-y']
    if length is not None:
        command_list.extend(['-t', str(length)])
    command_list.extend(['-i', media_fn])
    if ffmpeg_options is None:
        command_list.extend(['-c:a', 'libopus', '-b:a', '36k', '-vbr', 'on',
            '-compression_level', '10', '-frame_duration', '60', '-application', 'voip'])
    else:
        command_list += ffmpeg_options.split(' ')

    command_list.extend(['-sample_fmt', 's16'])
    command_list.extend([conv_fn])
    try:
        ffmpeg = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        stdout, stderr = ffmpeg.communicate()
        if ffmpeg.returncode != 0:
            raise IOError('FFmpeg conversion error, exit code: {}, command:\n{}'.format(
                ffmpeg.returncode, ' '.join(command_list)))
    except:
        # remove incomplete file
        if os.path.isfile(conv_fn):
            os.remove(conv_fn)
        raise


class Broadcast:
    def __init__(self, initial_data_dict=None):
        self.data = {}
        self.metadata = {}
        if initial_data_dict is not None:
            self.update_data(initial_data_dict)

    def update_data(self, update_dict):
        self.data.update(update_dict)
        strip_re = re.compile(r'^[\r\n\s]+|[\r\n\s]+$')
        h = html2text.HTML2Text()
        h.ignore_links = True
        scheduled_start = datetime.datetime.fromtimestamp(int(self.data['scheduledStart']) // 1000)
        self.metadata.update({
            'id': self.data['id'],
            'title': (self.data.get('title', None) or '').strip(),
            'subtitle': strip_re.sub('', h.handle((self.data.get('subtitle', None) or '')).strip()),
            'href': self.data.get('href', None) or '',
            'url': self.data.get('url', None) or '',
            'tags': ', '.join(self.data.get('tags', [])),
            'scheduled_start': scheduled_start,
            'extended_info': '',
            'extended_info_text_only': '',
            'info_1line': '',
            'download_url': self.download_url,
        })
        text = []
        for key in 'subtitle,description,pressRelease,akm'.split(','):
            value = strip_re.sub('', self.data.get(key, None) or '')
            if value:
                text.append(value)
        if text:
            h.ignore_links = False
            self.metadata['extended_info'] = '\n\n'.join((strip_re.sub('', h.handle(t)) for t in text))
            h.ignore_links = True
            self.metadata['extended_info_text_only'] = '\n\n'.join((strip_re.sub('', h.handle(t)) for t in text))
            self.metadata['info_1line'] = re.sub(r'[\n\r\s]+', ' ', self.metadata['extended_info_text_only'])
            self.metadata['info_1line_limited'] = self.metadata['info_1line'][0:120]

    @property
    def id(self):
        return self.data['id']

    @property
    def scheduled_datetime(self):
        return datetime.datetime.fromtimestamp(int(self.data['scheduledStart']) // 1000)

    @property
    def download_filename(self):
        return repl_unsave(self.data['streams'][0]['loopStreamId'])

    @property
    def download_url(self):
        return DOWNLOAD_BASE_URL + self.download_filename

    def __str__(self):
        return '{scheduled_start:%Y-%m-%d %Hh%M} Ö1 {title} {info_1line_limited}'.format_map(self.metadata)


class BroadcastsDownloader:
    def __init__(
            self,
            download_basedir,
            ini_file,
            dry_run=False,
            no_cache=False,
            retag=False,
            reconvert=False,
            cache_file=None,
            length=0,
            ffmpeg=FFMPEG_EXECUTABLE):
        self.download_basedir = download_basedir
        if not cache_file:
            cache_file = os.path.normpath(os.path.join(self.download_basedir, HTML_CACHE_FN))
        self.dry_run = dry_run
        self.no_cache = no_cache
        self.retag = retag
        self._length = length
        self.reconvert = reconvert
        self.he2 = False
        self.ini_fn = ini_file
        self.html_cache_fn = cache_file
        self.ffmpeg = ffmpeg
        self.broadcasts_for_current_week = []
        self.broadcasts_of_interest = defaultdict(set)
        self.broadcasts_data = {}
        self.broadcasts_rules = {}

        try:
            self._load_configuration()
        except Exception as e:
            print('Error parsing configuration file: {}'.format(self.ini_fn), file=sys.stderr)
            sys.exit(1)

        try:
            self._load_cache()
        except Exception as e:
            print('Error opening cache file: {}, {}'.format(self.html_cache_fn, e), file=sys.stderr)

        try:
            broadcasts_last_week = requests.get(CURRENT_URL).json()
        except Exception as e:
            print('Error loading current broadcasts: {}'.format(e), file=sys.stderr)
            sys.exit(1)

        for broadcasts_for_day in broadcasts_last_week:
            for single_broadcast in broadcasts_for_day['broadcasts']:
                self.broadcasts_for_current_week.append(single_broadcast)

        broadcasts_of_interest = []
        for broadcast in self.broadcasts_for_current_week:
            section = self._is_broadcast_of_interest(broadcast)
            if section:
                broadcasts_of_interest.append((section, broadcast))

        print('Parsing information for {} broadcasts:'.format(len(broadcasts_of_interest)))
        for section, broadcast_of_interest in tqdm(broadcasts_of_interest, desc='   Parsing'):
            href = broadcast_of_interest['href']
            if not self.no_cache and href in self.broadcasts_data and 'message' not in self.broadcasts_data[href]:
                data = self.broadcasts_data[href]
            else:
                try:
                    data = requests.get(href).json()
                    if 'message' in data:
                        print('No data available for {}'.format(href), file=sys.stderr)
                        continue
                    self.broadcasts_data[href] = data
                except Exception as e:
                    print('Error loading info from {}: {}'.format(href, e), file=sys.stderr)
                    continue
            if 'streams' in data and len(data['streams']):
                self.broadcasts_of_interest[section].add(Broadcast(data))

    def download_interesting(self):
        for section, broadcasts in tqdm(self.broadcasts_of_interest.items(), unit='Broadcast', desc='Processing'):
            for broadcast in broadcasts:
                try:
                    metadata = {
                        'SECTION': section,
                        'DOWNLOAD_BASEDIR': self.download_basedir,
                    }
                    metadata.update(broadcast.metadata)

                    target_dir = self.broadcasts_rules[section]['ini']['TargetDir'].format_map(metadata)
                    ffmpeg_options = self.broadcasts_rules[section]['ini']['FFmpegArguments']
                    target_fn = repl_unsave(self.broadcasts_rules[section]['ini']['TargetName'].format_map(metadata))
                    if 'opus' in ffmpeg_options.lower():
                        target_fn += '.opus'
                    elif 'mp3' in ffmpeg_options.lower():
                        target_fn += '.mp3'
                    elif 'vorbis' in ffmpeg_options.lower():
                        target_fn += '.ogg'
                    elif 'aac' in ffmpeg_options.lower():
                        target_fn += '.m4a'
                    else:
                        tqdm.write('Warning: no extension for output audio file {}'.format(target_fn))
                    download_fn = os.path.normpath(os.path.join(target_dir, broadcast.download_filename))
                    conversion_fn = os.path.normpath(os.path.join(target_dir, target_fn))
                    if not self.dry_run:
                        if not os.path.isdir(target_dir):
                            os.makedirs(target_dir)
                        # download media file
                        if not os.path.isfile(download_fn):
                            try:
                                response = requests.get(broadcast.download_url, stream=True)
                                total_size = int(response.headers.get('content-length', 0))
                                chunk_size = 1024 * 1024
                                with open(download_fn, 'wb') as fout:
                                    for data in tqdm(
                                            response.iter_content(chunk_size),
                                            desc=broadcast.download_filename,
                                            total=total_size // chunk_size,
                                            leave=False,
                                            unit='MB',
                                            unit_scale=False):
                                        fout.write(data)
                            except:
                                if os.path.isfile(download_fn):
                                    os.remove(download_fn)
                                raise
                        if not os.path.isfile(download_fn):
                            raise ValueError('File {} does not exist'.format(download_fn))
                        if download_fn == conversion_fn:
                            raise ValueError('Conversion: Same filename as input file')
                        newly_converted = False
                        if not os.path.isfile(conversion_fn) or self.reconvert:
                            # convert media file
                            tqdm.write('Encoding {}'.format(target_fn))
                            encode_audiofile(download_fn, conversion_fn,
                                ffmpeg_executable=self.ffmpeg,
                                ffmpeg_options=ffmpeg_options,
                                length=self._length if self._length > 0 else None)
                            newly_converted = True
                        else:
                            tqdm.write('Using already existing file: {}'.format(conversion_fn))
                        # tag media file
                        if newly_converted or self.retag:
                            tag_dict = {}
                            for key, value in self.broadcasts_rules[section]['ini'].items():
                                if key.startswith('Tag'):
                                    tag_name = key[3:].lower()
                                    tag_dict[tag_name] = value.format_map(metadata)
                            tag_media_file(conversion_fn, tag_dict)
                        if self.broadcasts_rules[section]['ini']['KeepOriginal'].lower() == 'false':
                            os.remove(download_fn)
                except Exception as e:
                    tqdm.write('Error {} {}'.format(broadcast, e))
                    continue


    def _is_broadcast_of_interest(self, broadcast):
        """Returns the corresponding section if it is of interest"""
        dt = datetime.datetime.fromtimestamp(int(broadcast['scheduledStart']) // 1000)
        scheduled_time = dt.time()
        weekday = dt.weekday()
        for section, rule in self.broadcasts_rules.items():
            if (rule['start_time'] <= scheduled_time <= rule['end_time']
                    and weekday in rule['days']
                    and rule['search_regexes']['title'].search(broadcast['title'])):
                return section
        return ''

    def _load_configuration(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        try:
            with open(self.ini_fn, 'r', encoding='utf-8') as fin:
                config.read_file(fin)
        except Exception as e:
            print('Unable to parse configuration file: {}\n{}'.format(self.ini_fn, e), file=sys.stderr)
            sys.exit(1)
        for section in config.sections():
            self.broadcasts_rules[section] = {}
            sr = self.broadcasts_rules[section]
            sr['ini'] = INI_SECTION_DEFAULTS.copy()
            sr['ini'].update({key: value for key, value in config[section].items()})
            m = re.match(r'\s*(\d\d):(\d\d)\s*\-\s*(\d\d):(\d\d)\s*', sr['ini']['TimeWindow'])
            sr['start_time'] = datetime.time(int(m.group(1)), int(m.group(2)))
            sr['end_time'] = datetime.time(int(m.group(3)), int(m.group(4)))
            sr['search_regexes'] = {
                'title': re.compile(sr['ini']['title'], re.IGNORECASE)
            }
            sr['days'] = set(map(int, sr['ini']['Days'].split(',')))

    def _load_cache(self):
        with bz2.BZ2File(self.html_cache_fn, 'rb') as fin:
            self.broadcasts_data.update(json.loads(fin.read().decode('utf-8')))

    def _write_cache(self):
        if self.broadcasts_data:
            with bz2.BZ2File(self.html_cache_fn, 'wb', compresslevel=9) as fout:
                fout.write(json.dumps(self.broadcasts_data, indent=4, ensure_ascii=False).encode('utf-8'))

    def __del__(self):
        try:
            self._write_cache()
        except Exception as e:
            print('Error writing cache file: {}'.format(e), file=sys.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download media files from ORF Ö1 7-Tage on demand services',
        epilog='Written by Christoph Haunschmidt, Version %s' % __version__)

    parser.add_argument('download_basedir',
        help='root path containing the downloaded files')

    parser.add_argument('ini_file',
        help='ini file for the description of items to download')

    parser.add_argument('--dry-run', action='store_true',
        help='dry run, do not do conversion, tagging or deleting')

    parser.add_argument('--no-cache', action='store_true', help='do not use cached data')

    parser.add_argument('--reconvert', action='store_true',
        help='do the conversion again, even if the file already exists (overwrite it)')

    parser.add_argument('--retag', action='store_true',
        help='tag already existing target files again')

    parser.add_argument('--cache-file', default='',
        help='the bz2 compressed json cache file (default: [download_basedir]/%s' % HTML_CACHE_FN)

    parser.add_argument('--length', metavar='SECONDS', type=int, default=0,
        help='just convert these first seconds (useful for debugging)')

    parser.add_argument('--ffmpeg', metavar='FFMPEG_EXECUTABLE',
        default=FFMPEG_EXECUTABLE, help='ffmpeg executable (default: %(default)s)')

    ARGS = parser.parse_args()

    if shutil.which(ARGS.ffmpeg) is None:
        print('FFmpeg executable not found: {}'.format(ARGS.ffmpeg), file=sys.stderr)
        sys.exit(1)

    broadcast_downloader = BroadcastsDownloader(**vars(ARGS))
    broadcast_downloader.download_interesting()
    if ARGS.dry_run:
        print('This was a dry run.')

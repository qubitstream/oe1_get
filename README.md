# oe1_get.py

This script downloads, converts and tags broadcasts of Austria's [ORF Ö1 radio station](http://oe1.orf.at/).
It is compatible with the current 2017 program schedule
([Programmschema 2017](http://oe1.orf.at/pdf/01_OE1_03_17_Programmfolder_100x288_endversion.pdf)).

__NOTE__: It is recommended to run this script more than one time per week, because otherwise broadcasts become
inaccessible.

## Q&As

**Q: Why not use Ö1's podcasts service to download broadcasts?**

A: Because not everything is made available there for download. With this script, you can download any file in
the [on-demand library](http://oe1.orf.at/player/) (broadcasts of the last 7 days).

## Requirements ##

* Python 3.4+
* Additional python libraries: `tqdm, requests, mutagen, html2text`. Install them via `pip install -U tqdm requests mutagen html2text`.
* [`ffmpeg`](https://ffmpeg.org/), either in PATH or with the path to the executable given via the `--ffmpeg` argument

## Usage

    usage: oe1_get.py [-h] [--dry-run] [--no-cache] [--reconvert] [--retag]
                      [--cache-file CACHE_FILE] [--length SECONDS]
                      [--ffmpeg FFMPEG_EXECUTABLE]
                      download_basedir ini_file

    Download media files from ORF Ö1 7-Tage on demand services

    positional arguments:
      download_basedir      root path containing the downloaded files
      ini_file              ini file for the description of items to download

    optional arguments:
      -h, --help            show this help message and exit
      --dry-run             dry run, do not do conversion, tagging or deleting
      --no-cache            do not use cached data
      --reconvert           do the conversion again, even if the file already
                            exists (overwrite it)
      --retag               tag already existing target files again
      --cache-file CACHE_FILE
                            the bz2 compressed json cache file (default:
                            [download_basedir]/oe1cache.json.bz2
      --length SECONDS      just convert these first seconds (useful for
                            debugging)
      --ffmpeg FFMPEG_EXECUTABLE
                            ffmpeg executable (default: ffmpeg)

    Written by Christoph Haunschmidt, Version 2017-05-18.0

## The ini file

See `oe1_download.ini.example` for a commented example.

### Available variables in the ini-file:

These can be accessed and manipulated via Python's powerful [`str.format()`](https://docs.python.org/3/library/string.html#formatspec) syntax.

| Name | Data Source | Description |
| --- | --- | --- |
| `DOWNLOAD_BASEDIR` | command line parameter: `download_basedir` | root directory of the media files (given as command line parameter) |
| `SECTION` | ini file | the current section header |
| `extended_info` | broadcast JSON: `subtitle`, `description`, `pressRelease`, `akm` | values joined together as markdown |
| `extended_info_text_only` | broadcast JSON: `subtitle`, `description`, `pressRelease`, `akm` | the same as above, only with the links stripped (=text only) |
| `href` | broadcast JSON: `href` | URL of the broadcasts JSON data |
| `id` | broadcast JSON: `id` | given by Ö1 - probably too short to be unique |
| `info_1line` | `extended_info_text_only` | value of `extended_info_text_only` without newlines |
| `info_1line_limited` | `extended_info_text_only` | the same as above, limited to 120 chars |
| `scheduled_start` | broadcast JSON: `scheduled_start` | the scheduled start of the broadcast; is a python `datetime` object. You can format it, e.g. `{scheduled_start:%Y-%m-%d %Hh%M}` |
| `subtitle` | broadcast JSON: `subtitle` | subtitle of broadcast |
| `tags` | broadcast JSON: `tags` | comma separated tags of the metadata json given by Ö1 |
| `title` | broadcast JSON: `title` | title of broadcast |
| `url` | broadcast JSON: `url` | URL of the broadcast series |
| `download_url` | composed from broadcast JSON: `streams[0]['loopStreamId']` | URL to the audio file |

## Author

Christoph Haunschmidt
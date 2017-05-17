# oe1_get.py

This script downloads, converts and tags broadcasts of [Austria's Ö1 radio station](http://oe1.orf.at/).
It is compatible with the current 2017 program schedule
([Programmschema 2017](http://oe1.orf.at/pdf/01_OE1_03_17_Programmfolder_100x288_endversion.pdf)).

__It is recommended to run this script at more than one time per week, because otherwise broadcasts become
inaccessible after a week.__

## Q&As

**Q: Why not use Ö1's podcasts service to download broadcasts?**

A: Because not everything is made available there for download. With this script, you can download any file in
the [on-demand library](http://oe1.orf.at/player/) (broadcasts of the last 7 days).

## Requirements ##

* Python 3.4+
* Additional python libraries: `tqdm, requests, mutagen, html2text`. Install them via `pip install -U tqdm requests mutagen html2text`.
* [`ffmpeg`](https://ffmpeg.org/), either in path or the path to the executable given via the `--ffmpeg` argument

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

The can be accessed and manipulated via Python's `str.format()` syntax.

| Name | Description |
| --- | --- |
| `DOWNLOAD_BASEDIR` | root directory of the media files (given as command line parameter) |
| `SECTION` | ini section |
| `extended_info` | text of `subtitle`, `description`, `pressRelease` and `akm` joined together as markdown |
| `extended_info_text_only` | the same as above, only with the links stripped |
| `href` | URL of the metadata json given by Ö1 |
| `id` | `id` given by Ö1 |
| `info_1line` | value of `extended_info_text_only` without newlines |
| `info_1line_limited` | the same as above, limited to 120 chars |
| `scheduled_start` | the scheduled start of the broadcast; is a python `datetime` object |
| `subtitle` | subtitle of the metadata json given by Ö1 |
| `tags` | comma separated tags of the metadata json given by Ö1 |
| `title` | title of the metadata json given by Ö1 |
| `url` | URL of the broadcast series |
| `download_url` | URL for the audio file |

## Author

Christoph Haunschmidt
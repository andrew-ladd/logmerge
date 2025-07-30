#!/usr/bin/python3
#
# Copyright (c) Microsoft Corporation. All rights reserved.
#
# See LICENSE for license information.

import argparse
import collections
import datetime
import re
import sys
import os
import zipfile
import tempfile
import shutil


cloud_init_pattern = re.compile(r'(\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d,\d\d\d) ')
iso8601_pattern = re.compile(r'(\d\d\d\d/\d\d/\d\d \d\d:\d\d:\d\d\.\d+) ')
timestamp_pattern = re.compile(r'((\d+)(\.\d+)?) ')
custom_pattern = re.compile(r'^ (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2},\d{3})')
custom_format = '%Y-%m-%dT%H:%M:%S,%f'


def make_argument_parser():
    """
    Build command line argument parser.
    :return: Parser for command line
    :rtype argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(description="Merge multiple log files, from different sources, preserving order")
    parser.add_argument("-p", "--prefix", help="List of prefixes to be applied to log entries", nargs="+")
    parser.add_argument("--no-prefix", help="Suppress automatic generation of prefixes", action="store_true")
    parser.add_argument("-r", "--regex", help="Regex to match and capture the entire timestamp")
    parser.add_argument("-f", "--format", help="strptime format to convert the captured timestamp")
    # parser.add_argument("--colors", help="List of colors for each log", required=False, nargs="+")
    parser.add_argument("-c", "--colorize", help="Color-code log output", required=False, action="store_true")
    parser.add_argument("-j", "--jamfcloud", help="Fetch JAMFSoftwareServer logs from a specified folder or zip file")
    parser.add_argument("-o", "--output", help="Output filename prefix (default: merged)", default="merged")
    parser.add_argument('logfiles', nargs='*')

    return parser


def parse_datetime(line):
    """
    Parse the date and time from the beginning of a log line. If no timestamp can be recognized, return None.
    :param line: The log line to be parsed
    :return: Either a datetime or None
    """
    if custom_pattern:
        match = custom_pattern.match(line)
        if match:
            # Convert milliseconds to microseconds by padding with zeros
            timestamp_str = match.group(1)
            # Replace the 3-digit milliseconds with 6-digit microseconds
            timestamp_str = timestamp_str.replace(',', '.') + '000'
            entry_datetime = datetime.datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%f')
            return entry_datetime

    match = iso8601_pattern.match(line)
    if match:
        entry_datetime = datetime.datetime.strptime(match.group(1), '%Y/%m/%d %H:%M:%S.%f')
        return entry_datetime

    match = cloud_init_pattern.match(line)
    if match:
        entry_datetime = datetime.datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S,%f')
        return entry_datetime

    match = timestamp_pattern.match(line)
    if match:
        entry_datetime = datetime.datetime.utcfromtimestamp(float(match.group(1)))
        return entry_datetime

    return None


class Logfile:
    def _advance(self):
        """
        Read and accumulate saved line plus continuation lines (if any). When a line beginning with a timestamp is
        found, save that (new initial) line and the timestamp, then return the flattened accumulated array of strings.

        Invariant: All lines of the current entry have been read. The instance knows the timestamp of the *next*
        log entry, and has already read the first line of that entry, *or* EOF has been reached and the appropriate
        internal marker has been set. The instance is prepared for either timestamp() or entry() to be called.
        :rtype str[]
        """
        results = [self._line]
        while True:
            line = self._f.readline()
            if line == '':
                self._eof = True
                return results
            timestamp = parse_datetime(line)
            if timestamp is not None:
                self._line = line
                self._timestamp = timestamp
                return results
            results.append(line)

    def __init__(self, path):
        self._f = open(path, "r")
        self._eof = False
        self._timestamp = datetime.datetime.max
        self._line = ''
        self._advance()     # Ignoring any untimestamped lines at the beginning of the log

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def timestamp(self):
        if self._eof:
            raise EOFError
        return self._timestamp

    def entry(self):
        if self._eof:
            raise EOFError
        return self._advance()

    def close(self):
        self._f.close()
        self._f = None
        self._line = ''
        self._eof = True


class LogSet:
    def __init__(self, pathnames):
        self._logs = {}
        for pathname in pathnames:
            self._logs[pathname] = Logfile(pathname)

    def next_entry(self):
        """
        Find the earliest entry in the set of logs, advancing that one logfile to the next entry.
        :return: Pathname of the logfile, the entry as an array of one or more lines.
        :rtype str, str[]
        """
        if len(self._logs) == 0:
            raise EOFError
        low_path = ''
        low_timestamp = datetime.datetime.max
        to_delete = []
        for log_name, log in self._logs.items():
            try:
                timestamp = log.timestamp()
            except EOFError:
                to_delete.append(log_name)
                continue
            if timestamp <= low_timestamp:
                low_path = log_name
                low_timestamp = timestamp
        for log_name in to_delete:
            self._logs[log_name].close()
            del self._logs[log_name]
        if len(self._logs) == 0:
            # Last log hit EOF and was deleted
            raise EOFError
        return low_path, self._logs[low_path].entry()


def render(line, prefix_arg=None, color=-1):
    """
    Turn a line of text into a ready-to-display string.
    If prefix_arg is set, prepend it to the line.
    If color is set, change to that color at the beginning of the rendered line and change out before the newline (if
    there is a newline).
    :param str line: Output line to be rendered
    :param str prefix_arg: Optional prefix to be stuck at the beginning of the rendered line
    :param int color: If 0-255, insert escape codes to display the line in that color
    """
    pretext = '' if prefix_arg is None else prefix_arg
    if -1 < color < 256:
        pretext = "\x1b[38;5;{}m{}".format(str(color), pretext)
        if line[-1] == "\n":
            line = "{}\x1b[0m\n".format(line[:-1])
        else:
            line = "{}\x1b[0m".format(line)
    return "{}{}".format(pretext, line)


def get_unique_filename(base_name):
    """
    Generate a unique filename by appending a monotonically increasing integer if the base name is taken.
    :param base_name: The base name for the file
    :return: A unique filename
    """
    if not os.path.exists(base_name):
        return base_name

    base, ext = os.path.splitext(base_name)
    counter = 1
    while True:
        new_name = f"{base}{counter}{ext}"
        if not os.path.exists(new_name):
            return new_name
        counter += 1


def process_logs(args):
    """Process the log files and create merged output"""
    global custom_pattern, custom_format
    
    if args.logfiles is None or len(args.logfiles) < 2:
        print("Requires at least two logfiles")
        exit(1)
    elif bool(args.format) != bool(args.regex):
        print("Requires both timestamp regex and format or none")
        exit(1)

    if args.regex:
        custom_pattern = re.compile(args.regex.encode().decode('unicode_escape'))
        custom_format = args.format

    prefixes = collections.defaultdict(lambda: '')
    colorize = args.colorize if sys.stdout.isatty() else False
    colors = collections.defaultdict(lambda: 15 if colorize else -1)
    index = 1
    limit = len(args.prefix) if args.prefix else 0
    no_prefix = args.no_prefix or (colorize and limit == 0)

    for path in args.logfiles:
        if not no_prefix:
            prefixes[path] = "{} ".format(args.prefix[index-1]) if index <= limit else "log{} ".format(index)
        if colorize:
            colors[path] = index
        index += 1

    merger = LogSet(args.logfiles)
    output_file = get_unique_filename(f"{args.output}.log")
    with open(output_file, "w") as outfile:
        while True:
            try:
                path, entry = merger.next_entry()
            except EOFError:
                print(f"Merged logs saved to {output_file}")
                break
            for line in entry:
                outfile.write(render(line, prefixes[path], colors[path]))


def handle_jamfcloud_option(args):
    """Handle the -j/--jamfcloud option for JAMF log processing"""
    base_folder = args.jamfcloud
    temp_dir = None
    
    try:
        # Check if it's a zip file
        if base_folder.endswith('.zip') and os.path.isfile(base_folder):
            # Extract zip to temporary directory
            temp_dir = tempfile.mkdtemp()
            try:
                with zipfile.ZipFile(base_folder, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                # Find the extracted folder (should be the first directory in temp_dir)
                extracted_contents = os.listdir(temp_dir)
                if len(extracted_contents) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_contents[0])):
                    base_folder = os.path.join(temp_dir, extracted_contents[0])
                else:
                    base_folder = temp_dir
                print(f"Extracted zip to: {base_folder}")
            except zipfile.BadZipFile:
                print(f"Error: {args.jamfcloud} is not a valid zip file")
                if temp_dir:
                    shutil.rmtree(temp_dir)
                exit(1)
        else:
            # It's a regular directory, strip trailing slash
            base_folder = base_folder.rstrip('/')
        
        # Set up the log file paths
        primary_log = os.path.join(base_folder, 'primary/JAMFSoftwareServer/JAMFSoftwareServer_0729_0002.log')
        secondary_log = os.path.join(base_folder, 'secondary/JAMFSoftwareServer/JAMFSoftwareServer_0729_0030.log')
        
        # Check if files exist
        if not os.path.exists(primary_log):
            print(f"Error: Primary log file not found: {primary_log}")
            if temp_dir:
                shutil.rmtree(temp_dir)
            exit(1)
        if not os.path.exists(secondary_log):
            print(f"Error: Secondary log file not found: {secondary_log}")
            if temp_dir:
                shutil.rmtree(temp_dir)
            exit(1)
            
        args.logfiles = [primary_log, secondary_log]
        
        # Process the logs
        process_logs(args)
        
    finally:
        # Clean up temporary directory if it was created
        if temp_dir:
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")


def main():
    global custom_pattern, custom_format
    
    args = make_argument_parser().parse_args()
    
    # Handle JAMF cloud option
    if args.jamfcloud:
        handle_jamfcloud_option(args)
        exit(0)
    
    # Handle regular log file processing
    process_logs(args)


main()

# :vi ai sw=4 expandtab ts=4 :

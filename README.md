# logmerge

logmerge merges multiple log files into a single stream, preserving the total ordering of events across the multiple log files. The merged output is saved to a file named `merged.log` (or `merged1.log`, `merged2.log`, etc. if the file already exists).

## Requirements

This tool requires Python 3. If you don't have Python 3 installed:

### macOS Installation

Install Python 3 using Homebrew (recommended):

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3
brew install python
```

### Other Platforms

- **Linux**: Use your distribution's package manager (e.g., `apt install python3`, `yum install python3`)
- **Windows**: Download from [python.org](https://www.python.org/downloads/) or use Windows Package Manager (`winget install Python.Python.3`)

## Usage

```bash
python3 logmerge.py [OPTIONS] logfile1 logfile2 [logfile3 ...]
```

### Basic Usage

Merge two or more log files:

```bash
python3 logmerge.py app.log system.log error.log
```

### Command Line Options

- `-p, --prefix PREFIX [PREFIX ...]` - List of prefixes to be applied to log entries from each file
- `--no-prefix` - Suppress automatic generation of prefixes
- `-r, --regex REGEX` - Regex to match and capture the entire timestamp (must be used with `-f`)
- `-f, --format FORMAT` - strptime format to convert the captured timestamp (must be used with `-r`)
- `-c, --colorize` - Color-code log output (automatically disabled when output is not a TTY)
- `-j, --jamfcloud FOLDER_OR_ZIP` - Combine Primary and Secondary node JAMFSoftwareServer logs from a specified folder or zip file

### JAMF Cloud Log Processing

The `-j/--jamfcloud` option provides a convenient way to process JAMF Pro cloud logs. This option automatically extracts and merges the JAMFSoftwareServer logs from both primary and secondary servers.

**Process a zip file:**

```bash
python3 logmerge.py -j logs.zip
```

**Process an extracted folder:**

```bash
python3 logmerge.py -j /path/to/extracted/folder
```

When using this option, the script will:

1. If given a zip file, extract it to a temporary directory
2. Locate the JAMFSoftwareServer logs in both `primary/` and `secondary/` folders
3. Merge the logs chronologically
4. Clean up any temporary files automatically

The expected folder structure is:

```text
folder/
├── primary/
│   └── JAMFSoftwareServer/
│       └── JAMFSoftwareServer_MMDD_NNNN.log
└── secondary/
    └── JAMFSoftwareServer/
        └── JAMFSoftwareServer_MMDD_NNNN.log
```

### Examples

**Basic merge with automatic prefixes:**

```bash
python3 logmerge.py app.log system.log
# Output lines will be prefixed with "log1 " and "log2 "
```

**Merge with custom prefixes:**

```bash
python3 logmerge.py -p "APP" "SYS" "ERR" app.log system.log error.log
# Output lines will be prefixed with "APP ", "SYS ", and "ERR "
```

**Merge without any prefixes:**

```bash
python3 logmerge.py --no-prefix app.log system.log
```

**Merge with color coding (when outputting to terminal):**

```bash
python3 logmerge.py -c app.log system.log error.log
```

**Merge with custom timestamp format:**

```bash
python3 logmerge.py -r "(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})" -f "%Y-%m-%d %H:%M:%S" app.log system.log
```

## Features

- Supports multiple built-in timestamp formats:
  - Cloud-init format: `YYYY-MM-DD HH:MM:SS,mmm` (e.g., `2023-07-29 14:30:45,123`)
  - ISO8601-like format: `YYYY/MM/DD HH:MM:SS.ffffff` (e.g., `2023/07/29 14:30:45.123456`)
  - Unix timestamp: integer or float seconds since epoch (e.g., `1690635045.123`)
  - Custom format: `YYYY-MM-DDTHH:MM:SS,mmm` (e.g., `2023-07-29T14:30:45,123`)
- Custom timestamp parsing via regex and strptime format
- Automatic prefix generation (`log1`, `log2`, etc.) or custom prefixes
- Color-coded output when displaying to terminal
- Handles multi-line log entries (continuation lines without timestamps)
- Generates unique output filenames to avoid overwriting existing files

## Output

The merged log is saved to `merged.log` in the current directory. If this file already exists, a unique filename will be generated (e.g., `merged1.log`, `merged2.log`, etc.).

## Limitations

- Assumes all timestamps are UTC. The currently-supported timestamp formats don't support a timezone tag.
- Timestamps are not reformatted. If merged logs use different timestamp formats, the merged log will expose that.
- Requires at least two log files to merge.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

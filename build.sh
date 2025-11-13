#!/bin/bash

# This script copies over a build configuration from build_config/ then runs `python3 -m build`.

if [ -z "$1" ]; then
    echo "Usage: $0 <config_name>"
    echo "Error: You must provide the name of a configuration folder inside 'build_config'."
    exit 1
fi

CONFIG_NAME="$1"
SOURCE_DIR="build_config/$CONFIG_NAME"

# Validate that the source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Configuration directory '$SOURCE_DIR' was not found."
    echo "Please ensure the folder exists before running the script."
    exit 1
fi

# Get a list of files to be copied for later cleanup
# NOTE: This method may not work correctly with filenames containing spaces.
FILES_TO_CLEAN=$(ls -A "$SOURCE_DIR")


# Copy files and build
cp -r "$SOURCE_DIR"/. .
python3 -m build
BUILD_STATUS=$? # Store build status to exit with it later

# Clean up the copied files
if [ ! -z "$FILES_TO_CLEAN" ]; then
    for item in $FILES_TO_CLEAN; do
        rm -rf "./$item"
    done
fi

# Exit with the original build status code
exit $BUILD_STATUS

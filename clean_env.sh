#!/bin/bash

# Usage: ./clean_env.sh envs/.env .env.example

INPUT_ENV_FILE=${1:-.env}
OUTPUT_ENV_FILE=${2:-.env.example}

if [ ! -f "$INPUT_ENV_FILE" ]; then
    echo "Error: $INPUT_ENV_FILE does not exist."
    exit 1
fi

echo "Cleaning $INPUT_ENV_FILE and generating $OUTPUT_ENV_FILE..."

# Use awk to process lines:
awk '
    BEGIN { FS="="; OFS="=" }
    # Skip completely empty lines
    /^[[:space:]]*$/ { print; next }
    # Keep comment lines as is
    /^[[:space:]]*#/ { print; next }
    # For lines with key=value, clear the value or set placeholder
    {
        gsub(/^[ \t]+|[ \t]+$/, "", $1); # Trim whitespace from key
        if (NF > 1) {
            print $1"=";  # Keep key= but empty value
            # Optionally, to replace with a placeholder:
            # print $1"=your_value_here"
        } else {
            print $1"="  # Key without explicit value
        }
    }
' "$INPUT_ENV_FILE" > "$OUTPUT_ENV_FILE"

echo "Done! Created $OUTPUT_ENV_FILE"
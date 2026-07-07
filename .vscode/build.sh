#!/usr/bin/env bash

# Build the frontend JS
echo "Building frontend bundle..."
pnpm run build

echo "Packaging plugin..."
# Resolve pluginname from .vscode/settings.json, fallback to decky-torrent
PLUGIN_NAME=$(python3 -c "
import json, os
try:
    with open('.vscode/settings.json') as f:
        print(json.load(f).get('pluginname', 'decky-torrent'))
except:
    print('decky-torrent')
")

# Clean output dir
mkdir -p out
rm -f "out/${PLUGIN_NAME}.zip"

# Create a staging folder to package cleanly
STAGING_DIR="/tmp/decky-stage"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/${PLUGIN_NAME}"

# Copy required files to staging folder
cp -r dist "$STAGING_DIR/${PLUGIN_NAME}/"
cp main.py "$STAGING_DIR/${PLUGIN_NAME}/"
cp package.json "$STAGING_DIR/${PLUGIN_NAME}/"
cp plugin.json "$STAGING_DIR/${PLUGIN_NAME}/"
cp LICENSE "$STAGING_DIR/${PLUGIN_NAME}/"
cp README.md "$STAGING_DIR/${PLUGIN_NAME}/"


# Zip from staging
cd "$STAGING_DIR"
zip -r "${PLUGIN_NAME}.zip" "${PLUGIN_NAME}" > /dev/null
cd - > /dev/null

# Move zip to out/
mv "$STAGING_DIR/${PLUGIN_NAME}.zip" "out/${PLUGIN_NAME}.zip"
rm -rf "$STAGING_DIR"

echo "Successfully built out/${PLUGIN_NAME}.zip without Docker!"

#!/bin/sh
set -e

# Dynamically find the current installed version
CURRENT_VERSION=$(find "$PLAYWRIGHT_BROWSERS_PATH" -name "chromium_headless_shell-*" -type d 2>/dev/null | xargs -n1 basename 2>/dev/null | sort -V | tail -n 1 || echo "")

if [ -z "$CURRENT_VERSION" ]; then
  echo "Error: No Playwright browser version found. Installation may have failed."
  exit 1
fi

echo "Found browser version: $CURRENT_VERSION"

# List of known hardcoded versions that might be referenced in dependencies
# Add versions here as they are discovered causing issues
COMPAT_VERSIONS="chromium_headless_shell-1179"

# Create symlinks for all compatibility versions
for COMPAT_VERSION in $COMPAT_VERSIONS; do
  if [ "$CURRENT_VERSION" != "$COMPAT_VERSION" ] && [ ! -d "$PLAYWRIGHT_BROWSERS_PATH/$COMPAT_VERSION" ]; then
    echo "Creating symlinks for compatibility with $COMPAT_VERSION..."
    
    # Create the base symlink
    ln -s "$PLAYWRIGHT_BROWSERS_PATH/$CURRENT_VERSION" "$PLAYWRIGHT_BROWSERS_PATH/$COMPAT_VERSION"
    
    # Look for specific subdirectories in the current version that we need to replicate
    if [ -d "$PLAYWRIGHT_BROWSERS_PATH/$CURRENT_VERSION/chrome-linux" ]; then
      mkdir -p "$PLAYWRIGHT_BROWSERS_PATH/$COMPAT_VERSION/chrome-linux/"
      
      # Create symlinks for all executables in chrome-linux directory
      for EXECUTABLE in "$PLAYWRIGHT_BROWSERS_PATH/$CURRENT_VERSION/chrome-linux"/*; do
        if [ -f "$EXECUTABLE" ] && [ -x "$EXECUTABLE" ]; then
          EXEC_NAME=$(basename "$EXECUTABLE")
          if [ ! -e "$PLAYWRIGHT_BROWSERS_PATH/$COMPAT_VERSION/chrome-linux/$EXEC_NAME" ]; then
            echo "  Linking executable: $EXEC_NAME"
            ln -s "$EXECUTABLE" "$PLAYWRIGHT_BROWSERS_PATH/$COMPAT_VERSION/chrome-linux/$EXEC_NAME"
          fi
        fi
      done
    fi
    
    echo "Symlinks for $COMPAT_VERSION created successfully."
  fi
done

# Run the original command
exec "$@"

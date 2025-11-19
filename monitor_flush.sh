#!/bin/bash
# Monitor Bitcoin Knots memory pressure and flush operations during IBD
# Starts bitcoind, monitors, and saves output to text file and CSV for graphing

# Configuration
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
DBCACHE=2000
DBBATCH=67108864
BUILDDIR="memtests-build"
DATADIR="${HOME}/bitcoin-memtests"
PLATFORM="linux"
ENV="linuxVM"
EXTRA_ARGS=""
OUTPUT_SUBDIR="mempressure_test_results"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -dbcachesize)
            DBCACHE="$2"
            shift 2
            ;;
        -dbbatchsize)
            DBBATCH="$2"
            shift 2
            ;;
        -builddir)
            BUILDDIR="$2"
            shift 2
            ;;
        -datadir)
            DATADIR="$2"
            shift 2
            ;;
        -platform)
            PLATFORM="$2"
            shift 2
            ;;
        -env)
            ENV="$2"
            shift 2
            ;;
        -extraargs)
            EXTRA_ARGS="$2"
            shift 2
            ;;
        -outdir)
            OUTPUT_SUBDIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [-dbcachesize MB] [-dbbatchsize BYTES] [-builddir DIR] [-datadir DIR] [-platform PLATFORM] [-env NAME] [-outdir DIR] [-extraargs \"args\"]"
            echo ""
            echo "Options:"
            echo "  -dbcachesize  MB       Database cache size (default: 2000)"
            echo "  -dbbatchsize  BYTES    Database batch size in bytes (default: 67108864)"
            echo "  -builddir     DIR      Build directory name (default: memtests-build)"
            echo "  -datadir      DIR      Bitcoin data directory (default: \$HOME/bitcoin-memtests)"
            echo "  -platform     PLATFORM Platform type: linux or windows (default: linux)"
            echo "  -env          NAME     Environment name (default: linuxVM)"
            echo "  -outdir       DIR      Output subdirectory (default: mempressure_test_results)"
            echo "  -extraargs    ARGS     Additional bitcoind arguments (default: none)"
            echo ""
            echo "Example: $0 -dbcachesize 2000 -dbbatchsize 67108864 -env linuxVM"
            echo "Example: $0 -builddir build -dbcachesize 2000 -dbbatchsize 134217728 -env linux"
            echo "Example: $0 -platform windows -builddir build -dbcachesize 2000 -dbbatchsize 67108864 -env windows"
            echo "Example: $0 -dbcachesize 3000 -dbbatchsize 134217728 -datadir /custom/path -env docker"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Set paths after parsing arguments
# Add .exe extension for Windows binaries
if [ "$PLATFORM" = "windows" ]; then
    BITCOIND="${REPO_ROOT}/${BUILDDIR}/bin/bitcoind.exe"
    BITCOIN_CLI="${REPO_ROOT}/${BUILDDIR}/bin/bitcoin-cli.exe"
else
    BITCOIND="${REPO_ROOT}/${BUILDDIR}/bin/bitcoind"
    BITCOIN_CLI="${REPO_ROOT}/${BUILDDIR}/bin/bitcoin-cli"
fi
DEBUG_LOG="${DATADIR}/debug.log"

# Check if bitcoind exists
if [ ! -f "$BITCOIND" ]; then
    echo "Error: bitcoind not found at $BITCOIND"
    echo "Platform: $PLATFORM"
    exit 1
fi

echo "Bitcoin Knots Memory Pressure Test"
echo "==================================="
echo "dbcachesize: ${DBCACHE}MB"
echo "dbbatchsize: $((DBBATCH / 1024 / 1024))MB (${DBBATCH} bytes)"
echo "Environment: $ENV"
[ -n "$EXTRA_ARGS" ] && echo "Extra args: $EXTRA_ARGS"
echo ""

# Set output directory and create if needed
OUTPUT_DIR="${REPO_ROOT}/${OUTPUT_SUBDIR}"
mkdir -p "$OUTPUT_DIR"

# Generate filenames - one file per environment with multiple runs
TXT_FILE="${OUTPUT_DIR}/lowmem_thresholds_${ENV}.txt"
CSV_FILE="${OUTPUT_DIR}/lowmem_thresholds_${ENV}.csv"

# Track if we've written the header for this run
HEADER_WRITTEN=false

# Create CSV with header if it doesn't exist
if [ ! -f "$CSV_FILE" ]; then
    echo "dbcachesize_mb,dbbatchsize_mb,timestamp,cache_size_mb,overhead_mb,duration_ms,pre_flush_mb,peak_mb,post_flush_mb,sys_memavail_mb" > "$CSV_FILE"
fi

echo ""
echo "Starting bitcoind with:"
echo "  -dbcache=${DBCACHE}"
echo "  -dbbatchsize=${DBBATCH} ($((DBBATCH / 1024 / 1024))MB)"
echo "  -debug=mempressure"
echo "  -datadir=${DATADIR}"
[ -n "$EXTRA_ARGS" ] && echo "  $EXTRA_ARGS"
echo ""

# Start bitcoind
"$BITCOIND" \
    -datadir="$DATADIR" \
    -dbcache="$DBCACHE" \
    -dbbatchsize="$DBBATCH" \
    -debug=mempressure \
    $EXTRA_ARGS \
    -daemon

if [ $? -ne 0 ]; then
    echo "Error: Failed to start bitcoind"
    exit 1
fi

echo "bitcoind started successfully"
echo "Waiting for debug.log to be created..."

# Wait for debug.log to exist
for i in {1..30}; do
    if [ -f "$DEBUG_LOG" ]; then
        break
    fi
    sleep 1
done

if [ ! -f "$DEBUG_LOG" ]; then
    echo "Error: Debug log not found at $DEBUG_LOG after 30 seconds"
    exit 1
fi

echo "Monitoring started..."
echo "Text output: $TXT_FILE"
echo "CSV output: $CSV_FILE"
echo ""
echo "Press Ctrl+C to stop monitoring and bitcoind"
echo ""

# Function to handle script exit
cleanup() {
    echo ""
    echo "Stopping bitcoind..."
    "$BITCOIN_CLI" -datadir="$DATADIR" stop
    echo "Monitoring stopped"
    echo "Test results saved to:"
    echo "  $TXT_FILE"
    echo "  $CSV_FILE"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Tail and process the log
tail -f "$DEBUG_LOG" | grep -i -E '(\[mempressure\]|UTXO set to disk|Should flush due to)' --line-buffered | while IFS= read -r line; do
    # Print to console
    echo "$line"

    # Write header before first data line
    if [ "$HEADER_WRITTEN" = false ]; then
        {
            echo ""
            echo "dbcachesize=${DBCACHE}MB, dbbatchsize=$((DBBATCH / 1024 / 1024))MB"
        } >> "$TXT_FILE"
        HEADER_WRITTEN=true
    fi

    # Append to text file
    echo "$line" >> "$TXT_FILE"

    # Parse mempressure lines for CSV
    if [[ "$line" =~ \[mempressure\]\ Flush\ profile:\ cache_size=([0-9]+)\ MB,\ overhead=([0-9]+)\ MB,\ duration=([0-9]+)\ ms,\ pre_flush=([0-9]+)\ MB,\ peak=([0-9]+)\ MB,\ post_flush=([0-9]+)\ MB,\ sys_memavail=([0-9]+)\ MB ]]; then
        timestamp=$(echo "$line" | cut -d' ' -f1)
        cache_size="${BASH_REMATCH[1]}"
        overhead="${BASH_REMATCH[2]}"
        duration="${BASH_REMATCH[3]}"
        pre_flush="${BASH_REMATCH[4]}"
        peak="${BASH_REMATCH[5]}"
        post_flush="${BASH_REMATCH[6]}"
        sys_memavail="${BASH_REMATCH[7]}"

        echo "$DBCACHE,$DBBATCH,$timestamp,$cache_size,$overhead,$duration,$pre_flush,$peak,$post_flush,$sys_memavail" >> "$CSV_FILE"
    fi
done

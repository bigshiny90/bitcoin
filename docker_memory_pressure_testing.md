# Docker Memory Pressure Testing Guide

This guide shows how to test the memory pressure detection features in a Docker container with limited memory.

## Prerequisites

- Docker installed and running
- Bitcoin Knots source code with memory pressure detection changes

## Step 1: Build the Docker Image

From the Bitcoin repository root, build the Docker image:

```bash
docker build -t bitcoin-knots:mempressure -f contrib/docker/Dockerfile .
```

This compiles your modified code into a Docker image based on Alpine Linux.

**Note:** The build may take 10-30 minutes depending on your system.

## Step 2: Prepare Test Directory and Config

Create a directory for the blockchain data and a minimal config file:

```bash
# Create data directory
mkdir -p ~/bitcoin_mempressure_test

# Create bitcoin.conf with high dbcache to trigger memory pressure
cat > ~/bitcoin_mempressure_test/bitcoin.conf << 'EOF'
dbcache=1800
EOF
```

## Step 3: Run Container with Memory Limit

Run the container with a 2GB memory limit:

```bash
docker run -it --rm --memory=2g --name bitcoin-test \
  -v ~/bitcoin_mempressure_test:/var/lib/bitcoind \
  bitcoin-knots:mempressure \
  -conf=/var/lib/bitcoind/bitcoin.conf -printtoconsole
```

### Command explanation:

- `--memory=2g` - Limits container to 2GB RAM (creates Job Object on Windows or cgroup on Linux)
- `-v ~/bitcoin_mempressure_test:/var/lib/bitcoind` - Mounts data directory
- `-conf=/var/lib/bitcoind/bitcoin.conf` - Overrides default config path
- `-printtoconsole` - Shows logs in terminal

## Step 4: Monitor Memory Pressure Detection

Watch the logs for memory pressure events. You should see messages like:

**On Linux (container detected via cgroup):**
```
CheckMemoryPressure: YES: 50000000 available memory
```

**On Windows (container detected via Job Object):**
```
GetJobObjectMemoryLimit: Detected Job Object memory limit: 2147483648 bytes
CheckMemoryPressure: YES: 45000000 available memory (in container)
```

**Note:** Memory pressure triggers when available memory drops below the threshold (default 64MB = 67108864 bytes). With dbcache=1800 in a 2GB container, you should see pressure events as the cache fills up during IBD or block processing.

Make sure that after a memory pressure event in log, we then see a Flush and the next UpdateTip cache should be 0.  we should NOT immediately get another Flush attempt.

If you want to go wild and watch mem usage to confirm memory release
```bash
watch -n 1 "docker stats bitcoin-test --no-stream"
```

## Cleanup

Remove test data when done:
```bash
rm -rf ~/bitcoin_mempressure_test
```

Remove Docker image:
```bash
docker rmi bitcoin-knots:mempressure
```

## What This Tests

- **Linux containers**: `/proc/self/meminfo` detection (cgroup-aware)
- **Windows containers**: Job Object memory limit detection via `QueryInformationJobObject` and `GetProcessMemoryInfo`
- **Memory pressure triggers**: FlushStateToDisk should trigger when available memory drops below threshold
- **Container awareness**: System correctly calculates available memory within container limits rather than host memory

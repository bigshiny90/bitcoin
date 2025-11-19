# Memory Pressure Monitoring Commands

## 1. Start Monitor Script

Run the monitoring script to start bitcoind and capture flush profiling data:

```bash
# Basic usage (64MB batch, 2GB cache)
./monitor_flush.sh -dbcachesize 2000 -dbbatchsize 67108864 -env linux

# Custom datadir
./monitor_flush.sh -dbcachesize 2000 -dbbatchsize 67108864 -datadir /mnt/data/bitcoin -env linuxVM

# 128MB batch test
./monitor_flush.sh -dbcachesize 2000 -dbbatchsize 134217728 -env linuxVM

# 256MB batch test
./monitor_flush.sh -dbcachesize 2000 -dbbatchsize 268435456 -env linuxVM

# Windows binaries from WSL2 (adds .exe extension automatically)
./monitor_flush.sh -platform windows -builddir build -dbcachesize 2000 -dbbatchsize 67108864 -env windows

# With extra args (disable network connections for isolated testing)
./monitor_flush.sh -dbcachesize 2000 -dbbatchsize 67108864 -env linux -extraargs "-connect=0"

# With extra args (connect to specific node)
./monitor_flush.sh -dbcachesize 3000 -dbbatchsize 134217728 -env docker -extraargs "-connect=192.168.0.138:9333"
```

## 2. Manual Log Monitoring

Monitor debug.log directly for mempressure events:

```bash
# Real-time mempressure monitoring
tail -f ~/bitcoin-memtests/debug.log | grep -i -E '(\[mempressure\]|UTXO set to disk|Should flush due to)' --line-buffered

# Or with custom datadir
tail -f /custom/path/debug.log | grep -i -E '(\[mempressure\]|UTXO set to disk|Should flush due to)' --line-buffered
```

## 3. System Memory Watch

Monitor system memory in real-time (separate terminal):

```bash
# Watch MemAvailable and MemFree every 1 second
watch -n 1 'cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Cached|Buffers"'

# More compact view
watch -n 1 'free -h'

# Detailed process memory
watch -n 1 'ps aux | grep bitcoind | grep -v grep'
```

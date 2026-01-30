# Linux Performance Analysis for Container Optimization

## Overview

This lab teaches you to use powerful Linux performance analysis tools to understand what's happening inside your containers and on your host system. These tools help you:

- **Identify bottlenecks** before they cause outages
- **Right-size resources** by understanding actual usage patterns
- **Debug performance issues** with deep system visibility
- **Validate optimizations** with reproducible benchmarks

By the end of this lab, you will understand:

- **Why** each tool exists and when to use it
- How to benchmark system performance with \`sysbench\`
- How to analyze process memory with \`pmap\` and \`/proc/[pid]/smaps\`
- How to trace system calls and container activity with \`sysdig\`
- How to use \`eBPF\` for advanced kernel-level tracing

## Why These Tools Matter

| Tool | What It Does | Why You Need It |
|------|-------------|-----------------|
| **sysbench** | Synthetic benchmarking | Establish baselines, compare configurations, validate changes |
| **pmap** | Process memory mapping | See where memory is allocated (heap, stack, libraries) |
| **smaps** | Detailed memory analysis | Understand RSS, PSS, shared vs private memory |
| **sysdig** | System call tracing | See every syscall a container makes, filter by container |
| **eBPF/bpftrace** | Kernel tracing | Zero-overhead production tracing, custom metrics |

**The key insight:** Containers are just processes with namespaces. All these tools work on containers because containers ARE Linux processes.

---

## Prerequisites

This lab requires a Linux system with root access. The tools will be installed as part of the lab.

Create a working directory:

\`\`\`bash
mkdir -p ~/performance-lab && cd ~/performance-lab
\`\`\`

---

## Part 1: System Benchmarking with sysbench

### Why sysbench?

Before optimizing anything, you need to establish **baselines**. How do you know if a change improved performance? You measure before and after.

\`sysbench\` provides:
- **Reproducible tests** - Same test, same conditions, comparable results
- **Multiple workload types** - CPU, memory, I/O, MySQL, threads
- **Quick feedback** - Results in seconds, not hours

**When to use it:**
- Before and after configuration changes
- Comparing different instance types or hardware
- Validating container resource limits
- Capacity planning

### Step 1: Install sysbench

\`\`\`bash
sudo apt-get update && sudo apt-get install -y sysbench
\`\`\`

### Step 2: CPU Benchmark

**Why benchmark CPU?** Understanding your CPU capacity helps you:
- Set appropriate container CPU limits
- Identify CPU-bound applications
- Compare different instance types

Run a CPU benchmark:

\`\`\`bash
sysbench cpu --cpu-max-prime=20000 --threads=1 run
\`\`\`

**Understanding the parameters:**
- \`--cpu-max-prime=20000\`: Calculate primes up to 20,000 (workload intensity)
- \`--threads=1\`: Use single thread (isolates single-core performance)

**Key metric:** \`events per second\` - higher is better

Now test with multiple threads:

\`\`\`bash
# Get the number of CPU cores
nproc

# Run with all available cores
sysbench cpu --cpu-max-prime=20000 --threads=\$(nproc) run
\`\`\`

**What to look for:**
- Does performance scale linearly with threads? (Rarely perfect)
- What's the single-thread vs multi-thread ratio? (Shows parallelization efficiency)

### Step 3: Memory Benchmark

**Why benchmark memory?** Memory bandwidth affects:
- Data-intensive applications (databases, caches)
- Container density (how many containers can share the host)
- Performance of memory-mapped files

Run a memory benchmark:

\`\`\`bash
sysbench memory --memory-block-size=1K --memory-total-size=10G --threads=1 run
\`\`\`

**Understanding the parameters:**
- \`--memory-block-size=1K\`: Size of each memory operation (simulates different access patterns)
- \`--memory-total-size=10G\`: Total data to transfer
- \`--threads=1\`: Single thread for baseline

**Key metrics:**
- \`transferred\`: Total data moved
- \`MiB/sec\`: Memory bandwidth (higher is better)

Compare different block sizes to understand access pattern impact:

\`\`\`bash
echo "=== 1K blocks (small, random-like access) ==="
sysbench memory --memory-block-size=1K --memory-total-size=5G run 2>&1 | grep -E "transferred|Operations"

echo ""
echo "=== 1M blocks (large, sequential-like access) ==="
sysbench memory --memory-block-size=1M --memory-total-size=5G run 2>&1 | grep -E "transferred|Operations"
\`\`\`

**Why the difference?** Smaller blocks have more overhead per byte transferred. Larger blocks are more efficient but don't reflect all workloads.

### Step 4: File I/O Benchmark

**Why benchmark I/O?** Disk performance is often the bottleneck for:
- Databases
- Log-heavy applications
- Applications with large working sets

Prepare test files:

\`\`\`bash
sysbench fileio --file-total-size=1G prepare
\`\`\`

Run sequential read test:

\`\`\`bash
sysbench fileio --file-total-size=1G --file-test-mode=seqrd --time=30 run
\`\`\`

Run random read/write test (more realistic for databases):

\`\`\`bash
sysbench fileio --file-total-size=1G --file-test-mode=rndrw --time=30 run
\`\`\`

**Key metrics:**
- \`read, MiB/s\` and \`written, MiB/s\`: Throughput
- \`fsyncs/s\`: Critical for databases (durability operations)

Clean up test files:

\`\`\`bash
sysbench fileio --file-total-size=1G cleanup
\`\`\`

### Step 5: Benchmark Inside a Container

**Why test inside containers?** Container resource limits and isolation affect performance. Let's see how.

Run sysbench in a container with no limits:

\`\`\`bash
docker run --rm ubuntu:22.04 bash -c "
  apt-get update > /dev/null 2>&1 && apt-get install -y sysbench > /dev/null 2>&1
  echo '=== No CPU Limit ==='
  sysbench cpu --cpu-max-prime=20000 --threads=1 run 2>&1 | grep 'events per second'
"
\`\`\`

Now with a CPU limit:

\`\`\`bash
docker run --rm --cpus=0.5 ubuntu:22.04 bash -c "
  apt-get update > /dev/null 2>&1 && apt-get install -y sysbench > /dev/null 2>&1
  echo '=== 0.5 CPU Limit ==='
  sysbench cpu --cpu-max-prime=20000 --threads=1 run 2>&1 | grep 'events per second'
"
\`\`\`

**What you should see:** The CPU-limited container performs roughly proportionally slower. This demonstrates that CPU limits work as expected.

### Key Takeaways - sysbench

1. **Establish baselines before changes** - You can't measure improvement without a starting point
2. **Test what matters** - CPU, memory, or I/O depending on your workload
3. **Container limits work** - But you need to verify they're set appropriately
4. **Block size matters** - Small blocks test latency, large blocks test throughput

---

## Part 2: Memory Analysis with pmap and smaps

### Why Analyze Memory?

Container memory limits are one of the most common causes of OOM (Out of Memory) kills. To set appropriate limits, you need to understand:

- **How much memory does my application actually use?**
- **What's shared vs private memory?**
- **Where is the memory allocated?**

### Understanding Memory Metrics

| Metric | Meaning | Why It Matters |
|--------|---------|----------------|
| **VSZ (Virtual)** | Total address space | Can be huge, doesn't mean actual usage |
| **RSS (Resident)** | Physical memory used | What the kernel has loaded in RAM |
| **PSS (Proportional)** | RSS adjusted for sharing | Fairest measure for multi-process apps |
| **Shared** | Memory shared with other processes | Libraries, shared mappings |
| **Private** | Memory unique to this process | Your application's actual footprint |

**The key insight:** RSS can be misleading because it counts shared libraries fully for each process. If 10 processes share libc, RSS counts it 10 times. PSS divides it by 10.

### Step 1: Install Required Tools

\`\`\`bash
sudo apt-get install -y procps  # pmap is part of procps
\`\`\`

### Step 2: Create a Sample Process to Analyze

Let's create a Python process that allocates memory in predictable ways:

\`\`\`bash
cat << 'EOF' > memory_demo.py
import time
import sys

# Allocate some memory
data = []

# Allocate 50MB in 1MB chunks
for i in range(50):
    chunk = bytearray(1024 * 1024)  # 1MB
    data.append(chunk)

print(f"Allocated {len(data)} MB", file=sys.stderr)
print(f"PID: {__import__('os').getpid()}", file=sys.stderr)

# Keep running so we can analyze
while True:
    time.sleep(1)
EOF
\`\`\`

Start the process in the background:

\`\`\`bash
python3 memory_demo.py &
DEMO_PID=\$!
echo "Demo process PID: \$DEMO_PID"
sleep 2
\`\`\`

### Step 3: Analyze with pmap

**Why pmap?** It shows you the memory map of a process - every region of allocated memory and what it's for.

Basic pmap output:

\`\`\`bash
pmap \$DEMO_PID
\`\`\`

**What you see:**
- Address ranges
- Size of each region (Kbytes)
- Permissions (r=read, w=write, x=execute)
- Mapping (library name or [heap], [stack], etc.)

Extended output with more detail:

\`\`\`bash
pmap -x \$DEMO_PID
\`\`\`

**New columns:**
- \`RSS\`: Resident memory for this region
- \`Dirty\`: Modified pages (would need to be written back)

**What to look for:**
- \`[heap]\` - Dynamic allocations (malloc, Python objects)
- \`[stack]\` - Function call stack
- \`.so\` files - Shared libraries
- \`[anon]\` - Anonymous mappings (often large allocations)

Look at just the summary:

\`\`\`bash
pmap -x \$DEMO_PID | tail -1
\`\`\`

### Step 4: Deep Dive with /proc/[pid]/smaps

**Why smaps?** It provides the most detailed memory breakdown available, including PSS (Proportional Set Size) which accounts for shared memory fairly.

View the full smaps:

\`\`\`bash
sudo cat /proc/\$DEMO_PID/smaps | head -50
\`\`\`

**Key fields per mapping:**
- \`Size\`: Total size of the mapping
- \`Rss\`: Resident (in RAM) portion
- \`Pss\`: Proportional share (RSS / number of sharers)
- \`Shared_Clean\`: Shared, unmodified pages
- \`Shared_Dirty\`: Shared, modified pages
- \`Private_Clean\`: Private, unmodified pages
- \`Private_Dirty\`: Private, modified pages

Get a summary using smaps_rollup (faster):

\`\`\`bash
sudo cat /proc/\$DEMO_PID/smaps_rollup
\`\`\`

**This is the most accurate view of actual memory usage.**

### Step 5: Compare RSS vs PSS

Let's see the difference with a real example:

\`\`\`bash
echo "=== Memory Metrics for PID \$DEMO_PID ==="
echo ""

# RSS from /proc/[pid]/status
echo "RSS (from status):"
grep -E "^(VmRSS|VmSize)" /proc/\$DEMO_PID/status

echo ""
echo "PSS (from smaps_rollup):"
sudo grep -E "^(Rss|Pss)" /proc/\$DEMO_PID/smaps_rollup
\`\`\`

**Why PSS matters for containers:** When setting memory limits, PSS gives you a more accurate picture of what happens if this process runs alone (like in a container with one main process).

### Step 6: Analyze a Container's Memory

Run a container with a known memory allocation:

\`\`\`bash
docker run -d --name memory-test --memory=128m python:3.11-slim python3 -c "
import time
data = [bytearray(1024*1024) for _ in range(50)]  # 50MB
print(f'Allocated 50MB')
while True: time.sleep(60)
"
sleep 3
\`\`\`

Find the container's main process PID:

\`\`\`bash
CONTAINER_PID=\$(docker inspect --format '{{.State.Pid}}' memory-test)
echo "Container main process PID: \$CONTAINER_PID"
\`\`\`

Analyze the container's memory:

\`\`\`bash
echo "=== Container Memory Analysis ==="
sudo cat /proc/\$CONTAINER_PID/smaps_rollup

echo ""
echo "=== pmap summary ==="
sudo pmap -x \$CONTAINER_PID | tail -1
\`\`\`

Compare with Docker's view:

\`\`\`bash
echo "=== Docker stats ==="
docker stats memory-test --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
\`\`\`

**Why the numbers might differ:** Docker includes all processes in the container's cgroup, plus page cache. The smaps view is just for one process.

### Step 7: Cleanup

\`\`\`bash
kill \$DEMO_PID 2>/dev/null
docker rm -f memory-test 2>/dev/null
rm -f memory_demo.py
\`\`\`

### Key Takeaways - Memory Analysis

1. **RSS is not the whole story** - It double-counts shared memory
2. **PSS is the fairest metric** - Use it for capacity planning
3. **pmap shows structure** - See where memory is allocated
4. **smaps shows details** - Understand shared vs private, clean vs dirty
5. **Container memory != process memory** - Docker includes cgroup totals

---

## Part 3: System Call Tracing with sysdig

### Why sysdig?

\`sysdig\` captures system calls (the interface between programs and the kernel) and lets you filter and analyze them. It's like Wireshark for your system, not just your network.

**Why this matters for containers:**
- See exactly what your application is doing
- Filter by container (not possible with basic strace)
- Identify file access patterns, network connections, errors
- Debug issues that logs don't reveal

### Step 1: Install sysdig

\`\`\`bash
# Install dependencies
sudo apt-get update
sudo apt-get install -y linux-headers-\$(uname -r)

# Install sysdig
curl -sS https://download.sysdig.com/stable/install-sysdig | sudo bash
\`\`\`

### Step 2: Basic sysdig Usage

**Why capture syscalls?** Every action a process takes (file open, network connect, memory allocate) goes through system calls. Seeing them reveals what your application is actually doing.

Capture all system calls (run briefly, Ctrl+C to stop):

\`\`\`bash
sudo sysdig -c topprocs_cpu
\`\`\`

This shows the top processes by CPU usage with syscall-level detail.

View syscalls for a specific command:

\`\`\`bash
# In one terminal, run a command
# In another, capture it:
sudo timeout 5 sysdig proc.name=ls
\`\`\`

### Step 3: Trace a Container

**Why trace containers specifically?** In a multi-tenant environment, you need to isolate one container's activity from hundreds of others.

Start a test container:

\`\`\`bash
docker run -d --name trace-test alpine sh -c "while true; do wget -q -O /dev/null http://example.com; sleep 2; done"
sleep 2
\`\`\`

Trace only that container:

\`\`\`bash
sudo timeout 10 sysdig container.name=trace-test
\`\`\`

**What you see:**
- Every syscall the container makes
- File opens, reads, writes
- Network connections
- Process forks

### Step 4: Filter by Syscall Type

**Why filter?** Raw syscall output is overwhelming. Filtering lets you focus on what matters.

See only network-related syscalls:

\`\`\`bash
sudo timeout 10 sysdig container.name=trace-test and evt.type in \(connect, sendto, recvfrom, accept\)
\`\`\`

See only file operations:

\`\`\`bash
sudo timeout 10 sysdig container.name=trace-test and evt.type in \(open, openat, read, write, close\)
\`\`\`

See only errors:

\`\`\`bash
sudo timeout 10 sysdig container.name=trace-test and evt.failed=true
\`\`\`

**Why look at errors?** Applications often hide errors or retry silently. Sysdig reveals these hidden failures.

### Step 5: Use Chisels (Built-in Analysis Scripts)

**Why chisels?** They're pre-built analysis tools that extract useful information from the syscall stream.

List available chisels:

\`\`\`bash
sudo sysdig -cl
\`\`\`

Top files by read bytes:

\`\`\`bash
sudo timeout 10 sysdig -c topfiles_bytes container.name=trace-test
\`\`\`

Network connections:

\`\`\`bash
sudo timeout 10 sysdig -c netstat container.name=trace-test
\`\`\`

Top syscalls:

\`\`\`bash
sudo timeout 10 sysdig -c topscalls container.name=trace-test
\`\`\`

### Step 6: Capture to File for Later Analysis

**Why capture?** Production issues are often transient. Capturing lets you analyze after the fact.

Capture 10 seconds to a file:

\`\`\`bash
sudo timeout 10 sysdig -w /tmp/trace.scap container.name=trace-test
\`\`\`

Analyze the capture:

\`\`\`bash
# Read from file instead of live
sudo sysdig -r /tmp/trace.scap -c topscalls
\`\`\`

Filter the capture differently:

\`\`\`bash
sudo sysdig -r /tmp/trace.scap evt.failed=true
\`\`\`

### Step 7: Cleanup

\`\`\`bash
docker rm -f trace-test 2>/dev/null
rm -f /tmp/trace.scap
\`\`\`

### Key Takeaways - sysdig

1. **Syscalls reveal truth** - See what applications actually do, not what they claim
2. **Container filtering is powerful** - Isolate one container's activity
3. **Errors are hidden** - Sysdig reveals syscall failures your app might ignore
4. **Capture for later** - Record now, analyze when convenient
5. **Chisels automate analysis** - Don't parse raw output manually

---

## Part 4: Advanced Tracing with eBPF

### Why eBPF?

eBPF (extended Berkeley Packet Filter) lets you run custom code in the Linux kernel safely. It's the technology behind modern observability tools.

**Why eBPF over sysdig?**
- **Lower overhead** - Runs in kernel, no context switches
- **Production safe** - Can't crash the kernel
- **Custom tracing** - Write exactly what you need
- **No kernel modules** - Works on locked-down systems

### Understanding eBPF Tools

| Tool | What It Is | When to Use It |
|------|-----------|----------------|
| **bpftrace** | High-level tracing language | Quick one-liners, exploration |
| **BCC tools** | Pre-built eBPF tools | Common tasks (latency, I/O, CPU) |
| **libbpf** | Low-level C library | Custom production tools |

### Step 1: Install eBPF Tools

\`\`\`bash
sudo apt-get update
sudo apt-get install -y bpftrace bpfcc-tools linux-headers-\$(uname -r)
\`\`\`

### Step 2: Explore with bpftrace One-Liners

**Why start with one-liners?** They show eBPF's power without writing programs.

List available tracepoints:

\`\`\`bash
sudo bpftrace -l 'tracepoint:syscalls:*' | head -20
\`\`\`

Count syscalls by type (run for 5 seconds):

\`\`\`bash
sudo timeout 5 bpftrace -e 'tracepoint:syscalls:sys_enter_* { @[probe] = count(); }'
\`\`\`

**What you see:** Every syscall type and how many times it was called across the entire system.

Trace process creation:

\`\`\`bash
sudo timeout 10 bpftrace -e 'tracepoint:syscalls:sys_enter_execve { printf("%s ran %s\n", comm, str(args->filename)); }'
\`\`\`

**Try this:** In another terminal, run some commands. You'll see them appear.

### Step 3: BCC Tools for Common Tasks

**Why BCC tools?** They're pre-built eBPF programs for common performance questions.

**execsnoop** - Watch process execution:

\`\`\`bash
sudo timeout 10 execsnoop-bpfcc
\`\`\`

This shows every new process started. Very useful for debugging scripts and cron jobs.

**opensnoop** - Watch file opens:

\`\`\`bash
sudo timeout 10 opensnoop-bpfcc
\`\`\`

See every file open across the system. Useful for finding configuration files, dependency issues.

**biolatency** - Disk I/O latency histogram:

\`\`\`bash
sudo timeout 10 biolatency-bpfcc
\`\`\`

Shows a histogram of disk operation latencies. Critical for database performance.

**tcpconnect** - Watch TCP connections:

\`\`\`bash
sudo timeout 10 tcpconnect-bpfcc
\`\`\`

See every outbound TCP connection. Great for finding unexpected network calls.

### Step 4: Trace a Specific Container with eBPF

Start a test container:

\`\`\`bash
docker run -d --name ebpf-test alpine sh -c "while true; do ls /tmp; sleep 1; done"
sleep 2
\`\`\`

Get the container's cgroup ID for filtering:

\`\`\`bash
CONTAINER_ID=\$(docker inspect --format '{{.Id}}' ebpf-test)
echo "Container ID: \$CONTAINER_ID"
\`\`\`

Trace file opens in that container using opensnoop with PID filtering:

\`\`\`bash
# Get the main PID of the container
CONTAINER_PID=\$(docker inspect --format '{{.State.Pid}}' ebpf-test)
echo "Container PID: \$CONTAINER_PID"

# Trace that process and its children
sudo timeout 10 opensnoop-bpfcc -p \$CONTAINER_PID
\`\`\`

### Step 5: Measure Latency with bpftrace

**Why measure latency?** Throughput tells you "how many," latency tells you "how fast." Both matter.

Measure read syscall latency:

\`\`\`bash
sudo timeout 10 bpftrace -e '
tracepoint:syscalls:sys_enter_read { @start[tid] = nsecs; }
tracepoint:syscalls:sys_exit_read /@start[tid]/ {
    @us = hist((nsecs - @start[tid]) / 1000);
    delete(@start[tid]);
}
END { print(@us); }
'
\`\`\`

**What you see:** A histogram showing how long read() syscalls take, in microseconds.

### Step 6: Write a Custom bpftrace Script

Create a script that traces container network connections:

\`\`\`bash
cat << 'EOF' > trace_tcp.bt
#!/usr/bin/env bpftrace

tracepoint:syscalls:sys_enter_connect
{
    @connects[comm] = count();
}

interval:s:5 {
    print(@connects);
    clear(@connects);
}
EOF
\`\`\`

Run it:

\`\`\`bash
sudo timeout 15 bpftrace trace_tcp.bt
\`\`\`

**While it runs:** Make some network connections (curl, wget) and see them counted by process name.

### Step 7: Production-Ready BCC Tools

**runqlat** - CPU scheduler latency:

\`\`\`bash
sudo timeout 10 runqlat-bpfcc
\`\`\`

**Why it matters:** Shows how long processes wait for CPU time. High latency = CPU contention.

**cachestat** - Page cache hit/miss:

\`\`\`bash
sudo timeout 10 cachestat-bpfcc
\`\`\`

**Why it matters:** Low cache hit rate means lots of disk I/O. Critical for database performance.

**funccount** - Count function calls:

\`\`\`bash
sudo timeout 5 funccount-bpfcc 'vfs_*'
\`\`\`

**Why it matters:** See which kernel functions are called most. Identifies hot paths.

### Step 8: Cleanup

\`\`\`bash
docker rm -f ebpf-test 2>/dev/null
rm -f trace_tcp.bt
\`\`\`

### Key Takeaways - eBPF

1. **eBPF is production-safe** - Runs in kernel without risk
2. **bpftrace for exploration** - Quick one-liners reveal behavior
3. **BCC tools for common tasks** - Don't reinvent the wheel
4. **Latency histograms reveal truth** - Averages hide outliers
5. **Filter by container** - Use PID or cgroup to isolate

---

## Part 5: Putting It All Together

### Real-World Debugging Scenario

Let's use all our tools to investigate a performance issue.

Create a "problematic" application:

\`\`\`bash
cat << 'EOF' > slow_app.py
import os
import time
import random

# Simulate a slow application
while True:
    # CPU work
    sum([i*i for i in range(10000)])

    # Memory allocation
    data = bytearray(1024 * 1024)  # 1MB

    # File I/O
    with open('/tmp/test_output.txt', 'a') as f:
        f.write('x' * 10000)

    # Random sleep to simulate variable load
    time.sleep(random.uniform(0.1, 0.5))
EOF
\`\`\`

Run it in a container:

\`\`\`bash
docker run -d --name slow-app --memory=256m -v /tmp:/tmp python:3.11-slim python3 -c "
import os, time, random
while True:
    sum([i*i for i in range(10000)])
    data = bytearray(1024 * 1024)
    with open('/tmp/test_output.txt', 'a') as f:
        f.write('x' * 10000)
    time.sleep(random.uniform(0.1, 0.5))
"
sleep 3
\`\`\`

### Step 1: Benchmark Baseline with sysbench

Before investigating, establish what "normal" looks like:

\`\`\`bash
docker exec slow-app bash -c "
  apt-get update > /dev/null 2>&1 && apt-get install -y sysbench > /dev/null 2>&1
  echo '=== Container CPU Performance ==='
  sysbench cpu --cpu-max-prime=10000 --time=5 run 2>&1 | grep 'events per second'
" 2>/dev/null
\`\`\`

### Step 2: Analyze Memory with pmap/smaps

\`\`\`bash
SLOW_PID=\$(docker inspect --format '{{.State.Pid}}' slow-app)
echo "Slow app PID: \$SLOW_PID"

echo ""
echo "=== Memory Summary ==="
sudo cat /proc/\$SLOW_PID/smaps_rollup

echo ""
echo "=== Largest Memory Regions ==="
sudo pmap -x \$SLOW_PID | sort -k2 -n -r | head -10
\`\`\`

### Step 3: Trace with sysdig

\`\`\`bash
echo "=== Top Syscalls ==="
sudo timeout 5 sysdig -c topscalls container.name=slow-app

echo ""
echo "=== File Operations ==="
sudo timeout 5 sysdig -c topfiles_bytes container.name=slow-app
\`\`\`

### Step 4: Profile with eBPF

\`\`\`bash
echo "=== Open Files ==="
sudo timeout 5 opensnoop-bpfcc -p \$SLOW_PID

echo ""
echo "=== Syscall Latency (read) ==="
sudo timeout 5 bpftrace -e '
tracepoint:syscalls:sys_enter_read /pid == '\$SLOW_PID'/ { @start[tid] = nsecs; }
tracepoint:syscalls:sys_exit_read /@start[tid]/ {
    @us = hist((nsecs - @start[tid]) / 1000);
    delete(@start[tid]);
}
'
\`\`\`

### Step 5: Summary Analysis

Based on the tools we used:

1. **sysbench** showed us the container's CPU capacity with its memory limit
2. **pmap/smaps** revealed memory allocation patterns
3. **sysdig** identified the most frequent syscalls and files accessed
4. **eBPF** gave us latency distributions

**From this we could determine:**
- Is the app CPU-bound, memory-bound, or I/O-bound?
- Are there unexpected file accesses?
- Are syscall latencies reasonable?

### Cleanup

\`\`\`bash
docker rm -f slow-app 2>/dev/null
rm -f /tmp/test_output.txt slow_app.py
\`\`\`

---

## Command Reference

### sysbench Quick Reference

\`\`\`bash
# CPU benchmark
sysbench cpu --cpu-max-prime=20000 --threads=\$(nproc) run

# Memory benchmark
sysbench memory --memory-block-size=1M --memory-total-size=10G run

# File I/O benchmark
sysbench fileio --file-total-size=2G prepare
sysbench fileio --file-total-size=2G --file-test-mode=rndrw run
sysbench fileio --file-total-size=2G cleanup
\`\`\`

### pmap/smaps Quick Reference

\`\`\`bash
# Basic memory map
pmap <pid>

# Extended with RSS
pmap -x <pid>

# Summary only
pmap -x <pid> | tail -1

# Detailed smaps
cat /proc/<pid>/smaps

# Quick smaps summary
cat /proc/<pid>/smaps_rollup
\`\`\`

### sysdig Quick Reference

\`\`\`bash
# Live capture all syscalls
sudo sysdig

# Filter by container
sudo sysdig container.name=mycontainer

# Filter by syscall type
sudo sysdig evt.type=open

# Filter by error
sudo sysdig evt.failed=true

# Use a chisel
sudo sysdig -c topscalls

# Capture to file
sudo sysdig -w /tmp/capture.scap

# Read from file
sudo sysdig -r /tmp/capture.scap
\`\`\`

### eBPF/bpftrace Quick Reference

\`\`\`bash
# Count syscalls
sudo bpftrace -e 'tracepoint:syscalls:sys_enter_* { @[probe] = count(); }'

# Trace process execution
sudo bpftrace -e 'tracepoint:syscalls:sys_enter_execve { printf("%s\n", str(args->filename)); }'

# Histogram of latency
sudo bpftrace -e '
tracepoint:syscalls:sys_enter_read { @start[tid] = nsecs; }
tracepoint:syscalls:sys_exit_read /@start[tid]/ {
    @ns = hist(nsecs - @start[tid]);
    delete(@start[tid]);
}
'
\`\`\`

### BCC Tools Quick Reference

\`\`\`bash
# Process execution
sudo execsnoop-bpfcc

# File opens
sudo opensnoop-bpfcc

# TCP connections
sudo tcpconnect-bpfcc

# Disk I/O latency
sudo biolatency-bpfcc

# CPU scheduler latency
sudo runqlat-bpfcc

# Page cache stats
sudo cachestat-bpfcc
\`\`\`

---

## Cleanup

Remove all lab files:

\`\`\`bash
cd ~
rm -rf ~/performance-lab
\`\`\`

---

## Key Takeaways

1. **Measure before optimizing** - sysbench establishes baselines
2. **Memory has layers** - VSZ, RSS, PSS each tell different stories
3. **Syscalls reveal behavior** - sysdig shows what apps actually do
4. **eBPF is the future** - Low-overhead, production-safe tracing
5. **Containers are processes** - All these tools work on containers
6. **Latency matters** - Histograms reveal what averages hide

These tools form a complete observability toolkit for understanding and optimizing containerized applications.

---

## Congratulations

You've learned to use five powerful Linux performance analysis tools. These skills apply whether you're debugging a single container or optimizing a production Kubernetes cluster. The principles are the same - measure, understand, optimize, verify.
